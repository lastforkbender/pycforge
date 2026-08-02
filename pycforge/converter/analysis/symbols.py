from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from pycforge.converter.ir.python_ir import python_ir_reference_ids

from .model import BindingFact, ScopeFact


def _stable_id(prefix: str, *parts: str) -> str:
    seed = "\x1f".join(parts).encode("utf-8")
    return prefix + hashlib.sha256(seed).hexdigest()[:20]


class PythonIRIndex:
    def __init__(self, module: dict[str, Any]) -> None:
        self.module = module
        self.nodes = {node["node_id"]: node for node in module["nodes"]}
        self.ordinals = {node["node_id"]: index for index, node in enumerate(module["nodes"])}

    def node(self, node_id: str) -> dict[str, Any]:
        return self.nodes[node_id]

    def child_ids(self, node: dict[str, Any]) -> tuple[str, ...]:
        found: list[str] = []
        # Normalized fields retain ast.iter_fields order, which is semantic for
        # calls, operators, and statement lists.
        for key,value in node["fields"].items():
            found.extend(python_ir_reference_ids(node["kind"],key,value,self.nodes))
        return tuple(found)


class SymbolScopeAnalyzer:
    """Deterministic Python lexical scopes without source-order misresolution.

    Python decides function-local bindings for the whole function body.  The
    predeclaration pass below therefore records parameters, assignments, loop
    targets, and nested-definition names before resolving any load occurrence.
    This is essential for reporting use-before-binding rather than silently
    treating an early load as a global.
    """

    def analyze(
        self,
        module: dict[str, Any],
        *,
        allow_records: bool = False,
    ) -> tuple[tuple[ScopeFact, ...], tuple[BindingFact, ...], dict[str, str]]:
        index = PythonIRIndex(module)
        module_scope = _stable_id("scope-", module["document_id"], module["root_node_id"], "module")
        scopes: dict[str, dict[str, Any]] = {
            module_scope: {"kind": "module", "owner": module["root_node_id"], "parent": None, "children": [], "bindings": []}
        }
        scope_for_node: dict[str, str] = {}
        declarations: dict[tuple[str, str], tuple[str, str, str]] = {}
        occurrences: dict[str, list[str]] = defaultdict(list)
        store_node_ids: set[str] = set()
        for candidate in index.nodes.values():
            kind = candidate["kind"]
            fields = candidate["fields"]
            if kind == "Assign":
                store_node_ids.update(item for item in fields.get("targets", []) if isinstance(item, str))
            elif kind in {"AnnAssign", "AugAssign", "NamedExpr", "For"}:
                target_id = fields.get("target")
                if isinstance(target_id, str):
                    store_node_ids.add(target_id)

        def declare(scope_id: str, name: str, kind: str, node_id: str) -> str:
            key = (scope_id, name)
            if key not in declarations:
                binding_id = _stable_id("bind-", scope_id, name, kind)
                declarations[key] = (binding_id, kind, node_id)
                scopes[scope_id]["bindings"].append(binding_id)
            return declarations[key][0]

        def resolve(scope_id: str, name: str) -> str:
            current: str | None = scope_id
            while current is not None:
                key = (current, name)
                if key in declarations:
                    return declarations[key][0]
                current = scopes[current]["parent"]
            return declare(module_scope, name, "implicit-global", module["root_node_id"])

        def mark_annotation(node_id: str, scope_id: str) -> None:
            node = index.node(node_id)
            if node_id in scope_for_node:
                return
            scope_for_node[node_id] = scope_id
            for child_id in index.child_ids(node):
                mark_annotation(child_id, scope_id)

        def predeclare_target(node_id: str, scope_id: str, kind: str = "local") -> None:
            target = index.node(node_id)
            if target["kind"] == "Name":
                declare(scope_id, target["fields"].get("id", ""), kind, node_id)

        def predeclare_function_body(node_ids: list[str], scope_id: str) -> None:
            for node_id in node_ids:
                node = index.node(node_id)
                fields = node["fields"]
                kind = node["kind"]
                if kind in {"FunctionDef", "AsyncFunctionDef"}:
                    declare(scope_id, fields.get("name", ""), "nested-function", node_id)
                    continue
                if kind == "Assign":
                    for target_id in fields.get("targets", []):
                        predeclare_target(target_id, scope_id)
                elif kind in {"AnnAssign", "AugAssign", "NamedExpr"}:
                    target_id = fields.get("target")
                    if isinstance(target_id, str):
                        predeclare_target(target_id, scope_id)
                elif kind == "For":
                    target_id = fields.get("target")
                    if isinstance(target_id, str):
                        predeclare_target(target_id, scope_id, "loop-target")
                for field_name in ("body", "orelse", "finalbody"):
                    children = fields.get(field_name, [])
                    if isinstance(children, list):
                        predeclare_function_body(children, scope_id)

        def walk(node_id: str, scope_id: str) -> None:
            node = index.node(node_id)
            if node_id in scope_for_node:
                return
            scope_for_node[node_id] = scope_id
            kind = node["kind"]
            fields = node["fields"]

            if kind == "Module":
                for child_id in fields.get("body", []):
                    child = index.node(child_id)
                    if child["kind"] in {"FunctionDef", "AsyncFunctionDef"}:
                        declare(scope_id, child["fields"].get("name", ""), "function", child_id)
                    elif allow_records and child["kind"] == "ClassDef":
                        declare(scope_id, child["fields"].get("name", ""), "record-class", child_id)
                for child_id in fields.get("body", []):
                    walk(child_id, scope_id)
                return

            if allow_records and kind == "ClassDef":
                declare(scope_id, fields.get("name", ""), "record-class", node_id)
                child_scope = _stable_id("scope-", node_id, "record-class")
                scopes[child_scope] = {
                    "kind": "record-class",
                    "owner": node_id,
                    "parent": scope_id,
                    "children": [],
                    "bindings": [],
                }
                scopes[scope_id]["children"].append(child_scope)
                for child_id in fields.get("body", []):
                    child = index.node(child_id)
                    if child["kind"] == "AnnAssign":
                        target_id = child["fields"].get("target")
                        if isinstance(target_id, str):
                            target = index.node(target_id)
                            if target["kind"] == "Name":
                                declare(
                                    child_scope,
                                    target["fields"].get("id", ""),
                                    "record-field",
                                    target_id,
                                )
                    elif child["kind"] in {"FunctionDef", "AsyncFunctionDef"}:
                        declare(
                            child_scope,
                            child["fields"].get("name", ""),
                            "record-initializer" if child["fields"].get("name") == "__init__" else "record-method",
                            child_id,
                        )
                for child_id in fields.get("body", []):
                    walk(child_id, child_scope)
                return

            if kind in {"FunctionDef", "AsyncFunctionDef"}:
                declare(scope_id, fields.get("name", ""), "function" if scope_id == module_scope else "nested-function", node_id)
                child_scope = _stable_id("scope-", node_id, "function")
                scopes[child_scope] = {"kind": "function", "owner": node_id, "parent": scope_id, "children": [], "bindings": []}
                scopes[scope_id]["children"].append(child_scope)
                args_id = fields.get("args")
                if isinstance(args_id, str):
                    args_node = index.node(args_id)
                    scope_for_node[args_id] = child_scope
                    parameter_ids = list(args_node["fields"].get("posonlyargs", [])) + list(args_node["fields"].get("args", [])) + list(args_node["fields"].get("kwonlyargs", []))
                    for arg_id in parameter_ids:
                        arg = index.node(arg_id)
                        declare(child_scope, arg["fields"]["arg"], "parameter", arg_id)
                        scope_for_node[arg_id] = child_scope
                        annotation = arg["fields"].get("annotation")
                        if isinstance(annotation, str) and annotation in index.nodes:
                            mark_annotation(annotation, child_scope)
                predeclare_function_body(fields.get("body", []), child_scope)
                returns = fields.get("returns")
                if isinstance(returns, str) and returns in index.nodes:
                    mark_annotation(returns, child_scope)
                for child in fields.get("body", []):
                    walk(child, child_scope)
                return

            if kind == "Name":
                name = fields["id"]
                context = "Store" if node_id in store_node_ids else "Load"
                binding_id = declare(scope_id, name, "local", node_id) if context == "Store" else resolve(scope_id, name)
                occurrences[binding_id].append(node_id)

            for child_id in index.child_ids(node):
                if child_id not in scope_for_node:
                    walk(child_id, scope_id)

        walk(module["root_node_id"], module_scope)

        scope_facts = tuple(
            ScopeFact(
                scope_id=scope_id,
                scope_kind=data["kind"],
                owner_node_id=data["owner"],
                parent_scope_id=data["parent"],
                child_scope_ids=tuple(sorted(data["children"])),
                binding_ids=tuple(sorted(data["bindings"])),
            )
            for scope_id, data in sorted(scopes.items())
        )
        binding_facts = tuple(
            BindingFact(
                binding_id,
                scope_id,
                name,
                kind,
                declaration,
                tuple(sorted(occurrences[binding_id], key=lambda item: index.ordinals[item])),
            )
            for (scope_id, name), (binding_id, kind, declaration) in sorted(declarations.items(), key=lambda item: item[1][0])
        )
        return scope_facts, binding_facts, scope_for_node
