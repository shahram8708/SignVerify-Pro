$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python virtual environment not found at .venv\Scripts\python.exe"
}

$specFile = Join-Path $projectRoot "SignVerifyPro.spec"
if (-not (Test-Path $specFile)) {
    throw "Spec file not found: $specFile"
}

Write-Host "Cleaning old build output"
foreach ($folderName in @("build", "dist", "__pycache__")) {
    $folderPath = Join-Path $projectRoot $folderName
    if (Test-Path $folderPath) {
        Remove-Item -LiteralPath $folderPath -Recurse -Force
    }
}

Write-Host "Building SignVerify Pro executable"
& $pythonExe -m PyInstaller --noconfirm --clean $specFile
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

$exePath = Join-Path $projectRoot "dist\SignVerifyPro\SignVerifyPro.exe"
if (-not (Test-Path $exePath)) {
    throw "Build completed but executable was not found at $exePath"
}

Write-Host "Build successful"
Write-Host "Executable path: $exePath"
