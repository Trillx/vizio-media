param([string]$BindAddress, [int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Create .venv and install requirements.txt first. See README.md.'
}
if ($BindAddress) { $env:VIZIO_BIND_IP = $BindAddress }
$env:VIZIO_PORT = [string]$Port
& $projectPython run.py
exit $LASTEXITCODE
