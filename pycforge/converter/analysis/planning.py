from __future__ import annotations

import hashlib
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Callable

from pycforge.converter.contracts.identifiers import (
    C11_EXTERNAL_IDENTIFIERS as _C11_EXTERNAL_IDENTIFIERS,
    C_KEYWORDS as _C_KEYWORDS,
    TARGET_RESERVED_NAMES as _TARGET_RESERVED_NAMES,
)
from pycforge.converter.keyword_calls.model import KEYWORD_CALL_OBLIGATIONS
from pycforge.converter.keyword_only_calls.model import (
    KEYWORD_ONLY_CALL_OBLIGATIONS,
)

from .model import (EffectKind, NamePlan, RepresentationPlan, SupportState,
                    ValueCategory)
from .symbols import PythonIRIndex

class AnalysisCanceled(Exception):
    pass


def stable_id(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:20]


@dataclass(frozen=True, slots=True)
class RulePlan:
    plan_id: str
    decision_key: str
    rule_id: str
    rule_version: str
    source_node_id: str
    support_state: SupportState
    facts_used: tuple[str, ...]
    semantic_obligations: tuple[str, ...]
    resolved_obligations: tuple[str, ...]
    unresolved_obligations: tuple[str, ...]
    helper_requirements: tuple[str, ...]
    explanation_tokens: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "decision_key": self.decision_key,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "source_node_id": self.source_node_id,
            "support_state": self.support_state.value,
            "facts_used": list(self.facts_used),
            "semantic_obligations": list(self.semantic_obligations),
            "resolved_obligations": list(self.resolved_obligations),
            "unresolved_obligations": list(self.unresolved_obligations),
            "helper_requirements": list(self.helper_requirements),
            "explanation_tokens": list(self.explanation_tokens),
        }


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    rule_id: str
    rule_version: str
    node_kind: str
    specificity: tuple[int, ...]
    predicate: Callable[[dict[str, Any], dict[str, ValueCategory]], bool]
    obligations: tuple[str, ...]


class FrozenRuleRegistry:
    def __init__(self, rules: tuple[RuleDefinition, ...]) -> None:
        ordered = tuple(sorted(rules, key=lambda r: (r.node_kind, tuple(-x for x in r.specificity), r.rule_id, r.rule_version)))
        ids = [(r.rule_id, r.rule_version) for r in ordered]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate rule identity")
        self._rules = ordered
        self._audit_overlaps()

    @property
    def manifest(self) -> tuple[dict[str, Any], ...]:
        return tuple({"rule_id": r.rule_id, "rule_version": r.rule_version, "node_kind": r.node_kind, "specificity": list(r.specificity)} for r in self._rules)

    def select(self, node: dict[str, Any], categories: dict[str, ValueCategory], decision_key: str) -> RulePlan | None:
        matches = [r for r in self._rules if r.node_kind == node["kind"] and r.predicate(node, categories)]
        if not matches:
            return None
        matches.sort(key=lambda r: (tuple(-x for x in r.specificity), r.rule_id, r.rule_version))
        best = matches[0]
        if len(matches) > 1 and matches[1].specificity == best.specificity:
            raise ValueError(f"ambiguous best rule for {node['node_id']}")
        obligations = best.obligations
        return RulePlan(
            stable_id("plan-", decision_key, best.rule_id, best.rule_version), decision_key,
            best.rule_id, best.rule_version, node["node_id"], SupportState.SUPPORTED_DIRECT,
            tuple(sorted({f"value-category:{categories.get(node['node_id'], ValueCategory.UNKNOWN).value}"})),
            obligations, obligations, (), (),
            ("selected", best.rule_id, "for", node["kind"]),
        )

    def _audit_overlaps(self) -> None:
        for i, left in enumerate(self._rules):
            for right in self._rules[i + 1:]:
                if left.node_kind == right.node_kind and left.specificity == right.specificity:
                    raise ValueError(f"unapproved equal-specificity overlap: {left.rule_id}/{right.rule_id}")


