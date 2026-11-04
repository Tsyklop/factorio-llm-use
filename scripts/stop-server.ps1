param([int]$RconPort = 27075)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$serverProcessId = [int](Get-Content -LiteralPath (Join-Path $runtimeRoot 'server.pid'))
$serverProcess = Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -eq $serverProcessId }
if (-not $serverProcess -or $serverProcess.Name -notmatch '^factorio\.exe$' -or -not $serverProcess.CommandLine.Contains($runtimeRoot) -or -not $serverProcess.CommandLine.Contains('--start-server')) {
    throw 'The recorded PID does not identify this project server. No process was stopped.'
}
$env:FACTORIO_RCON_PORT = [string]$RconPort
& (Join-Path $projectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'save_session.py')
if ($LASTEXITCODE -ne 0) { throw 'Saving failed. The server was left running.' }
Stop-Process -Id $serverProcessId
Get-Process -Id $serverProcessId -ErrorAction SilentlyContinue | Wait-Process -Timeout 30
Remove-Item -LiteralPath (Join-Path $runtimeRoot 'server.pid')
Write-Output "Saved the session and stopped project server PID $serverProcessId."
