"""Closed, linear proof pass for conditional temporary placement."""

from __future__ import annotations

from typing import Any, Mapping

from pycforge.converter.analysis.model import ValueCategory
from pycforge.converter.ir.python_ir import python_ir_reference_ids

from .model import (
    CONDITIONAL_REGION_LOWERING_SHAPE,
    ConditionalEvaluationMode,
    ConditionalGuardPolarity,
    ConditionalOperandPlacementFact,
    ConditionalRegionAnalysis,
    ConditionalRegionAnalysisCanceled,
    ConditionalRegionAnalysisError,
    ConditionalRegionFact,
    ConditionalRegionKind,
    conditional_region_id,
)


_SCALAR_CATEGORIES = frozenset(
    {
        ValueCategory.INTEGER.value,
        ValueCategory.FLOAT.value,
        ValueCategory.BOOLEAN.value,
        ValueCategory.STRING.value,
    }
)
_COMPARABLE_CATEGORIES = frozenset(
    {
        ValueCategory.INTEGER.value,
        ValueCategory.FLOAT.value,
        ValueCategory.BOOLEAN.value,
    }
)
_COMPARISON_OPERATORS = frozenset({"Eq", "NotEq", "Lt", "LtE", "Gt", "GtE"})


def _category_value(value: ValueCategory | str | None) -> str:
    return value.value if isinstance(value, ValueCategory) else str(value or "unknown")


class _PrerequisiteClosure:
    """Persistent, ordered prerequisite rope.

    Building one closure costs only the number of direct child expressions.
    Flattening is delayed until a published fact needs the sequence, making
    nested wrapper analysis linear plus the size of serialized fact output.
    """

    __slots__ = ("parts", "node_id", "nonempty")

    def __init__(
        self,
        parts: tuple["_PrerequisiteClosure", ...] = (),
        node_id: str | None = None,
    ) -> None:
        self.parts = tuple(part for part in parts if part.nonempty)
        self.node_id = node_id
        self.nonempty = bool(self.parts) or node_id is not None

    def materialize(self, check_cancellation: Any) -> tuple[str, ...]:
        if not self.nonempty:
            return ()
        result: list[str] = []
        seen_node_ids: set[str] = set()
        seen_closures: set[int] = set()
        stack: list[_PrerequisiteClosure | str] = [self]
        while stack:
            check_cancellation()
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


_EMPTY_PREREQUISITES = _PrerequisiteClosure()


def _closure(
    parts: tuple[_PrerequisiteClosure, ...] = (),
    node_id: str | None = None,
) -> _PrerequisiteClosure:
    if node_id is None and not any(part.nonempty for part in parts):
        return _EMPTY_PREREQUISITES
    return _PrerequisiteClosure(parts, node_id)


