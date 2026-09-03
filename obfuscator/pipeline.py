"""Obfuscation pipeline configuration and orchestration."""

from __future__ import annotations

import ast
import random
from dataclasses import dataclass
from typing import Callable

from .emitter import emit_source
from .languages import SourceLanguage, detect_language
from .native import obfuscate_native
from .parser import parse_source
from .passes import (
    EncodeStringsPass,
    InsertDeadCodePass,
    ObfuscationPass,
    RenameIdentifiersPass,
    TransformNumbersPass,
)


MAX_INTERMEDIATE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class ObfuscationConfig:
    seed: int | None = None
    rename_identifiers: bool = True
    encode_strings: bool = True
    transform_numbers: bool = True
    insert_dead_code: bool = True
    iterations: int = 1
    preserve_interfaces: bool = False

    def __post_init__(self) -> None:
        if type(self.iterations) is not int or self.iterations < 1:
            raise ValueError("iterations must be a positive integer (at least 1)")


class Obfuscator:
    def __init__(self, config: ObfuscationConfig | None = None) -> None:
        self.config = config or ObfuscationConfig()

    def passes(self) -> list[ObfuscationPass]:
        selected: list[ObfuscationPass] = []
        if self.config.rename_identifiers:
            selected.append(RenameIdentifiersPass(preserve_interfaces=self.config.preserve_interfaces))
        if self.config.encode_strings:
            selected.append(EncodeStringsPass())
        if self.config.transform_numbers:
            selected.append(TransformNumbersPass())
        if self.config.insert_dead_code:
            selected.append(InsertDeadCodePass())
        return selected

    def transform_tree(self, tree: ast.Module) -> ast.Module:
        """Apply one complete round of enabled passes to an AST."""
        rng = random.Random(self.config.seed)
        for obfuscation_pass in self.passes():
            tree = obfuscation_pass.apply(tree, rng)
            ast.fix_missing_locations(tree)
        return tree

    def obfuscate(
        self,
        source: str,
        filename: str = "<unknown>",
        *,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> str:
        """Feed each round's emitted source into the next; return only the final output."""
        language = detect_language(filename, default=SourceLanguage.PYTHON)
        result = source
        for iteration in range(1, self.config.iterations + 1):
            if iteration > 1 and len(result.encode("utf-8")) > MAX_INTERMEDIATE_BYTES:
                raise ValueError(
                    f"round {iteration} stopped: intermediate source exceeds the 2 MiB limit; "
                    "reduce iterations or disable string encoding"
                )
            if on_progress is not None:
                on_progress(iteration, self.config.iterations)
            try:
                if language is SourceLanguage.PYTHON:
                    tree = parse_source(result, filename)
                    transformed = self.transform_tree(tree)
                    result = emit_source(transformed)
                    # Syntax-check every round, without executing the program.
                    compile(result, filename, "exec")
                else:
                    result = obfuscate_native(
                        result,
                        language,
                        rng=random.Random(self.config.seed),
                        rename_identifiers=self.config.rename_identifiers,
                        encode_strings=self.config.encode_strings,
                        transform_numbers=self.config.transform_numbers,
                        insert_dead_code=self.config.insert_dead_code,
                        filename=filename,
                        preserve_interfaces=self.config.preserve_interfaces,
                    )
            except RecursionError as error:
                raise ValueError(
                    f"round {iteration} stopped: AST nesting is too deep; reduce iterations"
                ) from error
        return result
