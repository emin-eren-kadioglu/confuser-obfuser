from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from obfuscator.cli import main
from obfuscator.pipeline import ObfuscationConfig
from obfuscator.project import default_project_output, obfuscate_project, validate_project
from obfuscator.terminal_ui import TerminalUI

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "project_demo"


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="confuser-project-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "sample project"
        self.source.mkdir()

    def write(self, name, content):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def python_project(self):
        self.write("lib/__init__.py", "from .helper import calculate\n")
        self.write("lib/helper.py", "def calculate(amount, factor=2):\n    total = amount * factor\n    return total\n")
        self.write("main.py", "from lib import calculate\nfrom pathlib import Path\nprint(Path('asset.txt').read_text(), calculate(amount=10))\n")
        self.write("asset.txt", "payload")
        (self.source / "empty").mkdir()

    def test_python_project_keeps_imports_keywords_names_assets_and_source(self):
        self.python_project()
        original = {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        for iterations in (1, 3):
            with self.subTest(iterations=iterations):
                result = obfuscate_project(self.source, self.root / f"result-{iterations}",
                                           config=ObfuscationConfig(seed=42, iterations=iterations), validate=True,
                                           validation_command=[sys.executable, "main.py"])
                self.assertTrue(result.validated)
                self.assertEqual(len(result.transformed), 3)
                self.assertEqual(result.copied_files, 1)
                self.assertEqual(set(original), {p.relative_to(result.output_path) for p in result.output_path.rglob("*") if p.is_file()})
                self.assertTrue((result.output_path / "empty").is_dir())
                self.assertEqual((result.output_path / "asset.txt").read_bytes(), b"payload")
                transformed = (result.output_path / "lib/helper.py").read_text()
                self.assertIn("def calculate(amount, factor=", transformed)
                self.assertNotIn("total =", transformed)
        self.assertEqual(original, {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*") if p.is_file()})

    def test_default_does_not_execute_project_and_is_reproducible(self):
        self.write("main.py", "raise RuntimeError('must not execute')\n")
        with patch("obfuscator.project.validate_project", side_effect=AssertionError("unexpected execution")):
            first = obfuscate_project(self.source, config=ObfuscationConfig(seed=42))
            second = obfuscate_project(self.source, self.root / "again", config=ObfuscationConfig(seed=42))
        self.assertEqual(first.output_path, default_project_output(self.source))
        self.assertFalse(first.validated)
        self.assertEqual((first.output_path / "main.py").read_bytes(), (second.output_path / "main.py").read_bytes())

    def test_existing_nested_and_source_outputs_are_rejected(self):
        self.write("main.py", "print(1)\n")
        existing = self.root / "existing"
        existing.mkdir()
        marker = existing / "keep.txt"
        marker.write_text("preserve")
        for output in (existing, self.source, self.source / "nested", self.root):
            with self.subTest(output=output), self.assertRaises(ValueError):
                obfuscate_project(self.source, output)
        self.assertEqual(marker.read_text(), "preserve")
        self.assertFalse((self.source / "nested").exists())

    def test_failed_transform_does_not_publish_a_partial_tree(self):
        self.write("a.py", "print(1)\n")
        self.write("z.py", "def broken(:\n")
        with self.assertRaisesRegex(ValueError, "z.py"):
            obfuscate_project(self.source)
        self.assertFalse(default_project_output(self.source).exists())
        self.assertFalse(list(self.root.glob(".confuser-project-*")))

    def test_caches_and_environment_directories_are_skipped(self):
        self.write("main.py", "print(1)\n")
        for name in (".git", ".venv", "__pycache__", "node_modules"):
            self.write(f"{name}/broken.py", "invalid code !")
        result = obfuscate_project(self.source)
        self.assertEqual(len(result.skipped_directories), 4)
        self.assertEqual(list(result.output_path.iterdir()), [result.output_path / "main.py"])

    def test_links_are_rejected_without_following_them(self):
        self.write("main.py", "print(1)\n")
        outside = self.root / "outside.py"
        outside.write_text("raise RuntimeError('outside')")
        try:
            (self.source / "link.py").symlink_to(outside)
        except OSError:
            self.skipTest("symlink creation not permitted")
        with self.assertRaisesRegex(ValueError, "symbolic links"):
            obfuscate_project(self.source)
        self.assertFalse(default_project_output(self.source).exists())

    def test_python_encoding_shebang_and_file_mode(self):
        original = self.source / "script.py"
        original.write_bytes(b"#!/usr/bin/env python3\n# coding: latin-1\nprint('caf\xe9')\n")
        original.chmod(0o755)
        result = obfuscate_project(self.source)
        generated = result.output_path / "script.py"
        self.assertTrue(generated.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3\n"))
        if os.name != "nt":
            self.assertEqual(generated.stat().st_mode & 0o777, 0o755)
        self.assertTrue(validate_project(self.source, result.output_path, [sys.executable, "script.py"]).equivalent)

    def test_validation_command_is_required_and_must_be_enabled(self):
        self.write("main.py", "print(1)\n")
        with self.assertRaisesRegex(ValueError, "explicit run/test command"):
            obfuscate_project(self.source, validate=True)
        with self.assertRaisesRegex(ValueError, "enable validation"):
            obfuscate_project(self.source, validation_command=[sys.executable, "main.py"])

    def test_validation_failure_and_timeout_leave_no_output_or_source_artifacts(self):
        self.write("main.py", "from pathlib import Path\nPath('artifact').write_text('x')\nraise SystemExit(2)\n")
        with self.assertRaisesRegex(ValueError, "validation failed"):
            obfuscate_project(self.source, validate=True, validation_command=[sys.executable, "main.py"])
        self.assertFalse((self.source / "artifact").exists())
        self.assertFalse(default_project_output(self.source).exists())
        self.write("main.py", "import time\ntime.sleep(2)\n")
        with self.assertRaises(subprocess.TimeoutExpired):
            obfuscate_project(self.source, validate=True, validation_command=[sys.executable, "main.py"], timeout=0.1)
        self.assertFalse(default_project_output(self.source).exists())

    def test_cli_folder_only_and_explicit_validation(self):
        self.python_project()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.source), "--seed", "42"]), 0)
            self.assertEqual(main([str(self.source), "--project", "-o", str(self.root / "checked"),
                                   "--validate", "--validation-command", sys.executable, "main.py"]), 0)
            self.assertEqual(main([str(self.source), "--project", "-o", str(self.root / "missing-command"), "--validate"]), 2)

    def test_ui_default_is_off_and_folder_mode_guides_paths(self):
        self.python_project()
        output = io.StringIO()
        destination = self.root / "ui result"
        ui = TerminalUI(io.StringIO(f"8\n1\n{self.source}\n2\n{destination}\n7\n\n0\n"), output)
        self.assertFalse(ui.state.validate)
        self.assertEqual(ui.run(), 0)
        self.assertFalse(TerminalUI().state.validate)
        self.assertIn("Yalnızca kaynak klasörün yolunu", output.getvalue())
        self.assertIn("Yalnızca yeni çıktı klasörünün yolunu", output.getvalue())
        self.assertIn("Proje obfuscation tamamlandı", output.getvalue())
        self.assertTrue((destination / "lib/helper.py").is_file())

    @unittest.skipUnless(shutil.which("clang") and shutil.which("go"), "Clang and Go required for mixed project")
    def test_mixed_demo_with_local_go_module_headers_and_assets(self):
        for rounds in (1, 3):
            with self.subTest(rounds=rounds):
                result = obfuscate_project(DEMO, self.root / f"mixed-{rounds}",
                                           config=ObfuscationConfig(seed=42, iterations=rounds), validate=True,
                                           validation_command=[sys.executable, "verify.py"], timeout=120)
                self.assertTrue(result.validated)
                self.assertIn("func Total(", (result.output_path / "go/calc/total.go").read_text())
                self.assertIn("int calculate_total(", (result.output_path / "c/math_ops.c").read_text())
                for name in ("c/include/math_ops.h", "go/go.mod", "go/message.txt", "data/settings.json"):
                    self.assertEqual((DEMO / name).read_bytes(), (result.output_path / name).read_bytes())
