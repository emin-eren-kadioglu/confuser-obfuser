from __future__ import annotations

import ast

from obfuscator import ObfuscationConfig, Obfuscator
from obfuscator.validator import validate_behavior


def obfuscate(source: str, **overrides: object) -> str:
    config = ObfuscationConfig(seed=7, **overrides)
    return Obfuscator(config).obfuscate(source)


def test_full_pipeline_preserves_observable_behavior() -> None:
    source = '''\
"""module docs"""
def greet(name):
    prefix = "hello"
    count = 3
    result = [f"{prefix} {name}" for _ in range(count)]
    return "|".join(result)

print(greet("Ada"))
'''
    result = obfuscate(source)
    validation = validate_behavior(source, result)
    assert validation.equivalent, (validation.original, validation.obfuscated, result)
    assert ast.get_docstring(ast.parse(result)) == "module docs"
    assert "prefix" not in result
    assert "result" not in result


def test_closure_and_nonlocal_follow_outer_rename() -> None:
    source = '''\
def counter():
    value = 1
    def bump():
        nonlocal value
        value += 2
        return value
    return bump
c = counter()
print(c(), c())
'''
    result = obfuscate(source)
    assert validate_behavior(source, result).equivalent
    assert "nonlocal value" not in result


def test_dynamic_namespace_access_disables_renaming_for_scope() -> None:
    source = '''\
def show():
    secret = 42
    print(locals()["secret"])
show()
'''
    result = obfuscate(source, encode_strings=False)
    assert "secret =" in result
    assert validate_behavior(source, result).equivalent


def test_pattern_literals_stay_valid() -> None:
    source = '''\
def classify(value):
    match value:
        case 1:
            answer = "one"
        case "x":
            answer = "letter"
        case _:
            answer = "other"
    return answer
print(classify(1), classify("x"))
'''
    result = obfuscate(source)
    compile(result, "<test>", "exec")
    assert validate_behavior(source, result).equivalent


def test_seed_is_reproducible() -> None:
    source = "def f():\n    local = 10\n    return local\nprint(f())\n"
    assert obfuscate(source) == obfuscate(source)


def test_walrus_in_comprehension_targets_enclosing_scope() -> None:
    source = '''\
def last():
    current = 0
    values = [current := item for item in range(4)]
    return current, values
print(last())
'''
    result = obfuscate(source)
    assert validate_behavior(source, result).equivalent


def test_future_annotations_keep_their_textual_meaning() -> None:
    source = '''\
from __future__ import annotations
def convert(value: "Widget") -> "Result":
    local: "Widget" = value
    return local
print(convert.__annotations__)
'''
    result = obfuscate(source)
    assert validate_behavior(source, result).equivalent


def test_validation_does_not_wait_for_interactive_input() -> None:
    source = '''\
try:
    value = input("Value: ")
    print(value)
except EOFError:
    print("no input")
'''
    result = obfuscate(source)
    validation = validate_behavior(source, result, timeout=1.0)
    assert validation.equivalent
    assert validation.original.stdout == b"Value: no input\n"
