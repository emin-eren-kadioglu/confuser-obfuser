"""Conservative call-target analysis for rewriting keyword parameter names."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from .scope_analyzer import Scope, ScopeAnalysis, resolve_binding


@dataclass
class CallAnalysis:
    functions: dict[tuple[ast.AST, str], list[Scope]] = field(default_factory=dict)
    targets: dict[ast.Call, Scope] = field(default_factory=dict)
    keyword_safe: set[ast.AST] = field(default_factory=set)


def analyze_calls(tree: ast.Module, scopes: ScopeAnalysis) -> CallAnalysis:
    result = CallAnalysis()
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def binding_key(node: ast.Name) -> tuple[ast.AST, str] | None:
        scope = resolve_binding(scopes.node_scopes[node], node.id, scopes.root)
        return (scope.node, node.id) if scope is not None else None

    for node, scope in scopes.by_node.items():
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            binding = resolve_binding(scopes.node_scopes[node], node.name, scopes.root)
            if binding is not None:
                result.functions.setdefault((binding.node, node.name), []).append(scope)

    stable: dict[tuple[ast.AST, str], Scope] = {}
    for key, definitions in result.functions.items():
        binding = scopes.by_node[key[0]]
        if len(definitions) == 1 and key[1] not in binding.excluded | binding.parameters:
            stable[key] = definitions[0]
            result.keyword_safe.add(definitions[0].node)

    # A reassignment/deletion makes a syntactically direct call ambiguous.
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            key = binding_key(node)
            target = stable.pop(key, None)
            if target is not None:
                result.keyword_safe.discard(target.node)
        # These binding forms store names in string fields instead of ast.Name.
        names: list[str] = []
        if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name:
            names.append(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            names.append(node.rest)
        for name in names:
            binding = resolve_binding(scopes.node_scopes[node], name, scopes.root)
            key = (binding.node, name) if binding is not None else None
            target = stable.pop(key, None)
            if target is not None:
                result.keyword_safe.discard(target.node)

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            target = stable.get(binding_key(node))
            if target is None:
                continue
            parent = parents.get(node)
            if isinstance(parent, ast.Call) and parent.func is node:
                result.targets[parent] = target
                if any(keyword.arg is None for keyword in parent.keywords):
                    result.keyword_safe.discard(target.node)
            else:
                # Aliases, callbacks, returned functions and introspection can
                # call the function with keyword names we cannot rewrite here.
                result.keyword_safe.discard(target.node)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Lambda):
            target = scopes.by_node[node.func]
            result.targets[node] = target
            if not any(keyword.arg is None for keyword in node.keywords):
                result.keyword_safe.add(target.node)

    return result