def default_registry(
    *,
    include_records: bool = False,
    include_numeric: bool = False,
    include_conditional_regions: bool = False,
    include_keyword_calls: bool = False,
    include_keyword_only_calls: bool = False,
) -> FrozenRuleRegistry:
    known = lambda node, cats: cats.get(node["node_id"]) not in {None, ValueCategory.UNKNOWN, ValueCategory.CONTRADICTORY}
    supported_value = lambda node, cats: cats.get(node["node_id"]) in {ValueCategory.INTEGER, ValueCategory.FLOAT, ValueCategory.BOOLEAN, ValueCategory.STRING}
    representable_name = lambda node, cats: cats.get(node["node_id"]) in {ValueCategory.INTEGER, ValueCategory.FLOAT, ValueCategory.BOOLEAN, ValueCategory.STRING, ValueCategory.CALLABLE}
    numeric_arithmetic = lambda node, cats: node["kind"] == "BinOp" and _operator_kind(node) in {"Add", "Sub", "Mult", "Div"} and cats.get(node["node_id"]) in {ValueCategory.INTEGER, ValueCategory.FLOAT}
    rules = (
        RuleDefinition("phase6.literal.known", "0.6", "Constant", (10,), supported_value, ("literal-representation-known",)),
        RuleDefinition("phase6.name.bound", "0.6", "Name", (10,), representable_name, ("binding-resolved", "representation-known")),
        RuleDefinition("phase6.assignment.simple", "0.6", "Assign", (10,), supported_value, ("target-binding-resolved", "rhs-representation-known", "evaluation-order-preserved")),
        RuleDefinition("phase6.numeric.arithmetic", "0.6", "BinOp", (20,), numeric_arithmetic, ("numeric-representation-selected", "overflow-and-division-policy-declared", "left-before-right-evaluation")),
        RuleDefinition("phase6.return.simple", "0.6", "Return", (10,), lambda n,c: known(n,c) and n.get("return_eligible", True), ("return-representation-compatible",)),
        RuleDefinition("phase6.function.annotated", "0.6", "FunctionDef", (10,), lambda n,c: known(n,c) and n.get("function_eligible", True), ("annotation-trust-policy-applied", "parameter-representations-known", "return-representation-known")),
        RuleDefinition("phase8.if.control", "0.8", "If", (20,), lambda n,c: True, ("truthiness-representation-known", "branch-order-preserved", "branch-binding-policy-declared")),
        RuleDefinition("phase8.boolean.short_circuit", "0.8", "BoolOp", (20,), lambda n,c: c.get(n["node_id"]) is ValueCategory.BOOLEAN, ("truthiness-representation-known", "short-circuit-order-preserved")),
        RuleDefinition("phase8.comparison.chain", "0.8", "Compare", (20,), lambda n,c: c.get(n["node_id"]) is ValueCategory.BOOLEAN, ("comparison-representations-compatible", "operands-evaluated-once-in-source-order")),
        RuleDefinition("phase8.while.control", "0.8", "While", (20,), lambda n,c: True, ("truthiness-representation-known", "zero-iteration-policy-declared", "break-continue-scope-valid")),
        RuleDefinition("phase8.for.range", "0.8", "For", (20,), lambda n,c: True, ("bounded-range-form-proved", "loop-bound-evaluated-once", "loop-target-lifetime-declared")),
        RuleDefinition("phase8.break.control", "0.8", "Break", (20,), lambda n,c: True, ("enclosing-loop-proved",)),
        RuleDefinition("phase8.continue.control", "0.8", "Continue", (20,), lambda n,c: True, ("enclosing-loop-proved",)),
        RuleDefinition("phase8.range.bound", "0.8", "Call", (20,), lambda n,c: n.get("call_target_kind") == "recognized-range", ("range-call-shape-validated", "loop-bound-evaluated-once")),
        RuleDefinition("phase9.call.understood_target", "0.9", "Call", (30,), lambda n,c: n.get("call_target_kind") == "understood-source-function", ("target-resolved-once", "positional-arity-exact", "argument-representations-compatible", "arguments-evaluated-left-to-right-once", "parameter-ownership-boundary-explicit", "recursion-policy-satisfied")),
        RuleDefinition("phase11.container.list_literal", "0.11", "List", (30,), lambda n,c: bool(n.get("container_shape_supported")), ("fixed-capacity-proved", "homogeneous-element-representation-proved", "local-storage-lifetime-proved", "no-alias-or-cleanup-required", "elements-evaluated-left-to-right-once")),
        RuleDefinition("phase11.container.tuple_literal", "0.11", "Tuple", (30,), lambda n,c: bool(n.get("container_shape_supported")), ("fixed-capacity-proved", "homogeneous-element-representation-proved", "tuple-immutability-boundary-proved", "local-storage-lifetime-proved", "elements-evaluated-left-to-right-once")),
        RuleDefinition("phase11.container.dict_literal", "0.11", "Dict", (30,), lambda n,c: bool(n.get("container_shape_supported")), ("fixed-capacity-proved", "homogeneous-key-value-representations-proved", "distinct-literal-keys-proved", "insertion-order-preserved", "no-runtime-lookup-or-cleanup-required")),
        RuleDefinition("phase11.container.index.proved", "0.11", "Subscript", (30,), lambda n,c: bool(n.get("container_access_supported")), ("container-binding-resolved", "index-or-key-statically-proved", "bounds-or-presence-proved", "result-representation-known")),
        RuleDefinition("phase11.container.for.bounded", "0.11", "For", (30,), lambda n,c: bool(n.get("container_iteration_supported")), ("container-binding-resolved", "fixed-iteration-bound-proved", "iteration-order-preserved", "loop-target-lifetime-declared", "break-continue-scope-valid")),
        RuleDefinition("phase11.container.assignment", "0.11", "Assign", (30,), lambda n,c: bool(n.get("container_binding_supported")), ("target-binding-resolved", "fixed-container-shape-resolved", "single-assignment-proved", "evaluation-order-preserved")),
        RuleDefinition("phase11.container.name", "0.11", "Name", (30,), lambda n,c: bool(n.get("container_name_supported")), ("container-binding-resolved", "container-use-context-approved")),
        RuleDefinition("phase12.module.document", "0.12", "ModuleDocument", (40,), lambda n,c: bool(n.get("module_document_supported")), ("module-identity-canonical", "logical-source-identity-unique", "explicit-sourcebundle-membership-proved", "module-top-level-profile-closed")),
        RuleDefinition("phase12.module.import_from", "0.12", "ImportFrom", (40,), lambda n,c: bool(n.get("module_import_supported")), ("explicit-sourcebundle-membership-proved", "import-target-function-proved", "module-namespace-binding-unique", "dependency-order-proved", "no-runtime-module-initialization", "no-source-driven-discovery")),
        RuleDefinition("phase12.module.imported_binding", "0.12", "alias", (40,), lambda n,c: bool(n.get("module_alias_supported")), ("imported-function-binding-exact", "alias-not-rebound-or-reexported", "target-signature-reused", "no-module-object-materialized")),
        RuleDefinition("phase12.module.function_namespace", "0.12", "FunctionDef", (40,), lambda n,c: bool(n.get("module_function_supported")) and n.get("function_eligible", True), ("module-function-membership-proved", "bundle-global-name-collision-absent", "source-function-external-linkage", "prototype-definition-module-order-consistent")),
        RuleDefinition("phase12.module.cross_call", "0.12", "Call", (40,), lambda n,c: bool(n.get("cross_module_call_supported")), ("foreign-target-binding-resolved-once", "target-signature-reused", "arguments-evaluated-left-to-right-once", "bundle-call-graph-acyclic", "source-output-call-mapping-required")),
        RuleDefinition("phase12.module.initialization", "0.12", "ModuleInitialization", (40,), lambda n,c: bool(n.get("module_initialization_supported")), ("dependency-graph-acyclic", "dependency-first-order-deterministic", "runtime-module-initialization-absent")),
        RuleDefinition("phase12.module.bundle_assembly", "0.12", "ModuleBundleAssembly", (40,), lambda n,c: bool(n.get("module_bundle_assembly_supported")), ("single-translation-unit", "all-source-prototypes-before-definitions", "registered-includes-only", "no-compile-link-or-execution", "all-source-mappings-document-qualified")),
    )
    if include_records:
        rules += (
            RuleDefinition("phase13.record.class", "0.13", "ClassDef", (50,), lambda n,c: bool(n.get("record_class_supported")), ("record-layout-closed", "object-model-surface-closed", "automatic-storage-policy-selected")),
            RuleDefinition("phase13.record.field", "0.13", "AnnAssign", (50,), lambda n,c: bool(n.get("record_field_supported")), ("field-ordinal-and-type-proved", "field-default-absent", "field-name-unique")),
            RuleDefinition("phase13.record.initializer", "0.13", "FunctionDef", (50,), lambda n,c: bool(n.get("record_initializer_supported")), ("initializer-signature-exact", "field-coverage-complete", "initializer-effects-bounded")),
            RuleDefinition("phase13.record.construction", "0.13", "Call", (50,), lambda n,c: bool(n.get("record_construction_supported")), ("constructor-target-static", "arguments-evaluated-left-to-right-once", "aggregate-fully-initialized")),
            RuleDefinition("phase13.record.binding", "0.13", "Assign", (50,), lambda n,c: bool(n.get("record_binding_supported")), ("fresh-function-local-owner", "single-construction-proved", "alias-rebind-escape-absent")),
            RuleDefinition("phase13.record.name", "0.13", "Name", (50,), lambda n,c: bool(n.get("record_name_supported")), ("record-binding-resolved", "record-use-context-approved")),
            RuleDefinition("phase13.record.attribute_read", "0.13", "Attribute", (50,), lambda n,c: bool(n.get("record_access_supported")), ("record-binding-resolved", "field-binding-exact", "post-initialization-read-proved")),
        )
    if include_numeric:
        rules += (
            RuleDefinition(
                "phase14.numeric.floor_arithmetic",
                "0.14",
                "BinOp",
                (60,),
                lambda n, c: bool(n.get("numeric_operation_supported")),
                (
                    "exact-int64-operands-proved",
                    "direct-safe-divisor-literal-proved",
                    "left-before-right-evaluation-once",
                    "helper-preconditions-proved",
                    "python-floor-semantics-preserved",
                    "no-runtime-failure-channel",
                    "scalar-value-ownership-by-value",
                    "allocation-and-cleanup-absent",
                    "source-provenance-anchored",
                    "cancellation-safe-points-honored",
                    "target-contract-exact",
                ),
            ),
        )
    if include_conditional_regions:
        conditional_obligations = (
            "scalar-operand-representations-proved",
            "unconditional-prefix-proved",
            "guard-polarity-proved",
            "short-circuit-order-preserved",
            "operands-evaluated-left-to-right-once",
            "prerequisite-statements-branch-contained",
            "intermediate-values-reused-without-reevaluation",
            "structured-c-ir-only",
            "result-materialized-once",
            "allocation-and-cleanup-absent",
            "runtime-failure-channel-unchanged",
            "source-provenance-anchored",
            "cancellation-safe-points-honored",
            "target-contract-exact",
        )
        rules += (
            RuleDefinition(
                "phase14.conditional.boolean_region",
                "0.14.1",
                "BoolOp",
                (70,),
                lambda n, c: bool(n.get("conditional_boolean_region_supported")),
                conditional_obligations,
            ),
            RuleDefinition(
                "phase14.conditional.comparison_region",
                "0.14.1",
                "Compare",
                (70,),
                lambda n, c: bool(n.get("conditional_comparison_region_supported")),
                conditional_obligations,
            ),
        )
    if include_keyword_calls:
        rules += (
            RuleDefinition(
                "phase14.keyword_call.exact_binding",
                "0.14.2",
                "Call",
                (80,),
                lambda n, c: bool(n.get("keyword_call_binding_supported")),
                KEYWORD_CALL_OBLIGATIONS,
            ),
        )
    if include_keyword_only_calls:
        rules += (
            RuleDefinition(
                "phase14.keyword_only_call.exact_binding",
                "0.14.3",
                "Call",
                (90,),
                lambda n, c: bool(n.get("keyword_only_call_binding_supported")),
                KEYWORD_ONLY_CALL_OBLIGATIONS,
            ),
        )
    return FrozenRuleRegistry(rules)


