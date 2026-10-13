# Install project-local Python/Appium tools; this does not install the app under test.
# Read docs/QUICKSTART.md first. Java/ADB and real-device authorization are external prerequisites.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python 3.10+ is required." }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Node.js is required." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm is required." }

node -e 'const [M,m]=process.versions.node.split(".").map(Number); if (!((M===20&&m>=19)||(M===22&&m>=12)||M>=24)) { console.error(`Unsupported Node ${process.versions.node}. Need ^20.19.0 || ^22.12.0 || >=24.`); process.exit(1); }'
if ($LASTEXITCODE -ne 0) { throw "Unsupported Node.js version." }
$npmVersion = (npm --version).Trim()
if ([int]($npmVersion.Split('.')[0]) -lt 10) { throw "Unsupported npm $npmVersion. Need npm >=10." }

Write-Host "== Python environment =="
# Known baseline gap: native Python exit codes below are not explicitly checked.
# A successful final message is not proof that every dependency installation succeeded.
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

$versions = Get-Content .\config\tool-versions.json | ConvertFrom-Json
$AppiumVersion = $versions.appium
$UiaVersion = $versions.uiautomator2

Write-Host "== Tool-local Appium $AppiumVersion =="
New-Item -ItemType Directory -Force .node,.appium | Out-Null
npm install --prefix .node "appium@$AppiumVersion"
if ($LASTEXITCODE -ne 0) { throw "Appium installation failed." }

$env:APPIUM_HOME = (Resolve-Path .appium).Path
# Driver replacement is scoped to this tool's .appium directory, not the tested app.
$Appium = ".\.node\node_modules\.bin\appium.cmd"
& $Appium driver uninstall uiautomator2 2>$null | Out-Null
& $Appium driver install "uiautomator2@$UiaVersion"
if ($LASTEXITCODE -ne 0) { throw "UiAutomator2 driver installation failed." }

Write-Host ""
Write-Host "Setup complete. Installed pinned versions from config/tool-versions.json."
Write-Host "Next:"
Write-Host "  .\.venv\Scripts\python.exe osdiff.py doctor"
