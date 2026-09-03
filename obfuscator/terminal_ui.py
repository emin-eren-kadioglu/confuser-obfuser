"""Interactive terminal interface for Confuser Obfuser."""

from __future__ import annotations

import os
import select
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .languages import SUPPORTED_EXTENSIONS, default_output_path, detect_language
from .pipeline import ObfuscationConfig, Obfuscator
from .validator import validate_behavior


BANNER = """
▄█████  ▄▄▄  ▄▄  ▄▄ ▄▄▄▄▄ ▄▄ ▄▄  ▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄
██     ██▀██ ███▄██ ██▄▄  ██ ██ ███▄▄ ██▄▄  ██▄█▄
▀█████ ▀███▀ ██ ▀██ ██    ▀███▀ ▄▄██▀ ██▄▄▄ ██ ██

▄████▄ ▄▄▄▄  ▄▄▄▄▄ ▄▄ ▄▄  ▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄
██  ██ ██▄██ ██▄▄  ██ ██ ███▄▄ ██▄▄  ██▄█▄
▀████▀ ██▄█▀ ██    ▀███▀ ▄▄██▀ ██▄▄▄ ██ ██
"""


class Style:
    """Charcoal and off-white palette with restrained amber accents."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    LOGO = "\033[38;5;253m"
    ACCENT = "\033[38;5;214m"
    SIGNATURE = "\033[38;5;214m"
    TEXT = "\033[38;5;252m"
    MUTED = "\033[38;5;245m"
    BORDER = "\033[38;5;240m"
    SELECT_BG = "\033[48;5;237m"


class StatusColor:
    """Fixed semantic colors, independent of the decorative menu palette."""

    SUCCESS = "\033[92m"
    ERROR = "\033[91m"


@dataclass
class UIState:
    input_path: Path | None = None
    output_path: Path | None = None
    seed: int | None = None
    iterations: int = 1
    validate: bool = True
    rename_identifiers: bool = True
    encode_strings: bool = True
    transform_numbers: bool = True
    insert_dead_code: bool = True


class TerminalUI:
    def __init__(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.state = UIState()
        self.interactive = bool(getattr(self.stdin, "isatty", lambda: False)()) and bool(
            getattr(self.stdout, "isatty", lambda: False)()
        )
        self.colors = (
            self.interactive
            and os.getenv("NO_COLOR") is None
            and os.getenv("TERM") != "dumb"
        )

    def _style(self, text: str, *styles: str) -> str:
        if not self.colors:
            return text
        return "".join(styles) + text + Style.RESET

    def _write(self, text: str = "") -> None:
        self.stdout.write(text + "\n")
        self.stdout.flush()

    def _input(self, prompt: str) -> str:
        self.stdout.write(prompt)
        self.stdout.flush()
        value = self.stdin.readline()
        if value == "":
            raise EOFError
        return value.strip()

    def _clear(self) -> None:
        if self.colors:
            self.stdout.write("\033[2J\033[H")

    @staticmethod
    def _status_text(value: bool) -> str:
        return "AÇIK" if value else "KAPALI"

    @staticmethod
    def _clean_path(value: str) -> Path:
        # Terminale sürüklenen dosya yolları çoğu shell'de tırnaklı gelebilir.
        cleaned = value.strip().strip("'\"")
        return Path(os.path.expandvars(os.path.expanduser(cleaned)))

    def _header(self) -> None:
        self._clear()
        self._write(self._style(BANNER.rstrip("\n"), Style.LOGO))
        self._write()
        self._write(self._style("  nothing changed. everything looks different.", Style.MUTED))
        self._write(self._style("  by | emin-eren-kadioglu", Style.SIGNATURE, Style.BOLD))
        self._write(self._style("────────────────────────────────────────────────────", Style.BORDER))

    def _menu_line(self, key: str, text: str, selected: str, status: bool | None = None) -> str:
        line = f"  [{key}] {text}"
        status_text = self._status_text(status) if status is not None else ""
        if key == selected:
            if not self.colors:
                return "▶" + line[1:] + (f" {status_text}" if status is not None else "")
            # Reapply the selected-row style after the semantic status color.
            selected_style = Style.SELECT_BG + Style.TEXT + Style.BOLD
            result = selected_style + "▶" + line[1:]
            if status is not None:
                status_color = StatusColor.SUCCESS if status else StatusColor.ERROR
                result += f" {status_color}{status_text}{selected_style}"
            return result + Style.RESET
        result = f"  {self._style(f'[{key}]', Style.ACCENT)} {self._style(text, Style.TEXT)}"
        if status is not None:
            status_color = StatusColor.SUCCESS if status else StatusColor.ERROR
            result += " " + self._style(status_text, status_color, Style.BOLD)
        return result

    def _main_menu(self, selected: str) -> None:
        if self.state.input_path:
            language = detect_language(self.state.input_path).display_name
            source = f"{self.state.input_path}  [{language}]"
        else:
            source = "seçilmedi (Python / C / Go otomatik)"
        output = str(self.state.output_path) if self.state.output_path else "otomatik"
        seed = str(self.state.seed) if self.state.seed is not None else "rastgele"
        rows = (
            ("1", f"{'Kaynak dosya':<20}: {source}", None),
            ("2", f"{'Çıktı dosyası':<20}: {output}", None),
            ("3", f"{'Dönüşüm seçenekleri':<20}: yapılandır", None),
            ("4", f"{'Seed':<20}: {seed}", None),
            ("5", f"{'Doğrulama':<20}:", self.state.validate),
            ("6", f"{'Tur sayısı':<20}: {self.state.iterations}", None),
        )
        for key, text, status in rows:
            self._write(self._menu_line(key, text, selected, status))
        self._write()
        self._write(self._menu_line("7", "OBFUSCATE ET", selected))
        self._write(self._menu_line("0", "Çıkış", selected))
        self._write()

    def _read_key(self) -> str:
        """Read one keypress, including arrow sequences on Unix and Windows."""
        if os.name == "nt":
            import msvcrt

            first = msvcrt.getwch()
            if first in {"\x00", "\xe0"}:
                return {
                    "H": "\x1b[A",
                    "P": "\x1b[B",
                    "M": "\x1b[C",
                    "K": "\x1b[D",
                }.get(msvcrt.getwch(), "")
            return first

        import termios
        import tty

        descriptor = self.stdin.fileno()
        previous = termios.tcgetattr(descriptor)
        try:
            tty.setcbreak(descriptor)
            first = os.read(descriptor, 1).decode(errors="ignore")
            if first != "\x1b":
                return first
            sequence = first
            for _ in range(2):
                ready, _, _ = select.select([descriptor], [], [], 0.08)
                if not ready:
                    break
                sequence += os.read(descriptor, 1).decode(errors="ignore")
            return sequence
        finally:
            termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)

    def _menu_choice(self, keys: tuple[str, ...], selected: int) -> tuple[str | None, int]:
        if not self.interactive:
            choice = self._input(self._style("  Seçim > ", Style.ACCENT, Style.BOLD))
            return (choice if choice in keys else None), selected

        self.stdout.write(self._style("  ←/↑ önceki  →/↓ sonraki  Enter seç  |  Sayı tuşları da aktif", Style.MUTED))
        self.stdout.flush()
        key = self._read_key()
        # An action may immediately display another prompt (for example a file
        # path). End the navigation hint first so that prompt starts below it.
        self._write()
        if key in {"\x1b[D", "\x1b[A"}:
            return None, (selected - 1) % len(keys)
        if key in {"\x1b[C", "\x1b[B"}:
            return None, (selected + 1) % len(keys)
        if key in {"\r", "\n"}:
            return keys[selected], selected
        if key in keys:
            return key, keys.index(key)
        return None, selected

    def _pause(self) -> None:
        self._input(self._style("\n  Devam etmek için Enter...", Style.MUTED))

    def _choose_input(self) -> None:
        value = self._input(self._style("  Python, C veya Go dosyasının yolunu gir: ", Style.ACCENT))
        path = self._clean_path(value)
        if not path.is_file():
            self._write(self._style("  Error: File not found.", StatusColor.ERROR, Style.BOLD))
            self._pause()
            return
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            self._write(self._style("  Error: Select a .py, .pyw, .c or .go file.", StatusColor.ERROR, Style.BOLD))
            self._pause()
            return
        self.state.input_path = path.resolve()
        self.state.output_path = default_output_path(path).resolve()

    def _choose_output(self) -> None:
        value = self._input(self._style("  Çıktı dosyasının yolunu gir: ", Style.ACCENT))
        path = self._clean_path(value)
        if not path.suffix and self.state.input_path is not None:
            path = path.with_suffix(self.state.input_path.suffix)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            self._write(self._style("  Error: Output extension must be .py, .pyw, .c or .go.", StatusColor.ERROR, Style.BOLD))
            self._pause()
            return
        if self.state.input_path is not None and detect_language(path) is not detect_language(self.state.input_path):
            self._write(self._style("  Error: Source and output must use the same language.", StatusColor.ERROR, Style.BOLD))
            self._pause()
            return
        self.state.output_path = path.resolve()

    def _choose_seed(self) -> None:
        value = self._input(self._style("  Seed gir (rastgele için boş bırak): ", Style.ACCENT))
        if not value:
            self.state.seed = None
            return
        try:
            self.state.seed = int(value)
        except ValueError:
            self._write(self._style("  Error: Seed must be an integer.", StatusColor.ERROR, Style.BOLD))
            self._pause()

    def _passes_menu(self) -> None:
        selected = 0
        keys = ("1", "2", "3", "4", "0")
        while True:
            self._header()
            self._write(self._style("  DÖNÜŞÜM SEÇENEKLERİ\n", Style.LOGO, Style.BOLD))
            options = (
                ("1", "Fonksiyon, parametre ve yerel adlar", "rename_identifiers"),
                ("2", "Stringleri parçala ve kodla", "encode_strings"),
                ("3", "Sayıları dönüştür", "transform_numbers"),
                ("4", "İşlevsiz kod ekle", "insert_dead_code"),
            )
            for key, label, attribute in options:
                self._write(
                    self._menu_line(key, f"{label:<38}", keys[selected], getattr(self.state, attribute))
                )
            self._write()
            self._write(self._menu_line("0", "Ana menüye dön", keys[selected]))
            self._write()
            choice, selected = self._menu_choice(keys, selected)
            if choice is None:
                continue
            if choice == "0":
                return
            for key, _, attribute in options:
                if choice == key:
                    setattr(self.state, attribute, not getattr(self.state, attribute))
                    break

    def _choose_iterations(self) -> None:
        self._write(self._style("  Fazla tur dosya boyutunu hızla artırır; genellikle 1–3 tur yeterlidir.", Style.MUTED))
        self._write(self._style("  2 MiB üzerindeki ara çıktılar yeni bir tura alınmaz.", Style.MUTED))
        value = self._input(self._style("  Tur sayısı (en az 1, boş bırak = 1): ", Style.ACCENT))
        try:
            iterations = int(value) if value else 1
            if iterations < 1:
                raise ValueError
        except ValueError:
            self._write(self._style("  Error: Iterations must be an integer of at least 1.", StatusColor.ERROR, Style.BOLD))
            self._pause()
            return
        self.state.iterations = iterations

    def _round_progress(self, iteration: int, total: int) -> None:
        self._write(self._style(f"  Tur {iteration}/{total} işleniyor...", Style.MUTED))

    def _obfuscate(self) -> None:
        if self.state.input_path is None:
            self._write(self._style("  Error: Select a source file first.", StatusColor.ERROR, Style.BOLD))
            self._pause()
            return
        output_path = self.state.output_path or default_output_path(self.state.input_path)
        if output_path == self.state.input_path:
            self._write(self._style("  Error: Output path must differ from the source path.", StatusColor.ERROR, Style.BOLD))
            self._pause()
            return
        if output_path.exists():
            answer = self._input(
                self._style(f"  '{output_path.name}' zaten var. Üzerine yazılsın mı? [e/H]: ", Style.ACCENT)
            ).lower()
            if answer not in {"e", "evet", "y", "yes"}:
                self._write(self._style("  İşlem iptal edildi; mevcut dosya korunuyor.", Style.MUTED))
                self._pause()
                return

        try:
            source = self.state.input_path.read_text(encoding="utf-8")
            language = detect_language(self.state.input_path)
            config = ObfuscationConfig(
                seed=self.state.seed,
                rename_identifiers=self.state.rename_identifiers,
                encode_strings=self.state.encode_strings,
                transform_numbers=self.state.transform_numbers,
                insert_dead_code=self.state.insert_dead_code,
                iterations=self.state.iterations,
            )
            self._write(self._style("  Kod dönüştürülüyor...", Style.MUTED))
            result = Obfuscator(config).obfuscate(
                source, str(self.state.input_path), on_progress=self._round_progress,
            )
            if self.state.validate:
                self._write(self._style("  Orijinal ve dönüştürülmüş kod doğrulanıyor...", Style.MUTED))
                validation = validate_behavior(
                    source,
                    result,
                    language=language,
                    filename=self.state.input_path,
                )
                if not validation.equivalent:
                    if not validation.original_compiled:
                        detail = "Original source could not be compiled."
                    elif not validation.obfuscated_compiled:
                        detail = "Obfuscated source could not be compiled."
                    else:
                        detail = "Program exit status or output differs."
                    self._write(self._style(f"  Validation failed: {detail}", StatusColor.ERROR, Style.BOLD))
                    self._pause()
                    return
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(result, encoding="utf-8")
        except subprocess.TimeoutExpired:
            self._write(self._style("  Error: Validation timed out (5 seconds).", StatusColor.ERROR, Style.BOLD))
            self._pause()
            return
        except (OSError, SyntaxError, ValueError) as error:
            self._write(self._style(f"  Error: {error}", StatusColor.ERROR, Style.BOLD))
            self._pause()
            return

        self.state.output_path = output_path.resolve()
        self._write()
        self._write(self._style("  ✓ Obfuscation tamamlandı!", StatusColor.SUCCESS, Style.BOLD))
        self._write(self._style(f"  Çıktı: {self.state.output_path}", Style.TEXT))
        if self.state.validate:
            self._write(self._style("  ✓ Doğrulama geçti.", StatusColor.SUCCESS))
        self._pause()

    def run(self) -> int:
        selected = 0
        keys = ("1", "2", "3", "4", "5", "6", "7", "0")
        try:
            while True:
                self._header()
                self._main_menu(keys[selected])
                choice, selected = self._menu_choice(keys, selected)
                if choice is None:
                    continue
                if choice == "1":
                    self._choose_input()
                elif choice == "2":
                    self._choose_output()
                elif choice == "3":
                    self._passes_menu()
                elif choice == "4":
                    self._choose_seed()
                elif choice == "5":
                    self.state.validate = not self.state.validate
                elif choice == "6":
                    self._choose_iterations()
                elif choice == "7":
                    self._obfuscate()
                elif choice == "0":
                    self._header()
                    self._write(self._style("  Görüşürüz!", Style.TEXT, Style.BOLD))
                    return 0
        except (EOFError, KeyboardInterrupt):
            self._write(self._style("\n  İşlem iptal edildi.", Style.MUTED))
            return 130


def run_interactive() -> int:
    return TerminalUI().run()
