"""Closed-world analysis for explicit logical modules in a SourceBundle.

This module deliberately operates only on normalized in-memory Python IR.  It
does not import, discover, open, or execute anything named by source imports.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from pycforge.converter.contracts.identifiers import (
    C11_EXTERNAL_IDENTIFIERS,
    C_KEYWORDS,
    TARGET_RESERVED_NAMES,
)
from pycforge.converter.ir.python_ir import python_ir_reference_ids

from .model import (
    ModuleAnalysisCanceled,
    ModuleResolutionError,
    ModuleResolutionProduct,
    ResolvedImport,
)


_DYNAMIC_IMPORT_ATTRIBUTES = frozenset(
    {"find_spec", "import_module", "module_from_spec", "reload"}
)


def _stable_id(prefix: str, *parts: object) -> str:
    seed = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return prefix + hashlib.sha256(seed).hexdigest()[:20]


def _thaw(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _legacy_function_token(source_name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", source_name)
    if not base or not (base[0].isalpha() or base[0] == "_"):
        base = "py_" + base
    if base.startswith("_"):
        base = "py" + base
    if (
        base in C_KEYWORDS
        or base in TARGET_RESERVED_NAMES
        or base in C11_EXTERNAL_IDENTIFIERS
        or base.startswith(("pycf_", "pycm_"))
    ):
        base = "py_" + base
    return base


def _module_escape(module_id: str) -> str:
    return module_id.replace("_", "_u").replace(".", "_d")


def _qualified_function_name(module_id: str, source_name: str) -> str:
    binding_identity = f"{module_id}.{source_name}"
    digest = hashlib.sha256(binding_identity.encode("utf-8")).hexdigest()
    # Put collision entropy inside C11's guaranteed 31 significant initial
    # characters for external identifiers.  The readable suffix is diagnostic
    # context only; portable identity does not depend on its tail.
    return f"pycm_{digest}__{_module_escape(module_id)}__{_legacy_function_token(source_name)}"


@dataclass(slots=True)
class _Module:
    module_id: str
    logical_name: str
    bundle_ordinal: int
    is_primary: bool
    document_id: str
    python_ir: dict[str, Any]
    source: dict[str, Any]
    nodes: dict[str, dict[str, Any]] = field(init=False)
    root: dict[str, Any] = field(init=False)
    body: tuple[str, ...] = field(init=False)
    function_ids: tuple[str, ...] = ()
    functions: dict[str, dict[str, Any]] = field(default_factory=dict)
    record_ids: tuple[str, ...] = ()
    records: dict[str, dict[str, Any]] = field(default_factory=dict)
    ineligible_functions: dict[str, dict[str, Any]] = field(default_factory=dict)
    deferred_top_level_node: dict[str, Any] | None = None
    import_node_ids: tuple[str, ...] = ()
    raw_imports: list[tuple[str, int, int, str, str, str]] = field(default_factory=list)
    resolved_imports: list[ResolvedImport] = field(default_factory=list)
    imported_bindings: dict[str, ResolvedImport] = field(default_factory=dict)
    document_plan_node_id: str = ""

    def __post_init__(self) -> None:
        self.nodes = {node["node_id"]: node for node in self.python_ir["nodes"]}
        self.root = self.nodes[self.python_ir["root_node_id"]]
        self.body = tuple(self.root["fields"].get("body", ()))


class ExplicitModuleAnalyzer:
    """Resolve the approved absolute-from-import module profile."""

    stage_id = "modules.resolve"

    def __init__(
        self,
        bundle: dict[str, Any],
        source_bundle: dict[str, Any],
        *,
        max_import_edges: int,
        cancellation: Any = None,
        invalidation_dependency: str,
        allow_records: bool = False,
        allow_required_keyword_only: bool = False,
    ) -> None:
        self.bundle = bundle
        self.source_bundle = source_bundle
        self.max_import_edges = max_import_edges
        self.cancellation = cancellation
        self.invalidation_dependency = invalidation_dependency
        self.allow_records = allow_records
        self.allow_required_keyword_only = allow_required_keyword_only
        sources = {
            item["module_id"]: item for item in source_bundle.get("documents", ())
        }
        self.modules = tuple(
            _Module(
                module_id=item["module_id"],
                logical_name=item["logical_name"],
                bundle_ordinal=item["bundle_ordinal"],
                is_primary=item["is_primary"],
                document_id=item["document_id"],
                python_ir=_thaw(item["python_ir"]),
                source=_thaw(sources.get(item["module_id"], {})),
            )
            for item in bundle["documents"]
        )
        self.by_id = {item.module_id: item for item in self.modules}

    def analyze(self) -> ModuleResolutionProduct:
        for module in self.modules:
            self._check_canceled()
            self._analyze_document_shape(module)
        import_count = sum(len(module.raw_imports) for module in self.modules)
        if import_count > self.max_import_edges:
            module = next(item for item in self.modules if item.raw_imports)
            node = module.nodes[module.raw_imports[0][0]]
            self._reject(
                module,
                "PYC3510",
                "SourceBundle exceeds max_import_edges",
                node,
            )
        for module in self.modules:
            self._check_canceled()
            self._resolve_imports(module)
        for module in self.modules:
            self._check_canceled()
            self._validate_import_binding_uses(module)
        for module in self.modules:
            if module.deferred_top_level_node is not None:
                self._reject(
                    module,
                    "PYC3509",
                    "Only eligible synchronous top-level functions may define a module namespace",
                    module.deferred_top_level_node,
                )

        dependency_edges = tuple(
            sorted(
                {
                    (item.module_id, resolved.target_module_id)
                    for item in self.modules
                    for resolved in item.resolved_imports
                }
            )
        )
        module_order = self._dependency_first_order(dependency_edges)
        return self._publish(module_order, dependency_edges)

    def _analyze_document_shape(self, module: _Module) -> None:
        if module.root["kind"] != "Module":
            self._reject(module, "PYC3509", "Module document lacks a module root", module.root)

        body_set = set(module.body)
        for node in sorted(module.nodes.values(), key=self._source_order_key):
            self._check_canceled()
            if node["kind"] in {"Import", "ImportFrom"} and node["node_id"] not in body_set:
                self._reject(
                    module,
                    "PYC3504",
                    "Local and conditional imports are unsupported",
                    node,
                )
            if self._is_dynamic_import_call(module, node):
                self._reject(
                    module,
                    "PYC3504",
                    "Dynamic import behavior is unsupported",
                    node,
                )

        imports: list[str] = []
        functions: list[str] = []
        records: list[str] = []
        seen_function = False
        function_names: set[str] = set()
        raw_imports: list[tuple[str, int, int, str, str, str]] = []
        import_item_ordinal = 0
        for node_id in module.body:
            self._check_canceled()
            node = module.nodes[node_id]
            kind = node["kind"]
            if kind == "ImportFrom":
                if seen_function:
                    self._reject(
                        module,
                        "PYC3504",
                        "Imports must form the module preamble before every function",
                        node,
                    )
                imports.append(node_id)
                target_module = node["fields"].get("module")
                level = node["fields"].get("level")
                aliases = node["fields"].get("names", ())
                if level != 0 or not isinstance(target_module, str) or not target_module or not aliases:
                    self._reject(
                        module,
                        "PYC3504",
                        "Only nonempty absolute from-import declarations are supported",
                        node,
                    )
                for alias_ordinal, alias_id in enumerate(aliases):
                    alias = module.nodes.get(alias_id)
                    if alias is None or alias.get("kind") != "alias":
                        self._reject(module, "PYC3504", "Import contains an invalid alias", node)
                    imported_name = alias["fields"].get("name")
                    asname = alias["fields"].get("asname")
                    if imported_name == "*" or not isinstance(imported_name, str) or not imported_name:
                        self._reject(
                            module,
                            "PYC3504",
                            "Star and malformed imports are unsupported",
                            alias,
                        )
                    if asname is not None and (not isinstance(asname, str) or not asname):
                        self._reject(module, "PYC3504", "Import alias is malformed", alias)
                    raw_imports.append(
                        (
                            node_id,
                            alias_ordinal,
                            import_item_ordinal,
                            target_module,
                            imported_name,
                            asname or imported_name,
                        )
                    )
                    import_item_ordinal += 1
            elif kind == "FunctionDef":
                seen_function = True
                functions.append(node_id)
                source_name = node["fields"].get("name")
                if not isinstance(source_name, str) or not source_name:
                    self._reject(module, "PYC3506", "Function binding is malformed", node)
                if source_name in function_names:
                    self._reject(
                        module,
                        "PYC3506",
                        f"Module function {source_name!r} is rebound",
                        node,
                    )
                function_names.add(source_name)
                module.functions[source_name] = node
            elif kind == "ClassDef" and self.allow_records:
                if seen_function:
                    self._reject(
                        module,
                        "PYC3601",
                        "Static record classes must precede every top-level function",
                        node,
                    )
                source_name = node["fields"].get("name")
                if not isinstance(source_name, str) or not source_name:
                    self._reject(module, "PYC3601", "Record class binding is malformed", node)
                if source_name in function_names:
                    self._reject(
                        module,
                        "PYC3506",
                        f"Module binding {source_name!r} is rebound",
                        node,
                    )
                function_names.add(source_name)
                records.append(node_id)
                module.records[source_name] = node
            elif kind == "AsyncFunctionDef":
                seen_function = True
                source_name = node["fields"].get("name")
                if not isinstance(source_name, str) or not source_name:
                    self._reject(module, "PYC3506", "Function binding is malformed", node)
                if source_name in function_names:
                    self._reject(
                        module,
                        "PYC3506",
                        f"Module function {source_name!r} is rebound",
                        node,
                    )
                function_names.add(source_name)
                module.ineligible_functions[source_name] = node
                module.deferred_top_level_node = module.deferred_top_level_node or node
            elif kind == "Import":
                self._reject(
                    module,
                    "PYC3504",
                    "Plain imports are unsupported",
                    node,
                )
            else:
                imported_names = {item[5] for item in raw_imports}
                rebound = sorted(imported_names & self._statement_bound_names(module, node))
                if rebound:
                    self._reject(
                        module,
                        "PYC3506",
                        f"Imported binding {rebound[0]!r} is rebound at module scope",
                        node,
                    )
                self._reject(
                    module,
                    "PYC3509",
                    "Executable module initialization and top-level state are unsupported",
                    node,
                )

        if not functions and not module.ineligible_functions:
            self._reject(
                module,
                "PYC3509",
                "Every module document must define at least one top-level function",
                module.nodes[module.body[0]] if module.body else None,
            )

        module.function_ids = tuple(functions)
        module.record_ids = tuple(records)
        module.import_node_ids = tuple(imports)
        module.raw_imports = raw_imports

    def _statement_bound_names(
        self,
        module: _Module,
        node: dict[str, Any],
    ) -> set[str]:
        fields = node["fields"]
        target_ids: list[str] = []
        if node["kind"] in {"Assign", "Delete"}:
            target_ids.extend(fields.get("targets", ()))
        elif node["kind"] in {"AnnAssign", "AugAssign", "For", "NamedExpr"}:
            target_id = fields.get("target")
            if isinstance(target_id, str):
                target_ids.append(target_id)
        names: set[str] = set()
        stack = list(target_ids)
        while stack:
            target = module.nodes.get(stack.pop())
            if not target:
                continue
            if target["kind"] == "Name":
                name = target["fields"].get("id")
                if isinstance(name, str):
                    names.add(name)
            for field_name, value in target["fields"].items():
                stack.extend(
                    python_ir_reference_ids(
                        target["kind"], field_name, value, module.nodes
                    )
                )
        return names

    def _is_dynamic_import_call(self, module: _Module, node: dict[str, Any]) -> bool:
        if node["kind"] != "Call":
            return False
        callee = module.nodes.get(node["fields"].get("func"))
        if not callee:
            return False
        if callee["kind"] == "Name":
            return callee["fields"].get("id") == "__import__"
        if callee["kind"] == "Attribute":
            path = self._attribute_path(module, callee)
            return bool(
                (path and path[0] == "importlib" and path[-1] in _DYNAMIC_IMPORT_ATTRIBUTES)
                or path in {("builtins", "__import__"), ("__builtins__", "__import__")}
            )
        return False

    def _attribute_path(
        self,
        module: _Module,
        node: dict[str, Any],
    ) -> tuple[str, ...] | None:
        if node["kind"] == "Name":
            name = node["fields"].get("id")
            return (name,) if isinstance(name, str) else None
        if node["kind"] != "Attribute":
            return None
        value = module.nodes.get(node["fields"].get("value"))
        if value is None:
            return None
        prefix = self._attribute_path(module, value)
        attribute = node["fields"].get("attr")
        if prefix is None or not isinstance(attribute, str):
            return None
        return prefix + (attribute,)

    @staticmethod
    def _source_order_key(node: dict[str, Any]) -> tuple[int, str]:
        span = node.get("provenance", {}).get("source_span") or {}
        start = span.get("start", {}) if isinstance(span, dict) else {}
        offset = start.get("offset") if isinstance(start, dict) else None
        return (offset if isinstance(offset, int) else 2**63 - 1, node["node_id"])

    def _resolve_imports(self, module: _Module) -> None:
        occupied = set(module.functions) | set(module.records)
        for node_id, alias_ordinal, source_ordinal, target_id, imported_name, local_name in module.raw_imports:
            self._check_canceled()
            import_node = module.nodes[node_id]
            alias_id = import_node["fields"]["names"][alias_ordinal]
            alias_node = module.nodes[alias_id]
            target = self.by_id.get(target_id)
            if target is None:
                code = "PYC3508" if self._has_package_relation(target_id) else "PYC3503"
                message = (
                    f"Import {target_id!r} requests unsupported package or implicit-parent behavior"
                    if code == "PYC3508"
                    else f"Import target module {target_id!r} is not present in SourceBundle"
                )
                self._reject(module, code, message, import_node)
            if target_id == module.module_id:
                self._reject(
                    module,
                    "PYC3507",
                    f"Module {module.module_id!r} imports itself",
                    import_node,
                )
            target_function = target.functions.get(imported_name)
            if target_function is None:
                if imported_name in target.records:
                    self._reject(
                        module,
                        "PYC3610",
                        f"Record class import {target_id}.{imported_name} is outside the module-private Phase 13 record boundary",
                        alias_node,
                        related=(self._span(target, target.records[imported_name]),),
                    )
                if imported_name in target.ineligible_functions:
                    self._reject(
                        module,
                        "PYC3505",
                        f"Imported member {target_id}.{imported_name} is not an eligible synchronous function",
                        alias_node,
                        related=(
                            self._span(target, target.ineligible_functions[imported_name]),
                        ),
                    )
                if imported_name in {item[5] for item in target.raw_imports}:
                    self._reject(
                        module,
                        "PYC3506",
                        f"Imported member {target_id}.{imported_name} would be a re-export",
                        alias_node,
                    )
                if f"{target_id}.{imported_name}" in self.by_id:
                    self._reject(
                        module,
                        "PYC3506",
                        f"Imported member {target_id}.{imported_name} would be a module object",
                        alias_node,
                    )
                self._reject(
                    module,
                    "PYC3505",
                    f"Imported member {target_id}.{imported_name} is not a direct top-level function",
                    alias_node,
                )
            if not self._importable_signature(target, target_function):
                self._reject(
                    module,
                    "PYC3505",
                    f"Imported member {target_id}.{imported_name} is not an eligible direct function",
                    alias_node,
                    related=(self._span(target, target_function),),
                )
            if local_name == "range" or local_name in occupied:
                self._reject(
                    module,
                    "PYC3506",
                    f"Imported binding {local_name!r} collides with another module binding",
                    alias_node,
                )
            occupied.add(local_name)
            resolved = ResolvedImport(
                import_item_id=(
                    f"module-import-{module.module_id}-{source_ordinal:04d}-"
                    + _stable_id(
                    "",
                    module.module_id,
                    node_id,
                    alias_ordinal,
                    target_id,
                    imported_name,
                    local_name,
                    )
                ),
                import_node_id=node_id,
                alias_node_id=alias_id,
                importer_module_id=module.module_id,
                target_module_id=target_id,
                imported_name=imported_name,
                local_name=local_name,
                target_function_node_id=target_function["node_id"],
                source_ordinal=source_ordinal,
            )
            module.resolved_imports.append(resolved)
            module.imported_bindings[local_name] = resolved

    def _has_package_relation(self, target_id: str) -> bool:
        return any(
            candidate.startswith(target_id + ".") or target_id.startswith(candidate + ".")
            for candidate in self.by_id
        )

    def _importable_signature(self, module: _Module, function: dict[str, Any]) -> bool:
        fields = function["fields"]
        if fields.get("decorator_list") or fields.get("type_params"):
            return False
        arguments = module.nodes.get(fields.get("args"), {})
        if arguments.get("kind") != "arguments":
            return False
        args = arguments["fields"]
        keyword_only_ids = tuple(args.get("kwonlyargs", ()))
        keyword_defaults = tuple(args.get("kw_defaults", ()))
        if (
            args.get("vararg") is not None
            or args.get("kwarg") is not None
            or args.get("defaults")
            or (
                bool(keyword_only_ids)
                and (
                    not self.allow_required_keyword_only
                    or len(keyword_defaults) != len(keyword_only_ids)
                    or any(item is not None for item in keyword_defaults)
                )
            )
        ):
            return False
        parameter_ids = (
            tuple(args.get("posonlyargs", ()))
            + tuple(args.get("args", ()))
            + keyword_only_ids
        )
        annotation_ids = [
            module.nodes[parameter_id]["fields"].get("annotation")
            for parameter_id in parameter_ids
        ]
        annotation_ids.append(fields.get("returns"))
        for annotation_id in annotation_ids:
            annotation = module.nodes.get(annotation_id)
            if (
                not annotation
                or annotation["kind"] != "Name"
                or annotation["fields"].get("id") not in {"bool", "float", "int", "str"}
            ):
                return False
        rejected_body_kinds = {
            "AsyncFunctionDef",
            "Await",
            "ClassDef",
            "Global",
            "Lambda",
            "Nonlocal",
            "Yield",
            "YieldFrom",
        }
        stack = list(function["fields"].get("body", ()))
        while stack:
            node_id = stack.pop()
            node = module.nodes[node_id]
            if node["kind"] in rejected_body_kinds or node["kind"] == "FunctionDef":
                return False
            for field_name, value in node["fields"].items():
                stack.extend(
                    python_ir_reference_ids(
                        node["kind"],
                        field_name,
                        value,
                        module.nodes,
                    )
                )
        return True

    def _validate_import_binding_uses(self, module: _Module) -> None:
        parents = self._parent_slots(module)
        imported_names = set(module.imported_bindings)
        owners = self._function_owners(module, parents)
        shadowed = self._function_shadow_names(module)
        foreign_function_names = {
            source_name
            for other in self.modules
            if other.module_id != module.module_id
            for source_name in set(other.functions) | set(other.ineligible_functions)
        }
        module_id_parts = {
            tuple(item.module_id.split(".")) for item in self.modules
        }
        for node in module.nodes.values():
            self._check_canceled()
            fields = node["fields"]
            if node["kind"] == "arg" and fields.get("arg") in imported_names:
                self._reject(
                    module,
                    "PYC3506",
                    f"Imported binding {fields['arg']!r} is rebound by a parameter",
                    node,
                )
            if node["kind"] in {"ExceptHandler", "MatchAs", "MatchStar"}:
                name = fields.get("name")
                if name in imported_names:
                    self._reject(
                        module,
                        "PYC3506",
                        f"Imported binding {name!r} is rebound by a local declaration",
                        node,
                    )
            if node["kind"] in {"FunctionDef", "AsyncFunctionDef"}:
                name = fields.get("name")
                if node["node_id"] not in module.function_ids and name in imported_names:
                    self._reject(
                        module,
                        "PYC3506",
                        f"Imported binding {name!r} is rebound by a nested definition",
                        node,
                    )
            if node["kind"] == "Attribute":
                parent_id, field_name = parents.get(node["node_id"], (None, None))
                parent = module.nodes.get(parent_id)
                if parent and parent["kind"] == "Attribute" and field_name == "value":
                    continue
                path = self._attribute_path(module, node)
                owner = owners.get(node["node_id"])
                if (
                    path
                    and path[0] not in shadowed.get(owner, set())
                    and any(path[: len(parts)] == parts for parts in module_id_parts)
                ):
                    self._reject(
                        module,
                        "PYC3506",
                        f"Logical module {'.'.join(path)!r} cannot be used as a runtime value",
                        node,
                    )
            if node["kind"] != "Name" or fields.get("id") not in imported_names:
                if node["kind"] != "Name":
                    continue
                source_name = fields.get("id")
                parent_id, field_name = parents.get(node["node_id"], (None, None))
                parent = module.nodes.get(parent_id)
                owner = owners.get(node["node_id"])
                if (
                    (source_name,) in module_id_parts
                    and source_name not in module.functions
                    and source_name not in shadowed.get(owner, set())
                ):
                    self._reject(
                        module,
                        "PYC3506",
                        f"Logical module {source_name!r} cannot be used as a runtime value",
                        node,
                    )
                if (
                    parent
                    and parent["kind"] == "Call"
                    and field_name == "func"
                    and source_name in foreign_function_names
                    and source_name not in module.functions
                    and source_name not in imported_names
                    and source_name != "range"
                    and source_name not in shadowed.get(owner, set())
                ):
                    self._reject(
                        module,
                        "PYC3506",
                        f"Foreign function {source_name!r} is used without an explicit import",
                        node,
                    )
                continue
            parent_id, field_name = parents.get(node["node_id"], (None, None))
            parent = module.nodes.get(parent_id)
            if not parent or parent["kind"] != "Call" or field_name != "func":
                self._reject(
                    module,
                    "PYC3506",
                    f"Imported binding {fields['id']!r} may only be used as a direct call target",
                    node,
                )

    def _parent_slots(self, module: _Module) -> dict[str, tuple[str, str]]:
        result: dict[str, tuple[str, str]] = {}
        known = set(module.nodes)
        for parent in module.nodes.values():
            for field_name, value in parent["fields"].items():
                for child_id in python_ir_reference_ids(parent["kind"], field_name, value, known):
                    result.setdefault(child_id, (parent["node_id"], field_name))
        return result

    def _dependency_first_order(
        self, dependency_edges: tuple[tuple[str, str], ...]
    ) -> tuple[str, ...]:
        dependencies = {module_id: set() for module_id in self.by_id}
        dependents = {module_id: set() for module_id in self.by_id}
        for importer, target in dependency_edges:
            dependencies[importer].add(target)
            dependents[target].add(importer)
        ready = sorted(module_id for module_id, values in dependencies.items() if not values)
        order: list[str] = []
        while ready:
            self._check_canceled()
            current = ready.pop(0)
            order.append(current)
            for dependent in sorted(dependents[current]):
                dependencies[dependent].discard(current)
                if not dependencies[dependent] and dependent not in ready and dependent not in order:
                    ready.append(dependent)
                    ready.sort()
        if len(order) != len(self.by_id):
            component = self._first_cyclic_component(dependency_edges)
            cycle_items = sorted(
                (
                    resolved.importer_module_id,
                    resolved.source_ordinal,
                    resolved.target_module_id,
                    module,
                    resolved,
                )
                for module in self.modules
                for resolved in module.resolved_imports
                if resolved.importer_module_id in component
                and resolved.target_module_id in component
            )
            _, _, _, module, resolved = cycle_items[0]
            related = tuple(
                self._span(item_module, item_module.nodes[item.import_node_id])
                for _, _, _, item_module, item in cycle_items[1:]
            )
            self._reject(
                module,
                "PYC3507",
                "Module dependency graph contains a rejected import cycle",
                module.nodes[resolved.import_node_id],
                related=related,
            )
        return tuple(order)

    def _first_cyclic_component(
        self,
        dependency_edges: tuple[tuple[str, str], ...],
    ) -> frozenset[str]:
        graph = {module_id: set() for module_id in self.by_id}
        reverse = {module_id: set() for module_id in self.by_id}
        for importer, target in dependency_edges:
            graph[importer].add(target)
            reverse[target].add(importer)

        visited: set[str] = set()
        finish: list[str] = []

        def visit(node: str) -> None:
            self._check_canceled()
            visited.add(node)
            for child in sorted(graph[node]):
                if child not in visited:
                    visit(child)
            finish.append(node)

        for module_id in sorted(graph):
            if module_id not in visited:
                visit(module_id)

        assigned: set[str] = set()
        cyclic: list[frozenset[str]] = []

        def collect(node: str, component: set[str]) -> None:
            self._check_canceled()
            assigned.add(node)
            component.add(node)
            for parent in sorted(reverse[node]):
                if parent not in assigned:
                    collect(parent, component)

        for module_id in reversed(finish):
            if module_id in assigned:
                continue
            component: set[str] = set()
            collect(module_id, component)
            if len(component) > 1 or any(item in graph[item] for item in component):
                cyclic.append(frozenset(component))
        if not cyclic:
            raise RuntimeError("topological ordering failed without a cyclic component")
        return min(cyclic, key=lambda item: tuple(sorted(item)))

    def _publish(
        self,
        module_order: tuple[str, ...],
        dependency_edges: tuple[tuple[str, str], ...],
    ) -> ModuleResolutionProduct:
        qualify_names = len(self.modules) > 1
        function_facts: dict[str, dict[str, Any]] = {}
        record_facts: dict[str, dict[str, Any]] = {}
        generated_by_node: dict[str, str] = {}
        generated_record_by_node: dict[str, str] = {}
        function_ordinal = 0
        for module_id in module_order:
            module = self.by_id[module_id]
            for function_id in module.function_ids:
                function = module.nodes[function_id]
                source_name = function["fields"]["name"]
                flattened_name = (
                    _qualified_function_name(module_id, source_name)
                    if qualify_names
                    else source_name
                )
                generated_by_node[function_id] = flattened_name
                function_facts[function_id] = {
                    "function_node_id": function_id,
                    "module_id": module_id,
                    "document_id": module.document_id,
                    "source_name": source_name,
                    "flattened_name": flattened_name,
                    "bundle_function_ordinal": function_ordinal,
                    "linkage": "external",
                    "module_generated_name": qualify_names,
                }
                function_ordinal += 1
            for record_ordinal, record_id in enumerate(module.record_ids):
                record = module.nodes[record_id]
                source_name = record["fields"]["name"]
                flattened_name = (
                    _qualified_function_name(module_id, source_name)
                    if qualify_names
                    else source_name
                )
                generated_record_by_node[record_id] = flattened_name
                record_facts[record_id] = {
                    "class_node_id": record_id,
                    "module_id": module_id,
                    "document_id": module.document_id,
                    "source_name": source_name,
                    "flattened_name": flattened_name,
                    "module_record_ordinal": record_ordinal,
                    "module_generated_name": qualify_names,
                }

        rewritten_nodes: dict[str, dict[str, Any]] = {}
        flattened_body: list[str] = []
        for module_id in module_order:
            self._check_canceled()
            module = self.by_id[module_id]
            parents = self._parent_slots(module)
            shadowed = self._function_shadow_names(module)
            owner_by_node = self._function_owners(module, parents)
            for original in module.python_ir["nodes"]:
                if original["node_id"] == module.python_ir["root_node_id"]:
                    continue
                node = _thaw(original)
                node_id = node["node_id"]
                if node["kind"] == "FunctionDef" and node_id in generated_by_node:
                    node["fields"]["name"] = generated_by_node[node_id]
                elif node["kind"] == "ClassDef" and node_id in generated_record_by_node:
                    node["fields"]["name"] = generated_record_by_node[node_id]
                elif node["kind"] == "Name":
                    parent_id, field_name = parents.get(node_id, (None, None))
                    parent = module.nodes.get(parent_id)
                    source_name = node["fields"].get("id")
                    owner = owner_by_node.get(node_id)
                    if (
                        source_name in module.records
                        and owner is not None
                        and source_name not in shadowed.get(owner, set())
                    ):
                        node["fields"]["id"] = generated_record_by_node[
                            module.records[source_name]["node_id"]
                        ]
                    if parent and parent["kind"] == "Call" and field_name == "func":
                        source_name = node["fields"].get("id")
                        if source_name in module.imported_bindings:
                            target_id = module.imported_bindings[source_name].target_function_node_id
                            node["fields"]["id"] = generated_by_node[target_id]
                        elif source_name in module.functions:
                            owner = owner_by_node.get(node_id)
                            if source_name not in shadowed.get(owner, set()):
                                node["fields"]["id"] = generated_by_node[
                                    module.functions[source_name]["node_id"]
                                ]
                rewritten_nodes[node_id] = node
            flattened_body.extend(module.body)

        document_nodes: list[dict[str, Any]] = []
        for module in self.modules:
            document_node_id = _stable_id(
                "syn-", "ModuleDocument", module.module_id, module.document_id
            )
            module.document_plan_node_id = document_node_id
            document_nodes.append(
                self._synthetic_node(
                    document_node_id,
                    "ModuleDocument",
                    {
                        "module_id": module.module_id,
                        "bundle_ordinal": module.bundle_ordinal,
                        "is_primary": module.is_primary,
                        "import_node_ids": list(module.import_node_ids),
                        "function_node_ids": list(module.function_ids),
                    },
                    tuple(module.import_node_ids + module.record_ids + module.function_ids),
                )
            )

        initialization_node_id = _stable_id(
            "syn-", "ModuleInitialization", *module_order, *dependency_edges
        )
        initialization_node = self._synthetic_node(
            initialization_node_id,
            "ModuleInitialization",
            {
                "module_order": list(module_order),
                "dependency_edges": [
                    {"importer_module_id": importer, "target_module_id": target}
                    for importer, target in dependency_edges
                ],
                "cycle_policy": "reject-all-cycles",
                "runtime_initialization": "none",
            },
            tuple(module.document_plan_node_id for module in self.modules),
        )
        assembly_node_id = _stable_id(
            "syn-", "ModuleBundleAssembly", initialization_node_id, *module_order
        )
        assembly_node = self._synthetic_node(
            assembly_node_id,
            "ModuleBundleAssembly",
            {
                "module_order": list(module_order),
                "translation_unit_count": 1,
                "runtime_initializers": 0,
            },
            (initialization_node_id,),
        )
        bundle_document_id = _stable_id(
            "bundle-", self.bundle["primary_module_id"], *(
                module.document_id for module in self.modules
            )
        )
        root_node_id = _stable_id("syn-", "Module", bundle_document_id, *flattened_body)
        root_node = self._synthetic_node(
            root_node_id,
            "Module",
            {"body": flattened_body, "type_ignores": []},
            tuple(module.document_plan_node_id for module in self.modules),
        )
        python_ir = {
            "schema_version": "python-ir/0.4",
            "document_id": bundle_document_id,
            "root_node_id": root_node_id,
            "nodes": [
                root_node,
                *(
                    rewritten_nodes[node["node_id"]]
                    for module_id in module_order
                    for node in self.by_id[module_id].python_ir["nodes"]
                    if node["node_id"] != self.by_id[module_id].python_ir["root_node_id"]
                ),
                *document_nodes,
                initialization_node,
                assembly_node,
            ],
        }

        import_facts = [
            resolved.to_fact()
            for module_id in module_order
            for resolved in self.by_id[module_id].resolved_imports
        ]
        identity_facts = [
            {
                "module_id": module.module_id,
                "document_id": module.document_id,
                "logical_name": module.logical_name,
                "bundle_ordinal": module.bundle_ordinal,
                "is_primary": module.is_primary,
                "document_plan_node_id": module.document_plan_node_id,
                "import_node_ids": list(module.import_node_ids),
                "function_node_ids": list(module.function_ids),
            }
            for module in self.modules
        ]
        source_facts = [self._source_fact(module) for module in self.modules]
        namespace_facts = [
            {
                "module_id": module.module_id,
                "document_plan_node_id": module.document_plan_node_id,
                "import_node_ids": list(module.import_node_ids),
                "function_node_ids": list(module.function_ids),
                "local_function_names": [
                    module.nodes[node_id]["fields"]["name"] for node_id in module.function_ids
                ],
                "imported_bindings": [
                    {
                        "local_name": item.local_name,
                        "target_module_id": item.target_module_id,
                        "target_function_node_id": item.target_function_node_id,
                    }
                    for item in module.resolved_imports
                ],
                "generated_function_names": [
                    generated_by_node[node_id] for node_id in module.function_ids
                ],
            }
            for module in self.modules
        ]
        initialization_fact = {
            "initialization_node_id": initialization_node_id,
            "module_order": list(module_order),
            "dependency_edges": [
                {"importer_module_id": importer, "target_module_id": target}
                for importer, target in dependency_edges
            ],
            "cycle_policy": "reject-all-cycles",
            "runtime_initialization": "none",
        }
        tables = (
            self._fact_table("module-identity-facts", "module-id", identity_facts, "module_id"),
            self._fact_table("module-import-facts", "module-import-item-id", import_facts, "import_item_id"),
            self._fact_table("module-function-facts", "function-node-id", list(function_facts.values()), "function_node_id"),
            self._fact_table("module-initialization-facts", "initialization-node-id", [initialization_fact], "initialization_node_id"),
            self._fact_table("module-namespace-facts", "module-id", namespace_facts, "module_id"),
            self._fact_table("module-source-facts", "module-id", source_facts, "module_id"),
        )
        resolution = {
            "schema_version": "module-resolution/0.12",
            "primary_module_id": self.bundle["primary_module_id"],
            "source_module_order": [module.module_id for module in self.modules],
            "module_order": list(module_order),
            "dependency_edges": initialization_fact["dependency_edges"],
            "import_item_count": len(import_facts),
            "flattened_root_node_id": root_node_id,
            "bundle_document_id": bundle_document_id,
            "function_renames": [
                {
                    "function_node_id": node_id,
                    "source_name": fact["source_name"],
                    "flattened_name": fact["flattened_name"],
                }
                for node_id, fact in sorted(
                    function_facts.items(), key=lambda item: item[1]["bundle_function_ordinal"]
                )
            ],
            "initialization_node_id": initialization_node_id,
            "module_bundle_assembly_node_id": assembly_node_id,
        }
        return ModuleResolutionProduct(
            python_ir=python_ir,
            module_bundle=_thaw(self.bundle),
            module_resolution=resolution,
            module_fact_tables=tables,
            module_import_node_ids=tuple(
                node_id
                for module_id in module_order
                for node_id in self.by_id[module_id].import_node_ids
            ),
            module_function_by_node={
                key: value for key, value in sorted(function_facts.items())
            },
            module_record_by_node={
                key: value for key, value in sorted(record_facts.items())
            },
            module_bundle_assembly_node_id=assembly_node_id,
        )

    def _function_shadow_names(self, module: _Module) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {node_id: set() for node_id in module.function_ids}
        owners = self._function_owners(module, self._parent_slots(module))
        store_parent_fields = {"targets", "target"}
        parents = self._parent_slots(module)
        for node in module.nodes.values():
            owner = owners.get(node["node_id"])
            if owner not in result:
                continue
            if node["kind"] == "arg":
                result[owner].add(node["fields"].get("arg", ""))
            elif node["kind"] == "Name":
                _, field_name = parents.get(node["node_id"], (None, None))
                if field_name in store_parent_fields:
                    result[owner].add(node["fields"].get("id", ""))
            elif node["kind"] in {"FunctionDef", "AsyncFunctionDef"} and node["node_id"] != owner:
                result[owner].add(node["fields"].get("name", ""))
        return result

    def _function_owners(
        self,
        module: _Module,
        parents: dict[str, tuple[str, str]],
    ) -> dict[str, str]:
        functions = set(module.function_ids)
        result: dict[str, str] = {}
        for node_id in module.nodes:
            current = node_id
            seen: set[str] = set()
            while current not in seen:
                seen.add(current)
                if current in functions:
                    result[node_id] = current
                    break
                parent_id, _ = parents.get(current, (None, None))
                if parent_id is None:
                    break
                current = parent_id
        return result

    def _source_fact(self, module: _Module) -> dict[str, Any]:
        source_document = module.source.get("source_document", {})
        return {
            "module_id": module.module_id,
            "source_document_id": module.document_id,
            "logical_source_name": module.logical_name,
            "document_id": module.document_id,
            "logical_name": module.logical_name,
            "bundle_ordinal": module.bundle_ordinal,
            "is_primary": module.is_primary,
            "document_plan_node_id": module.document_plan_node_id,
            "import_node_ids": list(module.import_node_ids),
            "function_node_ids": list(module.function_ids),
            "content_fingerprint": source_document.get("utf8_sha256"),
            "eligible": True,
            "diagnostic_code": None,
            "reason": None,
        }

    def _fact_table(
        self,
        table_id: str,
        key_domain: str,
        values: list[dict[str, Any]],
        key_field: str,
    ) -> dict[str, Any]:
        records = []
        for value in sorted(values, key=lambda item: item[key_field]):
            source_ids: list[str] = []
            for field_name in (
                "document_plan_node_id",
                "import_node_id",
                "alias_node_id",
                "target_function_node_id",
                "function_node_id",
                "initialization_node_id",
            ):
                item = value.get(field_name)
                if isinstance(item, str):
                    source_ids.append(item)
            for field_name in ("import_node_ids", "function_node_ids"):
                source_ids.extend(
                    item for item in value.get(field_name, ()) if isinstance(item, str)
                )
            for binding in value.get("imported_bindings", ()):
                target = binding.get("target_function_node_id") if isinstance(binding, dict) else None
                if isinstance(target, str):
                    source_ids.append(target)
            source_ids = list(dict.fromkeys(source_ids))
            records.append(
                {
                    "key": value[key_field],
                    "value": value,
                    "provenance": {
                        "source_node_ids": source_ids,
                        "evidence": ["explicit-sourcebundle-closed-world", "deterministic-module-resolution"],
                    },
                }
            )
        return {
            "schema_version": "fact-table/0.12",
            "table_id": table_id,
            "producer_stage": self.stage_id,
            "key_domain": key_domain,
            "completeness": "complete",
            "invalidation_dependencies": [self.invalidation_dependency],
            "records": records,
        }

    @staticmethod
    def _synthetic_node(
        node_id: str,
        kind: str,
        fields: dict[str, Any],
        origins: tuple[str, ...],
    ) -> dict[str, Any]:
        return {
            "node_id": node_id,
            "kind": kind,
            "fields": fields,
            "provenance": {
                "origin_kind": "synthetic",
                "source_span": None,
                "origin_node_ids": list(origins),
            },
        }

    def _span(self, module: _Module, node: dict[str, Any] | None) -> dict[str, Any]:
        if node is not None:
            span = node.get("provenance", {}).get("source_span")
            if isinstance(span, dict):
                return _thaw(span)
        return {
            "document_id": module.document_id,
            "start": {"line": 1, "column": 0, "offset": 0},
            "end": {"line": 1, "column": 0, "offset": 0},
        }

    def _reject(
        self,
        module: _Module,
        code: str,
        message: str,
        node: dict[str, Any] | None,
        *,
        related: tuple[dict[str, Any], ...] = (),
    ) -> None:
        raise ModuleResolutionError(
            code,
            message,
            module_id=module.module_id,
            logical_name=module.logical_name,
            source_span=self._span(module, node),
            related_spans=related,
        )

    def _check_canceled(self) -> None:
        if self.cancellation is not None and self.cancellation.is_canceled:
            raise ModuleAnalysisCanceled