def _operator_kind(node: dict[str, Any]) -> str | None:
    return node.get("op_kind")


class AnalysisPlanner:
    def analyze_categories(self, module: dict[str, Any], binding_by_occurrence: dict[str, str], binding_categories: dict[str, ValueCategory], call_return_categories: dict[str, ValueCategory] | None = None, cancellation: Any | None = None, container_access_categories: dict[str, ValueCategory] | None = None, container_iteration_categories: dict[str, ValueCategory] | None = None, record_access_categories: dict[str, ValueCategory] | None = None) -> dict[str, ValueCategory]:
        index = PythonIRIndex(module)
        categories: dict[str, ValueCategory] = {}
        call_return_categories = call_return_categories or {}
        container_access_categories = container_access_categories or {}
        container_iteration_categories = container_iteration_categories or {}
        record_access_categories = record_access_categories or {}
        bindings = dict(binding_categories)
        parents: dict[str, list[str]] = defaultdict(list)
        edge_count = 0
        for parent_id, parent in index.nodes.items():
            for child_id in index.child_ids(parent):
                parents[child_id].append(parent_id)
                edge_count += 1
        occurrences_by_binding: dict[str, list[str]] = defaultdict(list)
        for occurrence_id, binding_id in binding_by_occurrence.items():
            if occurrence_id in index.nodes:
                occurrences_by_binding[binding_id].append(occurrence_id)
        for node_id, node in index.nodes.items():
            if node["kind"] == "Constant":
                value = node["fields"].get("value")
                categories[node_id] = self._literal_category(value)
            elif node["kind"] == "Name" and node["fields"].get("id") in {"int", "float", "bool", "str"}:
                categories[node_id] = ValueCategory.CALLABLE

        queue = deque(index.nodes)
        queued = set(index.nodes)

        def schedule(node_ids: list[str]) -> None:
            for scheduled_id in sorted(set(node_ids), key=index.ordinals.__getitem__):
                if scheduled_id not in queued:
                    queue.append(scheduled_id)
                    queued.add(scheduled_id)

        steps = 0
        maximum_steps = max(64, (len(index.nodes) + edge_count + len(binding_by_occurrence)) * 16)
        while queue:
            if cancellation is not None and cancellation.is_canceled:
                raise AnalysisCanceled
            steps += 1
            if steps > maximum_steps:
                raise RuntimeError("value-category analysis did not converge")
            node_id = queue.popleft()
            queued.remove(node_id)
            node = index.nodes[node_id]
            prior = categories.get(node_id, ValueCategory.UNKNOWN)
            category = self._infer_node(node, index, categories, binding_by_occurrence, bindings, call_return_categories, container_access_categories, record_access_categories)
            if category != prior:
                categories[node_id] = category
                schedule(parents.get(node_id, []))
            if node["kind"] == "Assign":
                value_category = categories.get(node["fields"].get("value"), ValueCategory.UNKNOWN)
                for target_id in node["fields"].get("targets", []):
                    binding_id = binding_by_occurrence.get(target_id)
                    joined = self._join_categories(bindings.get(binding_id, ValueCategory.UNKNOWN), value_category)
                    if binding_id and bindings.get(binding_id, ValueCategory.UNKNOWN) != joined:
                        bindings[binding_id] = joined
                        schedule(occurrences_by_binding.get(binding_id, []))
            elif node["kind"] == "For":
                target_id = node["fields"].get("target")
                binding_id = binding_by_occurrence.get(target_id)
                iterator_id = node["fields"].get("iter")
                iterator = index.nodes.get(iterator_id, {})
                target_category = container_iteration_categories.get(node_id)
                if target_category is None and iterator.get("kind") == "Call":
                    target_category = ValueCategory.INTEGER
                if target_category is None:
                    continue
                joined = self._join_categories(bindings.get(binding_id, ValueCategory.UNKNOWN), target_category)
                if binding_id and bindings.get(binding_id, ValueCategory.UNKNOWN) != joined:
                    bindings[binding_id] = joined
                    schedule(occurrences_by_binding.get(binding_id, []))
        for node_id in index.nodes:
            categories.setdefault(node_id, ValueCategory.UNKNOWN)
        binding_categories.clear()
        binding_categories.update(bindings)
        return categories

    def _infer_node(self, node: dict[str, Any], index: PythonIRIndex, categories: dict[str, ValueCategory], occurrence_bindings: dict[str, str], binding_categories: dict[str, ValueCategory], call_return_categories: dict[str, ValueCategory], container_access_categories: dict[str, ValueCategory], record_access_categories: dict[str, ValueCategory]) -> ValueCategory:
        kind, fields = node["kind"], node["fields"]
        if kind == "Name":
            return binding_categories.get(occurrence_bindings.get(node["node_id"], ""), categories.get(node["node_id"], ValueCategory.UNKNOWN))
        if kind == "BoolOp":
            values = [categories.get(item, ValueCategory.UNKNOWN) for item in fields.get("values", [])]
            if values and all(item is ValueCategory.BOOLEAN for item in values):
                return ValueCategory.BOOLEAN
            if any(item is ValueCategory.CONTRADICTORY for item in values) or any(item not in {ValueCategory.UNKNOWN, ValueCategory.BOOLEAN} for item in values):
                return ValueCategory.CONTRADICTORY
            return ValueCategory.UNKNOWN
        if kind == "Compare":
            operands = [fields.get("left")] + list(fields.get("comparators", []))
            values = [categories.get(item, ValueCategory.UNKNOWN) for item in operands]
            supported = {ValueCategory.INTEGER, ValueCategory.FLOAT, ValueCategory.BOOLEAN}
            if values and all(item == values[0] and item in supported for item in values):
                return ValueCategory.BOOLEAN
            if any(item is ValueCategory.CONTRADICTORY for item in values) or (all(item is not ValueCategory.UNKNOWN for item in values) and len(set(values)) > 1):
                return ValueCategory.CONTRADICTORY
            return ValueCategory.UNKNOWN
        if kind == "BinOp":
            left, right = categories.get(fields.get("left"), ValueCategory.UNKNOWN), categories.get(fields.get("right"), ValueCategory.UNKNOWN)
            op_id = fields.get("op")
            op_kind = index.nodes.get(op_id, {}).get("kind")
            if op_kind == "Div":
                if left is ValueCategory.FLOAT and right is ValueCategory.FLOAT:
                    return ValueCategory.FLOAT
                if ValueCategory.UNKNOWN in {left, right}:
                    return ValueCategory.UNKNOWN
                return ValueCategory.CONTRADICTORY
            if left == right and left in {ValueCategory.INTEGER, ValueCategory.FLOAT, ValueCategory.STRING}:
                return left
            if ValueCategory.CONTRADICTORY in {left, right} or (left != right and ValueCategory.UNKNOWN not in {left, right}):
                return ValueCategory.CONTRADICTORY
        if kind == "UnaryOp":
            operand = categories.get(fields.get("operand"), ValueCategory.UNKNOWN)
            op_kind = index.nodes.get(fields.get("op"), {}).get("kind")
            if op_kind == "Not" and operand in {ValueCategory.BOOLEAN, ValueCategory.INTEGER, ValueCategory.FLOAT}:
                return ValueCategory.BOOLEAN
            if op_kind in {"UAdd", "USub"} and operand in {ValueCategory.INTEGER, ValueCategory.FLOAT}:
                return operand
            return ValueCategory.CONTRADICTORY if operand is ValueCategory.CONTRADICTORY else ValueCategory.UNKNOWN
        if kind == "Call":
            return call_return_categories.get(node["node_id"], ValueCategory.UNKNOWN)
        if kind == "List":
            return ValueCategory.LIST
        if kind == "Tuple":
            return ValueCategory.TUPLE
        if kind == "Dict":
            return ValueCategory.DICTIONARY
        if kind == "Subscript":
            return container_access_categories.get(node["node_id"], ValueCategory.UNKNOWN)
        if kind == "Attribute":
            return record_access_categories.get(node["node_id"], ValueCategory.UNKNOWN)
        if kind in {"Assign", "Return", "Expr"}:
            return categories.get(fields.get("value"), ValueCategory.UNKNOWN)
        if kind == "FunctionDef":
            return ValueCategory.CALLABLE
        if kind == "ClassDef":
            return ValueCategory.CALLABLE
        return categories.get(node["node_id"], ValueCategory.UNKNOWN)

    @staticmethod
    def _join_categories(left: ValueCategory, right: ValueCategory) -> ValueCategory:
        if left is ValueCategory.UNKNOWN:
            return right
        if right is ValueCategory.UNKNOWN:
            return left
        if left is right:
            return left
        return ValueCategory.CONTRADICTORY

    @staticmethod
    def _literal_category(value: Any) -> ValueCategory:
        if isinstance(value,(list,tuple)) and len(value)>=2 and tuple(value[:2]) == ("unsupported-python-value","float-nonfinite"):
            return ValueCategory.FLOAT
        if value is None: return ValueCategory.NONE
        if isinstance(value, bool): return ValueCategory.BOOLEAN
        if isinstance(value, int): return ValueCategory.INTEGER
        if isinstance(value, float): return ValueCategory.FLOAT
        if isinstance(value, str): return ValueCategory.STRING
        return ValueCategory.UNKNOWN

    def representation(self, decision_key: str, category: ValueCategory) -> RepresentationPlan:
        mapping = {
            ValueCategory.INTEGER: ("int64_t", "value", "not-applicable", ("fixed-width-overflow-policy",)),
            ValueCategory.FLOAT: ("double", "value", "not-applicable", ("floating-policy",)),
            ValueCategory.BOOLEAN: ("bool", "value", "not-applicable", ("boolean-representation",)),
            ValueCategory.STRING: ("const char *", "pointer", "borrowed", ("utf8-literal-lifetime",)),
            ValueCategory.LIST: ("bounded-local-array", "local-only", "automatic-owner", ("fixed-capacity", "no-alias", "no-cleanup")),
            ValueCategory.TUPLE: ("bounded-local-const-array", "local-only", "automatic-owner", ("fixed-capacity", "immutable-observation", "no-cleanup")),
            ValueCategory.DICTIONARY: ("parallel-bounded-local-arrays", "local-only", "automatic-owner", ("fixed-capacity", "insertion-order", "no-runtime-lookup", "no-cleanup")),
            ValueCategory.RECORD: ("static-record", "local-only", "automatic-owner", ("fully-initialized", "no-alias", "no-escape", "no-cleanup")),
            ValueCategory.NONE: (None, "not-applicable", "not-applicable", ("none-use-policy",)),
            ValueCategory.CALLABLE: ("function-signature", "direct-call-only", "not-applicable", ("understood-target-only",)),
        }
        if category not in mapping:
            return RepresentationPlan(stable_id("repr-", decision_key), decision_key, None, "unresolved", "unresolved", "unresolved", (), ("value-category-known",))
        c_type, passing, ownership, obligations = mapping[category]
        return RepresentationPlan(stable_id("repr-", decision_key), decision_key, c_type, passing, ownership, "lexical-scope", obligations, ())

    def effects(self, node: dict[str, Any]) -> tuple[EffectKind, ...]:
        kind = node["kind"]
        effects = {EffectKind.PURE}
        if kind == "Name": effects.add(EffectKind.READS_STATE)
        if kind in {"Assign", "AnnAssign", "AugAssign"}: effects.add(EffectKind.WRITES_STATE)
        if kind in {"Return", "FunctionDef", "If", "While", "For"}: effects.add(EffectKind.CONTROL_FLOW)
        if kind in {"BinOp", "Call", "Subscript"}: effects.add(EffectKind.MAY_FAIL)
        return tuple(sorted(effects, key=lambda e: e.value))

    def generated_names(self, bindings: tuple[dict[str, Any], ...]) -> tuple[NamePlan, ...]:
        used: set[str] = set()
        plans: list[NamePlan] = []
        for binding in sorted(bindings, key=lambda b: b["binding_id"]):
            base = re.sub(r"[^A-Za-z0-9_]", "_", binding["source_name"])
            if not base or not (base[0].isalpha() or base[0] == "_"):
                base = "py_" + base
            # Avoid every leading underscore.  C reserves all such names at
            # file scope, and a single allocator policy is safer than relying
            # on the eventual declaration scope.
            if base.startswith("_"):
                base = "py" + base
            external_collision = binding.get("binding_kind") in {"function", "record-class"} and base in _C11_EXTERNAL_IDENTIFIERS
            reserved_project_prefix = base.startswith("pycf_") or (
                base.startswith("pycm_") and not binding.get("module_generated_name", False)
            )
            if base in _C_KEYWORDS or base in _TARGET_RESERVED_NAMES or reserved_project_prefix or external_collision:
                base = "py_" + base
            candidate = base
            suffix = 1
            while candidate in used:
                suffix += 1
                candidate = f"{base}_{suffix}"
            used.add(candidate)
            plans.append(NamePlan(binding["binding_id"], candidate))
        return tuple(plans)
