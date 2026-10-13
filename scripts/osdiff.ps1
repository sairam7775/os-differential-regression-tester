# Run from the repository root using its .venv, forwarding CLI arguments/exit status.
# Global --config must precede the subcommand; see docs/CONFIGURATION.md.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".\.venv\Scripts\python.exe")) { throw "Run scripts\setup-local.ps1 first." }
& .\.venv\Scripts\python.exe osdiff.py @args
exit $LASTEXITCODE
