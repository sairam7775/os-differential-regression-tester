#!/usr/bin/env bash
# Select this checkout's environment and forward arguments/status unchanged.
# The wrapper's cwd is the tool root; JSON app paths resolve beside the config file.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || { echo "Run scripts/setup-local.sh first."; exit 1; }
. .venv/bin/activate
python osdiff.py "$@"
