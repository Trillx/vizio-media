param([string]$BindAddress, [string]$TvAddress = $env:VIZIO_TV_IP, [int]$Port = 8765)
$ErrorActionPreference = 'Stop'
if (-not $TvAddress) { throw 'Pass -TvAddress or set VIZIO_TV_IP to the TV address first.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this helper from an Administrator PowerShell terminal to add the scoped Windows Firewall rule.'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
Push-Location -LiteralPath $projectRoot
try {
    if (-not $BindAddress) {
        $BindAddress = & $projectPython -c 'from app.config import Settings; print(Settings.from_env().bind_ip)'
        if ($LASTEXITCODE -ne 0) { throw 'Could not determine the server address.' }
    }
    $interfaceAddress = Get-NetIPAddress -AddressFamily IPv4 -IPAddress $BindAddress
    if (-not $interfaceAddress) { throw 'The selected address is not assigned to this computer.' }
    # Windows venv launchers run a child using the base Python executable.
    $networkPython = & $projectPython -c 'import sys; print(sys._base_executable)'
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $networkPython)) { throw 'Could not identify the server executable.' }
    $ruleName = 'VizioMedia-HardwareTest'
    $ruleGroup = 'Vizio Media local hardware test'
    $existingRule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    if ($existingRule) {
        if ($existingRule.Group -ne $ruleGroup) { throw 'An unrelated rule uses this name. No rule was changed.' }
        Set-NetFirewallRule -Name $ruleName -Enabled True -Direction Inbound -Action Allow -Profile Private,Public -Protocol TCP -LocalAddress $BindAddress -LocalPort $Port -RemoteAddress $TvAddress -Program $networkPython | Out-Null
    } else {
        New-NetFirewallRule -Name $ruleName -DisplayName 'Vizio Media TV compatibility test' -Group $ruleGroup -Enabled True -Direction Inbound -Action Allow -Profile Private,Public -Protocol TCP -LocalAddress $BindAddress -LocalPort $Port -RemoteAddress $TvAddress -Program $networkPython | Out-Null
    }
    Write-Output "Allowed only TV $TvAddress to reach $BindAddress on TCP $Port using $networkPython."
    Write-Output 'The rule applies to Private and Public profiles without changing the network category.'
    Write-Output "To remove this rule: Remove-NetFirewallRule -Name '$ruleName'"
} finally {
    Pop-Location
}
