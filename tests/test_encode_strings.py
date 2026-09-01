from __future__ import annotations

import ast
import sys
import textwrap
import unittest

from obfuscator import ObfuscationConfig, Obfuscator
from obfuscator.validator import validate_behavior


class EncodeStringsTests(unittest.TestCase):
    def transform(self, source: str, *, seed: int = 42) -> tuple[str, ast.Module]:
        source = textwrap.dedent(source)
        result = Obfuscator(ObfuscationConfig(
            seed=seed, rename_identifiers=False, transform_numbers=False, insert_dead_code=False,
        )).obfuscate(source)
        check = validate_behavior(source, result)
        self.assertEqual(check.original.returncode, 0, check.original.stderr)
        self.assertTrue(check.equivalent, (result, check))
        return result, ast.parse(result)

    def test_fragments_are_assigned_shuffled_and_used_by_print(self) -> None:
        result, tree = self.transform('print("Hata: yanlış giriş")\n')
        self.assertNotIn("Hata: yanlış giriş", result)
        self.assertIsInstance(tree.body[0], ast.Import)
        self.assertEqual(tree.body[0].names[0].name, "base64")
        fragments = [node for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)]
        self.assertGreaterEqual(len(fragments), 2)
        self.assertTrue(all(isinstance(node.value.value, str) for node in fragments))
        decoded = next(node for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call))
        joined_names = [node.id for node in decoded.value.func.value.args[0].args[0].elts]
        self.assertCountEqual(joined_names, [node.targets[0].id for node in fragments])
        self.assertNotEqual(joined_names, [node.targets[0].id for node in fragments])
        self.assertEqual(tree.body[-1].value.args[0].id, decoded.targets[0].id)

    def test_f_string_literal_is_replaced_by_a_variable(self) -> None:
        result, tree = self.transform('''
            hata = ValueError("yanlış giriş")
            print(f"Hata: {hata}")
        ''')
        self.assertNotIn("Hata:", result)
        joined = tree.body[-1].value.args[0]
        self.assertIsInstance(joined, ast.JoinedStr)
        self.assertTrue(all(isinstance(node, ast.FormattedValue) for node in joined.values))
        self.assertIsInstance(joined.values[0].value, ast.Name)

    def test_f_string_conversion_format_spec_and_braces(self) -> None:
        self.transform('''
            number = 12.345
            width = 12
            text = "çığ"
            print(f"Değer: {number:>{width}.2f}; metin: {text!r:^10}; {{bitti}}")
        ''')

    def test_f_string_debug_labels_and_evaluation_order(self) -> None:
        self.transform('''
            calls = []
            def step(value):
                calls.append(value)
                return value
            print(f"Önce {step(1)=}, sonra {step(2)=}")
            print(calls)
        ''')

    def test_unicode_null_and_surrogate_round_trip(self) -> None:
        values = ["İstanbul çığ 🐍", "\x00\n\r\t", "\ud800", "\\'\"{}%", "a"]
        source = "\n".join(f"print(repr({value!r}))" for value in values)
        self.transform(source)

    def test_docstrings_remain_real_docstrings(self) -> None:
        _, tree = self.transform('''
            """module docs"""
            def show():
                """function docs"""
                return "payload"
            class Box:
                """class docs"""
            print(__doc__, show.__doc__, Box.__doc__, show())
        ''')
        self.assertEqual(ast.get_docstring(tree), "module docs")
        definition = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
        self.assertEqual(ast.get_docstring(definition), "function docs")

    def test_pool_follows_future_imports_and_preserves_annotations(self) -> None:
        _, tree = self.transform('''
            """module docs"""
            from __future__ import annotations
            from __future__ import generator_stop
            def convert(value: "Widget") -> "Result":
                return "payload"
            print(convert.__annotations__, convert(None))
        ''')
        self.assertEqual(tree.body[1].module, "__future__")
        self.assertEqual(tree.body[2].module, "__future__")
        self.assertIsInstance(tree.body[3], ast.Import)

    def test_match_values_and_mapping_keys_stay_literal(self) -> None:
        _, tree = self.transform('''
            def classify(value):
                match value:
                    case {"kind": "error", "message": text}:
                        return f"Hata: {text}"
                    case "ok":
                        return "başarılı"
                    case _:
                        return "diğer"
            print(classify({"kind": "error", "message": "x"}), classify("ok"))
        ''')
        mapping = next(node for node in ast.walk(tree) if isinstance(node, ast.MatchMapping))
        self.assertTrue(all(isinstance(node, ast.Constant) for node in mapping.keys))

    def test_identical_strings_share_one_decoded_variable(self) -> None:
        _, tree = self.transform('print("again", "again")\n')
        arguments = tree.body[-1].value.args
        self.assertEqual(arguments[0].id, arguments[1].id)
        decode_calls = [node for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr == "b64decode"]
        self.assertEqual(len(decode_calls), 1)

    def test_seed_is_reproducible_and_changes_fragment_layout(self) -> None:
        source = 'print("Hata: örnek mesaj")'
        first, _ = self.transform(source, seed=42)
        repeat, _ = self.transform(source, seed=42)
        other, _ = self.transform(source, seed=7)
        self.assertEqual(first, repeat)
        self.assertNotEqual(first, other)

    def test_generated_names_do_not_shadow_existing_identifiers(self) -> None:
        self.transform('''
            def show(_obf_s1OhbVrp=5):
                return "hello", _obf_s1OhbVrp
            print(show())
        ''')

    def test_builtins_and_base64_name_can_be_shadowed(self) -> None:
        self.transform('''
            base64 = None
            bytes = None
            str = None
            chr = None
            print("Hata: örnek")
        ''')

    def test_empty_strings_and_bytes_do_not_create_a_pool(self) -> None:
        result, tree = self.transform('print("", b"bytes", 5, True)')
        self.assertNotIn("base64", result)
        self.assertEqual(len(tree.body), 1)

    def test_no_strings_switch_keeps_plain_f_string(self) -> None:
        source = 'value = 3\nprint(f"Hata: {value}")'
        result = Obfuscator(ObfuscationConfig(encode_strings=False)).obfuscate(source)
        self.assertIn("Hata:", result)
        self.assertNotIn("b64decode", result)

    @unittest.skipIf(sys.version_info < (3, 12), "type aliases require Python 3.12+")
    def test_lazy_type_alias_is_preserved(self) -> None:
        self.transform('''
            from typing import Literal
            type Choice = Literal["yes", "no"]
            print(Choice.__value__, "payload")
        ''')

    @unittest.skipIf(sys.version_info < (3, 14), "template strings require Python 3.14+")
    def test_template_string_metadata_is_preserved(self) -> None:
        self.transform('''
            value = "Ada"
            template = t"Hi {value}"
            print(template.strings, template.interpolations[0].expression)
        ''')
