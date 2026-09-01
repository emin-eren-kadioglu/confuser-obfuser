"""Integer literal transformation."""

from __future__ import annotations

import ast
import random

from .base import ObfuscationPass


class _NumberTransformer(ast.NodeTransformer):
    def __init__(self, tree: ast.AST, rng: random.Random) -> None:
        self.rng = rng
        self.protected = {
            id(node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.MatchValue)
        }
        for node in ast.walk(tree):
            annotations = []
            if isinstance(node, ast.arg) and node.annotation:
                annotations.append(node.annotation)
            elif isinstance(node, ast.AnnAssign):
                annotations.append(node.annotation)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
                annotations.append(node.returns)
            for annotation in annotations:
                self.protected.update(
                    id(item)
                    for item in ast.walk(annotation)
                    if isinstance(item, ast.Constant)
                )

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        # bool is an int subclass, but changing True/False would be surprising.
        if id(node) not in self.protected and isinstance(node.value, int) and not isinstance(node.value, bool):
            delta = self.rng.randint(2, 97)
            replacement = ast.BinOp(
                left=ast.Constant(node.value + delta),
                op=ast.Sub(),
                right=ast.Constant(delta),
            )
            return ast.copy_location(replacement, node)
        return node


class TransformNumbersPass(ObfuscationPass):
    def apply(self, tree: ast.Module, rng: random.Random) -> ast.Module:
        return _NumberTransformer(tree, rng).visit(tree)  # type: ignore[return-value]
