"""Run this trusted, dependency-free demo; optionally select python, c or go."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def run(command, directory):
    environment = os.environ.copy()
    environment.update(GO111MODULE="auto", GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off", GOWORK="off", PYTHONIOENCODING="utf-8")
    result = subprocess.run(command, cwd=directory, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout


def main():
    root = Path(__file__).resolve().parent
    languages = sys.argv[1:] or ["python", "c", "go"]
    for language in languages:
        if language == "python":
            actual = run([sys.executable, "python/main.py"], root)
            expected = "Python: sample = 20\n"
        elif language == "c":
            compiler = shutil.which("clang") or shutil.which("cc")
            if compiler is None:
                raise RuntimeError("C compiler is required for the C demo")
            with tempfile.TemporaryDirectory(prefix="confuser-demo-") as directory:
                binary = str(Path(directory) / ("demo.exe" if os.name == "nt" else "demo"))
                run([compiler, "c/main.c", "c/math_ops.c", "-o", binary], root)
                actual = run([binary], root)
            expected = "C: sample = 20\n"
        elif language == "go":
            actual = run(["go", "run", "."], root / "go")
            run(["go", "test", "./..."], root / "go")
            expected = "Go: sample = 20\n"
        else:
            raise ValueError("Select python, c or go")
        if actual != expected:
            raise AssertionError((language, actual, expected))
        print(actual, end="")


if __name__ == "__main__":
    main()
