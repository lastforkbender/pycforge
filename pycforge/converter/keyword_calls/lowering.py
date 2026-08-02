"""Structured C IR staging for independently proved keyword-call bindings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from pycforge.converter.ir.c_ir import CIdentifierRef, CType

from .model import KEYWORD_CALL_LOWERING_SHAPE, KEYWORD_CALL_TABLE_ID


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _category_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value or "unknown")


def _sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple))


def _exact_permutation(
    value: Any,
    size: int,
    check_cancellation: Callable[[], None],
) -> bool:
    """Validate a bounded permutation in linear time without comparison sorting."""

    if not _sequence(value) or len(value) != size:
        return False
    seen = [False] * size
    for item in value:
        check_cancellation()
        if (
            not isinstance(item, int)
            or isinstance(item, bool)
            or item < 0
            or item >= size
            or seen[item]
        ):
            return False
        seen[item] = True
    return True


@dataclass(slots=True)
class KeywordCallLoweringServices:
    nodes: dict[str, dict[str, Any]]
    facts: dict[str, dict[str, Any]]
    expression: Callable[[dict[str, Any]], tuple[tuple[Any, ...], Any]]
    temporary: Callable[..., tuple[Any, CIdentifierRef]]
    type_from_name: Callable[[str | None], CType]
    reject: Callable[..., Any]
    check_cancellation: Callable[[], None]


class KeywordCallCIRLowerer:
    """Stage values in source order and return references in formal order."""

    def __init__(self, services: KeywordCallLoweringServices) -> None:
        self.services = services

    def has_fact(self, call_node_id: str) -> bool:
        return call_node_id in self.services.facts

    def arguments(
        self,
        node: dict[str, Any],
        signature: Any,
    ) -> tuple[tuple[Any, ...], tuple[CIdentifierRef, ...]]:
        s = self.services
        s.check_cancellation()
        if not isinstance(node, Mapping) or not isinstance(node.get("node_id"), str):
            s.reject("PYC2912", "Keyword-call node evidence is malformed", node)
        call_node_id = node.get("node_id")
        if call_node_id not in s.facts:
            s.reject(
                "PYC2910",
                "Keyword call lacks an exact binding fact",
                node,
            )
        fact = s.facts[call_node_id]
        if not isinstance(fact, Mapping):
            s.reject("PYC2912", "Keyword-call binding fact is malformed", node)
        rejection_node = s.nodes.get(fact.get("rejection_node_id"), node)
        if fact.get("supported") is False:
            if (
                not isinstance(fact.get("diagnostic_code"), str)
                or not isinstance(fact.get("reason"), str)
                or not isinstance(fact.get("rejection_node_id"), str)
                or not isinstance(rejection_node, Mapping)
            ):
                s.reject("PYC2912", "Keyword-call rejection fact is malformed", node)
            s.reject(
                fact.get("diagnostic_code") or "PYC2910",
                fact.get("reason") or "Unsupported keyword-call binding",
                rejection_node,
            )
        if fact.get("supported") is not True:
            s.reject("PYC2912", "Keyword-call support state is malformed", node)
        parameters_value = _value(signature, "parameters")
        if not _sequence(parameters_value):
            s.reject("PYC2912", "Keyword-call signature parameters are malformed", node)
        parameters: Sequence[Any] = tuple(parameters_value)
        sequence_fields = (
            "argument_bindings",
            "source_argument_node_ids",
            "evaluation_order",
            "source_to_parameter_ordinals",
            "parameter_argument_node_ids",
            "parameter_to_source_ordinals",
            "positional_argument_node_ids",
            "keyword_node_ids",
            "keyword_value_node_ids",
        )
        if any(not _sequence(fact.get(name)) for name in sequence_fields):
            s.reject("PYC2912", "Keyword-call binding sequences are malformed", node)
        bindings = tuple(fact["argument_bindings"])
        source_ids = tuple(fact["source_argument_node_ids"])
        evaluation_order = tuple(fact["evaluation_order"])
        source_to_parameter = tuple(fact["source_to_parameter_ordinals"])
        parameter_argument_ids = tuple(fact["parameter_argument_node_ids"])
        parameter_to_source = tuple(fact["parameter_to_source_ordinals"])
        expected_call_fields = node.get("fields")
        if (
            not isinstance(expected_call_fields, Mapping)
            or not _sequence(expected_call_fields.get("args"))
            or not _sequence(expected_call_fields.get("keywords"))
        ):
            s.reject("PYC2912", "Keyword-call node fields are malformed", node)
        expected_keyword_ids = tuple(expected_call_fields["keywords"])
        expected_keyword_values: list[str] = []
        for keyword_id in expected_keyword_ids:
            keyword = s.nodes.get(keyword_id)
            keyword_fields = keyword.get("fields") if isinstance(keyword, Mapping) else None
            if (
                not isinstance(keyword_id, str)
                or not isinstance(keyword, Mapping)
                or keyword.get("kind") != "keyword"
                or not isinstance(keyword_fields, Mapping)
                or not isinstance(keyword_fields.get("value"), str)
            ):
                s.reject("PYC2912", "Keyword-call keyword evidence is malformed", node)
            expected_keyword_values.append(keyword_fields["value"])
        if (
            fact.get("call_node_id") != node.get("node_id")
            or fact.get("callee_node_id") != expected_call_fields.get("func")
            or fact.get("lowering_shape") != KEYWORD_CALL_LOWERING_SHAPE
            or fact.get("arguments_evaluated_once") is not True
            or fact.get("parameter_coverage_exact") is not True
            or fact.get("allocation_model") != "none"
            or fact.get("cleanup_model") != "none"
            or fact.get("runtime_binding_failure") != "proved-absent"
            or tuple(fact.get("positional_argument_node_ids", ()))
            != tuple(expected_call_fields.get("args", ()))
            or tuple(fact.get("keyword_node_ids", ())) != expected_keyword_ids
            or tuple(fact.get("keyword_value_node_ids", ())) != tuple(expected_keyword_values)
            or source_ids != evaluation_order
            or len(bindings) != len(source_ids)
            or len(parameters) != len(parameter_argument_ids)
            or len(parameters) != len(parameter_to_source)
            or len(parameters) != len(source_ids)
            or not _exact_permutation(
                source_to_parameter,
                len(parameters),
                s.check_cancellation,
            )
            or not _exact_permutation(
                parameter_to_source,
                len(parameters),
                s.check_cancellation,
            )
        ):
            s.reject("PYC2912", "Keyword-call binding fact is incomplete or inconsistent", node)

        # Validate the whole permutation before lowering any value so tampered
        # evidence cannot publish a partial C IR prelude.
        for source_ordinal, binding in enumerate(bindings):
            s.check_cancellation()
            if not isinstance(binding, Mapping):
                s.reject("PYC2912", "Keyword-call argument binding is malformed", node)
            parameter_ordinal = binding.get("parameter_ordinal")
            argument_id = binding.get("source_argument_node_id")
            keyword_id = binding.get("keyword_node_id")
            if (
                binding.get("source_ordinal") != source_ordinal
                or argument_id != source_ids[source_ordinal]
                or parameter_ordinal != source_to_parameter[source_ordinal]
                or not isinstance(parameter_ordinal, int)
                or not 0 <= parameter_ordinal < len(parameters)
                or parameter_argument_ids[parameter_ordinal] != argument_id
                or parameter_to_source[parameter_ordinal] != source_ordinal
                or argument_id not in s.nodes
                or s.nodes[argument_id].get("kind") == "Starred"
                or (
                    keyword_id is not None
                    and (
                        keyword_id not in s.nodes
                        or s.nodes[keyword_id].get("kind") != "keyword"
                        or s.nodes[keyword_id].get("fields", {}).get("value") != argument_id
                        or s.nodes[keyword_id].get("fields", {}).get("arg")
                        != binding.get("keyword_name")
                    )
                )
                or binding.get("parameter_node_id")
                != _value(parameters[parameter_ordinal], "parameter_node_id")
                or binding.get("parameter_name")
                != _value(parameters[parameter_ordinal], "source_name")
                or binding.get("expected_category")
                != _category_value(_value(parameters[parameter_ordinal], "category"))
            ):
                s.reject("PYC2912", "Keyword-call argument permutation is inconsistent", node)

        prelude: list[Any] = []
        references: list[CIdentifierRef | None] = [None] * len(parameters)
        for source_ordinal, binding in enumerate(bindings):
            s.check_cancellation()
            argument_id = binding["source_argument_node_id"]
            parameter_ordinal = binding["parameter_ordinal"]
            expression_prelude, expression = s.expression(s.nodes[argument_id])
            prelude.extend(expression_prelude)
            keyword_id = binding.get("keyword_node_id")
            origins = tuple(
                item
                for item in (argument_id, keyword_id, node["node_id"])
                if isinstance(item, str)
            )
            declaration, reference = s.temporary(
                "arg",
                node,
                source_ordinal,
                s.type_from_name(_value(parameters[parameter_ordinal], "c_type")),
                expression,
                origins,
            )
            if not isinstance(reference, CIdentifierRef):
                s.reject("PYC2912", "Keyword-call staging did not produce a pure reference", node)
            prelude.append(declaration)
            references[parameter_ordinal] = reference
        s.check_cancellation()
        if any(item is None for item in references):
            s.reject("PYC2912", "Keyword-call staging omitted a formal parameter", node)
        return tuple(prelude), tuple(references)  # type: ignore[arg-type]


def bind_keyword_call_lowerer(owner: Any) -> KeywordCallCIRLowerer:
    """Bind the feature lowerer without adding keyword mechanics centrally."""

    return KeywordCallCIRLowerer(
        KeywordCallLoweringServices(
            nodes=owner.nodes,
            facts=owner._optional_values(KEYWORD_CALL_TABLE_ID, "call_node_id"),
            expression=owner._expression,
            temporary=owner._temporary,
            type_from_name=owner._type_from_name,
            reject=owner._reject,
            check_cancellation=owner._check_cancel,
        )
    )


__all__ = [
    "KeywordCallCIRLowerer",
    "KeywordCallLoweringServices",
    "bind_keyword_call_lowerer",
]
