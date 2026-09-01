"""Turn a transformed AST back into Python source."""

from __future__ import annotations

import ast


def emit_source(tree: ast.AST) -> str:
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"
