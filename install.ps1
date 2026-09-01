# Confuser Obfuser installer for Windows 10/11.
[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\ConfuserObfuser",
    [string]$UserBin = "$env:LOCALAPPDATA\ConfuserObfuser\bin"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot

function Write-Step([string]$Message) {
    Write-Host $Message -ForegroundColor Cyan
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"

    $knownToolDirectories = @(
        "$env:ProgramFiles\LLVM\bin",
        "$env:ProgramFiles\Go\bin",
        "$env:LOCALAPPDATA\Programs\Python\Launcher"
    )
    foreach ($directory in $knownToolDirectories) {
        if ((Test-Path $directory) -and ($env:Path -notlike "*$directory*")) {
            $env:Path = "$directory;$env:Path"
        }
    }
}

function Find-CompatiblePython {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($version in @("-3.14", "-3.13", "-3.12", "-3.11", "-3.10")) {
            $result = & $launcher.Source $version -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $result) {
                return $result.Trim()
            }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $result = & $python.Source -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $result) {
            return $result.Trim()
        }
    }

    $installed = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($installed) {
        $result = & $installed.FullName -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $result) {
            return $result.Trim()
        }
    }
    return $null
}

function Install-WingetPackage([string]$PackageId, [string]$DisplayName) {
    Write-Step "$DisplayName kuruluyor..."
    & winget install --id $PackageId --exact --source winget --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "$DisplayName kurulamadı. Winget çıkış kodu: $LASTEXITCODE"
    }
    Refresh-ProcessPath
}

function Test-CCompiler {
    $probeDirectory = Join-Path ([IO.Path]::GetTempPath()) ("confuser-c-probe-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $probeDirectory | Out-Null
    $probeSource = Join-Path $probeDirectory "probe.c"
    $probeBinary = Join-Path $probeDirectory "probe.exe"
    [IO.File]::WriteAllText($probeSource, "int main(void) { return 0; }", [Text.Encoding]::ASCII)
    & clang $probeSource -o $probeBinary 2>$null
    return ($LASTEXITCODE -eq 0 -and (Test-Path $probeBinary))
}

function Install-WindowsCBuildTools {
    Write-Step "Windows C SDK ve linker bileşenleri kuruluyor..."
    $installerOptions = "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
    & winget install --id "Microsoft.VisualStudio.2022.BuildTools" --exact --source winget --accept-package-agreements --accept-source-agreements --override $installerOptions
    if ($LASTEXITCODE -ne 0) {
        throw "Visual Studio C++ Build Tools kurulamadı. Winget çıkış kodu: $LASTEXITCODE"
    }
    Refresh-ProcessPath
}

Write-Step "Confuser Obfuser Windows kurulumu başlıyor..."

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "Winget bulunamadı. Microsoft App Installer'ı güncelleyip install.ps1 dosyasını yeniden çalıştırın."
}

$pythonExe = Find-CompatiblePython
if (-not $pythonExe) {
    Install-WingetPackage "Python.Python.3.12" "Python 3.12"
    $pythonExe = Find-CompatiblePython
}
if (-not $pythonExe) {
    throw "Python 3.10 veya daha yeni bir sürüm bulunamadı."
}

if (-not (Get-Command clang -ErrorAction SilentlyContinue)) {
    Install-WingetPackage "LLVM.LLVM" "LLVM/Clang"
}
if (-not (Get-Command go -ErrorAction SilentlyContinue)) {
    Install-WingetPackage "GoLang.Go" "Go toolchain"
}

Refresh-ProcessPath
foreach ($tool in @("clang", "go")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool kurulumdan sonra PATH içinde bulunamadı. Yeni bir PowerShell açıp install.ps1 dosyasını yeniden çalıştırın."
    }
}

if (-not (Test-CCompiler)) {
    Install-WindowsCBuildTools
    if (-not (Test-CCompiler)) {
        throw "Clang basit bir C programını derleyemedi. Windows yeniden başlatıldıktan sonra install.ps1 dosyasını tekrar çalıştırın."
    }
}

Write-Step "İzole uygulama ortamı hazırlanıyor..."
New-Item -ItemType Directory -Force -Path $InstallRoot, $UserBin | Out-Null
& $pythonExe -m venv "$InstallRoot\venv"
$venvPython = "$InstallRoot\venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install --upgrade $ProjectDir

$entryPoint = "$InstallRoot\venv\Scripts\confuser-obfuser.exe"
if (-not (Test-Path $entryPoint)) {
    throw "confuser-obfuser giriş komutu oluşturulamadı."
}

$wrapper = "$UserBin\confuser-obfuser.cmd"
$wrapperContent = "@echo off`r`n`"$entryPoint`" %*`r`n"
[IO.File]::WriteAllText($wrapper, $wrapperContent, [Text.UTF8Encoding]::new($false))

$currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$userSegments = @($currentUserPath -split ";" | Where-Object { $_ })
$requiredUserDirectories = @(
    $UserBin,
    (Split-Path (Get-Command clang).Source -Parent),
    (Split-Path (Get-Command go).Source -Parent)
)
foreach ($directory in $requiredUserDirectories) {
    if ($userSegments -notcontains $directory) {
        $userSegments = @($directory) + $userSegments
    }
}
[Environment]::SetEnvironmentVariable("Path", ($userSegments -join ";"), "User")
$env:Path = "$UserBin;$env:Path"

$checkDirectory = Join-Path ([IO.Path]::GetTempPath()) ("confuser-check-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $checkDirectory | Out-Null

Write-Step "Python motoru kontrol ediliyor..."
& $wrapper "$ProjectDir\examples\demo.py" -o "$checkDirectory\demo.obf.py" --seed 42 --validate
if ($LASTEXITCODE -ne 0) { throw "Python motor kontrolü başarısız." }

Write-Step "C/Clang AST motoru kontrol ediliyor..."
$env:CC = (Get-Command clang).Source
$env:CLANG = (Get-Command clang).Source
& $wrapper "$ProjectDir\examples\demo.c" -o "$checkDirectory\demo.obf.c" --seed 42 --validate
if ($LASTEXITCODE -ne 0) { throw "C motor kontrolü başarısız." }

Write-Step "Go AST motoru kontrol ediliyor..."
& $wrapper "$ProjectDir\examples\demo.go" -o "$checkDirectory\demo.obf.go" --seed 42 --validate
if ($LASTEXITCODE -ne 0) { throw "Go motor kontrolü başarısız." }

Write-Host ""
Write-Host "✓ Confuser Obfuser kuruldu ve üç motor doğrulandı." -ForegroundColor Green
Write-Host "Yeni bir PowerShell veya CMD açıp çalıştırın: confuser-obfuser"
