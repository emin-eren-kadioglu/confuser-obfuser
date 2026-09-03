# Confuser Obfuser installer for Windows 10/11.
[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\ConfuserObfuser",
    [string]$UserBin = "$env:LOCALAPPDATA\ConfuserObfuser\bin",
    [switch]$FromGitHub,
    [switch]$InstallTools
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
        $options = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "$sourceTemp\confuser-obfuser-main\install.ps1", "-InstallRoot", $InstallRoot, "-UserBin", $UserBin)
        if ($InstallTools) { $options += "-InstallTools" }
        & powershell @options
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
        # Enumerate installed runtimes; requesting absent versions can trigger downloads.
        $installedPaths = @()
        try { $installedPaths = @(& $launcher.Source -0p 2>$null) } catch { }
        foreach ($line in $installedPaths) {
            if ("$line" -notmatch '(?i)([a-z]:\\.*python(?:3(?:\.\d+)?)?\.exe)\s*$') { continue }
            $candidate = $Matches[1]
            try {
                $result = & $candidate -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $result) {
                    return $result.Trim()
                }
            } catch { continue }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and $python.Source -notlike '*\Microsoft\WindowsApps\*') {
        try {
            $result = & $python.Source -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $result) {
                return $result.Trim()
            }
        } catch { }
    }

    $candidates = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
    # Directory names are not version numbers (Python39 sorts above Python312).
    foreach ($installed in $candidates) {
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
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 treats native stderr warnings as error records.
        # The process exit code and generated executable determine success.
        $ErrorActionPreference = "Continue"
        & clang $probeSource -o $probeBinary 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0 -and (Test-Path $probeBinary))
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Remove-Item -LiteralPath $probeDirectory -Recurse -Force
    }
}

