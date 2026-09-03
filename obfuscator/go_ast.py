"""Bridge to the bundled Go AST/type-checking helper."""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
from pathlib import Path


def rename_go_identifiers(source: str, filename: str, rng: random.Random) -> str:
    go = shutil.which("go")
    if go is None:
        raise ValueError("Go identifier renaming requires an installed Go toolchain in PATH; no download was started")
    helper = Path(__file__).with_name("go_ast_helper") / "main.go"
    if not helper.is_file():
        raise ValueError("bundled Go AST helper is missing; reinstall Confuser Obfuser")
    actual_filename = str(Path(filename).resolve()) if filename not in {"", "<unknown>"} else str(Path.cwd() / "source.go")
    request = json.dumps(
        {
            "source": source,
            "filename": actual_filename,
            "seed": rng.getrandbits(63),
        }
    ).encode("utf-8")
    environment = os.environ.copy()
    environment.update(GO111MODULE="off", GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off")
    try:
        completed = subprocess.run(
            [go, "run", str(helper)],
            input=request,
            capture_output=True,
            timeout=60,
            check=False,
            env=environment,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("Go AST analysis timed out after 60 seconds") from error
    if completed.returncode != 0:
        diagnostic = completed.stderr.decode("utf-8", errors="replace").strip()
        detail = diagnostic.splitlines()[-1] if diagnostic else "unknown Go AST error"
        raise SyntaxError(f"Go AST engine could not process the source: {detail}")
    return completed.stdout.decode("utf-8")
