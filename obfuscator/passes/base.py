"""Common pass protocol."""

from __future__ import annotations

import ast
import random
from abc import ABC, abstractmethod


class ObfuscationPass(ABC):
    """A deterministic (for a seeded RNG) AST-to-AST transformation."""

    @abstractmethod
    def apply(self, tree: ast.Module, rng: random.Random) -> ast.Module:
        raise NotImplementedError
