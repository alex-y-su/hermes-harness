#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HERMES_INSTALL_DIR="${HERMES_INSTALL_DIR:-/usr/local/lib/hermes-agent}"
KANBAN_DB="${HERMES_INSTALL_DIR}/hermes_cli/kanban_db.py"
REMOTE_SRC="${HERMES_REMOTE_KANBAN_SRC:-${ROOT_DIR}/scripts/hermes/remote_team_kanban.py}"
REMOTE_DST="${HERMES_INSTALL_DIR}/hermes_cli/remote_team_kanban.py"

if [ ! -f "$KANBAN_DB" ]; then
  echo "Hermes kanban_db.py not found: $KANBAN_DB" >&2
  exit 1
fi
if [ ! -f "$REMOTE_SRC" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/remote_team_kanban.py" ]; then
  REMOTE_SRC="$(dirname "${BASH_SOURCE[0]}")/remote_team_kanban.py"
fi
if [ ! -f "$REMOTE_SRC" ]; then
  echo "Remote Kanban module source not found: $REMOTE_SRC" >&2
  exit 1
fi

cp "$REMOTE_SRC" "$REMOTE_DST"

"${HERMES_INSTALL_DIR}/venv/bin/python" - "$KANBAN_DB" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
marker = "# HERMES_HARNESS_REMOTE_TEAM_KANBAN_START"

if marker not in text:
    needle = '''        if not row["assignee"]:
            result.skipped_unassigned.append(row["id"])
            continue
'''
    insert = '''        # HERMES_HARNESS_REMOTE_TEAM_KANBAN_START
        # Route registered team:<name> assignees through the Hermes Harness
        # remote-team protocol adapter. If no registry entry exists, fall
        # through so local playground hooks can still handle the task.
        if str(row["assignee"]).startswith("team:"):
            from hermes_cli import remote_team_kanban as _remote_team_kanban
            handled = _remote_team_kanban.dispatch_team_task(
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
                        f"remote-team:{handled.get('team', '')}:{handled.get('status', '')}",
                    )
                )
                spawned += 1
                continue
        # HERMES_HARNESS_REMOTE_TEAM_KANBAN_END
'''
    if needle not in text:
        raise SystemExit("could not find kanban dispatch insertion point")
    text = text.replace(needle, needle + insert, 1)
    path.write_text(text, encoding="utf-8")

print(f"Remote-team Kanban installed into {path}")
PY
