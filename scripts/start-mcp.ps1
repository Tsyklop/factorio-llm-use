param(
    [int]$RconPort = 27075,
    [string]$PasswordFile = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $PasswordFile) { $PasswordFile = Join-Path $projectRoot '.runtime\rcon-password.txt' }
if (-not $env:FACTORIO_RCON_PASSWORD -and -not (Test-Path -LiteralPath $PasswordFile)) {
    throw 'Set FACTORIO_RCON_PASSWORD or provide -PasswordFile. See README.md.'
}
$env:FACTORIO_RCON_HOST = '127.0.0.1'
$env:FACTORIO_RCON_PORT = [string]$RconPort
$env:FACTORIO_RCON_PASSWORD_FILE = $PasswordFile
& uv run --project $projectRoot --frozen python -m factorio_llm_use.server
exit $LASTEXITCODE
