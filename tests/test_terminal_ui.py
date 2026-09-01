from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from obfuscator.terminal_ui import StatusColor, Style, TerminalUI


class TTYStream(io.StringIO):
    def isatty(self) -> bool:
        return True


class TerminalUITests(unittest.TestCase):
    def colored_ui(self) -> TerminalUI:
        with patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True):
            return TerminalUI(TTYStream(), TTYStream())

    def test_selected_row_has_one_continuous_background(self) -> None:
        ui = self.colored_ui()
        ui._main_menu("1")
        selected = next(line for line in ui.stdout.getvalue().splitlines() if "▶" in line)
        self.assertTrue(selected.startswith(Style.SELECT_BG + Style.TEXT + Style.BOLD))
        self.assertEqual(selected.count(Style.RESET), 1)
        self.assertTrue(selected.endswith(Style.RESET))

    def test_header_uses_off_white_logo_and_retro_signature(self) -> None:
        ui = self.colored_ui()
        ui._header()
        output = ui.stdout.getvalue()
        self.assertIn(Style.LOGO, output)
        self.assertIn(Style.MUTED + "  nothing changed. everything looks different.", output)
        self.assertIn(Style.SIGNATURE + Style.BOLD + "  by | emin-eren-kadioglu", output)
        self.assertNotIn("\033[?25l", output)

    def test_redirected_menu_contains_no_escape_codes(self) -> None:
        output = io.StringIO()
        ui = TerminalUI(io.StringIO("0\n"), output)
        self.assertEqual(ui.run(), 0)
        self.assertNotIn("\033", output.getvalue())

    def test_no_color_disables_palette(self) -> None:
        with patch.dict(os.environ, {"NO_COLOR": "", "TERM": "xterm-256color"}, clear=True):
            ui = TerminalUI(TTYStream(), TTYStream())
        self.assertFalse(ui.colors)
        self.assertEqual(ui._style("test", Style.ACCENT), "test")

    def test_unselected_keys_use_amber_without_a_background(self) -> None:
        ui = self.colored_ui()
        row = ui._menu_line("2", "Çıktı dosyası", "1")
        self.assertIn(Style.ACCENT + "[2]", row)
        self.assertNotIn(Style.SELECT_BG, row)

    def test_open_and_closed_statuses_are_green_and_red(self) -> None:
        ui = self.colored_ui()
        open_row = ui._menu_line("1", "Stringleri kodla", "2", True)
        closed_row = ui._menu_line("1", "Stringleri kodla", "2", False)
        self.assertIn(StatusColor.SUCCESS + Style.BOLD + "AÇIK", open_row)
        self.assertIn(StatusColor.ERROR + Style.BOLD + "KAPALI", closed_row)

    def test_status_color_survives_on_selected_row(self) -> None:
        ui = self.colored_ui()
        row = ui._menu_line("5", "Doğrulama            :", "5", True)
        self.assertTrue(row.startswith(Style.SELECT_BG + Style.TEXT + Style.BOLD))
        self.assertIn(StatusColor.SUCCESS + "AÇIK", row)
        self.assertIn("AÇIK" + Style.SELECT_BG + Style.TEXT + Style.BOLD, row)
        self.assertTrue(row.endswith(Style.RESET))

    def test_dumb_terminal_disables_palette(self) -> None:
        with patch.dict(os.environ, {"TERM": "dumb"}, clear=True):
            ui = TerminalUI(TTYStream(), TTYStream())
        self.assertFalse(ui.colors)

    def test_arrow_navigation_and_enter_still_work(self) -> None:
        ui = self.colored_ui()
        with patch.object(ui, "_read_key", side_effect=["\033[C", "\033[D", "\n"]):
            self.assertEqual(ui._menu_choice(("1", "2", "0"), 0), (None, 1))
            self.assertEqual(ui._menu_choice(("1", "2", "0"), 1), (None, 0))
            self.assertEqual(ui._menu_choice(("1", "2", "0"), 0), ("1", 0))
        self.assertTrue(ui.stdout.getvalue().endswith("\n"))

    def test_menu_columns_are_aligned(self) -> None:
        output = io.StringIO()
        ui = TerminalUI(io.StringIO(), output)
        ui._main_menu("1")
        positions = [line.index(":") for line in output.getvalue().splitlines() if ":" in line]
        self.assertEqual(len(set(positions)), 1)

    def test_menu_obfuscates_with_static_status_messages(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-ui-test-") as directory:
            source = Path(directory) / "demo.py"
            source.write_text("print('hello')\n", encoding="utf-8")
            output = io.StringIO()
            ui = TerminalUI(io.StringIO(f"1\n{source}\n7\n\n0\n"), output)
            self.assertEqual(ui.run(), 0)
            self.assertTrue(source.with_name("demo.obf.py").is_file())
            self.assertIn("Kod dönüştürülüyor...", output.getvalue())
            self.assertIn("Obfuscation tamamlandı!", output.getvalue())
            self.assertNotIn("\033", output.getvalue())

    def test_success_messages_are_green_independent_of_palette(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-status-test-") as directory:
            source = Path(directory) / "demo.py"
            source.write_text("print('hello')\n", encoding="utf-8")
            ui = self.colored_ui()
            ui.state.input_path = source
            with patch.object(ui, "_pause"), patch.object(Style, "ACCENT", "\033[35m"):
                ui._obfuscate()
            output = ui.stdout.getvalue()
            self.assertIn(StatusColor.SUCCESS + Style.BOLD + "  ✓ Obfuscation tamamlandı!", output)
            self.assertIn(StatusColor.SUCCESS + "  ✓ Doğrulama geçti.", output)
            self.assertNotIn(StatusColor.ERROR, output)

    def test_missing_input_error_is_red(self) -> None:
        ui = self.colored_ui()
        with patch.object(ui, "_pause"):
            ui._obfuscate()
        self.assertIn(StatusColor.ERROR + Style.BOLD, ui.stdout.getvalue())
        self.assertNotIn(StatusColor.SUCCESS, ui.stdout.getvalue())

    def test_validation_failure_is_red_and_does_not_report_success(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-status-test-") as directory:
            source = Path(directory) / "demo.py"
            source.write_text("print('hello')\n", encoding="utf-8")
            ui = self.colored_ui()
            ui.state.input_path = source
            with patch.object(ui, "_pause"), patch("obfuscator.terminal_ui.validate_behavior") as validate:
                validate.return_value.equivalent = False
                ui._obfuscate()
            output = ui.stdout.getvalue()
            self.assertIn(StatusColor.ERROR + Style.BOLD + "  Doğrulama başarısız", output)
            self.assertNotIn(StatusColor.SUCCESS, output)
            self.assertFalse(source.with_name("demo.obf.py").exists())
