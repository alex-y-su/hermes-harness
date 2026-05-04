from __future__ import annotations

import json
from pathlib import Path

from harness.bridge.dispatch import dispatch_assignment
from harness.bridge.hmac import canonical_json, sign_push, verify_push_signature
from harness.bridge.push import process_push
from harness.bridge.secrets import SecretResolver, parse_dotenv
from harness.bridge.store import BridgeDb


def setup_bridge(tmp_path: Path):
    factory_dir = tmp_path / "factory"
    team_dir = factory_dir / "teams" / "dev"
    (team_dir / "inbox").mkdir(parents=True)
    (team_dir / "outbox").mkdir()
    (team_dir / "transport.json").write_text(
        json.dumps(
            {
                "protocol": "a2a",
                "endpoint_url": "https://remote.example/rpc",
                "push_url": "https://boss.example/a2a/push",
                "team_bearer_token_ref": "env://TEAM_BEARER",
                "push_token_ref": "env://PUSH_TOKEN",
                "bridge_secret_ref": "env://BRIDGE_SECRET",
            }
        ),
        encoding="utf-8",
    )
    env_path = tmp_path / "bridge.env"
    env_path.write_text("TEAM_BEARER=remote-token\nPUSH_TOKEN=push-token\nBRIDGE_SECRET=bridge-secret\n", encoding="utf-8")
    return factory_dir, team_dir, BridgeDb(tmp_path / "bridge.sqlite"), SecretResolver(env_path)


def test_dispatch_is_idempotent_after_a_task_id_is_recorded(tmp_path: Path) -> None:
    factory_dir, team_dir, db, secrets = setup_bridge(tmp_path)
    inbox_path = team_dir / "inbox" / "assign-1.md"
    inbox_path.write_text("# Assignment\n", encoding="utf-8")

    class StubClient:
        sends = 0

        def send_assignment(self, **kwargs):
            self.sends += 1
            return {"task_id": "task-1", "result": {"id": "task-1", "kind": "task"}}

    client = StubClient()
    dispatch_assignment(db=db, secrets=secrets, a2a_client=client, team_name="dev", team_dir=team_dir, inbox_path=inbox_path)
    dispatch_assignment(db=db, secrets=secrets, a2a_client=client, team_name="dev", team_dir=team_dir, inbox_path=inbox_path)

    assert factory_dir.exists()
    assert client.sends == 1
    assert db.get_assignment("assign-1")["a2a_task_id"] == "task-1"
    assert (team_dir / "inbox" / "assign-1.in-flight.md").exists()
    db.close()


def test_push_duplicate_sequence_is_accepted_as_a_no_op(tmp_path: Path) -> None:
    factory_dir, _team_dir, db, secrets = setup_bridge(tmp_path)
    db.ensure_assignment(assignment_id="assign-1", team_name="dev", inbox_path="/tmp/assign-1.md")
    db.mark_dispatched(assignment_id="assign-1", task_id="task-1", in_flight_path="/tmp/assign-1.in-flight.md")
    body = {"team_name": "dev", "task_id": "task-1", "state": "working", "sequence": 1, "message": "started"}
    signature = sign_push(secret="bridge-secret", team_name="dev", task_id="task-1", state="working", sequence=1, body=body)
    headers = {"authorization": "Bearer push-token", "x-a2a-notification-token": signature}

    assert process_push(db=db, secrets=secrets, factory_dir=factory_dir, headers=headers, body=body)["status"] == 202
    duplicate = process_push(db=db, secrets=secrets, factory_dir=factory_dir, headers=headers, body=body)

    assert duplicate == {"status": 202, "body": {"duplicate": True}}
    db.close()


def test_completed_push_writes_sanitized_artifact(tmp_path: Path) -> None:
    factory_dir, team_dir, db, secrets = setup_bridge(tmp_path)
    db.ensure_assignment(assignment_id="assign-1", team_name="dev", inbox_path="/tmp/assign-1.md")
    db.mark_dispatched(assignment_id="assign-1", task_id="task-1", in_flight_path="/tmp/assign-1.in-flight.md")
    body = {
        "team_name": "dev",
        "task_id": "task-1",
        "state": "completed",
        "sequence": 2,
        "artifacts": [{"name": "../result?.md", "text": "done"}],
    }
    signature = sign_push(secret="bridge-secret", team_name="dev", task_id="task-1", state="completed", sequence=2, body=body)
    result = process_push(
        db=db,
        secrets=secrets,
        factory_dir=factory_dir,
        headers={"authorization": "Bearer push-token", "x-a2a-notification-token": signature},
        body=body,
    )

    assert result["status"] == 202
    assert (team_dir / "outbox" / "result_.md").read_text(encoding="utf-8") == "done"
    assert db.get_assignment("assign-1")["status"] == "completed"
    db.close()


def test_canonical_json_is_stable_for_object_key_ordering() -> None:
    assert canonical_json({"b": 1, "a": {"d": 2, "c": 3}}) == canonical_json({"a": {"c": 3, "d": 2}, "b": 1})


def test_push_signatures_verify_and_reject_tampering() -> None:
    body = {"state": "working", "sequence": 7, "task_id": "task-1", "team_name": "dev"}
    signature = sign_push(secret="bridge-secret", team_name="dev", task_id="task-1", state="working", sequence=7, body=body)

    assert verify_push_signature(
        expected=f"sha256={signature}",
        secret="bridge-secret",
        team_name="dev",
        task_id="task-1",
        state="working",
        sequence=7,
        body=body,
    )
    assert not verify_push_signature(
        expected=signature,
        secret="bridge-secret",
        team_name="dev",
        task_id="task-1",
        state="completed",
        sequence=7,
        body=body,
    )


def test_parse_dotenv_reads_quoted_and_unquoted_values() -> None:
    assert parse_dotenv("A=one\nB='two two'\nC=\"three\\nlines\"\n# nope\n") == {
        "A": "one",
        "B": "two two",
        "C": "three\nlines",
    }
