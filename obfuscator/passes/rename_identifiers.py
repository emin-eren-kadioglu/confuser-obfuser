"""Scope-aware function, parameter and local-variable renaming."""

from __future__ import annotations

import ast
import random
import string

from obfuscator.call_analyzer import analyze_calls
from obfuscator.scope_analyzer import Scope, analyze_scopes, resolve_binding

from .base import ObfuscationPass


class _Renamer(ast.NodeTransformer):
    def __init__(
        self,
        by_node: dict[ast.AST, Scope],
        root: Scope,
        call_keywords: dict[ast.Call, dict[str, str]],
    ) -> None:
        self.by_node = by_node
        self.current = root
        self.root = root
        self.call_keywords = call_keywords

    def _resolved_name(self, name: str) -> str:
        scope = resolve_binding(self.current, name, self.root)
        return scope.rename_map.get(name, name) if scope is not None else name

    def visit_Call(self, node: ast.Call) -> ast.AST:
        mapping = self.call_keywords.get(node, {})
        for keyword in node.keywords:
            if keyword.arg is not None:
                keyword.arg = mapping.get(keyword.arg, keyword.arg)
        return self.generic_visit(node)

    def _rename_parameters(self, args: ast.arguments, scope: Scope) -> None:
        parameters = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        if args.vararg:
            parameters.append(args.vararg)
        if args.kwarg:
            parameters.append(args.kwarg)
        for parameter in parameters:
            parameter.arg = scope.rename_map.get(parameter.arg, parameter.arg)

    def visit_Name(self, node: ast.Name) -> ast.AST:
        node.id = self._resolved_name(node.id)
        return node

    def visit_NamedExpr(self, node: ast.NamedExpr) -> ast.AST:
        node.value = self.visit(node.value)
        if self.current.kind != "comprehension":
            node.target = self.visit(node.target)
            return node
        current = self.current
        while self.current.kind == "comprehension" and self.current.parent is not None:
            self.current = self.current.parent
        node.target = self.visit(node.target)
        self.current = current
        return node

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.AST:
        node.name = self._resolved_name(node.name)
        # Decorators, defaults and annotations are evaluated in the parent scope.
        node.decorator_list = [self.visit(item) for item in node.decorator_list]
        node.args.defaults = [self.visit(item) for item in node.args.defaults]
        node.args.kw_defaults = [self.visit(item) if item else None for item in node.args.kw_defaults]
        for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
            if arg.annotation:
                arg.annotation = self.visit(arg.annotation)
        if node.args.vararg and node.args.vararg.annotation:
            node.args.vararg.annotation = self.visit(node.args.vararg.annotation)
        if node.args.kwarg and node.args.kwarg.annotation:
            node.args.kwarg.annotation = self.visit(node.args.kwarg.annotation)
        if node.returns:
            node.returns = self.visit(node.returns)
        parent = self.current
        self.current = self.by_node[node]
        self._rename_parameters(node.args, self.current)
        node.body = [self.visit(item) for item in node.body]
        self.current = parent
        return node

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Lambda(self, node: ast.Lambda) -> ast.AST:
        node.args.defaults = [self.visit(item) for item in node.args.defaults]
        node.args.kw_defaults = [self.visit(item) if item else None for item in node.args.kw_defaults]
        parent = self.current
        self.current = self.by_node[node]
        self._rename_parameters(node.args, self.current)
        node.body = self.visit(node.body)
        self.current = parent
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        node.decorator_list = [self.visit(item) for item in node.decorator_list]
        node.bases = [self.visit(item) for item in node.bases]
        for keyword in node.keywords:
            keyword.value = self.visit(keyword.value)
        parent = self.current
        self.current = self.by_node[node]
        node.body = [self.visit(item) for item in node.body]
        self.current = parent
        return node

    def _comprehension(self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp) -> ast.AST:
        self.visit(node.generators[0].iter)
        parent = self.current
        self.current = self.by_node[node]
        for index, generator in enumerate(node.generators):
            if index:
                self.visit(generator.iter)
            self.visit(generator.target)
            generator.ifs = [self.visit(item) for item in generator.ifs]
        if isinstance(node, ast.DictComp):
            node.key = self.visit(node.key)
            node.value = self.visit(node.value)
        else:
            node.elt = self.visit(node.elt)
        self.current = parent
        return node

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_DictComp = _comprehension
    visit_GeneratorExp = _comprehension

    def visit_Nonlocal(self, node: ast.Nonlocal) -> ast.AST:
        node.names = [self._resolved_name(name) for name in node.names]
        return node

    def visit_Global(self, node: ast.Global) -> ast.AST:
        node.names = [self.root.rename_map.get(name, name) for name in node.names]
        return node

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ast.AST:
        if node.name:
            node.name = self._resolved_name(node.name)
        return self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> ast.AST:
        if node.name:
            node.name = self._resolved_name(node.name)
        return self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> ast.AST:
        if node.name:
            node.name = self._resolved_name(node.name)
        return node

    def visit_MatchMapping(self, node: ast.MatchMapping) -> ast.AST:
        if node.rest:
            node.rest = self._resolved_name(node.rest)
        return self.generic_visit(node)


