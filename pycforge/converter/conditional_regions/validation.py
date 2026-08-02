"""Independent validation for published conditional-region facts.

This module intentionally does not import the producer or lowerer.  It rebuilds
the exact eligible-region set from Python IR and cumulative fact tables, then
checks the serialized facts and RulePlans for exact equality.
"""

from __future__ import annotations

from typing import Any, Mapping

from pycforge.converter.ir.python_ir import python_ir_reference_ids

from .model import (
    CONDITIONAL_REGION_KEY_DOMAIN,
    CONDITIONAL_REGION_LOWERING_SHAPE,
    CONDITIONAL_REGION_OBLIGATIONS,
    CONDITIONAL_REGION_PROVENANCE_EVIDENCE,
    CONDITIONAL_REGION_TABLE_DEPENDENCIES,
    CONDITIONAL_REGION_TABLE_ID,
    ConditionalRegionKind,
    ConditionalRegionValidationCanceled,
    conditional_region_id,
)


_SCALARS = {"integer-like", "floating-like", "boolean-like", "string-like"}
_COMPARABLE = {"integer-like", "floating-like", "boolean-like"}
_COMPARE_OPS = {"Eq", "NotEq", "Lt", "LtE", "Gt", "GtE"}


def _check_cancellation(cancellation: Any) -> None:
    if cancellation is not None and bool(
        getattr(cancellation, "is_canceled", False)
    ):
        raise ConditionalRegionValidationCanceled


class _ValidationPrerequisiteClosure:
    """Independent persistent prerequisite rope for linear reconstruction."""

    __slots__ = ("parts", "node_id", "nonempty")

    def __init__(
        self,
        parts: tuple["_ValidationPrerequisiteClosure", ...] = (),
        node_id: str | None = None,
    ) -> None:
        self.parts = tuple(part for part in parts if part.nonempty)
        self.node_id = node_id
        self.nonempty = bool(self.parts) or node_id is not None

    def materialize(self, cancellation: Any) -> tuple[str, ...]:
        if not self.nonempty:
            return ()
        result: list[str] = []
        seen_node_ids: set[str] = set()
        seen_closures: set[int] = set()
        stack: list[_ValidationPrerequisiteClosure | str] = [self]
        while stack:
            _check_cancellation(cancellation)
            item = stack.pop()
            if isinstance(item, str):
                if item not in seen_node_ids:
                    seen_node_ids.add(item)
                    result.append(item)
                continue
            identity = id(item)
            if identity in seen_closures:
                continue
            seen_closures.add(identity)
            if item.node_id is not None:
                stack.append(item.node_id)
            stack.extend(reversed(item.parts))
        return tuple(result)


_EMPTY_VALIDATION_PREREQUISITES = _ValidationPrerequisiteClosure()


def _validation_closure(
    parts: tuple[_ValidationPrerequisiteClosure, ...] = (),
    node_id: str | None = None,
) -> _ValidationPrerequisiteClosure:
    if node_id is None and not any(part.nonempty for part in parts):
        return _EMPTY_VALIDATION_PREREQUISITES
    return _ValidationPrerequisiteClosure(parts, node_id)


def validate_conditional_region_facts(
    payload: dict[str, Any],
    tables: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    *,
    expected_fact_schema: str | None = None,
    require_table: bool = True,
    cancellation: Any = None,
) -> tuple[bool, str]:
    """Validate the exact conditional-region table and its RulePlans.

    The complete independent reconstruction is implemented below this public
    boundary; the signature intentionally accepts a caller-supplied table list
    so the cumulative validator need not reshape its payload.
    """

    return _validate(
        payload,
        tuple(tables if tables is not None else payload.get("fact_tables", ())),
        expected_fact_schema=expected_fact_schema,
        require_table=require_table,
        cancellation=cancellation,
    )


