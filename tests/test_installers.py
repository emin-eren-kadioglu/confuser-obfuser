from __future__ import annotations

import subprocess
import sys
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Run the real local-copy/launcher path, with system discovery isolated. No VM,
# tool installation, or persistent PATH change is needed for these regressions.
WINDOWS_LOCAL_TEST = r'''
param([string]$InstallerPath, [string]$PythonPath, [string]$TestRoot, [string]$Case)
$ErrorActionPreference = 'Stop'
$savedUserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$env:CONFUSER_TEST_SOURCE = Split-Path $InstallerPath -Parent
$env:CONFUSER_TEST_PYTHON = $PythonPath
$env:CONFUSER_TEST_CASE = $Case
$global:ConfuserTestPrompts = @()
$global:ConfuserTestDownloads = @()
$source = Get-Content -Raw -Encoding UTF8 $InstallerPath
$source = $source.Replace('$ProjectDir = $PSScriptRoot', '$ProjectDir = $env:CONFUSER_TEST_SOURCE')
$overrides = @'
function Find-CompatiblePython { return $env:CONFUSER_TEST_PYTHON }
function Refresh-ProcessPath { }
function Get-Command {
    param($Name, $ErrorAction)
    if ($env:CONFUSER_TEST_CASE -like 'sdk-*' -and $Name -in @('clang', 'go')) {
        return [pscustomobject]@{ Source = "C:\mock\$Name.exe" }
    }
    return $null
}
function Test-CCompiler { return $false }
function Install-WingetPackage {
    param($PackageId, $DisplayName)
    $global:ConfuserTestDownloads += $PackageId
}
function Install-WindowsCBuildTools { $global:ConfuserTestDownloads += 'SDK' }
function Ensure-Winget { $global:ConfuserTestDownloads += 'UNEXPECTED WINGET' }
function Test-InteractiveInput { return ($env:CONFUSER_TEST_CASE -ne 'no-console') }
function Read-Host {
    param($Prompt)
    $global:ConfuserTestPrompts += $Prompt
    if ($env:CONFUSER_TEST_CASE -eq 'clang' -and $Prompt -like '*clang?*') { return 'y' }
    if ($env:CONFUSER_TEST_CASE -eq 'go' -and $Prompt -like '*go?*') { return 'yes' }
    if ($env:CONFUSER_TEST_CASE -eq 'sdk-approve' -and $Prompt -like '*Build Tools/SDK?*') { return 'y' }
    if ($env:CONFUSER_TEST_CASE -eq 'blank') { return '' }
    return 'n'
}
'@
$marker = 'Write-Step "Starting Confuser Obfuser setup for Windows..."'
if (-not $source.Contains($marker)) { throw 'Test injection point missing' }
$source = $source.Replace($marker, $overrides + "`n" + $marker)
$app = Join-Path $TestRoot 'app'
$bin = Join-Path $TestRoot 'bin'
try {
    $options = @{ InstallRoot = $app; UserBin = $bin }
    if ($Case -eq 'skip') { $options.SkipTools = $true }
    & ([scriptblock]::Create($source)) @options
    foreach ($name in @('confuser', 'confuser-obfuser')) {
        & (Join-Path $bin ($name + '.cmd')) --help
        if ($LASTEXITCODE -ne 0) { throw 'Installed launcher failed' }
    }
    $expectedPrompts = 2
    if ($Case -in @('skip', 'no-console')) { $expectedPrompts = 0 }
    if ($Case -like 'sdk-*') { $expectedPrompts = 1 }
    if ($ConfuserTestPrompts.Count -ne $expectedPrompts) { throw 'Unexpected prompt count' }
    $expectedDownloads = ''
    if ($Case -eq 'clang') { $expectedDownloads = 'LLVM.LLVM' }
    if ($Case -eq 'go') { $expectedDownloads = 'GoLang.Go' }
    if ($Case -eq 'sdk-approve') { $expectedDownloads = 'SDK' }
    if (($ConfuserTestDownloads -join ',') -ne $expectedDownloads) { throw 'Wrong tool installation requested' }
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
    'winget-rejected' {
        $SkipTools = $false
        function Get-Command { param($Name, $ErrorAction) return $null }
        function Test-InteractiveInput { return $true }
        function Read-Host { param($Prompt) return 'n' }
        function Install-PackageProvider { throw 'UNEXPECTED DOWNLOAD' }
        function Install-Module { throw 'UNEXPECTED DOWNLOAD' }
        try {
            Ensure-Winget
            throw 'Unapproved WinGet setup succeeded'
        } catch {
            if ($_.Exception.Message -notlike '*WinGet installation was not approved*') { throw }
        }
    }
    'ci-no-prompt' {
        $SkipTools = $false
        $env:CI = 'true'
        function Read-Host { throw 'UNEXPECTED PROMPT' }
        if (Confirm-ToolInstall 'clang' 'Test only') { throw 'CI approved a download' }
    }
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
        for case in ("reject", "blank", "no-console", "skip", "clang", "go", "sdk-reject", "sdk-approve"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                driver = root / "local-test.ps1"
                driver.write_text(WINDOWS_LOCAL_TEST, encoding="ascii")
                command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(driver),
                           "-InstallerPath", str(ROOT / "install.ps1"), "-PythonPath", sys.executable,
                           "-TestRoot", str(root / "spaces & Türkçe ! % path"), "-Case", case]
                result = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("WINDOWS_LOCAL_INSTALL_TEST_PASSED", result.stdout)

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell tests")
    def test_windows_helpers(self) -> None:
        for case in ("winget-rejected", "ci-no-prompt", "python-launcher-enumeration", "python-fallback", "compiler-warning", "compiler-failure", "build-tools-arm64", "build-tools-x64"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                check_windows_installer_helpers(Path(directory), case)

    def test_windows_installer_is_ascii_for_powershell_51(self) -> None:
        (ROOT / "install.ps1").read_bytes().decode("ascii")
        (ROOT / "install.sh").read_bytes().decode("ascii")

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
                                            env=environment, capture_output=True, text=True, timeout=60,
                                            start_new_session=True, stdin=subprocess.DEVNULL)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("clang was not found", result.stdout)
                    self.assertIn("go was not found", result.stdout)
                    self.assertIn("Python validated", result.stdout)
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
                                    capture_output=True, text=True, timeout=15,
                                    start_new_session=True, stdin=subprocess.DEVNULL)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Python 3.10+ is required", result.stdout)
            self.assertIn("No download started", result.stdout)

    @unittest.skipIf(os.name == "nt", "POSIX terminal tests")
    def test_posix_per_tool_consent_in_terminal(self) -> None:
        import pty
        import select
        import signal

        cases = (
            ("reject", ("n", "n"), (), ""),
            ("blank", ("", ""), (), ""),
            ("clang", ("y", "n"), (), "update\ninstall -y clang\n"),
            ("go", ("n", "yes"), (), "update\ninstall -y golang-go\n"),
            ("both", ("yes", "y"), (), "update\ninstall -y clang\ninstall -y golang-go\n"),
            ("skip", (), ("--no-tools",), ""),
            ("ci", (), (), ""),
            ("python-reject", ("n",), (), ""),
            ("python-approve", ("y",), (), "update\ninstall -y python3\n"),
        )
        for case, answers, options, expected_log in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                tools = root / "tools"
                tools.mkdir()
                for name in ("sh", "dirname", "mkdir", "mktemp", "rm"):
                    (tools / name).symlink_to(shutil.which(name))
                if not case.startswith("python-"):
                    (tools / "python3").symlink_to(sys.executable)
                # Exercise the Linux branch on macOS too. All package commands
                # are harmless stubs; an unexpected approval cannot download.
                for name, content in {
                    "uname": "#!/bin/sh\nprintf 'Linux\\n'\n",
                    "id": "#!/bin/sh\nprintf '0\\n'\n",
                    "apt-get": '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CONFUSER_PACKAGE_LOG"\n',
                }.items():
                    stub = tools / name
                    stub.write_text(content, encoding="ascii")
                    stub.chmod(0o755)
                user_bin = root / "bin"
                log = root / "packages.log"
                environment = os.environ.copy()
                environment.update(PATH=os.pathsep.join((str(user_bin), str(tools))),
                                   CI="true" if case == "ci" else "",
                                   CONFUSER_PACKAGE_LOG=str(log), CONFUSER_USER_BIN=str(user_bin),
                                   CONFUSER_INSTALL_ROOT=str(root / "app"))
                pid, terminal = pty.fork()
                if pid == 0:
                    os.execve(str(tools / "sh"), ["sh", str(ROOT / "install.sh"), *options], environment)
                output = b""
                sent = 0
                status = None
                deadline = time.monotonic() + 30
                try:
                    while time.monotonic() < deadline:
                        if select.select([terminal], [], [], 0.1)[0]:
                            try:
                                data = os.read(terminal, 65536)
                            except OSError:
                                data = b""
                            output += data
                            if output.count(b"[y/N]: ") > sent and sent < len(answers):
                                os.write(terminal, (answers[sent] + "\n").encode("ascii"))
                                sent += 1
                        finished, status_value = os.waitpid(pid, os.WNOHANG)
                        if finished:
                            status = status_value
                            break
                    self.assertIsNotNone(status, output.decode(errors="replace"))
                finally:
                    if status is None:
                        os.kill(pid, signal.SIGKILL)
                        os.waitpid(pid, 0)
                    os.close(terminal)
                self.assertEqual(sent, len(answers), output.decode(errors="replace"))
                self.assertEqual(os.waitstatus_to_exitcode(status), 1 if case.startswith("python-") else 0,
                                 output.decode(errors="replace"))
                self.assertEqual(log.read_text() if log.exists() else "", expected_log)
                if not case.startswith("python-"):
                    self.assertTrue((user_bin / "confuser").is_file())

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
            self.assertIn("hundreds of MB", result.stdout)
            self.assertIn("No download started", result.stdout)
