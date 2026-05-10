from __future__ import annotations

from harness.tools.boss_team_intelligence_test import profile_names, score_result


def test_profile_names_accepts_manifest_strings_and_objects() -> None:
    assert profile_names(["boss", {"profile": "critic"}, {"name": "ignored"}, 1]) == ["boss", "critic"]


def test_score_result_requires_all_roles_and_core_answer() -> None:
    role_outputs = {
        "supervisor": "TEAM_MEMBER\nsupervisor\nMakespan must be 8.",
        "hr": "TEAM_MEMBER\nhr\nRoute the schedule check.",
        "conductor": "TEAM_MEMBER\nconductor\nA 0-3, B 0-2, C 3-7, D 7-8.",
        "critic": "TEAM_MEMBER\ncritic\nReject any third-worker improvement claim.",
    }
    bridge_report = {"ok": True}
    boss_output = """\
TEAM_MEMBER: boss
FINAL_ANSWER: supervisor, hr, conductor, critic, and a2a-bridge contributed.
The minimum makespan is 8. One schedule is A 0-3, B 0-2, C 3-7, D 7-8.
A third worker does not improve the makespan because the critical path is 8.
"""

    checks = score_result(role_outputs, bridge_report, boss_output)

    assert all(checks.values())


def test_score_result_fails_when_boss_omits_role_or_wrong_claim() -> None:
    role_outputs = {
        "supervisor": "TEAM_MEMBER: supervisor",
        "hr": "TEAM_MEMBER: hr",
        "conductor": "TEAM_MEMBER: conductor",
        "critic": "TEAM_MEMBER: critic",
    }

    checks = score_result(role_outputs, {"ok": True}, "TEAM_MEMBER: boss\nMakespan is 8.")

    assert checks["boss_answered"] is True
    assert checks["boss_mentions_all_roles"] is False
    assert checks["boss_says_third_worker_no_help"] is False
