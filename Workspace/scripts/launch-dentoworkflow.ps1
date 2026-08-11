[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [string]$Config = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0

$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = [IO.Path]::GetFullPath(
    (Join-Path $ScriptDirectory "..\..")
)
$ModulePath = Join-Path $RepositoryRoot "DENTOWorkflow"
$ConfigTemplate = Join-Path $RepositoryRoot "Workspace\.dentobot.windows.env.example"
if ([string]::IsNullOrWhiteSpace($Config)) {
    $Config = Join-Path $RepositoryRoot ".dentobot.windows.env"
}

function Read-DentobotEnvironmentFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Windows configuration is missing: $Path`nCopy $ConfigTemplate there and edit it."
    }
    $Values = @{}
    foreach ($RawLine in Get-Content -LiteralPath $Path) {
        $Line = $RawLine.Trim()
        if (-not $Line -or $Line.StartsWith("#")) {
            continue
        }
        $SeparatorIndex = $Line.IndexOf("=")
        if ($SeparatorIndex -le 0) {
            throw "Invalid configuration line in ${Path}: $RawLine"
        }
        $Name = $Line.Substring(0, $SeparatorIndex).Trim()
        $Value = $Line.Substring($SeparatorIndex + 1).Trim()
        if (
            $Value.Length -ge 2 -and
            (($Value.StartsWith('"') -and $Value.EndsWith('"')) -or
             ($Value.StartsWith("'") -and $Value.EndsWith("'")))
        ) {
            $Value = $Value.Substring(1, $Value.Length - 2)
        }
        $Values[$Name] = $Value
    }
    return $Values
}

function Get-RequiredSetting {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Values,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if (-not $Values.ContainsKey($Name) -or [string]::IsNullOrWhiteSpace($Values[$Name])) {
        throw "Required setting is missing from ${Config}: $Name"
    }
    return [string]$Values[$Name]
}

$Settings = Read-DentobotEnvironmentFile -Path $Config
$SlicerExecutable = Get-RequiredSetting $Settings "DENTOBOT_SLICER_EXECUTABLE"
$WslDistribution = Get-RequiredSetting $Settings "DENTOBOT_WSL_DISTRIBUTION"
$BackendPython = Get-RequiredSetting $Settings "DENTOBOT_BACKEND_PYTHON"
$ArtifactRoot = Get-RequiredSetting $Settings "DENTOBOT_RUN_ARTIFACT_ROOT"
$BackendDevice = Get-RequiredSetting $Settings "DENTOBOT_BACKEND_DEVICE"
$RosProfile = if ($Settings.ContainsKey("DENTOBOT_ROS_PROFILE")) {
    [string]$Settings["DENTOBOT_ROS_PROFILE"]
} else {
    "none"
}

if (-not (Test-Path -LiteralPath $SlicerExecutable -PathType Leaf)) {
    throw "3D Slicer executable is unavailable: $SlicerExecutable"
}
if (-not (Test-Path -LiteralPath (Join-Path $ModulePath "DENTOWorkflow.py") -PathType Leaf)) {
    throw "DENTOWorkflow source is unavailable below: $ModulePath"
}
if (-not $BackendPython.StartsWith("/")) {
    throw "DENTOBOT_BACKEND_PYTHON must be an absolute Linux path inside WSL2."
}
if ($ArtifactRoot.StartsWith("\\") -or $ArtifactRoot.StartsWith("//")) {
    throw "DENTOBOT_RUN_ARTIFACT_ROOT must not be a network/UNC path."
}
if ($ArtifactRoot -notmatch '^[A-Za-z]:[\\/]') {
    throw "DENTOBOT_RUN_ARTIFACT_ROOT must be a local absolute path such as C:\DENTOBOTRuns."
}
if ($BackendDevice -notin @("cpu", "cuda:0")) {
    throw "DENTOBOT_BACKEND_DEVICE must be cpu or cuda:0."
}
if ($RosProfile -ne "none") {
    throw (
        "The native-Windows profile supports DENTOBOT_ROS_PROFILE=none. " +
        "Current upstream SlicerROS2 targets Ubuntu; use the verified Linux " +
        "SlicerROS2 profile for ROS-integrated operation."
    )
}

$WslCommand = Get-Command "wsl.exe" -ErrorAction Stop
$WslExecutable = $WslCommand.Source

& $WslExecutable --distribution $WslDistribution --exec test -x $BackendPython
if ($LASTEXITCODE -ne 0) {
    throw "Backend Python is not executable in WSL distribution ${WslDistribution}: $BackendPython"
}

& $WslExecutable --distribution $WslDistribution --exec `
    $BackendPython -m dentobot_inference health --json `
    --require-device $BackendDevice
if ($LASTEXITCODE -ne 0) {
    throw "DENTOBOT backend health check failed in WSL2."
}

New-Item -ItemType Directory -Path $ArtifactRoot -Force | Out-Null

$env:DENTOBOT_BACKEND_EXECUTION_MODE = "wsl"
$env:DENTOBOT_WSL_DISTRIBUTION = $WslDistribution
$env:DENTOBOT_BACKEND_PYTHON = $BackendPython
$env:DENTOBOT_RUN_ARTIFACT_ROOT = $ArtifactRoot
$env:DENTOBOT_BACKEND_DEVICE = $BackendDevice

Write-Host "DENTOBOT Windows/WSL launcher check passed."
Write-Host "Slicer: $SlicerExecutable"
Write-Host "Module: $ModulePath"
Write-Host "Backend adapter: wsl ($WslDistribution)"
Write-Host "Backend Python: $BackendPython"
Write-Host "Backend device: $BackendDevice"
Write-Host "Run artifacts: $ArtifactRoot"
Write-Host "ROS profile: none (Docker is not required for planning)"

if ($CheckOnly) {
    exit 0
}

$SlicerArguments = @(
    "--no-splash",
    "--additional-module-paths", $ModulePath,
    "--python-code", 'slicer.util.selectModule("DENTOWorkflow")'
)
& $SlicerExecutable @SlicerArguments
exit $LASTEXITCODE
