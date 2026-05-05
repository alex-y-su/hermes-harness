from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from harness import db as harness_db
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


def test_assignment_lease_is_atomic_and_expires(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    harness_db.init_db(db_path)
    now = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
    with harness_db.session(db_path) as conn:
        assert harness_db.acquire_lease(
            conn,
            resource_type="assignment",
            resource_id="assign-1",
            holder="bridge-a",
            ttl_seconds=60,
            now=now,
        )
        assert not harness_db.acquire_lease(
            conn,
            resource_type="assignment",
            resource_id="assign-1",
            holder="bridge-b",
            ttl_seconds=60,
            now=now + timedelta(seconds=30),
        )
        assert harness_db.acquire_lease(
            conn,
            resource_type="assignment",
            resource_id="assign-1",
            holder="bridge-b",
            ttl_seconds=60,
            now=now + timedelta(seconds=61),
        )


def test_dispatch_failure_becomes_retryable_and_can_dispatch_later(tmp_path: Path) -> None:
    _factory_dir, team_dir, db, secrets = setup_bridge(tmp_path)
    inbox_path = team_dir / "inbox" / "assign-1.md"
    inbox_path.write_text("# Assignment\n", encoding="utf-8")

    class FlakyClient:
        sends = 0

        def send_assignment(self, **kwargs):
            self.sends += 1
            if self.sends == 1:
                raise RuntimeError("temporary outage")
            return {"task_id": "task-1", "result": {"id": "task-1", "kind": "task"}}

    client = FlakyClient()
    first = dispatch_assignment(
        db=db,
        secrets=secrets,
        a2a_client=client,
        team_name="dev",
        team_dir=team_dir,
        inbox_path=inbox_path,
        retry_delay_seconds=0,
    )
    assert first["status"] == "retrying"
    row = db.get_assignment("assign-1")
    assert row["retry_count"] == 1
    assert row["a2a_task_id"] is None

    second = dispatch_assignment(
        db=db,
        secrets=secrets,
        a2a_client=client,
        team_name="dev",
        team_dir=team_dir,
        inbox_path=inbox_path,
        retry_delay_seconds=0,
    )
    assert second["dispatched"] is True
    assert client.sends == 2
    assert db.get_assignment("assign-1")["a2a_task_id"] == "task-1"
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


def test_input_required_push_creates_user_request_without_finalizing_sandbox(tmp_path: Path) -> None:
    factory_dir, _team_dir, db, secrets = setup_bridge(tmp_path)
    db.ensure_assignment(assignment_id="assign-1", team_name="dev", inbox_path="/tmp/assign-1.md")
    db.mark_dispatched(assignment_id="assign-1", task_id="task-1", in_flight_path="/tmp/assign-1.in-flight.md")
    db.save_assignment_sandbox(
        assignment_id="assign-1",
        team_name="dev",
        substrate="e2b",
        handle=json.dumps({"sandbox_id": "dry"}),
        agent_card_url="http://sandbox.example/.well-known/agent-card.json",
        status="booted",
        metadata={"dry_run": True},
    )
    body = {
        "team_name": "dev",
        "task_id": "task-1",
        "state": "input-required",
        "sequence": 3,
        "title": "Pick a region",
        "message": "Which deploy region should I use?",
        "required_fields": [{"name": "region", "type": "string"}],
    }
    signature = sign_push(secret="bridge-secret", team_name="dev", task_id="task-1", state="input-required", sequence=3, body=body)

    result = process_push(
        db=db,
        secrets=secrets,
        factory_dir=factory_dir,
        headers={"authorization": "Bearer push-token", "x-a2a-notification-token": signature},
        body=body,
    )

    assert result["status"] == 202
    assert db.get_assignment("assign-1")["status"] == "input-required"
    request = db.get_approval_request("assign-1:input-required:3")
    assert request["status"] == "open"
    assert request["title"] == "Pick a region"
    assert json.loads(request["required_fields_json"]) == [{"name": "region", "type": "string"}]
    assert Path(request["escalation_path"]).exists()
    assert "request_id: assign-1:input-required:3" in Path(request["escalation_path"]).read_text(encoding="utf-8")
    sandbox = db.get_assignment_sandbox("assign-1")
    assert sandbox["status"] == "booted"
    assert sandbox["terminal_at"] is None
    db.close()


def test_repeated_input_required_pushes_create_distinct_user_requests(tmp_path: Path) -> None:
    factory_dir, _team_dir, db, secrets = setup_bridge(tmp_path)
    db.ensure_assignment(assignment_id="assign-1", team_name="dev", inbox_path="/tmp/assign-1.md")
    db.mark_dispatched(assignment_id="assign-1", task_id="task-1", in_flight_path="/tmp/assign-1.in-flight.md")

    for sequence, message in ((3, "Need region."), (4, "Need rollout window.")):
        body = {
            "team_name": "dev",
            "task_id": "task-1",
            "state": "input-required",
            "sequence": sequence,
            "message": message,
        }
        signature = sign_push(
            secret="bridge-secret",
            team_name="dev",
            task_id="task-1",
            state="input-required",
            sequence=sequence,
            body=body,
        )
        assert (
            process_push(
                db=db,
                secrets=secrets,
                factory_dir=factory_dir,
                headers={"authorization": "Bearer push-token", "x-a2a-notification-token": signature},
                body=body,
            )["status"]
            == 202
        )

    assert db.get_approval_request("assign-1:input-required:3")["prompt"] == "Need region."
    assert db.get_approval_request("assign-1:input-required:4")["prompt"] == "Need rollout window."
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
