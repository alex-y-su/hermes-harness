#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/vm/hermes-home}"
HERMES_INSTALL_DIR="${HERMES_INSTALL_DIR:-/usr/local/lib/hermes-agent}"
INSTALLER_URL="${HERMES_INSTALLER_URL:-https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh}"

mkdir -p "$HERMES_HOME" "$(dirname "$HERMES_INSTALL_DIR")" /vm/factory

installer="/tmp/hermes-agent-install.sh"
curl -fsSL "$INSTALLER_URL" -o "$installer"

if [ -d "$HERMES_INSTALL_DIR/.git" ]; then
  git -C "$HERMES_INSTALL_DIR" pull --ff-only
else
  if [ "${HERMES_INSTALL_BROWSER_TOOLS:-0}" != "1" ]; then
  python3 - "$installer" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace(
    "    check_node\n",
    "    if [ \"${HERMES_INSTALL_BROWSER_TOOLS:-0}\" = \"1\" ]; then\n"
    "        check_node\n"
    "    else\n"
    "        log_info \"Skipping Node.js/browser dependency check (HERMES_INSTALL_BROWSER_TOOLS=0)\"\n"
    "        HAS_NODE=false\n"
    "    fi\n",
    1,
)
text = text.replace(
    "    install_node_deps\n",
    "    if [ \"${HERMES_INSTALL_BROWSER_TOOLS:-0}\" = \"1\" ]; then\n"
    "        install_node_deps\n"
    "    else\n"
    "        log_info \"Skipping Node.js/browser dependency install (HERMES_INSTALL_BROWSER_TOOLS=0)\"\n"
    "    fi\n",
    1,
)
path.write_text(text, encoding="utf-8")
PY
  fi

  bash "$installer" --skip-setup --dir "$HERMES_INSTALL_DIR" --hermes-home "$HERMES_HOME"
fi

command -v hermes >/dev/null 2>&1
hermes version >/tmp/hermes-version.txt 2>&1 || hermes --version >/tmp/hermes-version.txt 2>&1
git -C "$HERMES_INSTALL_DIR" rev-parse HEAD >/tmp/hermes-commit.txt

if [ ! -x /usr/local/bin/hermes ]; then
  ln -sfn /root/.local/bin/hermes /usr/local/bin/hermes
fi

rm -rf /root/.cache/uv /root/.cache/pip /tmp/hermes-agent-install.sh
