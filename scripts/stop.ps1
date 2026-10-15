$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot 'data\server.pid'
if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Output 'No background server PID is recorded. Stop a foreground server with Ctrl+C.'
    return
}
[int]$serverId = Get-Content -LiteralPath $pidFile
$serverInstance = Get-CimInstance Win32_Process -Filter "ProcessId = $serverId"
if (-not $serverInstance) {
    Write-Output 'The recorded background process has already stopped.'
    return
}
$expectedPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if ($serverInstance.ExecutablePath -ne $expectedPython -or $serverInstance.CommandLine -notmatch '\brun\.py\b') {
    throw 'The recorded PID no longer matches this project server. No process was stopped.'
}
# A Windows venv executable can launch a Python child. Stop only this verified process tree.
& taskkill.exe /PID $serverId /T /F
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the recorded server process tree.' }
Remove-Item -LiteralPath $pidFile
Write-Output 'Stopped the Vizio Media background server.'
