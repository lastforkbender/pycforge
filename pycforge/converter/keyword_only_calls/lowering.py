"""Structured C IR staging for proved required keyword-only calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from pycforge.converter.ir.c_ir import CIdentifierRef, CType

from .model import (
    KEYWORD_ONLY_CALL_LOWERING_SHAPE,
    KEYWORD_ONLY_CALL_TABLE_ID,
)


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _category(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value or "unknown")


def _sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple))


def lowering_supports_parameter_shape(
    fields: Any,
    *,
    allow_required_keyword_only: bool,
) -> bool:
    """Recognize the exact declaration shape accepted by the C lowering boundary."""

    if not isinstance(fields, Mapping):
        return False
    keyword_only = fields.get("kwonlyargs")
    keyword_defaults = fields.get("kw_defaults")
    if (
        not _sequence(fields.get("posonlyargs"))
        or not _sequence(fields.get("args"))
        or not _sequence(keyword_only)
        or not _sequence(keyword_defaults)
        or fields.get("vararg")
        or fields.get("kwarg")
        or fields.get("defaults")
    ):
        return False
    if not keyword_only:
        return not keyword_defaults
    return (
        allow_required_keyword_only
        and len(keyword_defaults) == len(keyword_only)
        and all(item is None for item in keyword_defaults)
    )


def lowered_parameter_node_ids(
    fields: Mapping[str, Any],
    *,
    include_required_keyword_only: bool,
) -> tuple[str, ...]:
    result = tuple(fields.get("posonlyargs", ())) + tuple(fields.get("args", ()))
    if include_required_keyword_only:
        result += tuple(fields.get("kwonlyargs", ()))
    return result


def _exact_permutation(
    value: Any,
    size: int,
    check_cancellation: Callable[[], None],
) -> bool:
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
class KeywordOnlyCallLoweringServices:
    nodes: dict[str, dict[str, Any]]
    facts: dict[str, dict[str, Any]]
    expression: Callable[[dict[str, Any]], tuple[tuple[Any, ...], Any]]
    temporary: Callable[..., tuple[Any, CIdentifierRef]]
    type_from_name: Callable[[str | None], CType]
    reject: Callable[..., Any]
    check_cancellation: Callable[[], None]


class KeywordOnlyCallCIRLowerer:
    """Stage actuals in source order and return references in formal order."""

    def __init__(self, services: KeywordOnlyCallLoweringServices) -> None:
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
            s.reject("PYC2912", "Keyword-only call node is malformed", node)
        call_id = node["node_id"]
        fact = s.facts.get(call_id)
        if not isinstance(fact, Mapping):
            s.reject(
                "PYC2910",
                "Required keyword-only call lacks an exact binding fact",
                node,
            )
        rejection = s.nodes.get(fact.get("rejection_node_id"), node)
        if fact.get("supported") is False:
            if (
                not isinstance(fact.get("diagnostic_code"), str)
                or not isinstance(fact.get("reason"), str)
                or not isinstance(fact.get("rejection_node_id"), str)
                or not isinstance(rejection, Mapping)
            ):
                s.reject("PYC2912", "Keyword-only rejection fact is malformed", node)
            s.reject(
                fact["diagnostic_code"],
                fact["reason"],
                rejection,
            )
        if fact.get("supported") is not True:
            s.reject("PYC2912", "Keyword-only support state is malformed", node)
        parameters_value = _value(signature, "parameters")
        if not _sequence(parameters_value):
            s.reject("PYC2912", "Keyword-only signature is malformed", node)
        parameters: Sequence[Any] = tuple(parameters_value)
        sequence_fields = (
            "parameter_node_ids",
            "parameter_names",
            "parameter_kinds",
            "parameter_categories",
            "required_keyword_only_parameter_node_ids",
            "required_keyword_only_parameter_names",
            "required_keyword_only_parameter_categories",
            "argument_bindings",
            "source_argument_node_ids",
            "source_argument_categories",
            "evaluation_order",
            "source_to_parameter_ordinals",
            "parameter_argument_node_ids",
            "parameter_to_source_ordinals",
            "positional_argument_node_ids",
            "keyword_node_ids",
            "keyword_names",
            "keyword_value_node_ids",
        )
        if any(not _sequence(fact.get(name)) for name in sequence_fields):
            s.reject("PYC2912", "Keyword-only binding sequences are malformed", node)
        bindings = tuple(fact["argument_bindings"])
        source_ids = tuple(fact["source_argument_node_ids"])
        source_categories = tuple(fact["source_argument_categories"])
        source_to_parameter = tuple(fact["source_to_parameter_ordinals"])
        parameter_arguments = tuple(fact["parameter_argument_node_ids"])
        parameter_to_source = tuple(fact["parameter_to_source_ordinals"])
        parameter_kinds = tuple(fact["parameter_kinds"])
        call_fields = node.get("fields")
        if (
            not isinstance(call_fields, Mapping)
            or not _sequence(call_fields.get("args"))
            or not _sequence(call_fields.get("keywords"))
        ):
            s.reject("PYC2912", "Keyword-only call fields are malformed", node)
        keyword_ids = tuple(call_fields["keywords"])
        keyword_names: list[str | None] = []
        keyword_values: list[str] = []
        for keyword_id in keyword_ids:
            keyword = s.nodes.get(keyword_id)
            fields = keyword.get("fields") if isinstance(keyword, Mapping) else None
            if (
                not isinstance(keyword_id, str)
                or not isinstance(keyword, Mapping)
                or keyword.get("kind") != "keyword"
                or not isinstance(fields, Mapping)
                or not isinstance(fields.get("value"), str)
            ):
                s.reject("PYC2912", "Keyword-only keyword evidence is malformed", node)
            keyword_names.append(fields.get("arg"))
            keyword_values.append(fields["value"])
        positional_only_count = fact.get("positional_only_parameter_count")
        positional_or_keyword_count = fact.get(
            "positional_or_keyword_parameter_count"
        )
        keyword_only_count = fact.get("keyword_only_parameter_count")
        if (
            not isinstance(positional_only_count, int)
            or not isinstance(positional_or_keyword_count, int)
            or not isinstance(keyword_only_count, int)
            or positional_only_count < 0
            or positional_or_keyword_count < 0
            or keyword_only_count <= 0
            or positional_only_count
            + positional_or_keyword_count
            + keyword_only_count
            != len(parameters)
            or fact.get("call_node_id") != call_id
            or fact.get("callee_node_id") != call_fields.get("func")
            or fact.get("lowering_shape") != KEYWORD_ONLY_CALL_LOWERING_SHAPE
            or fact.get("arguments_evaluated_once") is not True
            or fact.get("parameter_coverage_exact") is not True
            or fact.get("keyword_only_coverage_exact") is not True
            or fact.get("allocation_model") != "none"
            or fact.get("cleanup_model") != "none"
            or fact.get("runtime_binding_failure") != "proved-absent"
            or tuple(fact["positional_argument_node_ids"])
            != tuple(call_fields["args"])
            or tuple(fact["keyword_node_ids"]) != keyword_ids
            or tuple(fact["keyword_names"]) != tuple(keyword_names)
            or tuple(fact["keyword_value_node_ids"]) != tuple(keyword_values)
            or source_ids != tuple(fact["evaluation_order"])
            or len(bindings) != len(parameters)
            or len(source_ids) != len(parameters)
            or len(source_categories) != len(parameters)
            or len(parameter_arguments) != len(parameters)
            or len(parameter_to_source) != len(parameters)
            or tuple(
                parameter_kinds[
                    positional_only_count + positional_or_keyword_count :
                ]
            )
            != ("keyword-only",) * keyword_only_count
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
            s.reject(
                "PYC2912",
                "Keyword-only binding fact is incomplete or inconsistent",
                node,
            )

        for source_ordinal, binding in enumerate(bindings):
            s.check_cancellation()
            if not isinstance(binding, Mapping):
                s.reject("PYC2912", "Keyword-only argument binding is malformed", node)
            parameter_ordinal = binding.get("parameter_ordinal")
            argument_id = binding.get("source_argument_node_id")
            keyword_id = binding.get("keyword_node_id")
            if (
                binding.get("source_ordinal") != source_ordinal
                or argument_id != source_ids[source_ordinal]
                or binding.get("category") != source_categories[source_ordinal]
                or parameter_ordinal != source_to_parameter[source_ordinal]
                or not isinstance(parameter_ordinal, int)
                or not 0 <= parameter_ordinal < len(parameters)
                or parameter_arguments[parameter_ordinal] != argument_id
                or parameter_to_source[parameter_ordinal] != source_ordinal
                or argument_id not in s.nodes
                or s.nodes[argument_id].get("kind") == "Starred"
                or binding.get("parameter_node_id")
                != _value(parameters[parameter_ordinal], "parameter_node_id")
                or binding.get("parameter_name")
                != _value(parameters[parameter_ordinal], "source_name")
                or binding.get("parameter_kind")
                != parameter_kinds[parameter_ordinal]
                or binding.get("expected_category")
                != _category(_value(parameters[parameter_ordinal], "category"))
            ):
                s.reject(
                    "PYC2912",
                    "Keyword-only argument permutation is inconsistent",
                    node,
                )
            if keyword_id is not None:
                keyword = s.nodes.get(keyword_id)
                if (
                    not isinstance(keyword, Mapping)
                    or keyword.get("kind") != "keyword"
                    or keyword.get("fields", {}).get("value") != argument_id
                    or keyword.get("fields", {}).get("arg")
                    != binding.get("keyword_name")
                ):
                    s.reject(
                        "PYC2912",
                        "Keyword-only named binding is inconsistent",
                        node,
                    )
            if parameter_kinds[parameter_ordinal] == "keyword-only" and keyword_id is None:
                s.reject(
                    "PYC2912",
                    "Keyword-only formal was not supplied by explicit keyword",
                    node,
                )

        prelude: list[Any] = []
        references: list[CIdentifierRef | None] = [None] * len(parameters)
        for source_ordinal, binding in enumerate(bindings):
            s.check_cancellation()
            argument_id = binding["source_argument_node_id"]
            parameter_ordinal = binding["parameter_ordinal"]
            expression_prelude, expression = s.expression(s.nodes[argument_id])
            prelude.extend(expression_prelude)
            origins = tuple(
                item
                for item in (
                    argument_id,
                    binding.get("keyword_node_id"),
                    call_id,
                )
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
                s.reject(
                    "PYC2912",
                    "Keyword-only staging did not produce a pure reference",
                    node,
                )
            prelude.append(declaration)
            references[parameter_ordinal] = reference
        s.check_cancellation()
        if any(item is None for item in references):
            s.reject("PYC2912", "Keyword-only staging omitted a formal", node)
        return tuple(prelude), tuple(references)  # type: ignore[arg-type]


def bind_keyword_only_call_lowerer(owner: Any) -> KeywordOnlyCallCIRLowerer:
    return KeywordOnlyCallCIRLowerer(
        KeywordOnlyCallLoweringServices(
            nodes=owner.nodes,
            facts=owner._optional_values(
                KEYWORD_ONLY_CALL_TABLE_ID,
                "call_node_id",
            ),
            expression=owner._expression,
            temporary=owner._temporary,
            type_from_name=owner._type_from_name,
            reject=owner._reject,
            check_cancellation=owner._check_cancel,
        )
    )


__all__ = [
    "KeywordOnlyCallCIRLowerer",
    "KeywordOnlyCallLoweringServices",
    "bind_keyword_only_call_lowerer",
    "lowered_parameter_node_ids",
    "lowering_supports_parameter_shape",
]