def _validate(
    payload: dict[str, Any],
    tables: tuple[dict[str, Any], ...],
    *,
    expected_fact_schema: str | None,
    require_table: bool,
    cancellation: Any,
) -> tuple[bool, str]:
    _check_cancellation(cancellation)
    table = next(
        (item for item in tables if item.get("table_id") == CONDITIONAL_REGION_TABLE_ID),
        None,
    )
    if table is None:
        return (False, "conditional-region fact table is absent") if require_table else (True, "")
    if (
        (expected_fact_schema is not None and table.get("schema_version") != expected_fact_schema)
        or not isinstance(table.get("schema_version"), str)
        or not table.get("schema_version")
        or table.get("producer_stage") != "analysis.plan"
        or table.get("key_domain") != CONDITIONAL_REGION_KEY_DOMAIN
        or table.get("completeness") != "complete"
        or tuple(table.get("invalidation_dependencies", ()))
        != CONDITIONAL_REGION_TABLE_DEPENDENCIES
    ):
        return False, "conditional-region fact schema is invalid"

    module = payload.get("python_ir")
    if not isinstance(module, dict) or not isinstance(module.get("nodes"), list):
        return False, "conditional-region validation lacks Python IR"
    table_map: dict[Any, dict[str, Any]] = {}
    for candidate in tables:
        _check_cancellation(cancellation)
        if isinstance(candidate, dict):
            table_map[candidate.get("table_id")] = candidate
    required = {
        "value-category-facts",
        "call-target-facts",
        "container-access-facts",
        "record-access-facts",
        "numeric-operation-facts",
        "module-function-facts",
        "module-source-facts",
    }
    if not required.issubset(table_map):
        return False, "conditional-region proof dependencies are absent"

    def values(table_id: str) -> tuple[dict[str, Any], ...]:
        result: list[dict[str, Any]] = []
        for record in table_map[table_id].get("records", ()):
            _check_cancellation(cancellation)
            if isinstance(record, dict) and isinstance(record.get("value"), dict):
                result.append(record["value"])
        return tuple(result)

    categories: dict[Any, Any] = {}
    for record in table_map["value-category-facts"].get("records", ()):
        _check_cancellation(cancellation)
        if isinstance(record, dict):
            categories[record.get("key")] = record.get("value")
    supported_calls: set[Any] = set()
    for item in values("call-target-facts"):
        if (
            item.get("supported") is True
            and item.get("resolution") == "understood-source-function"
        ):
            supported_calls.add(item.get("call_node_id"))
    numeric_operations: set[Any] = set()
    for item in values("numeric-operation-facts"):
        numeric_operations.add(item.get("binop_node_id"))
    container_accesses: set[Any] = set()
    for item in values("container-access-facts"):
        if item.get("supported") is True:
            container_accesses.add(item.get("subscript_node_id"))
    record_accesses: set[Any] = set()
    for item in values("record-access-facts"):
        record_accesses.add(item.get("access_node_id"))
    module_sources: dict[Any, dict[str, Any]] = {}
    for item in values("module-source-facts"):
        module_sources[item.get("module_id")] = item
    function_records: dict[str, dict[str, Any]] = {}
    for item in values("module-function-facts"):
        _check_cancellation(cancellation)
        source = module_sources.get(item.get("module_id"), {})
        function_records[str(item.get("function_node_id"))] = {
            **item,
            "logical_name": source.get("logical_name"),
        }

    reconstruction = _IndependentReconstruction(
        module,
        categories=categories,
        function_records=function_records,
        supported_calls=frozenset(item for item in supported_calls if isinstance(item, str)),
        numeric_operations=frozenset(item for item in numeric_operations if isinstance(item, str)),
        container_accesses=frozenset(item for item in container_accesses if isinstance(item, str)),
        record_accesses=frozenset(item for item in record_accesses if isinstance(item, str)),
        target_contract=str(payload.get("target_contract", "")),
        cancellation=cancellation,
    )
    try:
        expected = reconstruction.expected_regions()
    except ValueError as exc:
        return False, str(exc)

    records = table.get("records")
    if not isinstance(records, list):
        return False, "conditional-region records are malformed"
    keys: list[Any] = []
    for record in records:
        _check_cancellation(cancellation)
        if isinstance(record, dict):
            keys.append(record.get("key"))
    if len(keys) != len(records) or keys != sorted(keys) or len(keys) != len(set(keys)):
        return False, "conditional-region keys are not unique and sorted"
    found: dict[str, dict[str, Any]] = {}
    provenance: dict[str, dict[str, Any]] = {}
    for record in records:
        _check_cancellation(cancellation)
        key, value = record.get("key"), record.get("value")
        if not isinstance(key, str) or not isinstance(value, dict):
            return False, "conditional-region record identity is malformed"
        if value.get("region_node_id") != key:
            return False, "conditional-region record key disagrees with its value"
        found[key] = value
        provenance[key] = record.get("provenance")
    if set(found) != set(expected):
        return False, "conditional-region facts do not exactly cover eligible regions"
    for node_id, value in expected.items():
        _check_cancellation(cancellation)
        if found[node_id] != value:
            return False, "conditional-region fact disagrees with independent reconstruction"
        proof = provenance.get(node_id)
        if not isinstance(proof, dict) or proof.get(
            "source_node_ids"
        ) != _provenance_ids(value, cancellation):
            return False, "conditional-region provenance nodes are incomplete"
        if proof.get("evidence") != list(CONDITIONAL_REGION_PROVENANCE_EVIDENCE):
            return False, "conditional-region provenance evidence is invalid"

    valid, reason = _validate_plans(payload, expected, cancellation)
    if not valid:
        return valid, reason
    return True, ""