class ConditionalRegionAnalyzer:
    """Prove statement-prerequisite placement for existing scalar expressions.

    The pass is deliberately independent of C IR.  It computes one postorder
    staging-demand map and then selects only source forms rejected by the
    predecessor's eager-prelude boundary.
    """

    def __init__(
        self,
        module: dict[str, Any],
        *,
        categories: Mapping[str, ValueCategory | str],
        function_records: Mapping[str, Mapping[str, Any]],
        owner_by_node: Mapping[str, str],
        supported_call_node_ids: frozenset[str],
        numeric_operation_node_ids: frozenset[str],
        supported_container_access_node_ids: frozenset[str] = frozenset(),
        supported_record_access_node_ids: frozenset[str] = frozenset(),
        cancellation: Any,
        target_contract: str = "c11-portable-fixed-v1",
    ) -> None:
        self.module = module
        self.cancellation = cancellation
        self.nodes: dict[str, dict[str, Any]] = {}
        self.ordinals: dict[str, int] = {}
        for ordinal, node in enumerate(module["nodes"]):
            self._check_cancellation()
            self.nodes[node["node_id"]] = node
            self.ordinals[node["node_id"]] = ordinal
        self.categories = {
            node_id: _category_value(category) for node_id, category in categories.items()
        }
        self.function_records = function_records
        self.owner_by_node = owner_by_node
        self.supported_calls = supported_call_node_ids
        self.numeric_operations = numeric_operation_node_ids
        self.supported_container_accesses = supported_container_access_node_ids
        self.supported_record_accesses = supported_record_access_node_ids
        self.target_contract = target_contract
        self.children: dict[str, tuple[str, ...]] = {}
        for node_id, node in self.nodes.items():
            self._check_cancellation()
            self.children[node_id] = self._children(node)
        self.approved: dict[str, bool] = {}
        self.prerequisites: dict[str, _PrerequisiteClosure] = {}

    def analyze(self) -> ConditionalRegionAnalysis:
        for node_id in self._postorder():
            self._check_cancellation()
            self.approved[node_id] = self._approved_expression(self.nodes[node_id])
            self.prerequisites[node_id] = self._statement_prerequisites(
                self.nodes[node_id]
            )

        regions: list[ConditionalRegionFact] = []
        for node in self.module["nodes"]:
            self._check_cancellation()
            if not self.approved.get(node["node_id"], False):
                continue
            if node["kind"] == "BoolOp" and self._boolean_requires_region(node):
                regions.append(self._region(node, ConditionalRegionKind.BOOLEAN_SHORT_CIRCUIT))
            elif node["kind"] == "Compare" and self._comparison_requires_region(node):
                regions.append(self._region(node, ConditionalRegionKind.CHAINED_COMPARISON))
        return ConditionalRegionAnalysis(
            tuple(sorted(regions, key=lambda item: item.region_node_id))
        )

    def _children(self, node: dict[str, Any]) -> tuple[str, ...]:
        found: list[str] = []
        for field_name, value in node.get("fields", {}).items():
            found.extend(
                python_ir_reference_ids(node["kind"], field_name, value, self.nodes)
            )
        return tuple(found)

    def _postorder(self) -> tuple[str, ...]:
        """Return a deterministic iterative postorder over the bounded IR graph."""

        state: dict[str, int] = {}
        result: list[str] = []
        for start in sorted(self.nodes, key=self.ordinals.__getitem__):
            if state.get(start) == 2:
                continue
            stack: list[tuple[str, bool]] = [(start, False)]
            while stack:
                self._check_cancellation()
                node_id, expanded = stack.pop()
                if expanded:
                    if state.get(node_id) != 2:
                        state[node_id] = 2
                        result.append(node_id)
                    continue
                current = state.get(node_id, 0)
                if current == 2:
                    continue
                if current == 1:
                    self._error(
                        "PYC2950",
                        "Conditional-region analysis encountered a cyclic Python IR reference",
                        self.nodes[node_id],
                    )
                state[node_id] = 1
                stack.append((node_id, True))
                for child_id in reversed(self.children[node_id]):
                    if state.get(child_id, 0) == 1:
                        self._error(
                            "PYC2950",
                            "Conditional-region analysis encountered a cyclic Python IR reference",
                            self.nodes[child_id],
                        )
                    if state.get(child_id, 0) != 2:
                        stack.append((child_id, False))
        return tuple(result)

    def _approved_expression(self, node: dict[str, Any]) -> bool:
        kind = node["kind"]
        fields = node.get("fields", {})
        node_id = node["node_id"]
        category = self.categories.get(node_id, "unknown")
        if kind in {"Name", "Constant"}:
            return category in _SCALAR_CATEGORIES
        if kind == "Attribute":
            return node_id in self.supported_record_accesses and category in _SCALAR_CATEGORIES
        if kind == "Subscript":
            return node_id in self.supported_container_accesses and category in _SCALAR_CATEGORIES
        if kind == "Call":
            arguments = tuple(fields.get("args", ()))
            return (
                node_id in self.supported_calls
                and category in _SCALAR_CATEGORIES
                and all(self.approved.get(item, False) for item in arguments)
            )
        if kind == "UnaryOp":
            operator = self.nodes.get(fields.get("op"), {}).get("kind")
            operand_id = fields.get("operand")
            operand_category = self.categories.get(operand_id, "unknown")
            if not isinstance(operand_id, str) or not self.approved.get(operand_id, False):
                return False
            if operator == "Not":
                return category == ValueCategory.BOOLEAN.value and operand_category in {
                    ValueCategory.INTEGER.value,
                    ValueCategory.FLOAT.value,
                    ValueCategory.BOOLEAN.value,
                }
            return operator in {"UAdd", "USub"} and category in {
                ValueCategory.INTEGER.value,
                ValueCategory.FLOAT.value,
            }
        if kind == "BinOp":
            left_id, right_id = fields.get("left"), fields.get("right")
            operator = self.nodes.get(fields.get("op"), {}).get("kind")
            if not (
                isinstance(left_id, str)
                and isinstance(right_id, str)
                and self.approved.get(left_id, False)
                and self.approved.get(right_id, False)
            ):
                return False
            if operator in {"FloorDiv", "Mod"}:
                return node_id in self.numeric_operations
            if operator == "Div":
                return category == ValueCategory.FLOAT.value
            return operator in {"Add", "Sub", "Mult"} and category in {
                ValueCategory.INTEGER.value,
                ValueCategory.FLOAT.value,
            }
        if kind == "BoolOp":
            values = tuple(fields.get("values", ()))
            operator = self.nodes.get(fields.get("op"), {}).get("kind")
            return (
                operator in {"And", "Or"}
                and len(values) >= 2
                and category == ValueCategory.BOOLEAN.value
                and all(
                    self.categories.get(item) == ValueCategory.BOOLEAN.value
                    and self.approved.get(item, False)
                    for item in values
                )
            )
        if kind == "Compare":
            operands = (fields.get("left"), *tuple(fields.get("comparators", ())))
            operators = tuple(fields.get("ops", ()))
            operand_categories = tuple(self.categories.get(item, "unknown") for item in operands)
            operator_kinds = tuple(
                self.nodes.get(item, {}).get("kind") for item in operators
            )
            return (
                bool(operators)
                and len(operands) == len(operators) + 1
                and all(isinstance(item, str) and self.approved.get(item, False) for item in operands)
                and all(item in _COMPARISON_OPERATORS for item in operator_kinds)
                and operand_categories
                and operand_categories[0] in _COMPARABLE_CATEGORIES
                and all(item == operand_categories[0] for item in operand_categories)
                and category == ValueCategory.BOOLEAN.value
            )
        return False

    def _statement_prerequisites(
        self,
        node: dict[str, Any],
    ) -> _PrerequisiteClosure:
        if not self.approved.get(node["node_id"], False):
            return _EMPTY_PREREQUISITES
        kind = node["kind"]
        fields = node.get("fields", {})
        node_id = node["node_id"]

        def merge(node_ids: tuple[str, ...] | list[str]) -> _PrerequisiteClosure:
            return _closure(
                tuple(
                    self.prerequisites.get(child_id, _EMPTY_PREREQUISITES)
                    for child_id in node_ids
                )
            )

        if kind == "Call":
            return _closure((merge(tuple(fields.get("args", ()))),), node_id)
        if kind == "UnaryOp":
            operand_id = fields.get("operand")
            return self.prerequisites.get(operand_id, _EMPTY_PREREQUISITES)
        if kind == "BinOp":
            children = (fields.get("left"), fields.get("right"))
            inherited = merge(tuple(item for item in children if isinstance(item, str)))
            if node_id in self.numeric_operations:
                return _closure((inherited,), node_id)
            return inherited
        if kind == "BoolOp":
            inherited = merge(tuple(fields.get("values", ())))
            return (
                _closure((inherited,), node_id)
                if inherited.nonempty
                else _EMPTY_PREREQUISITES
            )
        if kind == "Compare":
            operands = (fields.get("left"), *tuple(fields.get("comparators", ())))
            inherited = merge(tuple(item for item in operands if isinstance(item, str)))
            if len(tuple(fields.get("ops", ()))) > 1:
                return _closure((inherited,), node_id)
            return inherited
        return _EMPTY_PREREQUISITES

    def _boolean_requires_region(self, node: dict[str, Any]) -> bool:
        return any(
            self.prerequisites.get(item, _EMPTY_PREREQUISITES).nonempty
            for item in node.get("fields", {}).get("values", ())
        )

    def _comparison_requires_region(self, node: dict[str, Any]) -> bool:
        fields = node.get("fields", {})
        operators = tuple(fields.get("ops", ()))
        operands = (fields.get("left"), *tuple(fields.get("comparators", ())))
        if len(operators) <= 1:
            return False
        return any(
            self.nodes[item]["kind"] not in {"Name", "Constant"}
            or self.prerequisites.get(item, _EMPTY_PREREQUISITES).nonempty
            for item in operands[2:]
        )

    def _region(
        self,
        node: dict[str, Any],
        kind: ConditionalRegionKind,
    ) -> ConditionalRegionFact:
        fields = node["fields"]
        if kind is ConditionalRegionKind.BOOLEAN_SHORT_CIRCUIT:
            operand_ids = tuple(fields.get("values", ()))
            operator_ids = (fields["op"],)
            prefix_count = 1
            boolean_operator = self.nodes[operator_ids[0]]["kind"]
            guarded_polarity = (
                ConditionalGuardPolarity.WHEN_RESULT_TRUE
                if boolean_operator == "And"
                else ConditionalGuardPolarity.WHEN_RESULT_FALSE
            )
        else:
            operand_ids = (fields["left"], *tuple(fields.get("comparators", ())))
            operator_ids = tuple(fields.get("ops", ()))
            prefix_count = 2
            guarded_polarity = ConditionalGuardPolarity.WHEN_RESULT_TRUE

        owner_id = self.owner_by_node.get(node["node_id"])
        owner = self.function_records.get(owner_id or "")
        if not isinstance(owner_id, str) or not isinstance(owner, Mapping):
            self._error(
                "PYC2950" if kind is ConditionalRegionKind.BOOLEAN_SHORT_CIRCUIT else "PYC2951",
                "Conditional temporary placement requires an understood top-level function owner",
                node,
            )
        module_id = owner.get("module_id")
        document_id = owner.get("document_id")
        logical_name = owner.get("logical_name")
        if not all(isinstance(item, str) and item for item in (module_id, document_id, logical_name)):
            self._error(
                "PYC2950" if kind is ConditionalRegionKind.BOOLEAN_SHORT_CIRCUIT else "PYC2951",
                "Conditional temporary placement lacks exact module or source ownership",
                node,
            )

        placements: list[ConditionalOperandPlacementFact] = []
        for ordinal, operand_id in enumerate(operand_ids):
            self._check_cancellation()
            unconditional = ordinal < prefix_count
            prerequisite_node_ids = self.prerequisites.get(
                operand_id,
                _EMPTY_PREREQUISITES,
            ).materialize(self._check_cancellation)
            placements.append(
                ConditionalOperandPlacementFact(
                    operand_node_id=operand_id,
                    ordinal=ordinal,
                    category=self.categories[operand_id],
                    evaluation_mode=(
                        ConditionalEvaluationMode.UNCONDITIONAL
                        if unconditional
                        else ConditionalEvaluationMode.GUARDED
                    ),
                    guard_polarity=(
                        ConditionalGuardPolarity.NONE
                        if unconditional
                        else guarded_polarity
                    ),
                    guard_after_operand_ordinal=None if unconditional else ordinal - 1,
                    requires_statement_prelude=bool(prerequisite_node_ids),
                    prerequisite_node_ids=prerequisite_node_ids,
                    legacy_direct_safe=self.nodes[operand_id]["kind"] in {"Name", "Constant"},
                )
            )
        prerequisite_values: list[str] = []
        prerequisite_seen: set[str] = set()
        for placement in placements:
            for prerequisite in placement.prerequisite_node_ids:
                self._check_cancellation()
                if prerequisite not in prerequisite_seen:
                    prerequisite_seen.add(prerequisite)
                    prerequisite_values.append(prerequisite)
        prerequisites = tuple(prerequisite_values)
        return ConditionalRegionFact(
            region_id=conditional_region_id(node["node_id"], kind),
            region_node_id=node["node_id"],
            region_kind=kind,
            function_node_id=owner_id,
            module_id=module_id,
            document_id=document_id,
            logical_name=logical_name,
            operator_node_ids=operator_ids,
            operator_kinds=tuple(self.nodes[item]["kind"] for item in operator_ids),
            operand_node_ids=operand_ids,
            operand_categories=tuple(self.categories[item] for item in operand_ids),
            unconditional_prefix_count=prefix_count,
            placements=tuple(placements),
            guarded_operand_node_ids=operand_ids[prefix_count:],
            prerequisite_node_ids=prerequisites,
            result_category=ValueCategory.BOOLEAN.value,
            result_c_type="bool",
            evaluation_order=operand_ids,
            operands_evaluated_once=True,
            lowering_shape=CONDITIONAL_REGION_LOWERING_SHAPE,
            allocation_model="none",
            cleanup_model="none",
            runtime_failure_channel="unchanged",
            target_contract=self.target_contract,
        )

    def _error(self, code: str, message: str, node: dict[str, Any]) -> None:
        raise ConditionalRegionAnalysisError(
            code,
            message,
            node["node_id"],
            node.get("provenance", {}).get("source_span"),
        )

    def _check_cancellation(self) -> None:
        if bool(getattr(self.cancellation, "is_canceled", False)):
            raise ConditionalRegionAnalysisCanceled


__all__ = ["ConditionalRegionAnalyzer"]
