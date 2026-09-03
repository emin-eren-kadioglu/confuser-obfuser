"""Black-box behavior comparison for trusted Python, C and Go programs."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .languages import SourceLanguage


@dataclass(frozen=True)
class ExecutionResult:
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class ValidationResult:
    equivalent: bool
    original: ExecutionResult
    obfuscated: ExecutionResult
    original_compiled: bool = True
    obfuscated_compiled: bool = True


def _execute_python(path: Path, argv: list[str], timeout: float) -> ExecutionResult:
    environment = os.environ.copy()
    # Windows PowerShell runners commonly expose a cp1252 console. Use a
    # deterministic UTF-8 pipe so programs containing Turkish or other Unicode
    # text can be compared instead of failing while printing their output.
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, str(path), *argv],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
        env=environment,
    )
    return ExecutionResult(completed.returncode, completed.stdout, completed.stderr)


def _compile_and_execute(
    path: Path,
    language: SourceLanguage,
    argv: list[str],
    timeout: float,
    include_directory: Path | None,
) -> tuple[bool, ExecutionResult]:
    binary = path.with_suffix(".exe" if os.name == "nt" else ".bin")
    if language is SourceLanguage.C:
        compiler = shutil.which(os.environ.get("CC", "cc")) or shutil.which("clang")
        if compiler is None:
            raise ValueError("C validation requires a C compiler (cc or clang) in PATH")
        command = [compiler, str(path), "-o", str(binary)]
        if include_directory is not None:
            command[1:1] = ["-I", str(include_directory)]
        command[1:1] = shlex.split(os.environ.get("CONFUSER_CLANG_ARGS", ""))
    else:
        compiler = shutil.which("go")
        if compiler is None:
            raise ValueError("Go validation requires the go command in PATH")
        command = [compiler, "build", "-o", str(binary), str(path)]
    environment = os.environ.copy()
    if language is SourceLanguage.GO:
        environment.update(GO111MODULE="off", GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off")
    compiled = subprocess.run(
        command,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
        env=environment,
    )
    if compiled.returncode != 0:
        return False, ExecutionResult(compiled.returncode, compiled.stdout, compiled.stderr)
    completed = subprocess.run(
        [str(binary), *argv],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )
    return True, ExecutionResult(completed.returncode, completed.stdout, completed.stderr)


def validate_behavior(
    original_source: str,
    obfuscated_source: str,
    *,
    argv: list[str] | None = None,
    timeout: float = 5.0,
    language: SourceLanguage = SourceLanguage.PYTHON,
    filename: str | Path | None = None,
) -> ValidationResult:
    """Execute both sources and compare exit code, stdout and stderr.

    This function executes code. Only use it with sources you trust.
    """
    with tempfile.TemporaryDirectory(prefix="confuser-obfuser-") as directory:
        root = Path(directory)
        suffix = language.extensions[0]
        original_path = root / f"original{suffix}"
        obfuscated_path = root / f"obfuscated{suffix}"
        original_path.write_text(original_source, encoding="utf-8")
        obfuscated_path.write_text(obfuscated_source, encoding="utf-8")
        arguments = argv or []
        if language is SourceLanguage.PYTHON:
            original = _execute_python(original_path, arguments, timeout)
            obfuscated = _execute_python(obfuscated_path, arguments, timeout)
            return ValidationResult(original == obfuscated, original, obfuscated)
        include_directory = Path(filename).resolve().parent if filename is not None else None
        original_compiled, original = _compile_and_execute(
            original_path, language, arguments, timeout, include_directory,
        )
        obfuscated_compiled, obfuscated = _compile_and_execute(
            obfuscated_path, language, arguments, timeout, include_directory,
        )
    equivalent = original_compiled and obfuscated_compiled and original == obfuscated
    return ValidationResult(equivalent, original, obfuscated, original_compiled, obfuscated_compiled)
