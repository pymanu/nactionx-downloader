# Compila NactionX Downloader para Windows: carpeta portable + ZIP + instalador.
# Usa el Python oficial firmado para que funcione con Smart App Control de Windows 11.
# Los archivos pesados van a %USERPROFILE%\.nactionx-dev, fuera de OneDrive.
# Uso: powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 [-SkipTests]
param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Dev = Join-Path $env:USERPROFILE '.nactionx-dev'
$Venv = Join-Path $Dev 'venv'
$Py = Join-Path $Venv 'Scripts\python.exe'
New-Item -ItemType Directory -Force $Dev | Out-Null
Set-Location $Root

if (-not (Test-Path $Py)) {
    Write-Host '== Creando entorno de compilación (Python 3.13)'
    py -3.13 -m venv $Venv
    if ($LASTEXITCODE) { python -m venv $Venv }
}
& $Py -m pip install --upgrade pip --quiet
& $Py -m pip install -r requirements-build.txt --quiet
if ($LASTEXITCODE) { throw 'No se pudieron instalar las dependencias' }

Write-Host '== Iconos'
& $Py packaging\make_icons.py
if ($LASTEXITCODE) { throw 'Fallaron los iconos' }

if (-not $SkipTests) {
    Write-Host '== Tests'
    & $Py -m pytest tests -q -p no:cacheprovider
    if ($LASTEXITCODE) { throw 'Los tests fallaron' }
}

Write-Host '== Distribución portable'
& $Py packaging\build_windows_portable.py --work $Dev --zip
if ($LASTEXITCODE) { throw 'Falló la distribución portable' }

$Version = & $Py -c "import nactionx; print(nactionx.__version__)"
$Iscc = @(
    (Join-Path $Dev 'innosetup\ISCC.exe'),
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) {
    Write-Warning 'No se encontró Inno Setup 6: se omite el instalador (el ZIP portable sí está en releases\).'
    exit 0
}
Write-Host '== Instalador'
& $Iscc "/DAppVersion=$Version" "/DSourceDir=$(Join-Path $Dev 'portable\NactionX Downloader')" "/DOutputDir=$(Join-Path $Root 'releases')" packaging\windows\installer.iss
if ($LASTEXITCODE) { throw 'Falló Inno Setup' }
Write-Host "Listo: $(Join-Path $Root 'releases')"
