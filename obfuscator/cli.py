"""Command-line interface."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .languages import SourceLanguage, detect_language
from .pipeline import ObfuscationConfig, Obfuscator
from .project import obfuscate_project
from .validator import validate_behavior


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="confuser",
        description="Obfuscate Python, C or Go source; language is detected from the extension.",
    )
    parser.add_argument("input", type=Path, help="source file or project directory; a folder path alone is sufficient")
    parser.add_argument("-o", "--output", type=Path, help="output file or project directory (project default: <name>-obfuscated; file default: stdout)")
    parser.add_argument("--project", action="store_true", help="process a whole folder recursively, preserving filenames and extensions")
    parser.add_argument("--seed", type=int, help="seed for reproducible output")
    parser.add_argument("--iterations", type=int, default=1, help="obfuscation rounds (default: 1; output can grow rapidly)")
    parser.add_argument("--no-rename", action="store_true", help="disable function, parameter and local renaming")
    parser.add_argument("--no-strings", action="store_true", help="disable fragmented string encoding")
    parser.add_argument("--no-numbers", action="store_true", help="disable integer transformation")
    parser.add_argument("--no-dead-code", action="store_true", help="disable dead-code insertion")
    parser.add_argument("--validate", action="store_true", help="execute and compare both programs (default: off; trusted code only)")
    parser.add_argument("--validation-command", nargs=argparse.REMAINDER, help="project run/test command and arguments; requires --validate and must be the last option")
    parser.add_argument("--timeout", type=float, default=5.0, help="validation timeout per program")
    return parser


def main(argv: list[str] | None = None) -> int:
    actual_argv = sys.argv[1:] if argv is None else argv
    if not actual_argv:
        from .terminal_ui import run_interactive

        return run_interactive()
    args = build_parser().parse_args(actual_argv)
    if args.iterations < 1:
        print("error: --iterations must be at least 1", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("error: --timeout must be greater than zero", file=sys.stderr)
        return 2
    config = ObfuscationConfig(
        seed=args.seed,
        rename_identifiers=not args.no_rename,
        encode_strings=not args.no_strings,
        transform_numbers=not args.no_numbers,
        insert_dead_code=not args.no_dead_code,
        iterations=args.iterations,
    )
    if args.project or args.input.is_dir():
        try:
            result = obfuscate_project(
                args.input, args.output, config=config, validate=args.validate,
                validation_command=args.validation_command, timeout=args.timeout,
                on_progress=lambda path, index, total: print(f"[{index}/{total}] {path}", file=sys.stderr),
            )
        except subprocess.TimeoutExpired:
            print(f"validation failed: timed out after {args.timeout:g} seconds", file=sys.stderr)
            return 2
        except (OSError, ValueError, SyntaxError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        print(f"Project obfuscated: {result.output_path}")
        print(f"{len(result.transformed)} source files transformed; {result.copied_files} other files copied.")
        if result.skipped_directories:
            print("Skipped cache/environment/VCS directories: " + ", ".join(map(str, result.skipped_directories)), file=sys.stderr)
        if result.validated:
            print("project validation passed", file=sys.stderr)
        return 0
    if args.validation_command is not None:
        print("error: --validation-command is only available for project directories", file=sys.stderr)
        return 2
    if args.output and args.input.resolve() == args.output.resolve():
        print("error: input and output paths must be different", file=sys.stderr)
        return 2
    try:
        language = detect_language(args.input)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.output:
        try:
            output_language = detect_language(args.output)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        if output_language is not language:
            print("error: input and output extensions must represent the same language", file=sys.stderr)
            return 2
    try:
        source = args.input.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"error: could not read input: {error}", file=sys.stderr)
        return 2
    try:
        result = Obfuscator(config).obfuscate(source, str(args.input))
    except SyntaxError as error:
        print(f"error: invalid {language.display_name} source: {error}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.validate:
        try:
            if language is SourceLanguage.PYTHON:
                validation = validate_behavior(source, result, timeout=args.timeout)
            else:
                validation = validate_behavior(
                    source,
                    result,
                    timeout=args.timeout,
                    language=language,
                    filename=args.input,
                )
        except subprocess.TimeoutExpired:
            print(f"validation failed: timed out after {args.timeout:g} seconds", file=sys.stderr)
            return 2
        except (ValueError, OSError) as error:
            print(f"validation failed: {error}", file=sys.stderr)
            return 2
        if not validation.equivalent:
            print("validation failed: compilation, exit status or observable outputs differ", file=sys.stderr)
            return 2
        print("validation passed", file=sys.stderr)

    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result, encoding="utf-8")
        except OSError as error:
            print(f"error: could not write output: {error}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
