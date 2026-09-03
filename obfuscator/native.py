"""C and Go transformations layered after AST/type-aware renaming.

This module deliberately avoids regular-expression source replacement. Clang or
Go type information handles identifiers; a small lexer preserves comments,
whitespace, directives and literals for the remaining structural passes.
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass

from .c_ast import rename_c_identifiers
from .go_ast import rename_go_identifiers
from .languages import SourceLanguage


@dataclass
class Token:
    kind: str
    text: str


@dataclass(frozen=True)
class FunctionRegion:
    name_index: int
    parameters_open: int
    parameters_close: int
    body_open: int
    body_close: int
    is_method: bool = False


_C_KEYWORDS = frozenset(
    "auto break case char const continue default do double else enum extern float for goto if inline int "
    "long register restrict return short signed sizeof static struct switch typedef union unsigned void "
    "volatile while _Alignas _Alignof _Atomic _Bool _Complex _Generic _Imaginary _Noreturn _Static_assert "
    "_Thread_local".split()
)
_IGNORED = frozenset({"space", "comment", "directive"})
_MULTI_OPERATORS = (
    "<<=", ">>=", "...", "&^=", "->", "++", "--", "&&", "||", "<=", ">=", "==", "!=", ":=",
    "<<", ">>", "&^", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<-",
)


def tokenize(source: str, language: SourceLanguage) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    at_line_start = True
    length = len(source)
    while index < length:
        char = source[index]
        if char.isspace():
            end = index + 1
            while end < length and source[end].isspace():
                end += 1
            text = source[index:end]
            tokens.append(Token("space", text))
            if "\n" in text:
                at_line_start = True
            index = end
            continue
        if language is SourceLanguage.C and char == "#" and at_line_start:
            end = index
            while end < length:
                newline = source.find("\n", end)
                if newline < 0:
                    end = length
                    break
                end = newline + 1
                before = source[index:newline].rstrip()
                if not before.endswith("\\"):
                    break
            tokens.append(Token("directive", source[index:end]))
            at_line_start = True
            index = end
            continue
        at_line_start = False
        if source.startswith("//", index):
            end = source.find("\n", index)
            end = length if end < 0 else end
            tokens.append(Token("comment", source[index:end]))
            index = end
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            end = length if end < 0 else end + 2
            text = source[index:end]
            tokens.append(Token("comment", text))
            at_line_start = text.endswith("\n")
            index = end
            continue
        if char in {'"', "'", "`"}:
            quote = char
            end = index + 1
            if quote == "`":
                closing = source.find("`", end)
                end = length if closing < 0 else closing + 1
            else:
                while end < length:
                    if source[end] == "\\":
                        end += 2
                    elif source[end] == quote:
                        end += 1
                        break
                    else:
                        end += 1
            tokens.append(Token("string" if quote != "'" else "char", source[index:end]))
            index = end
            continue
        if char.isalpha() or char == "_" or (language is SourceLanguage.GO and ord(char) >= 128):
            end = index + 1
            while end < length and (
                source[end].isalnum() or source[end] == "_" or (language is SourceLanguage.GO and ord(source[end]) >= 128)
            ):
                end += 1
            tokens.append(Token("identifier", source[index:end]))
            index = end
            continue
        if char.isdigit() or (char == "." and index + 1 < length and source[index + 1].isdigit()):
            end = index + 1
            while end < length:
                if source[end] in "+-" and source[end - 1] in "eEpP":
                    end += 1
                elif source[end].isalnum() or source[end] in "._'":
                    end += 1
                else:
                    break
            tokens.append(Token("number", source[index:end]))
            index = end
            continue
        operator = next((value for value in _MULTI_OPERATORS if source.startswith(value, index)), char)
        tokens.append(Token("operator", operator))
        index += len(operator)
    return tokens


def _significant(tokens: list[Token]) -> list[int]:
    return [index for index, token in enumerate(tokens) if token.kind not in _IGNORED]


def _matching_pairs(tokens: list[Token]) -> dict[int, int]:
    pairs: dict[int, int] = {}
    stack: list[tuple[str, int]] = []
    closing = {")": "(", "]": "[", "}": "{"}
    for index in _significant(tokens):
        text = tokens[index].text
        if text in {"(", "[", "{"}:
            stack.append((text, index))
        elif text in closing:
            if not stack or stack[-1][0] != closing[text]:
                raise SyntaxError(f"unbalanced delimiter near {text!r}")
            _, opening = stack.pop()
            pairs[opening] = index
            pairs[index] = opening
    if stack:
        raise SyntaxError(f"unclosed delimiter {stack[-1][0]!r}")
    return pairs


def _position_map(tokens: list[Token]) -> tuple[list[int], dict[int, int]]:
    significant = _significant(tokens)
    return significant, {token_index: position for position, token_index in enumerate(significant)}


def _next(significant: list[int], positions: dict[int, int], index: int, offset: int = 1) -> int | None:
    position = positions.get(index)
    target = -1 if position is None else position + offset
    return significant[target] if 0 <= target < len(significant) else None


def _previous(significant: list[int], positions: dict[int, int], index: int, offset: int = 1) -> int | None:
    return _next(significant, positions, index, -offset)


def _name(rng: random.Random, used: set[str], prefix: str = "_cf_") -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        candidate = prefix + "".join(rng.choice(alphabet) for _ in range(9))
        if candidate not in used:
            used.add(candidate)
            return candidate


def _find_c_functions(tokens: list[Token], pairs: dict[int, int]) -> list[FunctionRegion]:
    significant, positions = _position_map(tokens)
    regions: list[FunctionRegion] = []
    for name_index in significant:
        token = tokens[name_index]
        if token.kind != "identifier" or token.text in _C_KEYWORDS:
            continue
        opening = _next(significant, positions, name_index)
        if opening is None or tokens[opening].text != "(" or opening not in pairs:
            continue
        closing = pairs[opening]
        after = _next(significant, positions, closing)
        if after is None or tokens[after].text != "{" or after not in pairs:
            continue
        before = _previous(significant, positions, name_index)
        if before is None or tokens[before].text in {".", "->", ")", "]"}:
            continue
        regions.append(FunctionRegion(name_index, opening, closing, after, pairs[after]))
    return regions


def _find_go_functions(tokens: list[Token], pairs: dict[int, int]) -> list[FunctionRegion]:
    significant, positions = _position_map(tokens)
    regions: list[FunctionRegion] = []
    for func_index in significant:
        if tokens[func_index].text != "func":
            continue
        cursor = _next(significant, positions, func_index)
        is_method = cursor is not None and tokens[cursor].text == "("
        if is_method:
            cursor = _next(significant, positions, pairs.get(cursor, cursor))
        if cursor is None or tokens[cursor].kind != "identifier":
            continue  # function literal
        name_index = cursor
        opening = _next(significant, positions, name_index)
        if opening is not None and tokens[opening].text == "[" and opening in pairs:
            opening = _next(significant, positions, pairs[opening])
        if opening is None or tokens[opening].text != "(" or opening not in pairs:
            continue
        closing = pairs[opening]
        cursor = _next(significant, positions, closing)
        while cursor is not None and tokens[cursor].text != "{":
            if tokens[cursor].text == ";":
                cursor = None
                break
            cursor = _next(significant, positions, cursor)
        if cursor is not None and cursor in pairs:
            regions.append(FunctionRegion(name_index, opening, closing, cursor, pairs[cursor], is_method))
    return regions


def _encoded_literal(text: str, language: SourceLanguage, rng: random.Random) -> str | None:
    if len(text) < 4 or not (text.startswith('"') and text.endswith('"')) or "\\" in text:
        return None
    raw = text[1:-1].encode("utf-8")
    if not raw:
        return None
    chunks: list[bytes] = []
    cursor = 0
    while cursor < len(raw):
        size = rng.randint(1, min(4, len(raw) - cursor))
        chunks.append(raw[cursor:cursor + size])
        cursor += size
    encoded = ['"' + "".join(f"\\x{byte:02x}" for byte in chunk) + '"' for chunk in chunks]
    return ("(" + " + ".join(encoded) + ")") if language is SourceLanguage.GO else "".join(encoded)


def _encode_strings(tokens: list[Token], language: SourceLanguage, rng: random.Random) -> None:
    significant, positions = _position_map(tokens)
    import_depth = 0
    for index in significant:
        token = tokens[index]
        if language is SourceLanguage.GO:
            previous = _previous(significant, positions, index)
            previous_text = tokens[previous].text if previous is not None else ""
            if previous_text == "import" and token.text == "(":
                import_depth += 1
            if import_depth and token.text == ")":
                import_depth -= 1
                continue
            if token.kind == "string" and (previous_text == "import" or import_depth):
                continue
        if token.kind == "string":
            previous = _previous(significant, positions, index)
            if language is SourceLanguage.C and previous is not None and tokens[previous].text in {"L", "u", "U", "u8"}:
                continue
            if language is SourceLanguage.GO:
                previous_text = tokens[previous].text if previous is not None else ""
                if previous_text not in {"(", "[", "{", ",", "=", ":=", "return", "case", ":", "+"}:
                    continue
            replacement = _encoded_literal(token.text, language, rng)
            if replacement is not None:
                token.text = replacement


def _transform_numbers(tokens: list[Token], rng: random.Random) -> None:
    for token in tokens:
        if (
            token.kind != "number"
            or not token.text.isascii()
            or not token.text.isdecimal()
            or (len(token.text) > 1 and token.text.startswith("0"))
        ):
            continue
        value = int(token.text)
        # Larger C literals may have a wider type than their generated operands.
        # Preserve them instead of introducing signed-int overflow.
        if value > 2_147_483_647:
            continue
        factor = rng.randint(2, 9)
        quotient, remainder = divmod(value, factor)
        token.text = f"(({quotient} * {factor}) + {remainder})"


def _insert_dead_code(tokens: list[Token], language: SourceLanguage, rng: random.Random) -> None:
    pairs = _matching_pairs(tokens)
    regions = _find_c_functions(tokens, pairs) if language is SourceLanguage.C else _find_go_functions(tokens, pairs)
    used = {token.text for token in tokens if token.kind == "identifier"}
    for region in reversed(regions):
        variable = _name(rng, used, "_cf_dead_")
        value = rng.randint(1000, 9999)
        if language is SourceLanguage.C:
            code = f"\n    if (0) {{ volatile int {variable} = {value}; (void){variable}; }}"
        else:
            code = f"\n\tif 0 != 0 {{ {variable} := {value}; _ = {variable} }}\n\t"
        tokens.insert(region.body_open + 1, Token("space", code))


def obfuscate_native(
    source: str,
    language: SourceLanguage,
    *,
    rng: random.Random,
    rename_identifiers: bool,
    encode_strings: bool,
    transform_numbers: bool,
    insert_dead_code: bool,
    filename: str = "<unknown>",
    preserve_interfaces: bool = False,
) -> str:
    """Apply one structural pass round to C or Go source."""
    if language not in {SourceLanguage.C, SourceLanguage.GO}:
        raise ValueError(f"native transformer does not support {language.value}")
    if rename_identifiers and language is SourceLanguage.C:
        source = rename_c_identifiers(source, filename, rng, preserve_interfaces=preserve_interfaces)
    elif rename_identifiers and language is SourceLanguage.GO:
        source = rename_go_identifiers(source, filename, rng, preserve_interfaces=preserve_interfaces)
    tokens = tokenize(source, language)
    _matching_pairs(tokens)
    if encode_strings:
        _encode_strings(tokens, language, rng)
    if transform_numbers:
        _transform_numbers(tokens, rng)
    if insert_dead_code:
        _insert_dead_code(tokens, language, rng)
    result = "".join(token.text for token in tokens)
    _matching_pairs(tokenize(result, language))
    return result
