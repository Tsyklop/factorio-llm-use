param(
    [Parameter(Mandatory = $true)][string]$FactorioExe,
    [string]$Save = '',
    [string]$SourceMods = (Join-Path $env:APPDATA 'Factorio\mods'),
    [int]$GamePort = 34199,
    [int]$RconPort = 27075,
    [switch]$Resume
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$dataRoot = Join-Path $runtimeRoot 'data'
$modRoot = Join-Path $runtimeRoot 'mods'
$pidFile = Join-Path $runtimeRoot 'server.pid'
if (Test-Path -LiteralPath $pidFile) {
    $previousServerId = [int](Get-Content -LiteralPath $pidFile)
    if (Get-Process -Id $previousServerId -ErrorAction SilentlyContinue) {
        throw 'The previous server process still exists. Stop it explicitly before starting another.'
    }
}
$exePath = (Resolve-Path -LiteralPath $FactorioExe).Path
if (-not $Resume -and -not $Save) { throw 'Provide -Save for a new session or -Resume for an existing one.' }
$gameData = Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $exePath))) 'data'
New-Item -ItemType Directory -Path $runtimeRoot, $dataRoot, $modRoot, (Join-Path $dataRoot 'saves') -Force | Out-Null
Get-ChildItem -LiteralPath $SourceMods -File | Copy-Item -Destination $modRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run uv sync first.' }
& $python (Join-Path $PSScriptRoot 'package_mod.py') | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot 'dist\factorio_llm_use_0.1.0.zip') -Destination $modRoot
$modListPath = Join-Path $modRoot 'mod-list.json'
$modList = Get-Content -LiteralPath $modListPath -Raw | ConvertFrom-Json
$modList.mods = @($modList.mods | Where-Object { $_.name -ne 'factorio_llm_use' }) + @(@{name='factorio_llm_use';enabled=$true})
$modList | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $modListPath -Encoding utf8
$sessionSave = Join-Path $runtimeRoot 'session.zip'
if ($Resume) {
    $lastSessionSave = Get-ChildItem -LiteralPath (Join-Path $dataRoot 'saves') -Filter '*.zip' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($lastSessionSave) { $sessionSave = $lastSessionSave.FullName }
    elseif (-not (Test-Path -LiteralPath $sessionSave)) { throw 'No session exists to resume.' }
} else {
    if (Test-Path -LiteralPath $sessionSave) {
        throw 'A session save already exists. Use -Resume; the session will not be overwritten.'
    }
    $savePath = (Resolve-Path -LiteralPath $Save).Path
    Copy-Item -LiteralPath $savePath -Destination $sessionSave
}
$passwordFile = Join-Path $runtimeRoot 'rcon-password.txt'
if (-not (Test-Path -LiteralPath $passwordFile)) {
    [Guid]::NewGuid().ToString('N') | Set-Content -LiteralPath $passwordFile -NoNewline
}
$rconPassword = (Get-Content -LiteralPath $passwordFile -Raw).Trim()
$configFile = Join-Path $runtimeRoot 'config.ini'
"[path]`nread-data=$($gameData.Replace('\','/'))`nwrite-data=$($dataRoot.Replace('\','/'))`n" | Set-Content -LiteralPath $configFile -Encoding utf8
$settingsFile = Join-Path $runtimeRoot 'server-settings.json'
@{name='Factorio LLM Use';description='Local AI engineer session';visibility=@{public=$false;lan=$false};require_user_verification=$false;auto_pause=$false;autosave_interval=5} | ConvertTo-Json | Set-Content -LiteralPath $settingsFile -Encoding utf8
$serverArgs = @('--config',('"{0}"' -f $configFile),'--mod-directory',('"{0}"' -f $modRoot),'--start-server',('"{0}"' -f $sessionSave),'--server-settings',('"{0}"' -f $settingsFile),'--bind','127.0.0.1','--port',[string]$GamePort,'--rcon-bind',"127.0.0.1:$RconPort",'--rcon-password',$rconPassword)
$server = Start-Process -FilePath $exePath -ArgumentList $serverArgs -WorkingDirectory $runtimeRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'server.log') -RedirectStandardError (Join-Path $runtimeRoot 'server.stderr.log') -PassThru
$server.Id | Set-Content -LiteralPath $pidFile
Write-Output "Server started as PID $($server.Id), game 127.0.0.1:$GamePort, RCON 127.0.0.1:$RconPort."
Write-Output "Session data and autosaves: $dataRoot"
