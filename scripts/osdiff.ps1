$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".\.venv\Scripts\python.exe")) { throw "Run scripts\setup-local.ps1 first." }
& .\.venv\Scripts\python.exe osdiff.py @args
exit $LASTEXITCODE
