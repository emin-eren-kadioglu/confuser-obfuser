from __future__ import annotations

import io
import shutil
import tempfile
import unittest
from pathlib import Path

from obfuscator import ObfuscationConfig, Obfuscator, SourceLanguage, detect_language
from obfuscator.cli import main
from obfuscator.languages import default_output_path
from obfuscator.terminal_ui import TerminalUI
from obfuscator.validator import validate_behavior


C_SOURCE = r'''#include <stdio.h>

struct Pair { int left; int right; };

int add(int left, int right) {
    int first = left, second = right;
    struct Pair pair = {.left = first, .right = second};
    return pair.left + pair.right;
}

int main(void) {
    printf("total=%d", add(2, 3));
    return 0;
}
'''


GO_SOURCE = '''package main

import "fmt"

func add(left, right int) int {
    total := left + right
    fmt.Println("total", total)
    return total
}

func main() {
    add(2, 3)
}
'''


class LanguageDetectionTests(unittest.TestCase):
    def test_supported_extensions_are_detected_case_insensitively(self) -> None:
        expectations = {
            "demo.py": SourceLanguage.PYTHON,
            "demo.PYW": SourceLanguage.PYTHON,
            "demo.C": SourceLanguage.C,
            "demo.GO": SourceLanguage.GO,
        }
        for filename, expected in expectations.items():
            with self.subTest(filename=filename):
                self.assertIs(detect_language(filename), expected)

    def test_unsupported_extension_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported source extension"):
            detect_language("demo.rs")

    def test_default_output_keeps_the_language_extension(self) -> None:
        for filename in ("demo.py", "demo.pyw", "demo.c", "demo.go"):
            with self.subTest(filename=filename):
                self.assertEqual(default_output_path(Path(filename)).name, f"demo.obf{Path(filename).suffix}")


