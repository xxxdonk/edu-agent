[CmdletBinding()]
param(
    [switch]$SkipPreflight
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$backendDirectory = Join-Path $projectRoot "backend"
$frontendDirectory = Join-Path $projectRoot "frontend"
$vite = Join-Path $frontendDirectory "node_modules\.bin\vite.cmd"
$envFile = Join-Path $projectRoot ".env"
$preflight = Join-Path $projectRoot "scripts\preflight_demo.py"
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue

function Stop-WithMessage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Test-LocalPortAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        $Port
    )
    try {
        $listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        try {
            $listener.Stop()
        }
        catch {
        }
    }
}

function Wait-ForEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSeconds = 30
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited) {
            return $false
        }
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        }
        catch {
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Stop-ProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [int]$RootProcessId
    )

    $children = @(
        Get-CimInstance Win32_Process `
            -Filter "ParentProcessId = $RootProcessId" `
            -ErrorAction SilentlyContinue
    )
    foreach ($child in $children) {
        Stop-ProcessTree -RootProcessId $child.ProcessId
    }
    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Stop-WithMessage "Python virtual environment is missing. Install the backend dependencies from README first."
}
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    Stop-WithMessage "The root .env file is missing. Copy .env.example to .env and configure it before starting the demo."
}
if ($null -eq $nodeCommand) {
    Stop-WithMessage "node.exe is missing. Install Node.js 20 or newer and try again."
}
if ($null -eq $npmCommand) {
    Stop-WithMessage "npm.cmd is missing. Install Node.js 20 or newer and try again."
}
if (-not (Test-Path -LiteralPath $vite -PathType Leaf)) {
    Stop-WithMessage "Frontend dependencies are missing. Run npm ci in the frontend directory first."
}
if (-not $SkipPreflight) {
    if (-not (Test-Path -LiteralPath $preflight -PathType Leaf)) {
        Stop-WithMessage "Demo preflight script is missing: scripts/preflight_demo.py"
    }
    & $python $preflight
    if ($LASTEXITCODE -ne 0) {
        Stop-WithMessage "Demo preflight failed. Resolve the reported blocking checks and try again."
    }
}
if (-not (Test-LocalPortAvailable -Port 8000)) {
    Stop-WithMessage "Port 8000 is already in use. Stop the program using that port first."
}
if (-not (Test-LocalPortAvailable -Port 5173)) {
    Stop-WithMessage "Port 5173 is already in use. Stop the program using that port first."
}

$logDirectory = Join-Path ([System.IO.Path]::GetTempPath()) "eduagent-demo"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backendOutput = Join-Path $logDirectory "backend-$timestamp.out.log"
$backendError = Join-Path $logDirectory "backend-$timestamp.err.log"
$frontendOutput = Join-Path $logDirectory "frontend-$timestamp.out.log"
$frontendError = Join-Path $logDirectory "frontend-$timestamp.err.log"

$backendProcess = $null
$frontendProcess = $null

try {
    $backendProcess = Start-Process `
        -FilePath $python `
        -ArgumentList @(
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000"
        ) `
        -WorkingDirectory $backendDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $backendOutput `
        -RedirectStandardError $backendError `
        -PassThru

    $frontendProcess = Start-Process `
        -FilePath $npmCommand.Source `
        -ArgumentList @(
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            "5173"
        ) `
        -WorkingDirectory $frontendDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $frontendOutput `
        -RedirectStandardError $frontendError `
        -PassThru

    $backendReady = Wait-ForEndpoint `
        -Uri "http://127.0.0.1:8000/api/health" `
        -Process $backendProcess
    if (-not $backendReady) {
        throw "The backend did not start within 30 seconds. Check the EduAgent backend log in the system temporary directory."
    }

    $frontendReady = Wait-ForEndpoint `
        -Uri "http://127.0.0.1:5173/" `
        -Process $frontendProcess
    if (-not $frontendReady) {
        throw "The frontend did not start within 30 seconds. Check the EduAgent frontend log in the system temporary directory."
    }

    Write-Host "EduAgent is ready."
    Write-Host "Frontend: http://127.0.0.1:5173/"
    Write-Host "Backend health: http://127.0.0.1:8000/api/health"
    Write-Host "Logs are in the eduagent-demo folder under the system temporary directory."
    Write-Host "Keep this window open. Press Ctrl+C to stop both services."

    while (-not $backendProcess.HasExited -and -not $frontendProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
    throw "The frontend or backend exited unexpectedly. Check the temporary logs."
}
finally {
    foreach ($process in @($frontendProcess, $backendProcess)) {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-ProcessTree -RootProcessId $process.Id
        }
    }
}
