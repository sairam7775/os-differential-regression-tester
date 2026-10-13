#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || { echo "Run scripts/setup-local.sh first."; exit 1; }
. .venv/bin/activate
python osdiff.py "$@"