class NativeObfuscatorTests(unittest.TestCase):
    def config(self, **overrides: object) -> ObfuscationConfig:
        values = dict(seed=42)
        values.update(overrides)
        return ObfuscationConfig(**values)

    def test_c_renames_functions_parameters_and_locals_without_touching_fields(self) -> None:
        result = Obfuscator(self.config()).obfuscate(C_SOURCE, "demo.c")
        self.assertNotIn("int add(", result)
        self.assertNotIn("int left, int right", result)
        self.assertNotIn("int first", result)
        self.assertIn(".left", result)
        self.assertIn(".right", result)
        self.assertIn("#include <stdio.h>", result)
        self.assertIn("if (0)", result)
        self.assertIn("\\x", result)

    @unittest.skipUnless(shutil.which("cc"), "C compiler is not installed")
    def test_c_output_compiles_and_matches_behavior(self) -> None:
        result = Obfuscator(self.config()).obfuscate(C_SOURCE, "demo.c")
        validation = validate_behavior(C_SOURCE, result, language=SourceLanguage.C, filename="demo.c")
        self.assertTrue(validation.original_compiled, validation.original.stderr)
        self.assertTrue(validation.obfuscated_compiled, validation.obfuscated.stderr)
        self.assertTrue(validation.equivalent, validation)

    def test_c_preserves_comments_prefixed_directives_and_octal_numbers(self) -> None:
        source = "  #define LIMIT 07\nint main(void) { /* LIMIT */ return LIMIT; }\n"
        result = Obfuscator(self.config(rename_identifiers=False, encode_strings=False, insert_dead_code=False)).obfuscate(
            source, "demo.c",
        )
        self.assertIn("  #define LIMIT 07", result)
        self.assertIn("/* LIMIT */", result)
        self.assertIn("return LIMIT", result)

    @unittest.skipUnless(shutil.which("clang"), "Clang is not installed")
    def test_c_ast_offsets_remain_correct_after_utf8_text(self) -> None:
        source = '/* İstanbul, çığ */\nint add(int value) { return value + 1; }\nint main(void) { return add(2) == 3 ? 0 : 1; }\n'
        result = Obfuscator(self.config(encode_strings=False, insert_dead_code=False)).obfuscate(source, "demo.c")
        self.assertIn("/* İstanbul, çığ */", result)
        self.assertNotIn("int add(", result)
        self.assertTrue(validate_behavior(source, result, language=SourceLanguage.C).equivalent)

    @unittest.skipUnless(shutil.which("cc"), "C compiler is not installed")
    def test_c_function_names_do_not_collide_with_struct_fields(self) -> None:
        source = '''
struct Box { int calculate; };
int calculate(int value) { return value + 1; }
int main(void) {
    struct Box box = {.calculate = 8};
    return calculate(box.calculate) == 9 ? 0 : 1;
}
'''
        result = Obfuscator(self.config()).obfuscate(source, "demo.c")
        self.assertIn("int calculate;", result)
        self.assertIn(".calculate", result)
        self.assertTrue(validate_behavior(source, result, language=SourceLanguage.C).equivalent)

    @unittest.skipUnless(shutil.which("go"), "Go toolchain is not installed")
    def test_go_renames_free_function_parameters_and_locals(self) -> None:
        result = Obfuscator(self.config()).obfuscate(GO_SOURCE, "demo.go")
        self.assertNotIn("func add(", result)
        self.assertNotIn("left, right int", result)
        self.assertNotIn("total :=", result)
        self.assertIn('import "fmt"', result)
        self.assertIn("fmt.Println", result)
        self.assertIn("if false", result)
        self.assertIn("\\x", result)

    @unittest.skipUnless(shutil.which("go"), "Go toolchain is not installed")
    def test_go_output_compiles_and_matches_behavior(self) -> None:
        result = Obfuscator(self.config()).obfuscate(GO_SOURCE, "demo.go")
        validation = validate_behavior(GO_SOURCE, result, language=SourceLanguage.GO, filename="demo.go")
        self.assertTrue(validation.original_compiled, validation.original.stderr)
        self.assertTrue(validation.obfuscated_compiled, validation.obfuscated.stderr)
        self.assertTrue(validation.equivalent, validation)

    @unittest.skipUnless(shutil.which("go"), "Go toolchain is not installed")
    def test_go_does_not_rewrite_struct_tags_or_methods(self) -> None:
        source = '''package sample
type Item struct { Name string "json" }
func (item Item) Label(prefix string) string { return prefix + item.Name }
'''
        result = Obfuscator(self.config()).obfuscate(source, "demo.go")
        self.assertIn('Name string "json"', result)
        self.assertIn(") Label(", result)
        self.assertIn(".Name", result)

    @unittest.skipUnless(shutil.which("go"), "Go toolchain is not installed")
    def test_go_free_function_name_does_not_rename_same_named_method_or_field(self) -> None:
        source = '''package sample
type Item struct { Label string }
func Label(value string) string { return value }
func (item Item) LabelText() string { return item.Label }
'''
        result = Obfuscator(self.config()).obfuscate(source, "demo.go")
        self.assertIn("Label string", result)
        self.assertIn("LabelText()", result)
        self.assertIn(".Label", result)

    @unittest.skipUnless(shutil.which("go"), "Go toolchain is not installed")
    def test_go_preserves_symbols_used_by_sibling_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-go-package-") as directory:
            root = Path(directory)
            target = root / "first.go"
            source = "package sample\nfunc Shared(value int) int { return value + 1 }\n"
            target.write_text(source, encoding="utf-8")
            (root / "second.go").write_text(
                "package sample\nfunc Use() int { return Shared(4) }\n", encoding="utf-8",
            )
            result = Obfuscator(self.config()).obfuscate(source, str(target))
        self.assertIn("func Shared(", result)

    def test_native_seed_is_reproducible(self) -> None:
        first = Obfuscator(self.config(rename_identifiers=False)).obfuscate(GO_SOURCE, "demo.go")
        repeat = Obfuscator(self.config(rename_identifiers=False)).obfuscate(GO_SOURCE, "demo.go")
        other = Obfuscator(self.config(seed=7, rename_identifiers=False)).obfuscate(GO_SOURCE, "demo.go")
        self.assertEqual(first, repeat)
        self.assertNotEqual(first, other)

    def test_disabling_all_native_passes_preserves_source_exactly(self) -> None:
        config = self.config(
            rename_identifiers=False,
            encode_strings=False,
            transform_numbers=False,
            insert_dead_code=False,
        )
        self.assertEqual(Obfuscator(config).obfuscate(C_SOURCE, "demo.c"), C_SOURCE)
        self.assertEqual(Obfuscator(config).obfuscate(GO_SOURCE, "demo.go"), GO_SOURCE)

    def test_cli_writes_c_and_go_outputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-language-test-") as directory:
            root = Path(directory)
            for name, source in (("demo.c", C_SOURCE), ("demo.go", GO_SOURCE)):
                input_path = root / name
                output_path = default_output_path(input_path)
                input_path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    arguments = [str(input_path), "-o", str(output_path), "--seed", "42"]
                    if name.endswith(".go") and shutil.which("go") is None:
                        arguments.append("--no-rename")
                    self.assertEqual(main(arguments), 0)
                    self.assertTrue(output_path.is_file())

    def test_cli_rejects_cross_language_output_extension(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-language-test-") as directory:
            source = Path(directory) / "demo.c"
            source.write_text(C_SOURCE, encoding="utf-8")
            self.assertEqual(main([str(source), "-o", str(source.with_suffix(".go"))]), 2)

    def test_terminal_selects_language_and_automatic_output_name(self) -> None:
        with tempfile.TemporaryDirectory(prefix="confuser-language-test-") as directory:
            source = Path(directory) / "demo.go"
            source.write_text(GO_SOURCE, encoding="utf-8")
            ui = TerminalUI(io.StringIO(str(source) + "\n"), io.StringIO())
            ui._choose_input()
            self.assertEqual(ui.state.input_path, source.resolve())
            self.assertEqual(ui.state.output_path, source.with_name("demo.obf.go").resolve())
            ui._main_menu("1")
            self.assertIn("[Go]", ui.stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
