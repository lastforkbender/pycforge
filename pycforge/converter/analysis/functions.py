"""Phase 9 function, call, return-path, and local-declaration facts."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .model import ValueCategory
from .symbols import PythonIRIndex


ANNOTATION_CATEGORIES = {
    "int": ValueCategory.INTEGER,
    "float": ValueCategory.FLOAT,
    "bool": ValueCategory.BOOLEAN,
    "str": ValueCategory.STRING,
}

CATEGORY_C_TYPES = {
    ValueCategory.INTEGER: "int64_t",
    ValueCategory.FLOAT: "double",
    ValueCategory.BOOLEAN: "bool",
    ValueCategory.STRING: "const char *",
}


class FunctionAnalysisCanceled(Exception):
    """Raised at bounded safe points before function facts are published."""


def _boundary(category: ValueCategory) -> tuple[str, str, str]:
    if category is ValueCategory.STRING:
        return "borrowed-pointer", "borrowed", "caller-managed-valid-for-call"
    return "by-value", "not-applicable", "callee-activation"


@dataclass(frozen=True, slots=True)
class ParameterFact:
    parameter_node_id: str
    binding_id: str
    source_name: str
    ordinal: int
    category: ValueCategory
    c_type: str | None
    annotation_node_id: str | None
    annotation_spelling: str | None
    passing: str
    ownership: str
    lifetime: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_node_id": self.parameter_node_id,
            "binding_id": self.binding_id,
            "source_name": self.source_name,
            "ordinal": self.ordinal,
            "category": self.category.value,
            "c_type": self.c_type,
            "annotation_node_id": self.annotation_node_id,
            "annotation_spelling": self.annotation_spelling,
            "passing": self.passing,
            "ownership": self.ownership,
            "lifetime": self.lifetime,
        }


@dataclass(frozen=True, slots=True)
class FunctionSignatureFact:
    function_node_id: str
    binding_id: str | None
    source_name: str
    parameters: tuple[ParameterFact, ...]
    return_category: ValueCategory
    return_c_type: str | None
    return_annotation_node_id: str | None
    return_annotation_spelling: str | None
    return_passing: str
    return_ownership: str
    return_lifetime: str
    prototype_required: bool
    eligible: bool
    rejection_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "function_node_id": self.function_node_id,
            "binding_id": self.binding_id,
            "source_name": self.source_name,
            "parameters": [item.to_dict() for item in self.parameters],
            "return_category": self.return_category.value,
            "return_c_type": self.return_c_type,
            "return_annotation_node_id": self.return_annotation_node_id,
            "return_annotation_spelling": self.return_annotation_spelling,
            "return_passing": self.return_passing,
            "return_ownership": self.return_ownership,
            "return_lifetime": self.return_lifetime,
            "prototype_required": self.prototype_required,
            "eligible": self.eligible,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True, slots=True)
class CallTargetFact:
    call_node_id: str
    callee_node_id: str | None
    target_function_node_id: str | None
    target_binding_id: str | None
    target_name: str | None
    resolution: str
    argument_node_ids: tuple[str, ...]
    argument_categories: tuple[ValueCategory, ...]
    parameter_categories: tuple[ValueCategory, ...]
    return_category: ValueCategory
    evaluation_order: tuple[str, ...]
    arguments_evaluated_once: bool
    ownership_boundary: tuple[str, ...]
    annotation_evidence: tuple[str, ...]
    supported: bool
    diagnostic_code: str | None
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_node_id": self.call_node_id,
            "callee_node_id": self.callee_node_id,
            "target_function_node_id": self.target_function_node_id,
            "target_binding_id": self.target_binding_id,
            "target_name": self.target_name,
            "resolution": self.resolution,
            "argument_node_ids": list(self.argument_node_ids),
            "argument_categories": [item.value for item in self.argument_categories],
            "parameter_categories": [item.value for item in self.parameter_categories],
            "return_category": self.return_category.value,
            "evaluation_order": list(self.evaluation_order),
            "arguments_evaluated_once": self.arguments_evaluated_once,
            "ownership_boundary": list(self.ownership_boundary),
            "annotation_evidence": list(self.annotation_evidence),
            "supported": self.supported,
            "diagnostic_code": self.diagnostic_code,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ReturnPathFact:
    function_node_id: str
    return_node_ids: tuple[str, ...]
    return_categories: tuple[ValueCategory, ...]
    expected_category: ValueCategory
    compatible: bool
    fallthrough_possible: bool
    cleanup: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "function_node_id": self.function_node_id,
            "return_node_ids": list(self.return_node_ids),
            "return_categories": [item.value for item in self.return_categories],
            "expected_category": self.expected_category.value,
            "compatible": self.compatible,
            "fallthrough_possible": self.fallthrough_possible,
            "cleanup": self.cleanup,
        }


@dataclass(frozen=True, slots=True)
class LocalDeclarationFact:
    function_node_id: str
    use_before_binding_node_ids: tuple[str, ...]
    loop_target_escape_node_ids: tuple[str, ...]
    first_definitions_in_control_node_ids: tuple[str, ...]
    representation_conflict_node_ids: tuple[str, ...]
    loop_target_rebind_node_ids: tuple[str, ...]
    loop_target_mutation_node_ids: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not (
            self.use_before_binding_node_ids
            or self.loop_target_escape_node_ids
            or self.first_definitions_in_control_node_ids
            or self.representation_conflict_node_ids
            or self.loop_target_rebind_node_ids
            or self.loop_target_mutation_node_ids
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "function_node_id": self.function_node_id,
            "use_before_binding_node_ids": list(self.use_before_binding_node_ids),
            "loop_target_escape_node_ids": list(self.loop_target_escape_node_ids),
            "first_definitions_in_control_node_ids": list(self.first_definitions_in_control_node_ids),
            "representation_conflict_node_ids": list(self.representation_conflict_node_ids),
            "loop_target_rebind_node_ids": list(self.loop_target_rebind_node_ids),
            "loop_target_mutation_node_ids": list(self.loop_target_mutation_node_ids),
            "valid": self.valid,
        }


@dataclass(frozen=True, slots=True)
class CallGraphFact:
    edges: tuple[tuple[str, str], ...]
    recursive_function_node_ids: tuple[str, ...]
    recursive_call_node_ids: tuple[str, ...]
    policy: str = "direct-and-mutual-recursion-unsupported-in-phase9"

    def to_dict(self) -> dict[str, Any]:
        return {
            "edges": [{"caller": left, "callee": right} for left, right in self.edges],
            "recursive_function_node_ids": list(self.recursive_function_node_ids),
            "recursive_call_node_ids": list(self.recursive_call_node_ids),
            "policy": self.policy,
        }


class FunctionFactsAnalyzer:
    def __init__(
        self,
        module: dict[str, Any],
        bindings: tuple[dict[str, Any], ...],
        *,
        ignored_call_node_ids: frozenset[str] = frozenset(),
        allow_required_keyword_only: bool = False,
        cancellation: Any = None,
    ) -> None:
        self.module = module
        self.index = PythonIRIndex(module)
        self.bindings = bindings
        self.ignored_call_node_ids = ignored_call_node_ids
        self.allow_required_keyword_only = allow_required_keyword_only
        self.cancellation = cancellation
        self.binding_by_decl = {item["declaration_node_id"]: item for item in bindings}
        self.binding_by_occurrence = {node_id: item for item in bindings for node_id in item["occurrence_node_ids"]}
        self.parent_by_node: dict[str, str] = {}
        for parent in self.index.nodes.values():
            for child in self.index.child_ids(parent):
                self.parent_by_node.setdefault(child, parent["node_id"])
        root = self.index.node(module["root_node_id"])
        self.module_body = tuple(root["fields"].get("body", []))
        self.function_ids = tuple(node_id for node_id in self.module_body if self.index.node(node_id)["kind"] == "FunctionDef")

    def signatures(self) -> tuple[FunctionSignatureFact, ...]:
        self._check_cancellation()
        names: list[str] = []
        for node_id in self.function_ids:
            self._check_cancellation()
            names.append(self.index.node(node_id)["fields"].get("name", ""))
        duplicates = {name for name, count in Counter(names).items() if count > 1}
        facts: list[FunctionSignatureFact] = []
        for node_id in self.function_ids:
            self._check_cancellation()
            facts.append(self._signature(self.index.node(node_id), duplicates))
        return tuple(sorted(facts, key=lambda item: item.function_node_id))

    def _check_cancellation(self) -> None:
        if self.cancellation is not None and bool(
            getattr(self.cancellation, "is_canceled", False)
        ):
            raise FunctionAnalysisCanceled

    def preliminary_call_returns(self, signatures: tuple[FunctionSignatureFact, ...]) -> dict[str, ValueCategory]:
        by_binding = {item.binding_id: item for item in signatures if item.binding_id and item.eligible}
        result: dict[str, ValueCategory] = {}
        for node in self.index.nodes.values():
            if (
                node["kind"] != "Call"
                or node["node_id"] in self.ignored_call_node_ids
                or self._is_range_iterator(node)
            ):
                continue
            callee_id = node["fields"].get("func")
            callee_binding = self.binding_by_occurrence.get(callee_id)
            signature = by_binding.get(callee_binding["binding_id"] if callee_binding else None)
            if signature:
                result[node["node_id"]] = signature.return_category
        return result

    def calls(self, signatures: tuple[FunctionSignatureFact, ...], categories: dict[str, ValueCategory]) -> tuple[CallTargetFact, ...]:
        by_binding = {item.binding_id: item for item in signatures if item.binding_id}
        facts: list[CallTargetFact] = []
        for node in self.index.nodes.values():
            if node["kind"] != "Call":
                continue
            if node["node_id"] in self.ignored_call_node_ids:
                continue
            if self._is_range_iterator(node):
                facts.append(self._range_call_fact(node, categories))
                continue
            fields = node["fields"]
            callee_id = fields.get("func")
            callee = self.index.nodes.get(callee_id)
            args = tuple(fields.get("args", []))
            arg_categories = tuple(categories.get(item, ValueCategory.UNKNOWN) for item in args)
            if not callee or callee["kind"] != "Name":
                facts.append(self._unsupported_call(node, callee_id, args, arg_categories, "dynamic-target", "PYC2901", "Call target is not a directly resolved function name"))
                continue
            binding = self.binding_by_occurrence.get(callee_id)
            signature = by_binding.get(binding["binding_id"] if binding else None)
            if not signature:
                facts.append(self._unsupported_call(node, callee_id, args, arg_categories, "unresolved-target", "PYC2901", f"Unresolved call target: {callee['fields'].get('id')}"))
                continue
            if fields.get("keywords"):
                facts.append(self._call_from_signature(node, signature, args, arg_categories, False, "PYC2910", "Keyword and unpacked keyword arguments are unsupported"))
                continue
            if any(self.index.node(item)["kind"] == "Starred" for item in args):
                facts.append(self._call_from_signature(node, signature, args, arg_categories, False, "PYC2910", "Unpacked positional arguments are unsupported"))
                continue
            if not signature.eligible:
                facts.append(self._call_from_signature(node, signature, args, arg_categories, False, "PYC2902", signature.rejection_reason or "Target signature is ineligible"))
                continue
            params = tuple(item.category for item in signature.parameters)
            if len(args) != len(params):
                facts.append(self._call_from_signature(node, signature, args, arg_categories, False, "PYC2904", "Positional argument count does not match the target signature"))
                continue
            if arg_categories != params:
                facts.append(self._call_from_signature(node, signature, args, arg_categories, False, "PYC2905", "Argument representations do not match the target signature"))
                continue
            facts.append(self._call_from_signature(node, signature, args, arg_categories, True, None, None))
        return tuple(sorted(facts, key=lambda item: item.call_node_id))

    def return_paths(self, signatures: tuple[FunctionSignatureFact, ...], categories: dict[str, ValueCategory]) -> tuple[ReturnPathFact, ...]:
        by_node = {item.function_node_id: item for item in signatures}
        result: list[ReturnPathFact] = []
        for function_id in self.function_ids:
            function = self.index.node(function_id)
            signature = by_node[function_id]
            returns: list[str] = []
            self._collect_returns(function["fields"].get("body", []), returns)
            return_categories = tuple(categories.get(self.index.node(item)["fields"].get("value"), ValueCategory.NONE) for item in returns)
            compatible = bool(returns) and all(item is signature.return_category for item in return_categories)
            result.append(ReturnPathFact(function_id, tuple(returns), return_categories, signature.return_category, compatible, not self._block_guarantees_return(function["fields"].get("body", [])), "no-cleanup-required"))
        return tuple(sorted(result, key=lambda item: item.function_node_id))

    def local_declarations(self, categories: dict[str, ValueCategory], signatures: tuple[FunctionSignatureFact, ...]) -> tuple[LocalDeclarationFact, ...]:
        signature_by_function = {item.function_node_id: item for item in signatures}
        results: list[LocalDeclarationFact] = []
        for function_id in self.function_ids:
            function = self.index.node(function_id)
            args_node = self.index.node(function["fields"]["args"])
            parameter_ids = list(args_node["fields"].get("posonlyargs", [])) + list(args_node["fields"].get("args", []))
            if self.allow_required_keyword_only:
                parameter_ids += list(args_node["fields"].get("kwonlyargs", []))
            initialized = {self.binding_by_decl[item]["binding_id"] for item in parameter_ids if item in self.binding_by_decl}
            use_before: list[str] = []
            loop_escape: list[str] = []
            control_defs: list[str] = []
            self._analyze_statements(function["fields"].get("body", []), initialized, set(), 0, use_before, loop_escape, control_defs)
            signature = signature_by_function[function_id]
            binding_categories = {item.binding_id: item.category for item in signature.parameters}
            representation_conflicts: list[str] = []
            target_rebinds: list[str] = []
            target_mutations: list[str] = []
            target_store_escapes: list[str] = []
            self._binding_hazards(
                function["fields"].get("body", []),
                categories,
                binding_categories,
                set(),
                representation_conflicts,
                target_rebinds,
                target_mutations,
                target_store_escapes,
            )
            loop_escape.extend(target_store_escapes)
            results.append(LocalDeclarationFact(
                function_id,
                tuple(dict.fromkeys(use_before)),
                tuple(dict.fromkeys(loop_escape)),
                tuple(dict.fromkeys(control_defs)),
                tuple(dict.fromkeys(representation_conflicts)),
                tuple(dict.fromkeys(target_rebinds)),
                tuple(dict.fromkeys(target_mutations)),
            ))
        return tuple(sorted(results, key=lambda item: item.function_node_id))

    def call_graph(self, calls: tuple[CallTargetFact, ...]) -> CallGraphFact:
        owner_by_node = self.owner_by_node()
        edges: list[tuple[str, str]] = []
        call_for_edge: dict[tuple[str, str], list[str]] = {}
        for call in calls:
            caller = owner_by_node.get(call.call_node_id)
            callee = call.target_function_node_id
            if caller and callee:
                edge = (caller, callee)
                edges.append(edge)
                call_for_edge.setdefault(edge, []).append(call.call_node_id)
        graph = {item: set() for item in self.function_ids}
        for left, right in edges:
            graph.setdefault(left, set()).add(right)
        # Iterative Kosaraju SCC analysis is linear in the call graph and does
        # not consume Python recursion depth on large but bounded modules.
        visited: set[str] = set()
        finish: list[str] = []
        for start in sorted(graph):
            if start in visited:
                continue
            stack: list[tuple[str, bool]] = [(start, False)]
            while stack:
                current, expanded = stack.pop()
                if expanded:
                    finish.append(current)
                    continue
                if current in visited:
                    continue
                visited.add(current)
                stack.append((current, True))
                for child in reversed(sorted(graph.get(current, ()))):
                    if child not in visited:
                        stack.append((child, False))
        reverse = {item: set() for item in graph}
        for left, children in graph.items():
            for right in children:
                reverse.setdefault(right, set()).add(left)
        component_for: dict[str, int] = {}
        recursive: set[str] = set()
        recursive_components: set[int] = set()
        component_number = 0
        for start in reversed(finish):
            if start in component_for:
                continue
            component_number += 1
            component: list[str] = []
            stack = [start]
            component_for[start] = component_number
            while stack:
                current = stack.pop()
                component.append(current)
                for parent in reversed(sorted(reverse.get(current, ()))):
                    if parent not in component_for:
                        component_for[parent] = component_number
                        stack.append(parent)
            if len(component) > 1 or any(item in graph.get(item, ()) for item in component):
                recursive.update(component)
                recursive_components.add(component_number)
        recursive_calls = sorted(
            call_id
            for edge, call_ids in call_for_edge.items()
            if component_for.get(edge[0]) == component_for.get(edge[1])
            and component_for.get(edge[0]) in recursive_components
            for call_id in call_ids
        )
        return CallGraphFact(tuple(sorted(set(edges))), tuple(sorted(recursive)), tuple(recursive_calls))

    def owner_by_node(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for function_id in self.function_ids:
            self._mark_owned(function_id, function_id, result)
        return result

    def module_rejection(
        self,
        *,
        allow_imports: bool = False,
        allow_records: bool = False,
    ) -> tuple[str, str, str] | None:
        for node_id in self.module_body:
            node = self.index.node(node_id)
            if (
                node["kind"] != "FunctionDef"
                and not (allow_imports and node["kind"] == "ImportFrom")
                and not (allow_records and node["kind"] == "ClassDef")
            ):
                return "PYC2902", "Phase 9 accepts only top-level function definitions in the selected module subset", node_id
        for function_id in self.function_ids:
            stack = list(reversed(self.index.node(function_id)["fields"].get("body", [])))
            while stack:
                node = self.index.node(stack.pop())
                if node["kind"] in {"FunctionDef", "AsyncFunctionDef"}:
                    return "PYC2915", "Nested functions and closures are unsupported in Phase 9", node["node_id"]
                for field_name in ("body", "orelse", "finalbody"):
                    children = node["fields"].get(field_name, [])
                    if isinstance(children, list):
                        stack.extend(reversed(children))
        return None

    def _signature(self, node: dict[str, Any], duplicates: set[str]) -> FunctionSignatureFact:
        self._check_cancellation()
        fields = node["fields"]
        name = fields.get("name", "")
        binding = self.binding_by_decl.get(node["node_id"])
        args_node = self.index.node(fields["args"])
        pos_ids = list(args_node["fields"].get("posonlyargs", [])) + list(args_node["fields"].get("args", []))
        kwonly_ids = list(args_node["fields"].get("kwonlyargs", []))
        parameter_ids = pos_ids + (kwonly_ids if self.allow_required_keyword_only else [])
        parameters: list[ParameterFact] = []
        reasons: list[str] = []
        parameter_names: list[str] = []
        for parameter_id in parameter_ids:
            self._check_cancellation()
            parameter_names.append(
                self.index.node(parameter_id)["fields"].get("arg", "")
            )
        if len(parameter_names) != len(set(parameter_names)):
            reasons.append("duplicate positional parameter names are unsupported")
        if name in duplicates:
            reasons.append("top-level function name is rebound")
        if fields.get("decorator_list") or fields.get("type_params"):
            reasons.append("decorated or generic functions are unsupported")
        keyword_defaults = args_node["fields"].get("kw_defaults", [])
        keyword_only_valid = bool(
            self.allow_required_keyword_only
            and kwonly_ids
            and isinstance(keyword_defaults, list)
            and len(keyword_defaults) == len(kwonly_ids)
            and all(item is None for item in keyword_defaults)
        )
        if (
            args_node["fields"].get("vararg")
            or args_node["fields"].get("kwarg")
            or args_node["fields"].get("defaults")
            or (kwonly_ids and not keyword_only_valid)
        ):
            reasons.append("default, keyword-only, or variadic parameters are unsupported")
        for ordinal, parameter_id in enumerate(parameter_ids):
            self._check_cancellation()
            parameter = self.index.node(parameter_id)
            category, annotation_id, spelling = self._annotation(parameter["fields"].get("annotation"))
            parameter_binding = self.binding_by_decl.get(parameter_id)
            passing, ownership, lifetime = _boundary(category)
            parameters.append(ParameterFact(parameter_id, parameter_binding["binding_id"] if parameter_binding else "", parameter["fields"].get("arg", ""), ordinal, category, CATEGORY_C_TYPES.get(category), annotation_id, spelling, passing, ownership, lifetime))
            if category not in CATEGORY_C_TYPES or not parameter_binding:
                reasons.append(f"parameter {parameter['fields'].get('arg', '')} lacks an exact supported annotation")
        return_category, return_annotation_id, return_spelling = self._annotation(fields.get("returns"))
        if return_category not in CATEGORY_C_TYPES:
            reasons.append("function return lacks an exact supported annotation")
        return_passing, return_ownership, return_lifetime = _boundary(return_category)
        return FunctionSignatureFact(node["node_id"], binding["binding_id"] if binding else None, name, tuple(parameters), return_category, CATEGORY_C_TYPES.get(return_category), return_annotation_id, return_spelling, return_passing, return_ownership, return_lifetime, True, not reasons, "; ".join(dict.fromkeys(reasons)) or None)

    def _annotation(self, node_id: str | None) -> tuple[ValueCategory, str | None, str | None]:
        if not node_id or node_id not in self.index.nodes:
            return ValueCategory.UNKNOWN, None, None
        node = self.index.node(node_id)
        if node["kind"] != "Name":
            return ValueCategory.UNKNOWN, node_id, None
        spelling = node["fields"].get("id")
        return ANNOTATION_CATEGORIES.get(spelling, ValueCategory.UNKNOWN), node_id, spelling

    def _is_range_iterator(self, call: dict[str, Any]) -> bool:
        parent_id = self.parent_by_node.get(call["node_id"])
        if not parent_id:
            return False
        parent = self.index.node(parent_id)
        if parent["kind"] != "For" or parent["fields"].get("iter") != call["node_id"]:
            return False
        callee_id = call["fields"].get("func")
        callee = self.index.nodes.get(callee_id)
        binding = self.binding_by_occurrence.get(callee_id)
        return bool(
            callee
            and callee["kind"] == "Name"
            and callee["fields"].get("id") == "range"
            and binding
            and binding["binding_kind"] == "implicit-global"
        )

    def _range_call_fact(self, node: dict[str, Any], categories: dict[str, ValueCategory]) -> CallTargetFact:
        args = tuple(node["fields"].get("args", []))
        actual = tuple(categories.get(item, ValueCategory.UNKNOWN) for item in args)
        supported = not node["fields"].get("keywords") and 1 <= len(args) <= 3 and all(item is ValueCategory.INTEGER for item in actual)
        return CallTargetFact(node["node_id"], node["fields"].get("func"), None, None, "range", "recognized-range" if supported else "invalid-range", args, actual, tuple(ValueCategory.INTEGER for _ in args), ValueCategory.CALLABLE, args, True, tuple("by-value" for _ in args), (), supported, None if supported else "PYC2842", None if supported else "range requires one to three positional integer arguments")

    def _unsupported_call(self, node: dict[str, Any], callee_id: str | None, args: tuple[str, ...], categories: tuple[ValueCategory, ...], resolution: str, code: str, reason: str) -> CallTargetFact:
        return CallTargetFact(node["node_id"], callee_id, None, None, None, resolution, args, categories, (), ValueCategory.UNKNOWN, args, True, (), (), False, code, reason)

    def _call_from_signature(self, node: dict[str, Any], signature: FunctionSignatureFact, args: tuple[str, ...], categories: tuple[ValueCategory, ...], supported: bool, code: str | None, reason: str | None) -> CallTargetFact:
        params = tuple(item.category for item in signature.parameters)
        ownership = tuple(f"{item.passing}:{item.ownership}:{item.lifetime}" for item in signature.parameters)
        annotations = tuple(item.annotation_node_id for item in signature.parameters if item.annotation_node_id) + ((signature.return_annotation_node_id,) if signature.return_annotation_node_id else ())
        return CallTargetFact(node["node_id"], node["fields"].get("func"), signature.function_node_id, signature.binding_id, signature.source_name, "understood-source-function" if supported else "ineligible-source-function", args, categories, params, signature.return_category, args, True, ownership, annotations, supported, code, reason)

    def _collect_returns(self, node_ids: list[str], result: list[str]) -> None:
        for node_id in node_ids:
            node = self.index.node(node_id)
            if node["kind"] in {"FunctionDef", "AsyncFunctionDef"}:
                continue
            if node["kind"] == "Return":
                result.append(node_id)
            for name in ("body", "orelse", "finalbody"):
                children = node["fields"].get(name, [])
                if isinstance(children, list):
                    self._collect_returns(children, result)

    def _block_guarantees_return(self, node_ids: list[str]) -> bool:
        for node_id in node_ids:
            node = self.index.node(node_id)
            if node["kind"] == "Return":
                return True
            if node["kind"] == "If":
                body = node["fields"].get("body", [])
                other = node["fields"].get("orelse", [])
                if other and self._block_guarantees_return(body) and self._block_guarantees_return(other):
                    return True
        return False

    def _expression_loads(self, node_id: str) -> tuple[str, ...]:
        result: list[str] = []
        stack = [node_id]
        while stack:
            current = stack.pop()
            node = self.index.node(current)
            if node["kind"] == "Name" and current in self.binding_by_occurrence:
                result.append(current)
            stack.extend(reversed(self.index.child_ids(node)))
        return tuple(result)

    def _check_expression(self, node_id: str | None, initialized: set[str], loop_only: set[str], use_before: list[str], loop_escape: list[str]) -> None:
        if not node_id:
            return
        for occurrence in self._expression_loads(node_id):
            binding = self.binding_by_occurrence[occurrence]
            binding_id = binding["binding_id"]
            if binding["binding_kind"] in {"local", "loop-target"} and binding_id not in initialized:
                (loop_escape if binding_id in loop_only or binding["binding_kind"] == "loop-target" else use_before).append(occurrence)

    def _analyze_statements(self, node_ids: list[str], initialized: set[str], loop_only: set[str], control_depth: int, use_before: list[str], loop_escape: list[str], control_defs: list[str]) -> set[str]:
        state = set(initialized)
        for node_id in node_ids:
            node = self.index.node(node_id)
            fields = node["fields"]
            kind = node["kind"]
            if kind == "Assign":
                self._check_expression(fields.get("value"), state, loop_only, use_before, loop_escape)
                for target_id in fields.get("targets", []):
                    binding = self.binding_by_occurrence.get(target_id)
                    if binding:
                        if control_depth and binding["binding_id"] not in state:
                            control_defs.append(target_id)
                        state.add(binding["binding_id"])
            elif kind in {"Return", "Expr"}:
                self._check_expression(fields.get("value"), state, loop_only, use_before, loop_escape)
            elif kind == "If":
                self._check_expression(fields.get("test"), state, loop_only, use_before, loop_escape)
                left = self._analyze_statements(fields.get("body", []), set(state), set(loop_only), control_depth + 1, use_before, loop_escape, control_defs)
                right = self._analyze_statements(fields.get("orelse", []), set(state), set(loop_only), control_depth + 1, use_before, loop_escape, control_defs) if fields.get("orelse") else set(state)
                state |= left & right
            elif kind == "While":
                self._check_expression(fields.get("test"), state, loop_only, use_before, loop_escape)
                self._analyze_statements(fields.get("body", []), set(state), set(loop_only), control_depth + 1, use_before, loop_escape, control_defs)
            elif kind == "For":
                self._check_expression(fields.get("iter"), state, loop_only, use_before, loop_escape)
                target = self.binding_by_occurrence.get(fields.get("target"))
                body_state = set(state)
                body_loop_only = set(loop_only)
                if target:
                    body_state.add(target["binding_id"])
                    body_loop_only.add(target["binding_id"])
                self._analyze_statements(fields.get("body", []), body_state, body_loop_only, control_depth + 1, use_before, loop_escape, control_defs)
                if target:
                    loop_only.add(target["binding_id"])
            elif kind in {"FunctionDef", "AsyncFunctionDef"}:
                continue
        initialized.clear()
        initialized.update(state)
        return state

    def _binding_hazards(
        self,
        node_ids: list[str],
        categories: dict[str, ValueCategory],
        binding_categories: dict[str, ValueCategory],
        active_loop_targets: set[str],
        representation_conflicts: list[str],
        target_rebinds: list[str],
        target_mutations: list[str],
        target_store_escapes: list[str],
    ) -> None:
        for node_id in node_ids:
            node = self.index.node(node_id)
            fields = node["fields"]
            kind = node["kind"]
            if kind == "Assign":
                value_category = categories.get(fields.get("value"), ValueCategory.UNKNOWN)
                for target_id in fields.get("targets", []):
                    binding = self.binding_by_occurrence.get(target_id)
                    if not binding:
                        continue
                    binding_id = binding["binding_id"]
                    prior = binding_categories.get(binding_id, ValueCategory.UNKNOWN)
                    if value_category is ValueCategory.CONTRADICTORY or (
                        prior not in {ValueCategory.UNKNOWN, value_category}
                        and value_category is not ValueCategory.UNKNOWN
                    ):
                        representation_conflicts.append(target_id)
                    elif prior is ValueCategory.UNKNOWN and value_category is not ValueCategory.UNKNOWN:
                        binding_categories[binding_id] = value_category
                    if binding["binding_kind"] == "loop-target":
                        if binding_id in active_loop_targets:
                            target_mutations.append(target_id)
                        else:
                            target_store_escapes.append(target_id)
            elif kind == "For":
                target_id = fields.get("target")
                binding = self.binding_by_occurrence.get(target_id)
                nested_targets = set(active_loop_targets)
                if binding:
                    binding_id = binding["binding_id"]
                    if binding["declaration_node_id"] != target_id:
                        target_rebinds.append(target_id)
                    prior = binding_categories.get(binding_id, ValueCategory.UNKNOWN)
                    target_category = categories.get(target_id, ValueCategory.INTEGER)
                    if target_category is ValueCategory.UNKNOWN:
                        target_category = ValueCategory.INTEGER
                    if prior not in {ValueCategory.UNKNOWN, target_category}:
                        representation_conflicts.append(target_id)
                    binding_categories[binding_id] = target_category
                    nested_targets.add(binding_id)
                self._binding_hazards(fields.get("body", []), categories, binding_categories, nested_targets, representation_conflicts, target_rebinds, target_mutations, target_store_escapes)
            elif kind in {"If", "While"}:
                self._binding_hazards(fields.get("body", []), categories, binding_categories, set(active_loop_targets), representation_conflicts, target_rebinds, target_mutations, target_store_escapes)
                self._binding_hazards(fields.get("orelse", []), categories, binding_categories, set(active_loop_targets), representation_conflicts, target_rebinds, target_mutations, target_store_escapes)
            elif kind in {"FunctionDef", "AsyncFunctionDef"}:
                continue

    def _mark_owned(self, node_id: str, owner: str, result: dict[str, str]) -> None:
        if node_id in result:
            return
        result[node_id] = owner
        node = self.index.node(node_id)
        for child in self.index.child_ids(node):
            if child != node_id and self.index.node(child)["kind"] not in {"FunctionDef", "AsyncFunctionDef"}:
                self._mark_owned(child, owner, result)
