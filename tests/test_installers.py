from __future__ import annotations

import subprocess
import sys
import os
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Run the real local-copy/launcher path, with system discovery isolated. No VM,
# tool installation, or persistent PATH change is needed for these regressions.
WINDOWS_LOCAL_TEST = r'''
param([string]$InstallerPath, [string]$PythonPath, [string]$TestRoot, [switch]$DenyTools)
$ErrorActionPreference = 'Stop'
$savedUserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$env:CONFUSER_TEST_SOURCE = Split-Path $InstallerPath -Parent
$env:CONFUSER_TEST_PYTHON = $PythonPath
$source = Get-Content -Raw -Encoding UTF8 $InstallerPath
$source = $source.Replace('$ProjectDir = $PSScriptRoot', '$ProjectDir = $env:CONFUSER_TEST_SOURCE')
$overrides = @'
function Find-CompatiblePython { return $env:CONFUSER_TEST_PYTHON }
function Refresh-ProcessPath { }
function Get-Command { param($Name, $ErrorAction) return $null }
function Install-WingetPackage { throw 'UNEXPECTED DOWNLOAD' }
function Install-WindowsCBuildTools { throw 'UNEXPECTED DOWNLOAD' }
function Ensure-Winget { throw 'UNEXPECTED DOWNLOAD' }
function Read-Host { param($Prompt) return 'HAYIR' }
'@
$marker = 'Write-Step "Confuser Obfuser Windows kurulumu basliyor..."'
if (-not $source.Contains($marker)) { throw 'Test injection point missing' }
$source = $source.Replace($marker, $overrides + "`n" + $marker)
$app = Join-Path $TestRoot 'app'
$bin = Join-Path $TestRoot 'bin'
try {
    if ($DenyTools) {
        try {
            & ([scriptblock]::Create($source)) -InstallRoot $app -UserBin $bin -InstallTools
            throw 'Unconfirmed installation was accepted'
        } catch {
            if ($_.Exception.Message -notlike '*Iptal edildi; arac indirilmedi*') { throw }
        }
        if (Test-Path $app) { throw 'App was modified after rejected confirmation' }
    } else {
        & ([scriptblock]::Create($source)) -InstallRoot $app -UserBin $bin
        foreach ($name in @('confuser', 'confuser-obfuser')) {
            & (Join-Path $bin ($name + '.cmd')) --help
            if ($LASTEXITCODE -ne 0) { throw 'Installed launcher failed' }
        }
    }
} finally {
    [Environment]::SetEnvironmentVariable('Path', $savedUserPath, 'User')
}
Write-Output 'WINDOWS_LOCAL_INSTALL_TEST_PASSED'
'''

# Load only function definitions: never install packages or change the user's PATH.
HELPER_TEST = r'''
param([string]$InstallerPath, [string]$PythonPath, [string]$Case)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$tokens = $null
$parseErrors = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile($InstallerPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Installer syntax error' }
foreach ($definition in $tree.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    . ([scriptblock]::Create($definition.Extent.Text))
}
switch ($Case) {
    'python-launcher-enumeration' {
        function Get-Command {
            param($Name, $ErrorAction)
            if ($Name -eq 'py') { [pscustomobject]@{ Source = 'TestLauncher' } }
        }
        function TestLauncher {
            if ($args.Count -ne 1 -or $args[0] -ne '-0p') { throw 'Launcher requested a runtime instead of listing installations' }
            " -V:3.14 * $PythonPath"
            $global:LASTEXITCODE = 0
        }
        if ((Find-CompatiblePython) -ne $PythonPath) { throw 'Installed launcher runtime was missed' }
    }
    'python-fallback' {
        function Get-Command { param($Name, $ErrorAction) $null }
        function Get-ChildItem {
            param($Path, $Filter, [switch]$Recurse, $ErrorAction)
            [pscustomobject]@{ FullName = 'TestPython39' }
            [pscustomobject]@{ FullName = 'TestPython312' }
        }
        function TestPython39 { $global:LASTEXITCODE = 1 }
        function TestPython312 { $global:LASTEXITCODE = 0; 'C:\Python312\python.exe' }
        if ((Find-CompatiblePython) -ne 'C:\Python312\python.exe') { throw 'Compatible Python was missed' }
    }
    'compiler-warning' {
        function clang {
            & $PythonPath -c 'import sys; open(sys.argv[1], chr(119)+chr(98)).close(); print(123, file=sys.stderr)' $args[2]
        }
        if (-not (Test-CCompiler)) { throw 'A native warning rejected a successful compile' }
    }
    'compiler-failure' {
        function clang {
            & $PythonPath -c 'import sys; open(sys.argv[1], chr(119)+chr(98)).close(); sys.exit(2)' $args[2]
        }
        if (Test-CCompiler) { throw 'A failed compiler was accepted' }
    }
    { $_ -in @('build-tools-arm64', 'build-tools-x64') } {
        function Test-Path { param($Path) $false }
        function Ensure-Winget { }
        function Refresh-ProcessPath { }
        function Write-Step { }
        function winget { $script:installerArguments = $args -join ' '; $global:LASTEXITCODE = 0 }
        $env:PROCESSOR_ARCHITECTURE = 'AMD64'
        $env:PROCESSOR_ARCHITEW6432 = ''
        if ($Case -eq 'build-tools-arm64') { $env:PROCESSOR_ARCHITEW6432 = 'ARM64' }
        Install-WindowsCBuildTools
        if ($installerArguments -notlike '*--norestart*') { throw 'Installer could restart Windows unexpectedly' }
        if ($Case -eq 'build-tools-arm64' -and $installerArguments -notlike '*Microsoft.VisualStudio.Component.VC.Tools.ARM64*') {
            throw 'ARM64 components missing'
        }
        if ($Case -eq 'build-tools-x64' -and $installerArguments -like '*Microsoft.VisualStudio.Component.VC.Tools.ARM64*') {
            throw 'Unnecessary ARM64 components requested on x64'
        }
    }
    default { throw 'Unknown test case' }
}
if ($ErrorActionPreference -ne 'Stop') { throw 'Caller error handling changed' }
Write-Output 'INSTALLER_HELPER_TEST_PASSED'
'''


