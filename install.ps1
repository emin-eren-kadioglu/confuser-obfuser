# Confuser Obfuser installer for Windows 10/11.
[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\ConfuserObfuser",
    [string]$UserBin = "$env:LOCALAPPDATA\ConfuserObfuser\bin",
    [switch]$FromGitHub
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot

if ($FromGitHub) {
    $sourceTemp = Join-Path ([IO.Path]::GetTempPath()) ("confuser-source-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $sourceTemp | Out-Null
    try {
        $archive = Join-Path $sourceTemp "source.zip"
        Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/emin-eren-kadioglu/confuser-obfuser/archive/refs/heads/main.zip" -OutFile $archive
        Expand-Archive -LiteralPath $archive -DestinationPath $sourceTemp
        & powershell -NoProfile -ExecutionPolicy Bypass -File "$sourceTemp\confuser-obfuser-main\install.ps1" -InstallRoot $InstallRoot -UserBin $UserBin
        if ($LASTEXITCODE -ne 0) { throw "Kurulum tamamlanamadi (cikis kodu: $LASTEXITCODE)." }
        $env:Path = "$UserBin;$env:Path;$([Environment]::GetEnvironmentVariable('Path', 'User'));$([Environment]::GetEnvironmentVariable('Path', 'Machine'))"
    } finally {
        Remove-Item -LiteralPath $sourceTemp -Recurse -Force
    }
    return
}

function Write-Step([string]$Message) {
    Write-Host $Message -ForegroundColor Cyan
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$env:Path;$machinePath;$userPath"

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
            try {
                $result = & $launcher.Source $version -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $result) {
                    return $result.Trim()
                }
            } catch { continue }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        try {
            $result = & $python.Source -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $result) {
                return $result.Trim()
            }
        } catch { }
    }

    $installed = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($installed) {
        try {
            $result = & $installed.FullName -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $result) {
                return $result.Trim()
            }
        } catch { }
    }
    return $null
}

function Install-WingetPackage([string]$PackageId, [string]$DisplayName) {
    Ensure-Winget
    Write-Step "$DisplayName kuruluyor..."
    & winget install --id $PackageId --exact --source winget --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "$DisplayName kurulamadi. Winget cikis kodu: $LASTEXITCODE"
    }
    Refresh-ProcessPath
}

function Test-CCompiler {
    $probeDirectory = Join-Path ([IO.Path]::GetTempPath()) ("confuser-c-probe-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $probeDirectory | Out-Null
    $probeSource = Join-Path $probeDirectory "probe.c"
    $probeBinary = Join-Path $probeDirectory "probe.exe"
    [IO.File]::WriteAllText($probeSource, "#include <stdio.h>`nint main(void) { puts(`"ok`"); return 0; }", [Text.Encoding]::ASCII)
    try {
        & clang $probeSource -o $probeBinary 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0 -and (Test-Path $probeBinary))
    } catch {
        return $false
    } finally {
        Remove-Item -LiteralPath $probeDirectory -Recurse -Force
    }
}

function Install-WindowsCBuildTools {
    Ensure-Winget
    Write-Step "Windows C SDK ve linker bilesenleri kuruluyor..."
    $installerOptions = "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
    & winget install --id "Microsoft.VisualStudio.2022.BuildTools" --exact --source winget --accept-package-agreements --accept-source-agreements --override $installerOptions
    if ($LASTEXITCODE -ne 0) {
        throw "Visual Studio C++ Build Tools kurulamadi. Winget cikis kodu: $LASTEXITCODE"
    }
    Refresh-ProcessPath
}

function Ensure-Winget {
    if (Get-Command winget -ErrorAction SilentlyContinue) { return }
    Write-Step "Winget kuruluyor..."
    Install-PackageProvider -Name NuGet -Force -Scope CurrentUser | Out-Null
    Install-Module -Name Microsoft.WinGet.Client -Repository PSGallery -Force -Scope CurrentUser
    Import-Module Microsoft.WinGet.Client
    Repair-WinGetPackageManager -Latest
    Refresh-ProcessPath
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Winget kurulamadi. Windows App Installer'i kontrol edip ayni kurulum komutunu yeniden calistirin."
    }
}

Write-Step "Confuser Obfuser Windows kurulumu basliyor..."

Refresh-ProcessPath
$pythonExe = Find-CompatiblePython
if (-not $pythonExe) {
    Install-WingetPackage "Python.Python.3.12" "Python 3.12"
    $pythonExe = Find-CompatiblePython
}
if (-not $pythonExe) {
    throw "Python 3.10 veya daha yeni bir surum bulunamadi."
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
        throw "$tool kurulumdan sonra PATH icinde bulunamadi. Yeni bir PowerShell acip install.ps1 dosyasini yeniden calistirin."
    }
}

if (-not (Test-CCompiler)) {
    Install-WindowsCBuildTools
    if (-not (Test-CCompiler)) {
        throw "Clang basit bir C programini derleyemedi. Windows yeniden baslatildiktan sonra install.ps1 dosyasini tekrar calistirin."
    }
}

Write-Step "Izole uygulama ortami hazirlaniyor..."
New-Item -ItemType Directory -Force -Path $InstallRoot, $UserBin | Out-Null
& $pythonExe -m venv "$InstallRoot\venv"
if ($LASTEXITCODE -ne 0) { throw "Python sanal ortami olusturulamadi." }
$venvPython = "$InstallRoot\venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Pip hazirlanamadi." }
& $venvPython -m pip install --upgrade $ProjectDir
if ($LASTEXITCODE -ne 0) { throw "Uygulama paketi kurulamadi." }

$entryPoint = "$InstallRoot\venv\Scripts\confuser.exe"
if (-not (Test-Path $entryPoint)) {
    throw "confuser giris komutu olusturulamadi."
}

$wrapper = "$UserBin\confuser.cmd"
$wrapperContent = "@echo off`r`n`"$entryPoint`" %*`r`n"
[IO.File]::WriteAllText($wrapper, $wrapperContent, [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText("$UserBin\confuser-obfuser.cmd", $wrapperContent, [Text.UTF8Encoding]::new($false))

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

try {
    Write-Step "Python motoru kontrol ediliyor..."
    & $wrapper "$ProjectDir\examples\demo.py" -o "$checkDirectory\demo.obf.py" --seed 42 --validate
    if ($LASTEXITCODE -ne 0) { throw "Python motor kontrolu basarisiz." }

    Write-Step "C/Clang AST motoru kontrol ediliyor..."
    $env:CC = (Get-Command clang).Source
    $env:CLANG = (Get-Command clang).Source
    & $wrapper "$ProjectDir\examples\demo.c" -o "$checkDirectory\demo.obf.c" --seed 42 --validate
    if ($LASTEXITCODE -ne 0) { throw "C motor kontrolu basarisiz." }

    Write-Step "Go AST motoru kontrol ediliyor..."
    & $wrapper "$ProjectDir\examples\demo.go" -o "$checkDirectory\demo.obf.go" --seed 42 --validate
    if ($LASTEXITCODE -ne 0) { throw "Go motor kontrolu basarisiz." }
} finally {
    Remove-Item -LiteralPath $checkDirectory -Recurse -Force
}

Write-Host ""
Write-Host "OK - Confuser Obfuser kuruldu ve uc motor dogrulandi." -ForegroundColor Green
Write-Host "Baslatmak icin: confuser"
