"""Parsing helpers."""

from __future__ import annotations

import ast


def parse_source(source: str, filename: str = "<unknown>") -> ast.Module:
    """Parse *source* and preserve type comments where Python exposes them."""
    return ast.parse(source, filename=filename, type_comments=True)
