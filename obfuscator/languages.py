"""Supported source languages and extension-based detection."""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class SourceLanguage(str, Enum):
    PYTHON = "python"
    C = "c"
    GO = "go"

    @property
    def display_name(self) -> str:
        return {self.PYTHON: "Python", self.C: "C", self.GO: "Go"}[self]

    @property
    def extensions(self) -> tuple[str, ...]:
        return {
            self.PYTHON: (".py", ".pyw"),
            self.C: (".c",),
            self.GO: (".go",),
        }[self]


_LANGUAGE_BY_EXTENSION = {
    extension: language
    for language in SourceLanguage
    for extension in language.extensions
}

SUPPORTED_EXTENSIONS = frozenset(_LANGUAGE_BY_EXTENSION)


def detect_language(path: str | Path, *, default: SourceLanguage | None = None) -> SourceLanguage:
    """Detect a language from a filename suffix.

    ``default`` keeps the public in-memory API backward compatible when callers
    use its traditional ``<unknown>`` filename.
    """
    suffix = Path(path).suffix.lower()
    try:
        return _LANGUAGE_BY_EXTENSION[suffix]
    except KeyError:
        if default is not None:
            return default
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"unsupported source extension {suffix or '(none)'}; expected one of: {supported}")


def default_output_path(path: Path) -> Path:
    """Return ``name.obf.ext`` while preserving the source extension."""
    return path.with_name(f"{path.stem}.obf{path.suffix}")
