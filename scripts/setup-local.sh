#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

command -v python3 >/dev/null || { echo "Python 3.10+ is required."; exit 1; }
command -v node >/dev/null || { echo "Node.js is required."; exit 1; }
command -v npm >/dev/null || { echo "npm is required."; exit 1; }

node -e 'const [M,m]=process.versions.node.split(".").map(Number); if (!((M===20&&m>=19)||(M===22&&m>=12)||M>=24)) { console.error(`Unsupported Node ${process.versions.node}. Need ^20.19.0 || ^22.12.0 || >=24.`); process.exit(1); }'
node -e 'const {execFileSync}=require("child_process"); const v=execFileSync("npm",["--version"],{encoding:"utf8"}).trim(); const M=Number(v.split(".")[0]); if (M<10) { console.error(`Unsupported npm ${v}. Need npm >=10.`); process.exit(1); }'

echo "== Python environment =="
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

read_version() {
  python - "$1" <<'PY'
import json, sys
print(json.load(open("config/tool-versions.json", encoding="utf-8"))[sys.argv[1]])
PY
}

APPIUM_VERSION="$(read_version appium)"
UIA_VERSION="$(read_version uiautomator2)"
XCU_VERSION="$(read_version xcuitest)"

echo "== Tool-local Appium ${APPIUM_VERSION} =="
mkdir -p .node .appium
npm install --prefix .node "appium@${APPIUM_VERSION}"
APPIUM="$PWD/.node/node_modules/.bin/appium"
export APPIUM_HOME="$PWD/.appium"

# This APPIUM_HOME belongs only to this tool, so replacing drivers is safe and reproducible.
"$APPIUM" driver uninstall uiautomator2 >/dev/null 2>&1 || true
"$APPIUM" driver install "uiautomator2@${UIA_VERSION}"

if [ "$(uname -s)" = "Darwin" ]; then
  "$APPIUM" driver uninstall xcuitest >/dev/null 2>&1 || true
  "$APPIUM" driver install "xcuitest@${XCU_VERSION}"
fi

echo
echo "Setup complete. Installed pinned versions from config/tool-versions.json."
echo "Next:"
echo "  . .venv/bin/activate"
echo "  python osdiff.py doctor"
