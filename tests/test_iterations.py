from __future__ import annotations

import ast
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from obfuscator import ObfuscationConfig, Obfuscator
from obfuscator.cli import main
from obfuscator.terminal_ui import TerminalUI
from obfuscator.validator import validate_behavior


SOURCE = 'def add(left, right):\n    return f"Sonuç: {left + right}"\nprint(add(left=2, right=5))\n'


class IterationsTests(unittest.TestCase):
    def test_default_is_one_round(self) -> None:
        self.assertEqual(ObfuscationConfig().iterations, 1)
        self.assertEqual(
            Obfuscator(ObfuscationConfig(seed=42)).obfuscate(SOURCE),
            Obfuscator(ObfuscationConfig(seed=42, iterations=1)).obfuscate(SOURCE),
        )

    def test_three_rounds_match_three_manual_runs(self) -> None:
        single = Obfuscator(ObfuscationConfig(seed=42))
        expected = SOURCE
        for _ in range(3):
            expected = single.obfuscate(expected)
        actual = Obfuscator(ObfuscationConfig(seed=42, iterations=3)).obfuscate(SOURCE)
        self.assertEqual(actual, expected)
        check = validate_behavior(SOURCE, actual)
        self.assertEqual(check.original.returncode, 0)
        self.assertTrue(check.equivalent)

    def test_multi_round_seed_is_reproducible(self) -> None:
        obfuscator = Obfuscator(ObfuscationConfig(seed=42, iterations=2))
        self.assertEqual(obfuscator.obfuscate(SOURCE), obfuscator.obfuscate(SOURCE))
        self.assertNotEqual(
            obfuscator.obfuscate(SOURCE),
            Obfuscator(ObfuscationConfig(seed=7, iterations=2)).obfuscate(SOURCE),
        )

    def test_invalid_round_counts_are_rejected(self) -> None:
        for value in (0, -1, 1.5, "3", True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ObfuscationConfig(iterations=value)

    def test_progress_reports_each_round(self) -> None:
        events = []
        Obfuscator(ObfuscationConfig(seed=42, iterations=3)).obfuscate(
            SOURCE, on_progress=lambda current, total: events.append((current, total)),
        )
        self.assertEqual(events, [(1, 3), (2, 3), (3, 3)])

    def test_disabled_passes_stay_disabled_on_every_round(self) -> None:
        config = ObfuscationConfig(
            iterations=4, rename_identifiers=False, encode_strings=False,
            transform_numbers=False, insert_dead_code=False,
        )
        result = Obfuscator(config).obfuscate(SOURCE)
        self.assertEqual(ast.dump(ast.parse(result)), ast.dump(ast.parse(SOURCE)))

    def test_size_guard_stops_before_feeding_large_intermediate_source(self) -> None:
        events = []
        with patch("obfuscator.pipeline.MAX_INTERMEDIATE_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "round 2 stopped"):
                Obfuscator(ObfuscationConfig(iterations=3)).obfuscate(
                    SOURCE, on_progress=lambda current, total: events.append((current, total)),
                )
        self.assertEqual(events, [(1, 3)])

    def test_size_guard_does_not_change_single_round_behavior(self) -> None:
        with patch("obfuscator.pipeline.MAX_INTERMEDIATE_BYTES", 1):
            result = Obfuscator().obfuscate(SOURCE)
        compile(result, "<test>", "exec")

    def test_deep_ast_failure_is_actionable(self) -> None:
        with patch.object(Obfuscator, "transform_tree", side_effect=RecursionError):
            with self.assertRaisesRegex(ValueError, "AST nesting is too deep"):
                Obfuscator().obfuscate(SOURCE)

    def test_cli_accepts_iterations_and_validates_only_final_result(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-rounds-test-") as directory:
            source = Path(directory) / "source.py"
            output = Path(directory) / "output.py"
            source.write_text(SOURCE, encoding="utf-8")
            with patch("obfuscator.cli.validate_behavior", wraps=validate_behavior) as validate:
                self.assertEqual(main([
                    str(source), "-o", str(output), "--seed", "42", "--iterations", "3", "--validate",
                ]), 0)
            final = output.read_text(encoding="utf-8")
            validate.assert_called_once_with(SOURCE, final, timeout=5.0)

    def test_cli_invalid_count_does_not_write_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-rounds-test-") as directory:
            source = Path(directory) / "source.py"
            output = Path(directory) / "output.py"
            source.write_text(SOURCE, encoding="utf-8")
            for count in ("0", "-3"):
                self.assertEqual(main([str(source), "-o", str(output), "--iterations", count]), 2)
            self.assertFalse(output.exists())

    def test_cli_size_failure_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-rounds-test-") as directory:
            source = Path(directory) / "source.py"
            output = Path(directory) / "output.py"
            source.write_text(SOURCE, encoding="utf-8")
            output.write_text("keep me", encoding="utf-8")
            with patch("obfuscator.pipeline.MAX_INTERMEDIATE_BYTES", 1):
                self.assertEqual(main([str(source), "-o", str(output), "--iterations", "2"]), 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep me")

    def test_menu_changes_iteration_count_and_runs_all_rounds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-rounds-test-") as directory:
            source = Path(directory) / "source.py"
            source.write_text(SOURCE, encoding="utf-8")
            output = io.StringIO()
            ui = TerminalUI(io.StringIO(f"1\n{source}\n6\n2\n7\n\n0\n"), output)
            self.assertEqual(ui.run(), 0)
            self.assertEqual(ui.state.iterations, 2)
            self.assertIn("Tur 1/2 işleniyor", output.getvalue())
            self.assertIn("Tur 2/2 işleniyor", output.getvalue())
            result = source.with_name("source.obf.py").read_text(encoding="utf-8")
            self.assertTrue(validate_behavior(SOURCE, result).equivalent)

    def test_invalid_menu_count_keeps_previous_value(self) -> None:
        for value in ("0", "-3", "abc", "2.5"):
            with self.subTest(value=value):
                ui = TerminalUI(io.StringIO(value + "\n\n"), io.StringIO())
                ui.state.iterations = 2
                ui._choose_iterations()
                self.assertEqual(ui.state.iterations, 2)

    def test_empty_menu_count_resets_to_one(self) -> None:
        ui = TerminalUI(io.StringIO("\n"), io.StringIO())
        ui.state.iterations = 3
        ui._choose_iterations()
        self.assertEqual(ui.state.iterations, 1)