def check_windows_installer_helpers(tmp_path: Path, case: str) -> None:
    script = tmp_path / "helpers.ps1"
    script.write_text(HELPER_TEST, encoding="utf-8")
    installer = Path(__file__).resolve().parents[1] / "install.ps1"
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(script), "-InstallerPath", str(installer),
            "-PythonPath", sys.executable, "-Case", case,
        ],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "INSTALLER_HELPER_TEST_PASSED" in result.stdout


class InstallerTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell tests")
    def test_windows_default_install_and_rejected_tool_consent(self) -> None:
        for deny_tools in (False, True):
            with self.subTest(deny_tools=deny_tools), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                driver = root / "local-test.ps1"
                driver.write_text(WINDOWS_LOCAL_TEST, encoding="ascii")
                command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(driver),
                           "-InstallerPath", str(ROOT / "install.ps1"), "-PythonPath", sys.executable,
                           "-TestRoot", str(root / "spaces & Türkçe ! % path")]
                if deny_tools:
                    command.append("-DenyTools")
                result = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("WINDOWS_LOCAL_INSTALL_TEST_PASSED", result.stdout)

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell tests")
    def test_windows_helpers(self) -> None:
        for case in ("python-launcher-enumeration", "python-fallback", "compiler-warning", "compiler-failure", "build-tools-arm64", "build-tools-x64"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                check_windows_installer_helpers(Path(directory), case)

    def test_windows_installer_is_ascii_for_powershell_51(self) -> None:
        (ROOT / "install.ps1").read_bytes().decode("ascii")

    @unittest.skipIf(os.name == "nt", "POSIX shell tests")
    def test_posix_install_without_compilers_or_package_downloads(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-installer-") as directory:
            root = Path(directory)
            tools = root / "tools"
            tools.mkdir()
            # No package manager, pip, curl, C or Go toolchain is available.
            for name in ("sh", "dirname", "uname", "mkdir", "mktemp", "rm"):
                (tools / name).symlink_to(shutil.which(name))
            (tools / "python3").symlink_to(sys.executable)
            app = root / "app with spaces and 'quotes'"
            user_bin = root / "bin with spaces and 'quotes'"
            environment = os.environ.copy()
            environment.update(PATH=os.pathsep.join((str(user_bin), str(tools))),
                               CONFUSER_INSTALL_ROOT=str(app), CONFUSER_USER_BIN=str(user_bin))
            for attempt in range(2):
                with self.subTest(attempt=attempt):
                    result = subprocess.run([str(tools / "sh"), str(ROOT / "install.sh")],
                                            env=environment, capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("clang bulunamadı", result.stdout)
                    self.assertIn("go bulunamadı", result.stdout)
                    self.assertIn("Python doğrulandı", result.stdout)
                    self.assertIn("go_ast_helper/main.go", "\n".join(str(p) for p in app.rglob("main.go")))
                    for command in ("confuser", "confuser-obfuser"):
                        help_result = subprocess.run([str(user_bin / command), "--help"], env=environment,
                                                     capture_output=True, text=True, timeout=15)
                        self.assertEqual(help_result.returncode, 0, help_result.stderr)
                        self.assertIn("usage: confuser", help_result.stdout)

    @unittest.skipIf(os.name == "nt", "POSIX shell tests")
    def test_posix_missing_python_does_not_install_tools(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-installer-") as directory:
            tools = Path(directory)
            for name in ("sh", "dirname", "uname"):
                (tools / name).symlink_to(shutil.which(name))
            environment = os.environ.copy()
            environment["PATH"] = str(tools)
            result = subprocess.run([str(tools / "sh"), str(ROOT / "install.sh")], env=environment,
                                    capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Python 3.10+ gerekiyor", result.stdout)
            self.assertIn("Araç indirilmedi", result.stdout)

    @unittest.skipIf(os.name == "nt", "POSIX shell tests")
    def test_posix_optional_install_fails_closed_without_confirmation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-installer-") as directory:
            tools = Path(directory)
            for name in ("sh", "dirname", "uname"):
                (tools / name).symlink_to(shutil.which(name))
            environment = os.environ.copy()
            environment["PATH"] = str(tools)
            result = subprocess.run([str(tools / "sh"), str(ROOT / "install.sh"), "--install-tools"],
                                    env=environment, start_new_session=True, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("GB", result.stdout)
            self.assertIn("Onay alınamadı; araç indirilmedi", result.stdout)
