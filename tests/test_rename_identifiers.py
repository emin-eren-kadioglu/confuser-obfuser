from __future__ import annotations

import ast
import textwrap
import unittest

from obfuscator import ObfuscationConfig, Obfuscator
from obfuscator.validator import validate_behavior


class RenameIdentifiersTests(unittest.TestCase):
    def transform(self, source: str) -> tuple[str, ast.Module]:
        source = textwrap.dedent(source)
        result = Obfuscator(ObfuscationConfig(
            seed=42, encode_strings=False, transform_numbers=False, insert_dead_code=False,
        )).obfuscate(source)
        check = validate_behavior(source, result)
        self.assertEqual(check.original.returncode, 0, check.original.stderr)
        self.assertTrue(check.equivalent, (result, check))
        return result, ast.parse(result)

    def test_function_parameters_and_keyword_calls_are_renamed(self) -> None:
        _, tree = self.transform('''
            def add(first, second=5):
                total = first + second
                return total
            print(add(first=7, second=3))
        ''')
        definition = tree.body[0]
        call = tree.body[1].value.args[0]
        self.assertNotEqual(definition.name, "add")
        self.assertEqual(call.func.id, definition.name)
        parameter_names = [arg.arg for arg in definition.args.args]
        self.assertNotIn("first", parameter_names)
        self.assertNotIn("second", parameter_names)
        self.assertEqual([kw.arg for kw in call.keywords], parameter_names)

    def test_recursive_keyword_calls(self) -> None:
        result, _ = self.transform('''
            def factorial(amount):
                if amount < 2:
                    return 1
                return amount * factorial(amount=amount - 1)
            print(factorial(amount=5))
        ''')
        self.assertNotIn("factorial", result)
        self.assertNotIn("amount", result)

    def test_async_functions_and_keyword_only_parameters(self) -> None:
        result, _ = self.transform('''
            import asyncio
            async def greet(person, *, ending="!"):
                return person + ending
            print(asyncio.run(greet(person="Ada", ending="?")))
        ''')
        self.assertNotIn("person", result)
        self.assertNotIn("ending", result)
        self.assertNotIn("greet", result)

    def test_parameter_kinds_and_positional_only_keyword_capture(self) -> None:
        _, tree = self.transform('''
            def collect(head, /, normal=2, *items, extra=3, **options):
                return head, normal, items, extra, options
            print(collect(1, 4, 8, 9, extra=5, head=100, free=7))
        ''')
        definition = tree.body[0]
        self.assertNotEqual(definition.args.posonlyargs[0].arg, "head")
        self.assertNotEqual(definition.args.vararg.arg, "items")
        self.assertNotEqual(definition.args.kwarg.arg, "options")
        self.assertEqual(tree.body[1].value.args[0].keywords[1].arg, "head")

    def test_nested_closure_defaults_and_nonlocal(self) -> None:
        result, _ = self.transform('''
            def outer(initial):
                value = initial
                def inner(step=value):
                    nonlocal initial
                    value = 10
                    initial += step
                    return initial + value
                return inner(step=2), inner()
            print(outer(initial=4))
        ''')
        self.assertNotIn("initial", result)
        self.assertNotIn("step", result)

    def test_global_function_references(self) -> None:
        result, _ = self.transform('''
            def increment(value):
                return value + 1
            def caller():
                global increment
                return increment(value=4)
            print(caller())
        ''')
        self.assertNotIn("increment", result)
        self.assertIn("global _obf_", result)

    def test_function_created_through_global_declaration(self) -> None:
        result, _ = self.transform('''
            def setup():
                global calculate
                def calculate(value):
                    return value + 1
            setup()
            print(calculate(value=4))
        ''')
        self.assertNotIn("calculate", result)

    def test_shadowed_callee_does_not_rewrite_external_keywords(self) -> None:
        self.transform('''
            def work(value):
                return value + 1
            def apply(work):
                return work(value=3)
            external = lambda value: value * 2
            print(work(value=2), apply(work=external))
        ''')

    def test_alias_and_callback_preserve_keyword_contract(self) -> None:
        _, tree = self.transform('''
            def greet(person):
                return person.upper()
            alias = greet
            def use(callback):
                return callback(person="Ada")
            print(alias(person="Bob"), use(callback=greet))
        ''')
        self.assertNotEqual(tree.body[0].name, "greet")
        self.assertEqual(tree.body[0].args.args[0].arg, "person")

    def test_dynamic_keyword_unpack_preserves_parameter_names(self) -> None:
        _, tree = self.transform('''
            def greet(person, *, suffix="!"):
                return person + suffix
            options = {"person": "Ada", "suffix": "?"}
            print(greet(**options), greet(person="Bob"))
        ''')
        self.assertEqual(tree.body[0].args.args[0].arg, "person")
        self.assertEqual(tree.body[0].args.kwonlyargs[0].arg, "suffix")

    def test_methods_and_decorated_interfaces_are_preserved(self) -> None:
        _, tree = self.transform('''
            def identity(function):
                return function
            @identity
            def greet(person):
                result = "Hi " + person
                return result
            class Box:
                def scale(self, amount):
                    result = amount * 2
                    return result
            print(greet(person="Ada"), Box().scale(amount=3))
        ''')
        self.assertEqual(tree.body[1].name, "greet")
        self.assertEqual(tree.body[1].args.args[0].arg, "person")
        self.assertEqual(tree.body[2].body[0].name, "scale")
        self.assertEqual(tree.body[2].body[0].args.args[1].arg, "amount")

    def test_imported_function_keywords_are_not_changed(self) -> None:
        self.transform('''
            from json import dumps
            def render(value, *, flag):
                return dumps(value, ensure_ascii=flag)
            print(render(value={"word": "ç"}, flag=False))
        ''')

    def test_reassigned_function_preserves_parameters(self) -> None:
        _, tree = self.transform('''
            def choose(value):
                return value
            choose = lambda value: value * 3
            print(choose(value=4))
        ''')
        self.assertEqual(tree.body[0].args.args[0].arg, "value")

    def test_multiple_definitions_preserve_keyword_contract(self) -> None:
        _, tree = self.transform('''
            def choose(value):
                return value
            if True:
                def choose(value):
                    return value + 1
            print(choose(value=4))
        ''')
        self.assertEqual(tree.body[0].args.args[0].arg, "value")

    def test_immediate_lambda_parameters(self) -> None:
        result, _ = self.transform('''
            print((lambda amount: amount * 2)(amount=5))
        ''')
        self.assertNotIn("amount", result)

    def test_class_namespace_collision_does_not_break_global_lookup(self) -> None:
        self.transform('''
            def helper(value):
                return value + 1
            class Namespace:
                helper = helper
            print(Namespace.helper(value=4))
        ''')

    def test_method_closes_over_renamed_outer_parameter(self) -> None:
        self.transform('''
            def outer(initial):
                class Box:
                    def read(self):
                        return initial
                return Box().read()
            print(outer(initial=9))
        ''')

    def test_explicit_module_exports_are_preserved(self) -> None:
        _, tree = self.transform('''
            __all__ = ["greet"]
            def greet(person):
                return "Hi " + person
            print(greet(person="Ada"))
        ''')
        self.assertEqual(tree.body[1].name, "greet")
        self.assertEqual(tree.body[1].args.args[0].arg, "person")

    def test_reflective_names_are_preserved(self) -> None:
        _, tree = self.transform('''
            def greet(person):
                return locals()["person"]
            print(greet(person="Ada"), globals()["greet"].__name__)
        ''')
        self.assertEqual(tree.body[0].name, "greet")
        self.assertEqual(tree.body[0].args.args[0].arg, "person")

    def test_disable_rename_keeps_function_and_parameter_names(self) -> None:
        result = Obfuscator(ObfuscationConfig(rename_identifiers=False)).obfuscate(
            "def add(first, second):\n    return first + second\n"
        )
        self.assertIn("def add(first, second)", result)

    def test_aliased_namespace_access_is_protected(self) -> None:
        _, tree = self.transform('''
            def greet(person):
                return person
            namespace = globals
            print(namespace()["greet"](person="Ada"))
        ''')
        self.assertEqual(tree.body[0].name, "greet")

    def test_generated_names_do_not_collide_with_existing_parameters(self) -> None:
        self.transform('''
            def add(first, _obf_1OhbVrp=5):
                return first + _obf_1OhbVrp
            print(add(first=7, _obf_1OhbVrp=3))
        ''')
