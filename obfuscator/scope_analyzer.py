"""Conservative lexical-scope analysis used by identifier renaming."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


_DYNAMIC_CALLS = {"eval", "exec", "locals", "globals", "vars", "getattr", "setattr", "hasattr", "delattr"}


@dataclass
class Scope:
    node: ast.AST
    parent: "Scope | None"
    kind: str
    bound: set[str] = field(default_factory=set)
    excluded: set[str] = field(default_factory=set)
    globals: set[str] = field(default_factory=set)
    nonlocals: set[str] = field(default_factory=set)
    parameters: set[str] = field(default_factory=set)
    unsafe: bool = False
    rename_map: dict[str, str] = field(default_factory=dict)


@dataclass
class ScopeAnalysis:
    root: Scope
    by_node: dict[ast.AST, Scope]
    all_names: set[str]
    node_scopes: dict[ast.AST, Scope]


class _Builder(ast.NodeVisitor):
    def __init__(self, tree: ast.Module) -> None:
        self.root = Scope(tree, None, "module")
        self.current = self.root
        self.by_node: dict[ast.AST, Scope] = {tree: self.root}
        self.node_scopes: dict[ast.AST, Scope] = {}
        self.all_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    def visit(self, node: ast.AST) -> None:
        self.node_scopes[node] = self.current
        super().visit(node)

    def _visit_arguments_in_parent(self, args: ast.arguments) -> None:
        for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
            if arg.annotation:
                self.visit(arg.annotation)
        if args.vararg and args.vararg.annotation:
            self.visit(args.vararg.annotation)
        if args.kwarg and args.kwarg.annotation:
            self.visit(args.kwarg.annotation)
        for value in (*args.defaults, *(d for d in args.kw_defaults if d is not None)):
            self.visit(value)

    @staticmethod
    def _argument_names(args: ast.arguments) -> set[str]:
        result = {arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
        if args.vararg:
            result.add(args.vararg.arg)
        if args.kwarg:
            result.add(args.kwarg.arg)
        return result

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.current.bound.add(node.name)
        # Methods are attributes; decorated names may be used for registration.
        if self.current.kind == "class" or node.decorator_list:
            self.current.excluded.add(node.name)
        for item in node.decorator_list:
            self.visit(item)
        self._visit_arguments_in_parent(node.args)
        if node.returns:
            self.visit(node.returns)

        parent = self.current
        child = Scope(node, parent, "function")
        self.by_node[node] = child
        parameters = self._argument_names(node.args)
        child.bound.update(parameters)
        child.parameters.update(parameters)
        self.current = child
        for statement in node.body:
            self.visit(statement)
        child.bound.difference_update(child.globals)
        child.excluded.update(child.globals)
        self.current = parent

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_arguments_in_parent(node.args)
        parent = self.current
        child = Scope(node, parent, "function")
        self.by_node[node] = child
        parameters = self._argument_names(node.args)
        child.bound.update(parameters)
        child.parameters.update(parameters)
        self.current = child
        self.visit(node.body)
        self.current = parent

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.current.bound.add(node.name)
        self.current.excluded.add(node.name)
        for item in (*node.decorator_list, *node.bases):
            self.visit(item)
        for keyword in node.keywords:
            self.visit(keyword.value)
        parent = self.current
        child = Scope(node, parent, "class")
        self.by_node[node] = child
        self.current = child
        for statement in node.body:
            self.visit(statement)
        self.current = parent

    def _comprehension(self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp) -> None:
        # The first iterable is evaluated outside the comprehension's implicit scope.
        self.visit(node.generators[0].iter)
        parent = self.current
        child = Scope(node, parent, "comprehension")
        self.by_node[node] = child
        self.current = child
        for index, generator in enumerate(node.generators):
            if index:
                self.visit(generator.iter)
            self.visit(generator.target)
            for condition in generator.ifs:
                self.visit(condition)
        if isinstance(node, ast.DictComp):
            self.visit(node.key)
            self.visit(node.value)
        else:
            self.visit(node.elt)
        child.excluded.update(child.bound)
        self.current = parent

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_DictComp = _comprehension
    visit_GeneratorExp = _comprehension

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.current.bound.add(node.id)
        elif node.id in _DYNAMIC_CALLS:
            # Also catch aliases such as ``namespace = globals``.
            self.current.unsafe = True

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        # PEP 572: a walrus target inside a comprehension binds in the nearest
        # containing non-comprehension scope.
        target_scope = self.current
        while target_scope.kind == "comprehension" and target_scope.parent is not None:
            target_scope = target_scope.parent
        if isinstance(node.target, ast.Name):
            target_scope.bound.add(node.target.id)
            self.node_scopes[node.target] = target_scope
        self.visit(node.value)

    def visit_Global(self, node: ast.Global) -> None:
        self.current.globals.update(node.names)
        self.root.bound.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.current.nonlocals.update(node.names)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name.split(".", 1)[0]
            self.current.bound.add(name)
            self.current.excluded.add(name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self.current.bound.add(name)
            self.current.excluded.add(name)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.current.bound.add(node.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in _DYNAMIC_CALLS:
            self.current.unsafe = True
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self.current.bound.add(node.name)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self.current.bound.add(node.name)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self.current.bound.add(node.rest)
        self.generic_visit(node)


def analyze_scopes(tree: ast.Module) -> ScopeAnalysis:
    builder = _Builder(tree)
    builder.visit(tree)
    for scope in builder.by_node.values():
        builder.all_names.update(scope.bound | scope.globals | scope.nonlocals | scope.parameters)
    return ScopeAnalysis(builder.root, builder.by_node, builder.all_names, builder.node_scopes)


def resolve_binding(scope: Scope, name: str, root: Scope) -> Scope | None:
    """Resolve a lexical name before renaming, including global/nonlocal uses."""
    current: Scope | None = scope
    while current is not None:
        if name in current.globals:
            return root
        if name not in current.nonlocals and name in current.bound:
            return current
        current = current.parent
        # Enclosing class namespaces do not participate in lexical closures.
        while current is not None and current.kind == "class":
            current = current.parent
    return None
