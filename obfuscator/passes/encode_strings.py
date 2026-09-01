"""Store strings as shuffled Base64 fragments and reference decoded variables."""

from __future__ import annotations

import ast
import base64
import random
import string

from .base import ObfuscationPass


class _StringTransformer(ast.NodeTransformer):
    def __init__(self, tree: ast.Module, rng: random.Random) -> None:
        self.rng = rng
        self.protected: set[int] = set()
        self.used: set[str] = set()
        self.counter = 0
        self.decoder_name: str | None = None
        self.pool: dict[str, str] = {}
        self.fragments: list[ast.Assign] = []
        self.decoded: list[ast.Assign] = []

        for node in ast.walk(tree):
            # Include bindings stored in string fields, not just ast.Name.
            for field in ("id", "arg", "name", "asname"):
                name = getattr(node, field, None)
                if isinstance(name, str):
                    self.used.add(name)
                    self.used.add(name.split(".", 1)[0])
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                self.used.update(node.names)
            if isinstance(node, ast.MatchMapping) and node.rest:
                self.used.add(node.rest)

            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    self.protected.add(id(node.body[0].value))
            if isinstance(node, ast.match_case):
                self.protected.add(id(node.pattern))
            annotation = getattr(node, "annotation", None)
            if isinstance(annotation, ast.AST):
                self.protected.add(id(annotation))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
                self.protected.add(id(node.returns))
            # Preserve lazy type-alias and generic type-parameter expressions.
            if type(node).__name__ == "TypeAlias":
                self.protected.add(id(node))
            for parameter in getattr(node, "type_params", []):
                self.protected.add(id(parameter))

    def visit(self, node: ast.AST) -> ast.AST:
        if id(node) in self.protected:
            return node
        return super().visit(node)

    def _fresh_name(self) -> str:
        while True:
            self.counter += 1
            suffix = "".join(self.rng.choice(string.ascii_letters + string.digits) for _ in range(6))
            name = f"_obf_s{self.counter:x}{suffix}"
            if name not in self.used:
                self.used.add(name)
                return name

    @staticmethod
    def _assignment(name: str, value: ast.expr) -> ast.Assign:
        return ast.Assign(targets=[ast.Name(id=name, ctx=ast.Store())], value=value)

    def _pool_name(self, value: str) -> str:
        if value in self.pool:
            return self.pool[value]
        if self.decoder_name is None:
            self.decoder_name = self._fresh_name()

        encoded = base64.b64encode(value.encode("utf-8", errors="surrogatepass")).decode("ascii")
        count = self.rng.randint(2, min(6, len(encoded)))
        boundaries = [0, *sorted(self.rng.sample(range(1, len(encoded)), count - 1)), len(encoded)]
        fragment_names = []
        for start, end in zip(boundaries, boundaries[1:]):
            name = self._fresh_name()
            fragment_names.append(name)
            self.fragments.append(self._assignment(name, ast.Constant(encoded[start:end])))

        joined = ast.Call(
            func=ast.Attribute(value=ast.Constant(""), attr="join", ctx=ast.Load()),
            args=[ast.Tuple(elts=[ast.Name(id=name, ctx=ast.Load()) for name in fragment_names], ctx=ast.Load())],
            keywords=[],
        )
        decoded_bytes = ast.Call(
            func=ast.Attribute(value=ast.Name(id=self.decoder_name, ctx=ast.Load()), attr="b64decode", ctx=ast.Load()),
            args=[joined],
            keywords=[],
        )
        decoded_text = ast.Call(
            func=ast.Attribute(value=decoded_bytes, attr="decode", ctx=ast.Load()),
            args=[ast.Constant("utf-8"), ast.Constant("surrogatepass")],
            keywords=[],
        )
        name = self._fresh_name()
        self.pool[value] = name
        self.decoded.append(self._assignment(name, decoded_text))
        return name

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if not isinstance(node.value, str) or not node.value:
            return node
        return ast.copy_location(ast.Name(id=self._pool_name(node.value), ctx=ast.Load()), node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.AST:
        values = []
        for value in node.values:
            transformed = self.visit(value)
            if isinstance(value, ast.Constant) and isinstance(transformed, ast.Name):
                # JoinedStr only accepts literal pieces or FormattedValue nodes.
                transformed = ast.copy_location(
                    ast.FormattedValue(value=transformed, conversion=-1, format_spec=None), value,
                )
            values.append(transformed)
        node.values = values
        return node

    def visit_TemplateStr(self, node: ast.AST) -> ast.AST:
        # Python 3.14 template strings expose interpolation metadata; leave it intact.
        return node

    def inject_pool(self, tree: ast.Module) -> None:
        if self.decoder_name is None:
            return
        # Keep the module docstring and mandatory future-import prefix in place.
        position = 0
        if tree.body and isinstance(tree.body[0], ast.Expr) and id(tree.body[0].value) in self.protected:
            position = 1
        while position < len(tree.body):
            statement = tree.body[position]
            if not isinstance(statement, ast.ImportFrom) or statement.module != "__future__":
                break
            position += 1
        self.rng.shuffle(self.fragments)
        decoder_import = ast.Import(names=[ast.alias(name="base64", asname=self.decoder_name)])
        tree.body[position:position] = [decoder_import, *self.fragments, *self.decoded]


class EncodeStringsPass(ObfuscationPass):
    def apply(self, tree: ast.Module, rng: random.Random) -> ast.Module:
        transformer = _StringTransformer(tree, rng)
        transformer.visit(tree)
        transformer.inject_pool(tree)
        return tree
