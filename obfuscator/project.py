"""Transactional folder obfuscation with stable paths and cross-file APIs."""

from __future__ import annotations

import io
import os
import shutil
import stat
import subprocess
import tempfile
import tokenize
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Sequence

from .languages import SUPPORTED_EXTENSIONS
from .pipeline import ObfuscationConfig, Obfuscator
from .validator import ExecutionResult, ValidationResult


IGNORED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", ".tox",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules",
})


@dataclass(frozen=True)
class ProjectResult:
    output_path: Path
    transformed: tuple[Path, ...]
    copied_files: int
    skipped_directories: tuple[Path, ...]
    validated: bool


def default_project_output(source: Path) -> Path:
    source = source.expanduser().resolve()
    return source.with_name(source.name + "-obfuscated")


def _is_link(path: Path) -> bool:
    metadata = path.lstat()
    # Windows junctions/reparse points must not escape the selected tree either.
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def _inventory(root: Path) -> tuple[list[Path], list[Path], list[Path]]:
    directories: list[Path] = []
    files: list[Path] = []
    skipped: list[Path] = []

    def walk(directory: Path) -> None:
        for path in sorted(directory.iterdir(), key=lambda entry: entry.name):
            relative = path.relative_to(root)
            if path.name in IGNORED_DIRECTORIES and path.is_dir():
                skipped.append(relative)
                continue
            if _is_link(path):
                raise ValueError(f"symbolic links/junctions are not supported in project mode: {relative}")
            if path.is_dir():
                directories.append(relative)
                walk(path)
            elif path.is_file():
                if path.suffix.lower() not in {".pyc", ".pyo"}:
                    files.append(relative)
            else:
                raise ValueError(f"not a regular project file: {relative}")

    walk(root)
    return directories, files, skipped


def _copy_snapshot(source: Path, target: Path, directories: list[Path], files: list[Path]) -> None:
    target.mkdir()
    for relative in directories:
        (target / relative).mkdir(parents=True, exist_ok=True)
    for relative in files:
        shutil.copy2(source / relative, target / relative)


def validate_project(
    original: Path, obfuscated: Path, command: Sequence[str], *, timeout: float = 60,
) -> ValidationResult:
    """Run an explicit trusted command in disposable copies, never the source.

    This is NOT a sandbox. The command can access the host/network and must be
    trusted. Build/test artifacts in these copies are not exported to the user.
    """
    if not command or not all(isinstance(part, str) and part for part in command):
        raise ValueError("project validation requires a non-empty command")
    if timeout <= 0:
        raise ValueError("validation timeout must be greater than zero")
    environment = os.environ.copy()
    environment.update(PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
                       GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off", GOWORK="off")
    results = []
    with tempfile.TemporaryDirectory(prefix="confuser-project-check-") as directory:
        for name, source in (("original", original), ("obfuscated", obfuscated)):
            work = Path(directory) / name
            directories, files, _ = _inventory(source)
            _copy_snapshot(source, work, directories, files)
            completed = subprocess.run(list(command), cwd=work, env=environment,
                                       stdin=subprocess.DEVNULL, capture_output=True,
                                       timeout=timeout, check=False)
            results.append(ExecutionResult(completed.returncode, completed.stdout, completed.stderr))
    before, after = results
    return ValidationResult(before.returncode == 0 and after.returncode == 0 and before == after, before, after)


def obfuscate_project(
    source: Path,
    output: Path | None = None,
    *,
    config: ObfuscationConfig | None = None,
    validate: bool = False,
    validation_command: Sequence[str] | None = None,
    timeout: float = 60,
    on_progress: Callable[[Path, int, int], None] | None = None,
) -> ProjectResult:
    """Keep filenames/extensions/assets; publish only a complete, new tree."""
    source = Path(source).expanduser()
    if not source.is_dir():
        raise ValueError("source must be an existing project directory")
    if _is_link(source):
        raise ValueError("select a real project directory, not a symbolic link/junction")
    source = source.resolve()
    if source == source.parent:
        raise ValueError("select a project directory, not a filesystem root")
    selected_output = Path(output).expanduser() if output is not None else default_project_output(source)
    if selected_output.exists() or selected_output.is_symlink():
        raise ValueError("output directory already exists; choose a new directory to avoid overwriting files")
    target = selected_output.resolve()
    if target == source or source in target.parents or target in source.parents:
        raise ValueError("source and output directories must be separate, not nested")
    if validate and not validation_command:
        raise ValueError("project validation needs an explicit run/test command; no entry point is guessed")
    if validation_command and not validate:
        raise ValueError("enable validation before supplying a project validation command")

    directories, files, skipped = _inventory(source)
    code_files = [relative for relative in files if relative.suffix.lower() in SUPPORTED_EXTENSIONS]
    if not code_files:
        raise ValueError("no .py, .pyw, .c or .go source files found in the selected directory")
    engine = Obfuscator(replace(config or ObfuscationConfig(), preserve_interfaces=True))
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".confuser-project-", dir=target.parent) as temporary:
        staged = Path(temporary) / "project"
        staged.mkdir()
        for relative in directories:
            (staged / relative).mkdir(parents=True, exist_ok=True)
        completed_count = 0
        for relative in files:
            original = source / relative
            destination = staged / relative
            if relative.suffix.lower() not in SUPPORTED_EXTENSIONS:
                shutil.copy2(original, destination)
                continue
            completed_count += 1
            if on_progress is not None:
                on_progress(relative, completed_count, len(code_files))
            try:
                raw = original.read_bytes()
                encoding = tokenize.detect_encoding(io.BytesIO(raw).readline)[0] if relative.suffix.lower() in {".py", ".pyw"} else "utf-8"
                text = raw.decode(encoding)
                transformed = engine.obfuscate(text, str(original))
                if relative.suffix.lower() in {".py", ".pyw"} and text.startswith("#!"):
                    transformed = text.splitlines()[0] + "\n" + transformed
                destination.write_bytes(transformed.encode("utf-8"))
                shutil.copystat(original, destination)
            except (OSError, ValueError, SyntaxError) as error:
                raise ValueError(f"could not obfuscate {relative}: {error}") from error
        if validate:
            result = validate_project(source, staged, validation_command, timeout=timeout)
            if not result.equivalent:
                raise ValueError(
                    "project validation failed: both commands must exit successfully with identical stdout/stderr "
                    f"(original exit {result.original.returncode}, obfuscated exit {result.obfuscated.returncode})"
                )
        if target.exists() or target.is_symlink():
            raise ValueError("output directory appeared during processing; nothing was overwritten")
        staged.rename(target)
    return ProjectResult(target, tuple(code_files), len(files) - len(code_files), tuple(skipped), validate)
