from __future__ import annotations

from pathlib import Path

from obfuscator.cli import main


def test_cli_writes_valid_output(tmp_path: Path) -> None:
    source = tmp_path / "input.py"
    output = tmp_path / "output.py"
    source.write_text('value = "hello"\nprint(value)\n', encoding="utf-8")

    assert main([str(source), "-o", str(output), "--seed", "42", "--validate"]) == 0
    compile(output.read_text(encoding="utf-8"), str(output), "exec")


def test_cli_rejects_missing_input(tmp_path: Path) -> None:
    assert main([str(tmp_path / "missing.py")]) == 2


def test_cli_does_not_overwrite_input(tmp_path: Path) -> None:
    source = tmp_path / "input.py"
    original = "print('safe')\n"
    source.write_text(original, encoding="utf-8")

    assert main([str(source), "-o", str(source)]) == 2
    assert source.read_text(encoding="utf-8") == original


def test_cli_rejects_non_positive_timeout(tmp_path: Path) -> None:
    source = tmp_path / "input.py"
    source.write_text("print('ok')\n", encoding="utf-8")

    assert main([str(source), "--timeout", "0"]) == 2
