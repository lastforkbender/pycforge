"""Deterministic analysis for the approved fixed local-container profile."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Any

from pycforge.converter.analysis.model import ValueCategory
from pycforge.converter.analysis.symbols import PythonIRIndex

from .model import (
    MAX_CONTAINER_ELEMENTS,
    ContainerAccessFact,
    ContainerBindingFact,
    ContainerIterationFact,
    ContainerShapeFact,
)


_SCALAR_CATEGORIES = {
    ValueCategory.INTEGER,
    ValueCategory.FLOAT,
    ValueCategory.BOOLEAN,
    ValueCategory.STRING,
}
_LITERAL_KINDS = {"List": "list", "Tuple": "tuple", "Dict": "dict"}
_COMPREHENSION_KINDS = {
    "ListComp": "list-comprehension",
    "DictComp": "dict-comprehension",
    "GeneratorExp": "generator-expression",
}


class BoundedContainerAnalyzer:
    """Publish shapes, bindings, proven accesses, and bounded iterations."""

    def __init__(
        self,
        module: dict[str, Any],
        bindings: tuple[dict[str, Any], ...],
        categories: dict[str, ValueCategory],
    ) -> None:
        self.index = PythonIRIndex(module)
        self.categories = categories
        self.bindings = bindings
        self.binding_by_occurrence = {
            occurrence: binding
            for binding in bindings
            for occurrence in binding["occurrence_node_ids"]
        }
        self.parents: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for parent in self.index.nodes.values():
            for field_name, value in parent["fields"].items():
                for child_id in self._references(value):
                    if child_id in self.index.nodes:
                        self.parents[child_id].append((parent["node_id"], field_name))

    def analyze(
        self,
    ) -> tuple[
        tuple[ContainerShapeFact, ...],
        tuple[ContainerBindingFact, ...],
        tuple[ContainerAccessFact, ...],
        tuple[ContainerIterationFact, ...],
    ]:
        shapes = tuple(
            sorted(
                (
                    self._shape(node)
                    for node in self.index.nodes.values()
                    if node["kind"] in _LITERAL_KINDS | _COMPREHENSION_KINDS
                ),
                key=lambda item: item.literal_node_id,
            )
        )
        shape_by_node = {item.literal_node_id: item for item in shapes}
        raw_bindings, assignments_by_binding = self._raw_bindings(shape_by_node)
        raw_by_id = {item.binding_id: item for item in raw_bindings}
        accesses = self._accesses(raw_by_id, shape_by_node)
        iterations = self._iterations(raw_by_id, shape_by_node)
        bindings = self._finalize_bindings(
            raw_bindings,
            assignments_by_binding,
        )
        finalized = {item.binding_id: item for item in bindings}
        invalid_binding_ids = {
            binding_id for binding_id, item in finalized.items() if not item.valid
        }
        accesses = tuple(
            replace(
                item,
                result_category=ValueCategory.UNKNOWN,
                resolved_offset=None,
                supported=False,
                diagnostic_code="PYC3403",
                reason="Container access depends on an invalid fixed binding",
            )
            if item.supported and item.binding_id in invalid_binding_ids
            else item
            for item in accesses
        )
        iterations = tuple(
            replace(
                item,
                target_category=ValueCategory.UNKNOWN,
                supported=False,
                diagnostic_code="PYC3403",
                reason="Container iteration depends on an invalid fixed binding",
            )
            if item.supported and item.binding_id in invalid_binding_ids
            else item
            for item in iterations
        )
        return shapes, bindings, accesses, iterations

    def _shape(self, node: dict[str, Any]) -> ContainerShapeFact:
        kind = node["kind"]
        if kind in _COMPREHENSION_KINDS:
            return ContainerShapeFact(
                node["node_id"],
                _COMPREHENSION_KINDS[kind],
                0,
                (),
                (),
                (),
                ValueCategory.UNKNOWN,
                ValueCategory.UNKNOWN,
                ValueCategory.UNKNOWN,
                (),
                "unsupported-comprehension",
                False,
                False,
                "PYC3406",
                "Container comprehensions and generator expressions are unsupported",
            )
        if kind in {"List", "Tuple"}:
            elements = tuple(node["fields"].get("elts", ()))
            container_kind = _LITERAL_KINDS[kind]
            category = self._homogeneous_category(elements)
            problem = self._capacity_problem(len(elements))
            if problem is None and any(
                self.index.nodes.get(item, {}).get("kind") in _LITERAL_KINDS | _COMPREHENSION_KINDS
                for item in elements
            ):
                problem = ("PYC3401", "Nested containers are unsupported in the fixed profile")
            if problem is None and category not in _SCALAR_CATEGORIES:
                problem = (
                    "PYC3402",
                    "Container elements must have one homogeneous supported scalar representation",
                )
            valid = problem is None
            return ContainerShapeFact(
                node["node_id"],
                container_kind,
                len(elements),
                elements,
                (),
                (),
                category,
                ValueCategory.UNKNOWN,
                ValueCategory.UNKNOWN,
                (),
                "fixed-automatic-array",
                kind == "List",
                valid,
                None if valid else problem[0],
                None if valid else problem[1],
            )

        keys = tuple(node["fields"].get("keys", ()))
        values = tuple(node["fields"].get("values", ()))
        problem = self._capacity_problem(len(values))
        key_values: list[int | str] = []
        key_categories: list[ValueCategory] = []
        if problem is None and (len(keys) != len(values) or any(not isinstance(item, str) for item in keys)):
            problem = ("PYC3401", "Dictionary unpacking or malformed key/value shape is unsupported")
        if problem is None:
            for key_id in keys:
                literal = self._literal_key(key_id)
                if literal is None:
                    problem = ("PYC3402", "Dictionary keys must be literal int or str values")
                    break
                key_value, key_category = literal
                key_values.append(key_value)
                key_categories.append(key_category)
        if problem is None and (
            not key_categories
            or any(item is not key_categories[0] for item in key_categories)
        ):
            problem = ("PYC3402", "Dictionary keys must use one homogeneous int or str representation")
        if problem is None and len({(type(item).__name__, item) for item in key_values}) != len(key_values):
            problem = ("PYC3402", "Duplicate dictionary keys are unsupported in the fixed profile")
        value_category = self._homogeneous_category(values)
        if problem is None and any(
            self.index.nodes.get(item, {}).get("kind") in _LITERAL_KINDS | _COMPREHENSION_KINDS
            for item in values
        ):
            problem = ("PYC3401", "Nested containers are unsupported in the fixed profile")
        if problem is None and value_category not in _SCALAR_CATEGORIES:
            problem = (
                "PYC3402",
                "Dictionary values must have one homogeneous supported scalar representation",
            )
        valid = problem is None
        return ContainerShapeFact(
            node["node_id"],
            "dict",
            len(values),
            (),
            tuple(item for item in keys if isinstance(item, str)),
            values,
            ValueCategory.UNKNOWN,
            key_categories[0] if key_categories else ValueCategory.UNKNOWN,
            value_category,
            tuple(key_values),
            "parallel-fixed-automatic-arrays",
            False,
            valid,
            None if valid else problem[0],
            None if valid else problem[1],
        )

    @staticmethod
    def _capacity_problem(capacity: int) -> tuple[str, str] | None:
        if capacity <= 0:
            return "PYC3401", "Empty containers have no approved element representation"
        if capacity > MAX_CONTAINER_ELEMENTS:
            return (
                "PYC3401",
                f"Container capacity exceeds the fixed limit of {MAX_CONTAINER_ELEMENTS}",
            )
        return None

    def _homogeneous_category(self, node_ids: tuple[str, ...]) -> ValueCategory:
        values = tuple(self.categories.get(item, ValueCategory.UNKNOWN) for item in node_ids)
        if values and all(item is values[0] for item in values):
            return values[0]
        if any(item is ValueCategory.CONTRADICTORY for item in values) or values:
            return ValueCategory.CONTRADICTORY
        return ValueCategory.UNKNOWN

    def _raw_bindings(
        self,
        shapes: dict[str, ContainerShapeFact],
    ) -> tuple[tuple[ContainerBindingFact, ...], dict[str, tuple[str, ...]]]:
        assignments_by_binding: dict[str, list[str]] = defaultdict(list)
        candidates: dict[str, list[ContainerBindingFact]] = defaultdict(list)
        for node in self.index.nodes.values():
            if node["kind"] != "Assign":
                continue
            targets = tuple(node["fields"].get("targets", ()))
            if len(targets) != 1 or targets[0] not in self.index.nodes:
                continue
            target = self.index.node(targets[0])
            if target["kind"] != "Name":
                continue
            binding = self.binding_by_occurrence.get(target["node_id"])
            if not binding:
                continue
            binding_id = binding["binding_id"]
            assignments_by_binding[binding_id].append(node["node_id"])
            value_id = node["fields"].get("value")
            shape = shapes.get(value_id)
            if not shape or shape.container_kind not in {"list", "tuple", "dict"}:
                continue
            candidates[binding_id].append(
                ContainerBindingFact(
                    binding_id,
                    binding["source_name"],
                    node["node_id"],
                    target["node_id"],
                    shape.literal_node_id,
                    shape.container_kind,
                    shape.capacity,
                    shape.element_category,
                    shape.key_category,
                    shape.value_category,
                    (),
                    (),
                    shape.valid,
                    shape.diagnostic_code,
                    shape.literal_node_id if not shape.valid else None,
                    shape.reason,
                )
            )
        selected = tuple(
            sorted(
                (
                    sorted(items, key=lambda item: self._ordinal(item.assignment_node_id))[0]
                    for items in candidates.values()
                ),
                key=lambda item: item.binding_id,
            )
        )
        return selected, {
            key: tuple(sorted(values, key=self._ordinal))
            for key, values in assignments_by_binding.items()
        }

    def _finalize_bindings(
        self,
        bindings: tuple[ContainerBindingFact, ...],
        assignments_by_binding: dict[str, tuple[str, ...]],
    ) -> tuple[ContainerBindingFact, ...]:
        result: list[ContainerBindingFact] = []
        for fact in bindings:
            binding = next(item for item in self.bindings if item["binding_id"] == fact.binding_id)
            allowed: list[str] = []
            invalid: list[str] = []
            invalid_details: list[tuple[str, str, str]] = []
            if not self._is_direct_function_body(fact.assignment_node_id):
                invalid_details.append(
                    (
                        fact.assignment_node_id,
                        "PYC3403",
                        "A fixed container must be bound directly in a function body",
                    )
                )
            for occurrence in binding["occurrence_node_ids"]:
                if occurrence == fact.target_node_id:
                    allowed.append(occurrence)
                    continue
                parents = self.parents.get(occurrence, ())
                accepted = False
                rejected = False
                for parent_id, field_name in parents:
                    parent = self.index.node(parent_id)
                    if parent["kind"] == "Subscript" and field_name == "value":
                        accepted = True
                    elif parent["kind"] == "For" and field_name == "iter":
                        accepted = True
                    elif parent["kind"] == "Attribute" and field_name == "value":
                        invalid_details.append(
                            (
                                parent_id,
                                "PYC3406",
                                "Container methods and mutation are unsupported in the fixed profile",
                            )
                        )
                        rejected = True
                if accepted and not rejected:
                    allowed.append(occurrence)
                elif not accepted:
                    invalid.append(occurrence)
                    invalid_details.append(
                        (
                            occurrence,
                            "PYC3403",
                            "Container aliasing, escape, rebinding, or scalar use is unsupported",
                        )
                    )
                else:
                    invalid.append(occurrence)
            assignments = assignments_by_binding.get(fact.binding_id, ())
            if len(assignments) != 1:
                rejection = assignments[1] if len(assignments) > 1 else fact.assignment_node_id
                invalid_details.append(
                    (
                        rejection,
                        "PYC3403",
                        "A fixed container binding must be assigned exactly once",
                    )
                )
            if invalid_details:
                invalid_details.sort(key=lambda item: self._ordinal(item[0]))
                rejection_node, code, reason = invalid_details[0]
            else:
                rejection_node, code, reason = fact.rejection_node_id, fact.diagnostic_code, fact.reason
            valid = fact.valid and not invalid_details and len(assignments) == 1
            result.append(
                replace(
                    fact,
                    allowed_use_node_ids=tuple(sorted(set(allowed), key=self._ordinal)),
                    invalid_use_node_ids=tuple(sorted(set(invalid), key=self._ordinal)),
                    valid=valid,
                    diagnostic_code=None if valid else code,
                    rejection_node_id=None if valid else rejection_node,
                    reason=None if valid else reason,
                )
            )
        return tuple(sorted(result, key=lambda item: item.binding_id))

    def _accesses(
        self,
        bindings: dict[str, ContainerBindingFact],
        shapes: dict[str, ContainerShapeFact],
    ) -> tuple[ContainerAccessFact, ...]:
        result: list[ContainerAccessFact] = []
        for node in self.index.nodes.values():
            if node["kind"] != "Subscript":
                continue
            fields = node["fields"]
            base = self.index.nodes.get(fields.get("value"))
            binding = self.binding_by_occurrence.get(base["node_id"]) if base and base["kind"] == "Name" else None
            fact = bindings.get(binding["binding_id"] if binding else "")
            if not fact:
                continue
            shape = shapes[fact.literal_node_id]
            slice_id = fields.get("slice")
            if self._is_mutation_target(node["node_id"]):
                result.append(self._rejected_access(node, fact, slice_id, "PYC3406", "Container element mutation is unsupported"))
                continue
            if not shape.valid:
                result.append(self._rejected_access(node, fact, slice_id, shape.diagnostic_code or "PYC3402", shape.reason or "Invalid container shape"))
                continue
            if fact.container_kind in {"list", "tuple"}:
                index = self._signed_integer_literal(slice_id)
                if index is None:
                    result.append(self._rejected_access(node, fact, slice_id, "PYC3404", "List and tuple indices must be compile-time integer literals"))
                    continue
                offset = index if index >= 0 else fact.capacity + index
                if not 0 <= offset < fact.capacity:
                    result.append(self._rejected_access(node, fact, slice_id, "PYC3405", "Container index is outside the fixed capacity", source_index=index))
                    continue
                result.append(ContainerAccessFact(node["node_id"], fact.binding_id, fact.container_kind, slice_id, fact.element_category, offset, index, None, True, None, None))
                continue
            key = self._literal_key(slice_id)
            if key is None or key[1] is not fact.key_category:
                result.append(self._rejected_access(node, fact, slice_id, "PYC3404", "Dictionary lookup requires a literal key matching the fixed key representation"))
                continue
            key_value = key[0]
            try:
                offset = shape.key_values.index(key_value)
            except ValueError:
                result.append(self._rejected_access(node, fact, slice_id, "PYC3405", "Dictionary key is absent from the fixed literal", key_value=key_value))
                continue
            result.append(ContainerAccessFact(node["node_id"], fact.binding_id, "dict", slice_id, fact.value_category, offset, None, key_value, True, None, None))
        return tuple(sorted(result, key=lambda item: item.subscript_node_id))

    def _rejected_access(
        self,
        node: dict[str, Any],
        fact: ContainerBindingFact,
        slice_id: str | None,
        code: str,
        reason: str,
        *,
        source_index: int | None = None,
        key_value: int | str | None = None,
    ) -> ContainerAccessFact:
        return ContainerAccessFact(node["node_id"], fact.binding_id, fact.container_kind, slice_id, ValueCategory.UNKNOWN, None, source_index, key_value, False, code, reason)

    def _iterations(
        self,
        bindings: dict[str, ContainerBindingFact],
        shapes: dict[str, ContainerShapeFact],
    ) -> tuple[ContainerIterationFact, ...]:
        result: list[ContainerIterationFact] = []
        for node in self.index.nodes.values():
            if node["kind"] != "For":
                continue
            fields = node["fields"]
            iterator = self.index.nodes.get(fields.get("iter"))
            if not iterator:
                continue
            if iterator["kind"] in _LITERAL_KINDS:
                result.append(ContainerIterationFact(node["node_id"], None, _LITERAL_KINDS[iterator["kind"]], fields.get("target"), ValueCategory.UNKNOWN, 0, "unresolved", False, "PYC3407", "A container iterable must be a directly bound fixed local name"))
                continue
            if iterator["kind"] != "Name":
                continue
            binding = self.binding_by_occurrence.get(iterator["node_id"])
            fact = bindings.get(binding["binding_id"] if binding else "")
            if not fact:
                continue
            shape = shapes[fact.literal_node_id]
            target_id = fields.get("target")
            target = self.index.nodes.get(target_id)
            category = fact.key_category if fact.container_kind == "dict" else fact.element_category
            if not shape.valid:
                result.append(ContainerIterationFact(node["node_id"], fact.binding_id, fact.container_kind, target_id, ValueCategory.UNKNOWN, fact.capacity, "unresolved", False, shape.diagnostic_code, shape.reason))
            elif not target or target["kind"] != "Name" or fields.get("orelse"):
                result.append(ContainerIterationFact(node["node_id"], fact.binding_id, fact.container_kind, target_id, category, fact.capacity, "source-insertion-order", False, "PYC3407", "Container iteration requires a single-name target and no loop else"))
            else:
                result.append(ContainerIterationFact(node["node_id"], fact.binding_id, fact.container_kind, target_id, category, fact.capacity, "source-insertion-order", True, None, None))
        return tuple(sorted(result, key=lambda item: item.for_node_id))

    def _literal_key(self, node_id: str | None) -> tuple[int | str, ValueCategory] | None:
        if not node_id or node_id not in self.index.nodes:
            return None
        node = self.index.node(node_id)
        if node["kind"] == "Constant":
            value = node["fields"].get("value")
            if isinstance(value, bool):
                return None
            if isinstance(value, int) and -(2**63 - 1) <= value <= 2**63 - 1:
                return value, ValueCategory.INTEGER
            if isinstance(value, str) and "\x00" not in value:
                return value, ValueCategory.STRING
            return None
        value = self._signed_integer_literal(node_id)
        return (value, ValueCategory.INTEGER) if value is not None else None

    def _signed_integer_literal(self, node_id: str | None) -> int | None:
        if not node_id or node_id not in self.index.nodes:
            return None
        node = self.index.node(node_id)
        if node["kind"] == "Constant":
            value = node["fields"].get("value")
            if isinstance(value, int) and not isinstance(value, bool) and -(2**63 - 1) <= value <= 2**63 - 1:
                return value
            return None
        if node["kind"] != "UnaryOp":
            return None
        operator = self.index.nodes.get(node["fields"].get("op"), {}).get("kind")
        operand = self.index.nodes.get(node["fields"].get("operand"))
        if not operand or operand["kind"] != "Constant":
            return None
        value = operand["fields"].get("value")
        if not isinstance(value, int) or isinstance(value, bool) or value > 2**63 - 1:
            return None
        signed = -value if operator == "USub" else value if operator == "UAdd" else None
        return signed if signed is not None and -(2**63 - 1) <= signed <= 2**63 - 1 else None

    def _is_mutation_target(self, node_id: str) -> bool:
        for parent_id, field_name in self.parents.get(node_id, ()):
            parent = self.index.node(parent_id)
            if parent["kind"] in {"Assign", "AnnAssign", "AugAssign", "Delete"} and field_name in {"targets", "target"}:
                return True
        return False

    def _is_direct_function_body(self, node_id: str) -> bool:
        return any(
            field_name == "body" and self.index.node(parent_id)["kind"] == "FunctionDef"
            for parent_id, field_name in self.parents.get(node_id, ())
        )

    def _ordinal(self, node_id: str) -> tuple[int, str]:
        node = self.index.nodes.get(node_id, {})
        span = node.get("provenance", {}).get("source_span") or {}
        offset = (span.get("start") or {}).get("offset")
        return (offset if isinstance(offset, int) else 2**63 - 1, node_id)

    @classmethod
    def _references(cls, value: Any) -> tuple[str, ...]:
        if isinstance(value, str) and value.startswith(("py-", "syn-")):
            return (value,)
        if isinstance(value, (tuple, list)):
            return tuple(item for value_item in value for item in cls._references(value_item))
        if isinstance(value, dict):
            return tuple(item for value_item in value.values() for item in cls._references(value_item))
        return ()