class RenameIdentifiersPass(ObfuscationPass):
    def __init__(self, *, preserve_interfaces: bool = False) -> None:
        self.preserve_interfaces = preserve_interfaces

    def apply(self, tree: ast.Module, rng: random.Random) -> ast.Module:
        analysis = analyze_scopes(tree)
        # Reflective access can refer to identifiers via strings or metadata.
        # Type-parameter scopes require separate handling (Python 3.12+).
        reflective = {"__annotations__", "__name__", "__qualname__", "__code__", "f_locals"}
        if any(scope.unsafe for scope in analysis.by_node.values()) or any(
            (isinstance(node, ast.Attribute) and node.attr in reflective)
            or bool(getattr(node, "type_params", None))
            for node in ast.walk(tree)
        ):
            return tree

        calls = analyze_calls(tree, analysis)
        if self.preserve_interfaces:
            # Other files may import any module function or call a returned
            # callable by keyword. Only local bindings are private to this file.
            analysis.root.excluded.update(analysis.root.bound)
            for scope in analysis.by_node.values():
                scope.excluded.update(scope.parameters)
        # Class bodies resolve their namespace at runtime (e.g. ``f = f`` can
        # read a global before assigning an attribute). Preserve collisions.
        class_names = set().union(*(
            scope.bound for scope in analysis.by_node.values() if scope.kind == "class"
        ))
        for scope in analysis.by_node.values():
            scope.excluded.update(class_names)
        for (_, name), definitions in calls.functions.items():
            if name in class_names:
                for scope in definitions:
                    calls.keyword_safe.discard(scope.node)

        # Keep explicitly exported module APIs and their keyword contracts.
        if "__all__" in analysis.root.bound:
            for (binding_node, name), definitions in calls.functions.items():
                if binding_node is tree:
                    analysis.root.excluded.add(name)
                    for scope in definitions:
                        calls.keyword_safe.discard(scope.node)

        for node, scope in analysis.by_node.items():
            if scope.kind == "function" and node not in calls.keyword_safe:
                scope.excluded.update(scope.parameters)

        used = set(analysis.all_names)
        counter = 0

        def fresh_name() -> str:
            nonlocal counter
            while True:
                counter += 1
                suffix = "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(6))
                candidate = f"_obf_{counter:x}{suffix}"
                if candidate not in used:
                    used.add(candidate)
                    return candidate

        for scope in analysis.by_node.values():
            if scope.kind == "module":
                candidates = {
                    name for binding_node, name in calls.functions if binding_node is scope.node
                } - scope.excluded
            elif scope.kind == "function":
                candidates = scope.bound - scope.excluded - scope.globals - scope.nonlocals
            else:
                continue
            for name in sorted(candidates):
                if not (name.startswith("__") and name.endswith("__")):
                    scope.rename_map[name] = fresh_name()

        # Snapshot old keyword spellings before the transformer mutates ast.arg.
        call_keywords = {}
        for call, target in calls.targets.items():
            keyword_parameters = [*target.node.args.args, *target.node.args.kwonlyargs]
            call_keywords[call] = {
                parameter.arg: target.rename_map[parameter.arg]
                for parameter in keyword_parameters
                if parameter.arg in target.rename_map
            }
        return _Renamer(analysis.by_node, analysis.root, call_keywords).visit(tree)  # type: ignore[return-value]