def _provenance_ids(fact: dict[str, Any], cancellation: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    values = (
        fact["region_node_id"],
        fact["function_node_id"],
        *fact["operator_node_ids"],
        *fact["operand_node_ids"],
        *fact["prerequisite_node_ids"],
    )
    for value in values:
        _check_cancellation(cancellation)
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class _IndependentReconstruction:
    def __init__(
        self,
        module: dict[str, Any],
        *,
        categories: Mapping[str, Any],
        function_records: Mapping[str, Mapping[str, Any]],
        supported_calls: frozenset[str],
        numeric_operations: frozenset[str],
        container_accesses: frozenset[str],
        record_accesses: frozenset[str],
        target_contract: str,
        cancellation: Any,
    ) -> None:
        self.module = module
        self.cancellation = cancellation
        self.nodes: dict[str, dict[str, Any]] = {}
        self.order: dict[str, int] = {}
        for ordinal, node in enumerate(module["nodes"]):
            _check_cancellation(self.cancellation)
            self.nodes[node["node_id"]] = node
            self.order[node["node_id"]] = ordinal
        self.categories = categories
        self.function_records = function_records
        self.supported_calls = supported_calls
        self.numeric_operations = numeric_operations
        self.container_accesses = container_accesses
        self.record_accesses = record_accesses
        self.target_contract = target_contract
        self.children: dict[str, tuple[str, ...]] = {}
        for node_id, node in self.nodes.items():
            _check_cancellation(self.cancellation)
            self.children[node_id] = self._children(node)
        self.owner_by_node = self._owners()
        self.approved: dict[str, bool] = {}
        self.prerequisites: dict[str, _ValidationPrerequisiteClosure] = {}

    def _children(self, node: dict[str, Any]) -> tuple[str, ...]:
        return tuple(
            child
            for field, value in node.get("fields", {}).items()
            for child in python_ir_reference_ids(node["kind"], field, value, self.nodes)
        )

    def _owners(self) -> dict[str, str]:
        owners: dict[str, str] = {}
        for function_id in sorted(self.function_records):
            _check_cancellation(self.cancellation)
            if function_id not in self.nodes:
                continue
            stack = [function_id]
            while stack:
                _check_cancellation(self.cancellation)
                current = stack.pop()
                if current in owners:
                    continue
                owners[current] = function_id
                for child in reversed(self.children[current]):
                    if child != current and self.nodes[child]["kind"] not in {
                        "FunctionDef",
                        "AsyncFunctionDef",
                    }:
                        stack.append(child)
        return owners

    def _postorder(self) -> tuple[str, ...]:
        result: list[str] = []
        state: dict[str, int] = {}
        for start in sorted(self.nodes, key=self.order.__getitem__):
            if state.get(start) == 2:
                continue
            stack = [(start, False)]
            while stack:
                _check_cancellation(self.cancellation)
                node_id, expanded = stack.pop()
                if expanded:
                    if state.get(node_id) != 2:
                        state[node_id] = 2
                        result.append(node_id)
                    continue
                if state.get(node_id) == 2:
                    continue
                if state.get(node_id) == 1:
                    raise ValueError("conditional-region Python IR is cyclic")
                state[node_id] = 1
                stack.append((node_id, True))
                for child in reversed(self.children[node_id]):
                    if state.get(child) == 1:
                        raise ValueError("conditional-region Python IR is cyclic")
                    if state.get(child) != 2:
                        stack.append((child, False))
        return tuple(result)

    def expected_regions(self) -> dict[str, dict[str, Any]]:
        for node_id in self._postorder():
            node = self.nodes[node_id]
            self.approved[node_id] = self._approved(node)
            self.prerequisites[node_id] = self._prerequisites(node)
        result: dict[str, dict[str, Any]] = {}
        for node in self.module["nodes"]:
            _check_cancellation(self.cancellation)
            if not self.approved.get(node["node_id"]):
                continue
            fields = node["fields"]
            if node["kind"] == "BoolOp":
                values = tuple(fields.get("values", ()))
                if any(
                    self.prerequisites.get(
                        item,
                        _EMPTY_VALIDATION_PREREQUISITES,
                    ).nonempty
                    for item in values
                ):
                    result[node["node_id"]] = self._fact(
                        node, ConditionalRegionKind.BOOLEAN_SHORT_CIRCUIT
                    )
            elif node["kind"] == "Compare" and len(tuple(fields.get("ops", ()))) > 1:
                operands = (fields.get("left"), *tuple(fields.get("comparators", ())))
                if any(
                    self.nodes[item]["kind"] not in {"Name", "Constant"}
                    or self.prerequisites.get(
                        item,
                        _EMPTY_VALIDATION_PREREQUISITES,
                    ).nonempty
                    for item in operands[2:]
                ):
                    result[node["node_id"]] = self._fact(
                        node, ConditionalRegionKind.CHAINED_COMPARISON
                    )
        return result

    def _approved(self, node: dict[str, Any]) -> bool:
        kind, fields, node_id = node["kind"], node["fields"], node["node_id"]
        category = self.categories.get(node_id, "unknown")
        if kind in {"Name", "Constant"}:
            return category in _SCALARS
        if kind == "Attribute":
            return node_id in self.record_accesses and category in _SCALARS
        if kind == "Subscript":
            return node_id in self.container_accesses and category in _SCALARS
        if kind == "Call":
            return (
                node_id in self.supported_calls
                and category in _SCALARS
                and all(self.approved.get(item, False) for item in fields.get("args", ()))
            )
        if kind == "UnaryOp":
            operand = fields.get("operand")
            operator = self.nodes.get(fields.get("op"), {}).get("kind")
            operand_category = self.categories.get(operand)
            if not self.approved.get(operand, False):
                return False
            if operator == "Not":
                return category == "boolean-like" and operand_category in _COMPARABLE
            return operator in {"UAdd", "USub"} and category in {
                "integer-like",
                "floating-like",
            }
        if kind == "BinOp":
            left, right = fields.get("left"), fields.get("right")
            operator = self.nodes.get(fields.get("op"), {}).get("kind")
            if not self.approved.get(left, False) or not self.approved.get(right, False):
                return False
            if operator in {"FloorDiv", "Mod"}:
                return node_id in self.numeric_operations
            if operator == "Div":
                return category == "floating-like"
            return operator in {"Add", "Sub", "Mult"} and category in {
                "integer-like",
                "floating-like",
            }
        if kind == "BoolOp":
            values = tuple(fields.get("values", ()))
            operator = self.nodes.get(fields.get("op"), {}).get("kind")
            return (
                operator in {"And", "Or"}
                and len(values) >= 2
                and category == "boolean-like"
                and all(
                    self.categories.get(item) == "boolean-like"
                    and self.approved.get(item, False)
                    for item in values
                )
            )
        if kind == "Compare":
            operands = (fields.get("left"), *tuple(fields.get("comparators", ())))
            operators = tuple(fields.get("ops", ()))
            operand_categories = tuple(self.categories.get(item) for item in operands)
            return (
                bool(operators)
                and len(operands) == len(operators) + 1
                and all(self.approved.get(item, False) for item in operands)
                and all(self.nodes.get(item, {}).get("kind") in _COMPARE_OPS for item in operators)
                and operand_categories[0] in _COMPARABLE
                and all(item == operand_categories[0] for item in operand_categories)
                and category == "boolean-like"
            )
        return False

    def _prerequisites(
        self,
        node: dict[str, Any],
    ) -> _ValidationPrerequisiteClosure:
        if not self.approved.get(node["node_id"], False):
            return _EMPTY_VALIDATION_PREREQUISITES
        kind, fields, node_id = node["kind"], node["fields"], node["node_id"]

        def merge(ids: tuple[str, ...]) -> _ValidationPrerequisiteClosure:
            return _validation_closure(
                tuple(
                    self.prerequisites.get(
                        child,
                        _EMPTY_VALIDATION_PREREQUISITES,
                    )
                    for child in ids
                )
            )

        if kind == "Call":
            return _validation_closure(
                (merge(tuple(fields.get("args", ()))),),
                node_id,
            )
        if kind == "UnaryOp":
            return self.prerequisites.get(
                fields.get("operand"),
                _EMPTY_VALIDATION_PREREQUISITES,
            )
        if kind == "BinOp":
            inherited = merge((fields["left"], fields["right"]))
            return (
                _validation_closure((inherited,), node_id)
                if node_id in self.numeric_operations
                else inherited
            )
        if kind == "BoolOp":
            inherited = merge(tuple(fields.get("values", ())))
            return (
                _validation_closure((inherited,), node_id)
                if inherited.nonempty
                else _EMPTY_VALIDATION_PREREQUISITES
            )
        if kind == "Compare":
            operands = (fields["left"], *tuple(fields.get("comparators", ())))
            inherited = merge(operands)
            return (
                _validation_closure((inherited,), node_id)
                if len(tuple(fields.get("ops", ()))) > 1
                else inherited
            )
        return _EMPTY_VALIDATION_PREREQUISITES

    def _fact(self, node: dict[str, Any], kind: ConditionalRegionKind) -> dict[str, Any]:
        fields = node["fields"]
        if kind is ConditionalRegionKind.BOOLEAN_SHORT_CIRCUIT:
            operands = tuple(fields["values"])
            operators = (fields["op"],)
            prefix = 1
            guard = (
                "when-result-true"
                if self.nodes[operators[0]]["kind"] == "And"
                else "when-result-false"
            )
        else:
            operands = (fields["left"], *tuple(fields.get("comparators", ())))
            operators = tuple(fields["ops"])
            prefix = 2
            guard = "when-result-true"
        owner_id = self.owner_by_node.get(node["node_id"])
        owner = self.function_records.get(owner_id or "")
        if not isinstance(owner, Mapping):
            raise ValueError("conditional-region function ownership is absent")
        source = {
            "module_id": owner.get("module_id"),
            "document_id": owner.get("document_id"),
            "logical_name": owner.get("logical_name"),
        }
        if not all(isinstance(value, str) and value for value in source.values()):
            raise ValueError("conditional-region source ownership is invalid")
        placements = []
        for ordinal, operand in enumerate(operands):
            _check_cancellation(self.cancellation)
            unconditional = ordinal < prefix
            prerequisite_node_ids = self.prerequisites.get(
                operand,
                _EMPTY_VALIDATION_PREREQUISITES,
            ).materialize(self.cancellation)
            placements.append(
                {
                    "operand_node_id": operand,
                    "ordinal": ordinal,
                    "category": self.categories[operand],
                    "evaluation_mode": "unconditional" if unconditional else "guarded",
                    "guard_polarity": "none" if unconditional else guard,
                    "guard_after_operand_ordinal": None if unconditional else ordinal - 1,
                    "requires_statement_prelude": bool(prerequisite_node_ids),
                    "prerequisite_node_ids": list(prerequisite_node_ids),
                    "legacy_direct_safe": self.nodes[operand]["kind"] in {"Name", "Constant"},
                }
            )
        prerequisite_values: list[str] = []
        prerequisite_seen: set[str] = set()
        for placement in placements:
            for prerequisite in placement["prerequisite_node_ids"]:
                _check_cancellation(self.cancellation)
                if prerequisite not in prerequisite_seen:
                    prerequisite_seen.add(prerequisite)
                    prerequisite_values.append(prerequisite)
        prerequisites = tuple(prerequisite_values)
        return {
            "region_id": conditional_region_id(node["node_id"], kind),
            "region_node_id": node["node_id"],
            "region_kind": kind.value,
            "function_node_id": owner_id,
            **source,
            "operator_node_ids": list(operators),
            "operator_kinds": [self.nodes[item]["kind"] for item in operators],
            "operand_node_ids": list(operands),
            "operand_categories": [self.categories[item] for item in operands],
            "unconditional_prefix_count": prefix,
            "placements": placements,
            "guarded_operand_node_ids": list(operands[prefix:]),
            "prerequisite_node_ids": list(prerequisites),
            "result_category": "boolean-like",
            "result_c_type": "bool",
            "evaluation_order": list(operands),
            "operands_evaluated_once": True,
            "lowering_shape": CONDITIONAL_REGION_LOWERING_SHAPE,
            "allocation_model": "none",
            "cleanup_model": "none",
            "runtime_failure_channel": "unchanged",
            "target_contract": self.target_contract,
        }


def _validate_plans(
    payload: dict[str, Any],
    expected: dict[str, dict[str, Any]],
    cancellation: Any,
) -> tuple[bool, str]:
    _check_cancellation(cancellation)
    conditional_rule_ids = {
        "phase14.conditional.boolean_region",
        "phase14.conditional.comparison_region",
    }
    conditional_plans: list[dict[str, Any]] = []
    plans_by_source: dict[Any, list[dict[str, Any]]] = {}
    for item in payload.get("rule_plans", ()):
        _check_cancellation(cancellation)
        if isinstance(item, dict) and item.get("rule_id") in conditional_rule_ids:
            conditional_plans.append(item)
            plans_by_source.setdefault(item.get("source_node_id"), []).append(item)
    if {item.get("source_node_id") for item in conditional_plans} != set(expected):
        return False, "conditional-region RulePlans do not exactly cover facts"
    support: dict[Any, dict[str, Any]] = {}
    for item in payload.get("support_decisions", ()):
        _check_cancellation(cancellation)
        if isinstance(item, dict):
            support[item.get("node_id")] = item
    for node_id, fact in expected.items():
        _check_cancellation(cancellation)
        matches = plans_by_source.get(node_id, ())
        if len(matches) != 1:
            return False, "conditional region lacks exactly one RulePlan"
        plan = matches[0]
        rule_id = (
            "phase14.conditional.boolean_region"
            if fact["region_kind"] == "boolean-short-circuit"
            else "phase14.conditional.comparison_region"
        )
        rule_facts = {
            "value-category:boolean-like",
            f"conditional-region:{node_id}",
            f"conditional-region-kind:{fact['region_kind']}",
            f"conditional-unconditional-prefix:{fact['unconditional_prefix_count']}",
            f"conditional-guarded-operand-count:{len(fact['guarded_operand_node_ids'])}",
            f"conditional-lowering-shape:{fact['lowering_shape']}",
            f"conditional-target:{fact['target_contract']}",
        }
        explanation = [
            "selected",
            rule_id,
            "for",
            "BoolOp" if fact["region_kind"] == "boolean-short-circuit" else "Compare",
            "conditional-region",
            fact["region_kind"],
            "unconditional-prefix",
            str(fact["unconditional_prefix_count"]),
            "guarded-operands",
            str(len(fact["guarded_operand_node_ids"])),
            "lowered-as",
            fact["lowering_shape"],
        ]
        decision = support.get(node_id)
        if (
            plan.get("rule_id") != rule_id
            or plan.get("rule_version") != "0.14.1"
            or plan.get("support_state") != "SupportedDirect"
            or plan.get("helper_requirements") != []
            or set(plan.get("facts_used", ())) != rule_facts
            or plan.get("semantic_obligations") != list(CONDITIONAL_REGION_OBLIGATIONS)
            or plan.get("resolved_obligations") != list(CONDITIONAL_REGION_OBLIGATIONS)
            or plan.get("unresolved_obligations") != []
            or plan.get("explanation_tokens") != explanation
            or not isinstance(decision, dict)
            or decision.get("state") != "SupportedDirect"
            or decision.get("rule_plan_id") != plan.get("plan_id")
        ):
            return False, "conditional-region RulePlan does not close its exact proof"
    return True, ""


__all__ = ["validate_conditional_region_facts"]
