"""Clang AST-backed identifier renaming for C sources."""

from __future__ import annotations

import json
import os
import random
import shlex
import shutil
import string
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterator


def _walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("inner", ()):
        yield from _walk(child)


def _is_definition(node: dict[str, Any]) -> bool:
    return node.get("kind") == "FunctionDecl" and any(
        child.get("kind") == "CompoundStmt" for child in node.get("inner", ())
    )


def _direct_offset(location: dict[str, Any] | None) -> tuple[int, int] | None:
    """Return a spelling offset only when it belongs directly to the main file."""
    if not location or "offset" not in location:
        return None
    if "includedFrom" in location or "spellingLoc" in location or "expansionLoc" in location:
        return None
    return int(location["offset"]), int(location.get("tokLen", 0))


def _fresh_name(rng: random.Random, used: set[str]) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        candidate = "_cf_" + "".join(rng.choice(alphabet) for _ in range(9))
        if candidate not in used:
            used.add(candidate)
            return candidate


def _clang_ast(source: str, filename: str) -> dict[str, Any]:
    clang = shutil.which(os.environ.get("CLANG", "clang"))
    if clang is None:
        raise ValueError("C identifier renaming requires clang in PATH; run sh install.sh")
    source_path = Path(filename)
    include_directory = source_path.resolve().parent if source_path.name not in {"", "<unknown>"} else Path.cwd()
    extra_arguments = shlex.split(os.environ.get("CONFUSER_CLANG_ARGS", ""))
    with tempfile.TemporaryDirectory(prefix="confuser-clang-") as directory:
        temporary = Path(directory) / "source.c"
        # Preserve the source byte-for-byte. Text-mode writes turn LF into CRLF
        # on Windows, which shifts Clang's byte offsets away from source_bytes.
        temporary.write_bytes(source.encode("utf-8"))
        try:
            completed = subprocess.run(
                [
                    clang,
                    "-Xclang",
                    "-ast-dump=json",
                    "-fsyntax-only",
                    "-Wno-everything",
                    "-I",
                    str(include_directory),
                    *extra_arguments,
                    str(temporary),
                ],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError("Clang AST analysis timed out after 30 seconds") from error
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip().splitlines()
        detail = diagnostic[-1] if diagnostic else "unknown clang error"
        raise SyntaxError(f"Clang could not parse the C source: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("clang returned an invalid AST response") from error


def rename_c_identifiers(source: str, filename: str, rng: random.Random) -> str:
    """Rename C functions, parameters and local variables through Clang bindings.

    Clang declaration IDs connect each reference to its actual declaration, so
    shadowed locals, struct fields, typedefs and callbacks are not guessed from
    their spelling.
    """
    tree = _clang_ast(source, filename)
    nodes = list(_walk(tree))
    used = {
        str(node["name"])
        for node in nodes
        if isinstance(node.get("name"), str)
    }
    rename_by_id: dict[str, str] = {}
    function_name_map: dict[str, str] = {}
    declaration_nodes: list[dict[str, Any]] = []

    for function in (node for node in nodes if _is_definition(node)):
        if _direct_offset(function.get("loc")) is None:
            continue
        function_name = function.get("name")
        if isinstance(function_name, str) and function_name != "main":
            function_name_map.setdefault(function_name, _fresh_name(rng, used))
        for node in _walk(function):
            if node.get("kind") not in {"ParmVarDecl", "VarDecl"}:
                continue
            name = node.get("name")
            identifier = node.get("id")
            if (
                isinstance(name, str)
                and name
                and name != "_"
                and isinstance(identifier, str)
                and _direct_offset(node.get("loc")) is not None
            ):
                rename_by_id[identifier] = _fresh_name(rng, used)
                declaration_nodes.append(node)

    # A C function may have a prototype and a later definition with distinct
    # Clang declaration IDs. C has no overloading, so source-local declarations
    # with the same spelling belong to the same symbol chain.
    for node in nodes:
        if node.get("kind") == "FunctionDecl" and node.get("name") in function_name_map:
            identifier = node.get("id")
            if isinstance(identifier, str) and _direct_offset(node.get("loc")) is not None:
                rename_by_id[identifier] = function_name_map[str(node["name"])]
                declaration_nodes.append(node)

    edits: dict[tuple[int, int], bytes] = {}
    source_bytes = source.encode("utf-8")

    def add_edit(location: dict[str, Any] | None, old_name: str, new_name: str) -> None:
        direct = _direct_offset(location)
        if direct is None:
            return
        offset, token_length = direct
        old_bytes = old_name.encode("utf-8")
        length = token_length or len(old_bytes)
        if source_bytes[offset:offset + length] != old_bytes:
            return
        edits[(offset, length)] = new_name.encode("ascii")

    for node in declaration_nodes:
        identifier = node.get("id")
        old_name = node.get("name")
        if isinstance(identifier, str) and isinstance(old_name, str):
            add_edit(node.get("loc"), old_name, rename_by_id[identifier])

    for node in nodes:
        if node.get("kind") != "DeclRefExpr":
            continue
        referenced = node.get("referencedDecl", {})
        identifier = referenced.get("id")
        old_name = referenced.get("name")
        if not isinstance(identifier, str) or not isinstance(old_name, str):
            continue
        new_name = rename_by_id.get(identifier)
        if new_name is None and referenced.get("kind") == "FunctionDecl":
            new_name = function_name_map.get(old_name)
        if new_name is not None:
            add_edit(node.get("range", {}).get("begin"), old_name, new_name)

    result = source_bytes
    for (offset, length), replacement in sorted(edits.items(), reverse=True):
        result = result[:offset] + replacement + result[offset + length:]
    return result.decode("utf-8")
