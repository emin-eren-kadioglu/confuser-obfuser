"""Launch the menu without arguments, or forward arguments to the CLI."""

from obfuscator.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