function Install-WindowsCBuildTools {
    Write-Step "Windows C SDK ve linker bilesenleri kuruluyor..."
    $installerOptions = "--passive --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
    if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64" -or $env:PROCESSOR_ARCHITEW6432 -eq "ARM64") {
        $installerOptions += " --add Microsoft.VisualStudio.Component.VC.Tools.ARM64"
    }

    # An existing Build Tools installation can still be missing the C workload
    # or ARM64 libraries. WinGet install alone will not add those components.
    $setup = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\setup.exe"
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    $buildToolsPath = $null
    if ((Test-Path $setup) -and (Test-Path $vswhere)) {
        $buildToolsPath = & $vswhere -latest -products Microsoft.VisualStudio.Product.BuildTools -property installationPath
    }
    if ($buildToolsPath) {
        $arguments = 'modify --installPath "' + $buildToolsPath.Trim() + '" ' + $installerOptions
        $process = Start-Process -FilePath $setup -ArgumentList $arguments -Wait -PassThru
        if ($process.ExitCode -notin @(0, 3010)) {
            throw "Visual Studio C++ bilesenleri tamamlanamadi (cikis kodu: $($process.ExitCode))."
        }
        if ($process.ExitCode -eq 3010) {
            Write-Warning "Windows C araclari icin yeniden baslatma gerekebilir. Motorlar simdi kontrol edilecek."
        }
    } else {
        Ensure-Winget
        & winget install --id "Microsoft.VisualStudio.2022.BuildTools" --exact --source winget --accept-package-agreements --accept-source-agreements --override ("--wait " + $installerOptions)
        if ($LASTEXITCODE -ne 0) {
            throw "Visual Studio C++ Build Tools kurulamadi. Winget cikis kodu: $LASTEXITCODE"
        }
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

if ($InstallTools) {
    Write-Warning "Istege bagli Python/Clang/Go kurulumu yuzlerce MB; Windows C++ SDK/Build Tools birkac GB indirebilir."
    Write-Warning "Eksik WinGet de kurulabilir. Yonetici onayi veya yeniden baslatma gerekebilir."
    if ((Read-Host "Indirmeye izin vermek icin EVET yazin (diger yanitlar iptal eder)") -cne "EVET") {
        throw "Iptal edildi; arac indirilmedi."
    }
}

Refresh-ProcessPath
$pythonExe = Find-CompatiblePython
if (-not $pythonExe -and $InstallTools) {
    Install-WingetPackage "Python.Python.3.12" "Python 3.12"
    $pythonExe = Find-CompatiblePython
}
if (-not $pythonExe) {
    throw "Python 3.10+ gerekiyor. Arac indirilmedi. Python kurun veya -InstallTools ile onayli kurulumu secin."
}

if ($InstallTools -and -not (Get-Command clang -ErrorAction SilentlyContinue)) {
    Install-WingetPackage "LLVM.LLVM" "LLVM/Clang"
}
if ($InstallTools -and -not (Get-Command go -ErrorAction SilentlyContinue)) {
    Install-WingetPackage "GoLang.Go" "Go toolchain"
}

Refresh-ProcessPath
if ($InstallTools -and (Get-Command clang -ErrorAction SilentlyContinue) -and -not (Test-CCompiler)) {
    Install-WindowsCBuildTools
    if (-not (Test-CCompiler)) {
        throw "Clang basit bir C programini derleyemedi. Windows yeniden baslatildiktan sonra install.ps1 dosyasini tekrar calistirin."
    }
}

Write-Step "Uygulama hazirlaniyor (pip veya ek Python paketi indirilmez)..."
New-Item -ItemType Directory -Force -Path $InstallRoot, $UserBin | Out-Null
$releaseDirectory = Join-Path $InstallRoot ("app." + [Guid]::NewGuid().ToString("N"))
$copyCode = @'
import shutil, sys
from pathlib import Path
source, target = map(Path, sys.argv[1:])
target.mkdir()
shutil.copytree(source / 'obfuscator', target / 'obfuscator', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
shutil.copy2(source / 'confuser_obfuser.py', target)
shutil.copy2(source / 'LICENSE', target)
'@
& $pythonExe -c $copyCode $ProjectDir $releaseDirectory
if ($LASTEXITCODE -ne 0) { throw "Uygulama kopyalanamadi." }
$entryPoint = Join-Path $releaseDirectory "confuser_obfuser.py"

$checkDirectory = Join-Path ([IO.Path]::GetTempPath()) ("confuser-check-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $checkDirectory | Out-Null

try {
    Write-Step "Python motoru kontrol ediliyor..."
    & $pythonExe $entryPoint "$ProjectDir\examples\demo.py" -o "$checkDirectory\demo.obf.py" --seed 42 --validate
    if ($LASTEXITCODE -ne 0) { throw "Python motor kontrolu basarisiz." }

    foreach ($language in @("c", "go")) {
        $tool = "clang"
        if ($language -eq "go") { $tool = "go" }
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            Write-Warning "$tool bulunamadi; $language kontrolu atlandi. Python kullanilabilir; arac kurulmadi."
            continue
        }
        Write-Step "$language AST motoru kontrol ediliyor..."
        # Native diagnostics in Windows PowerShell 5.1 must not override exit status.
        $previousPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $pythonExe $entryPoint "$ProjectDir\examples\demo.$language" -o "$checkDirectory\demo.obf.$language" --seed 42 --validate --timeout 60
            if ($LASTEXITCODE -eq 0) { Write-Host "$language motoru dogrulandi." -ForegroundColor Green }
            else { Write-Warning "$language kontrolu gecmedi; araclari/SDK'yi kontrol edin. Otomatik indirme yapilmadi." }
        } finally { $ErrorActionPreference = $previousPreference }
    }
} finally {
    Remove-Item -LiteralPath $checkDirectory -Recurse -Force
}

# Switch launchers only after the required Python check has succeeded.
# Escape percent signs for CMD; quoted paths support spaces and ampersands.
$cmdPython = $pythonExe.Replace('%', '%%')
$cmdEntryPoint = $entryPoint.Replace('%', '%%')
$wrapperContent = @"
@echo off
setlocal DisableDelayedExpansion
for /f "tokens=2 delims=:" %%c in ('chcp') do set "confuserCodePage=%%c"
chcp 65001 >nul
"$cmdPython" "$cmdEntryPoint" %*
set "confuserExitCode=%errorlevel%"
chcp %confuserCodePage% >nul
exit /b %confuserExitCode%
"@
foreach ($name in @("confuser", "confuser-obfuser")) {
    [IO.File]::WriteAllText("$UserBin\$name.cmd", $wrapperContent, [Text.UTF8Encoding]::new($false))
}
$currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$userSegments = @($currentUserPath -split ";" | Where-Object { $_ })
$requiredUserDirectories = @($UserBin)
foreach ($tool in @("clang", "go")) {
    $foundTool = Get-Command $tool -ErrorAction SilentlyContinue
    if ($foundTool) { $requiredUserDirectories += Split-Path $foundTool.Source -Parent }
}
foreach ($directory in $requiredUserDirectories) {
    if ($userSegments -notcontains $directory) { $userSegments = @($directory) + $userSegments }
}
[Environment]::SetEnvironmentVariable("Path", ($userSegments -join ";"), "User")
$env:Path = "$UserBin;$env:Path"

Write-Host ""
Write-Host "OK - Confuser Obfuser kuruldu; Python dogrulandi. C/Go durumu yukarida ayri gosterildi." -ForegroundColor Green
Write-Host "Baslatmak icin: confuser"
