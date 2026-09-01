"""Insert harmless, unreachable branches."""

from __future__ import annotations

import ast
import random

from .base import ObfuscationPass


class _DeadCodeTransformer(ast.NodeTransformer):
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def _block(self) -> ast.If:
        marker = self.rng.randint(10_000, 99_999)
        return ast.If(
            test=ast.Compare(
                left=ast.Constant(marker),
                ops=[ast.Eq()],
                comparators=[ast.Constant(-1)],
            ),
            body=[ast.Expr(value=ast.Constant("unreachable"))],
            orelse=[],
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        position = 1 if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str) else 0
        node.body.insert(position, self._block())
        return node

    visit_AsyncFunctionDef = visit_FunctionDef


class InsertDeadCodePass(ObfuscationPass):
    def apply(self, tree: ast.Module, rng: random.Random) -> ast.Module:
        return _DeadCodeTransformer(rng).visit(tree)  # type: ignore[return-value]
