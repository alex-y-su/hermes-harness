#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HERMES_INSTALL_DIR="${HERMES_INSTALL_DIR:-/usr/local/lib/hermes-agent}"
KANBAN_DB="${HERMES_INSTALL_DIR}/hermes_cli/kanban_db.py"
MOCK_SRC="${HERMES_MOCK_KANBAN_SRC:-${ROOT_DIR}/scripts/hermes/mock_remote_kanban.py}"
MOCK_DST="${HERMES_INSTALL_DIR}/hermes_cli/mock_remote_kanban.py"

if [ ! -f "$KANBAN_DB" ]; then
  echo "Hermes kanban_db.py not found: $KANBAN_DB" >&2
  exit 1
fi
if [ ! -f "$MOCK_SRC" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/mock_remote_kanban.py" ]; then
  MOCK_SRC="$(dirname "${BASH_SOURCE[0]}")/mock_remote_kanban.py"
fi
if [ ! -f "$MOCK_SRC" ]; then
  echo "Mock module source not found: $MOCK_SRC" >&2
  exit 1
fi

cp "$MOCK_SRC" "$MOCK_DST"

"${HERMES_INSTALL_DIR}/venv/bin/python" - "$KANBAN_DB" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
marker = "# HERMES_HARNESS_MOCK_REMOTE_KANBAN_START"

if marker not in text:
    needle = '''        if not row["assignee"]:
            result.skipped_unassigned.append(row["id"])
            continue
'''
    insert = '''        # HERMES_HARNESS_MOCK_REMOTE_KANBAN_START
        # Local playground override: route team:<name> assignees to a mock
        # remote-team Kanban implementation instead of spawning a local
        # Hermes profile. This keeps Hermes' familiar Kanban surface while
        # testing the remote-team execution model.
        if str(row["assignee"]).startswith("team:"):
            from hermes_cli import mock_remote_kanban as _mock_remote_kanban
            handled = _mock_remote_kanban.dispatch_team_task(
                kb=sys.modules[__name__],
                conn=conn,
                task_id=row["id"],
                assignee=row["assignee"],
                board=board,
            )
            if handled.get("handled"):
                result.spawned.append(
                    (
                        row["id"],
                        row["assignee"],
                        f"mock-remote:{handled.get('team', '')}:{handled.get('status', '')}",
                    )
                )
                spawned += 1
            else:
                result.skipped_nonspawnable.append(row["id"])
            continue
        # HERMES_HARNESS_MOCK_REMOTE_KANBAN_END
'''
    if needle not in text:
        raise SystemExit("could not find kanban dispatch insertion point")
    text = text.replace(needle, needle + insert, 1)
    path.write_text(text, encoding="utf-8")

print(f"Mock remote Kanban installed into {path}")
PY
