"""Closed deterministic analysis for required keyword-only direct calls."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from pycforge.converter.analysis.model import ValueCategory

from .model import (
    KEYWORD_ONLY_CALL_LOWERING_SHAPE,
    KeywordOnlyArgumentBindingFact,
    KeywordOnlyCallAnalysis,
    KeywordOnlyCallAnalysisCanceled,
    KeywordOnlyCallAnalysisError,
    KeywordOnlyCallBindingFact,
    KeywordOnlyCallRejection,
    keyword_only_call_binding_id,
)


def _sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple))


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _category(value: ValueCategory | str | None) -> str:
    return value.value if isinstance(value, ValueCategory) else str(value or "unknown")


def _source_span(item: Any) -> dict[str, object] | None:
    if not isinstance(item, Mapping):
        return None
    provenance = item.get("provenance")
    span = provenance.get("source_span") if isinstance(provenance, Mapping) else None
    return span if isinstance(span, dict) else None


class KeywordOnlyCallAnalyzer:
    """Classify direct calls to exact required-keyword-only signatures."""

    def __init__(
        self,
        module: dict[str, Any],
        *,
        bindings: Sequence[Any],
        signatures: Sequence[Any],
        categories: Mapping[str, ValueCategory | str],
        cancellation: Any,
        ignored_call_node_ids: frozenset[str] = frozenset(),
    ) -> None:
        if not isinstance(module, Mapping):
            raise KeywordOnlyCallAnalysisError(
                "PYC2912",
                "Keyword-only call analysis requires a normalized module mapping",
                "",
                None,
            )
        self.module = module
        self.cancellation = cancellation
        self.ignored_call_node_ids = ignored_call_node_ids
        self.nodes: dict[str, dict[str, Any]] = {}
        self.node_order: dict[str, int] = {}
        node_values = module.get("nodes")
        if not _sequence(node_values):
            self._malformed(
                "Keyword-only call analysis requires a normalized node sequence",
                module,
            )
        self.node_values = tuple(node_values)
        for ordinal, node in enumerate(self.node_values):
            self._check_cancellation()
            node_id = node.get("node_id") if isinstance(node, Mapping) else None
            if not isinstance(node_id, str) or not node_id or node_id in self.nodes:
                raise KeywordOnlyCallAnalysisError(
                    "PYC2912",
                    "Keyword-only analysis requires unique normalized node identities",
                    str(node_id or module.get("root_node_id") or ""),
                    _source_span(node),
                )
            self.nodes[node_id] = node
            self.node_order[node_id] = ordinal
        if not isinstance(categories, Mapping):
            self._malformed("Keyword-only call categories are malformed", module)
        self.categories = {key: _category(value) for key, value in categories.items()}
        if any(not isinstance(key, str) for key in self.categories):
            self._malformed("Keyword-only category identities are malformed", module)
        if not _sequence(bindings):
            self._malformed("Keyword-only binding evidence is malformed", module)
        self.binding_by_occurrence: dict[str, Any] = {}
        for binding in bindings:
            self._check_cancellation()
            binding_id = _value(binding, "binding_id")
            occurrences = _value(binding, "occurrence_node_ids")
            if (
                not isinstance(binding_id, str)
                or not binding_id
                or not _sequence(occurrences)
                or any(not isinstance(item, str) for item in occurrences)
            ):
                self._malformed("Keyword-only binding evidence is malformed", module)
            for occurrence in occurrences:
                existing = self.binding_by_occurrence.get(occurrence)
                if existing is not None and _value(existing, "binding_id") != binding_id:
                    self._malformed(
                        "Keyword-only occurrence has conflicting binding evidence",
                        self.nodes.get(occurrence, module),
                    )
                self.binding_by_occurrence[occurrence] = binding
        if not _sequence(signatures):
            self._malformed("Keyword-only signature evidence is malformed", module)
        self.signature_by_binding: dict[str, Any] = {}
        for signature in signatures:
            self._check_cancellation()
            binding_id = _value(signature, "binding_id")
            parameters = _value(signature, "parameters")
            if (
                not isinstance(binding_id, str)
                or not binding_id
                or not _sequence(parameters)
                or binding_id in self.signature_by_binding
            ):
                self._malformed("Keyword-only signature evidence is malformed", module)
            self.signature_by_binding[binding_id] = signature

    def analyze(self) -> KeywordOnlyCallAnalysis:
        facts: list[KeywordOnlyCallBindingFact] = []
        rejections: list[KeywordOnlyCallRejection] = []
        for node in self.node_values:
            self._check_cancellation()
            if not self._candidate(node):
                continue
            fact = self._fact(node)
            facts.append(fact)
            if not fact.supported:
                rejection_node = self.nodes.get(
                    fact.rejection_node_id or fact.call_node_id,
                    node,
                )
                rejections.append(
                    KeywordOnlyCallRejection(
                        fact.call_node_id,
                        fact.diagnostic_code or "PYC2910",
                        fact.reason or "Unsupported required keyword-only call",
                        fact.rejection_node_id or fact.call_node_id,
                        _source_span(rejection_node),
                    )
                )
        return KeywordOnlyCallAnalysis(tuple(facts), tuple(rejections))

    def _candidate(self, node: dict[str, Any]) -> bool:
        if (
            node.get("kind") != "Call"
            or node.get("node_id") in self.ignored_call_node_ids
        ):
            return False
        fields = node.get("fields")
        if (
            not isinstance(fields, Mapping)
            or not _sequence(fields.get("args"))
            or not _sequence(fields.get("keywords"))
        ):
            self._malformed("Call has malformed normalized argument evidence", node)
        callee_id = fields.get("func")
        if not isinstance(callee_id, str):
            self._malformed("Call callee identity is malformed", node)
        callee = self.nodes.get(callee_id)
        if not callee or callee.get("kind") != "Name":
            return False
        binding = self.binding_by_occurrence.get(callee_id)
        signature = self.signature_by_binding.get(_value(binding, "binding_id"))
        if signature is None or _value(signature, "eligible") is not True:
            return False
        target = self.nodes.get(str(_value(signature, "function_node_id", "")))
        if not target or target.get("kind") != "FunctionDef":
            return False
        target_fields = target.get("fields")
        args = (
            self.nodes.get(target_fields.get("args"))
            if isinstance(target_fields, Mapping)
            else None
        )
        argument_fields = args.get("fields") if isinstance(args, Mapping) else None
        return bool(
            isinstance(argument_fields, Mapping)
            and _sequence(argument_fields.get("kwonlyargs"))
            and len(argument_fields["kwonlyargs"]) > 0
            and _sequence(argument_fields.get("kw_defaults"))
            and len(argument_fields["kw_defaults"])
            == len(argument_fields["kwonlyargs"])
            and all(item is None for item in argument_fields["kw_defaults"])
            and _sequence(argument_fields.get("defaults"))
            and not argument_fields["defaults"]
            and not argument_fields.get("vararg")
            and not argument_fields.get("kwarg")
        )

    def _fact(self, call: dict[str, Any]) -> KeywordOnlyCallBindingFact:
        self._check_cancellation()
        fields = call.get("fields")
        if not isinstance(fields, Mapping):
            self._malformed("Call fields are malformed", call)
        call_id = call["node_id"]
        callee_id = fields.get("func")
        if not isinstance(callee_id, str):
            self._malformed("Call callee identity is malformed", call)
        binding = self.binding_by_occurrence[callee_id]
        target_binding_id = str(_value(binding, "binding_id"))
        signature = self.signature_by_binding[target_binding_id]
        target_function_id = str(_value(signature, "function_node_id"))
        target = self.nodes.get(target_function_id)
        if not target or target.get("kind") != "FunctionDef":
            self._error(
                "PYC2912",
                "Exact keyword-only binding requires the normalized target function",
                call,
            )
        target_fields = target.get("fields")
        if not isinstance(target_fields, Mapping):
            self._malformed("Target function fields are malformed", target)
        arguments_node = self.nodes.get(target_fields.get("args"))
        argument_fields = (
            arguments_node.get("fields")
            if isinstance(arguments_node, Mapping)
            else None
        )
        if not isinstance(argument_fields, Mapping):
            self._error(
                "PYC2912",
                "Exact keyword-only binding requires normalized parameter evidence",
                target,
            )
        for name in (
            "posonlyargs",
            "args",
            "kwonlyargs",
            "kw_defaults",
            "defaults",
        ):
            if not _sequence(argument_fields.get(name)):
                self._malformed(
                    f"Normalized keyword-only {name} evidence is malformed",
                    arguments_node,
                )
        posonly_ids = tuple(argument_fields["posonlyargs"])
        positional_or_keyword_ids = tuple(argument_fields["args"])
        keyword_only_ids = tuple(argument_fields["kwonlyargs"])
        if (
            not keyword_only_ids
            or len(argument_fields["kw_defaults"]) != len(keyword_only_ids)
            or any(item is not None for item in argument_fields["kw_defaults"])
            or argument_fields["defaults"]
            or argument_fields.get("vararg")
            or argument_fields.get("kwarg")
        ):
            self._error(
                "PYC2911",
                "Keyword-only profile requires one or more required keyword-only "
                "parameters and forbids defaults and variadics",
                target,
            )
        formal_ids = posonly_ids + positional_or_keyword_ids + keyword_only_ids
        parameters_value = _value(signature, "parameters")
        if not _sequence(parameters_value):
            self._malformed("Eligible target signature parameters are malformed", target)
        parameters = tuple(parameters_value)
        parameter_node_ids = tuple(
            str(_value(item, "parameter_node_id", "")) for item in parameters
        )
        parameter_names = tuple(
            str(_value(item, "source_name", "")) for item in parameters
        )
        parameter_categories = tuple(
            _category(_value(item, "category")) for item in parameters
        )
        parameter_kinds = (
            ("positional-only",) * len(posonly_ids)
            + ("positional-or-keyword",) * len(positional_or_keyword_ids)
            + ("keyword-only",) * len(keyword_only_ids)
        )
        if (
            parameter_node_ids != formal_ids
            or any(not value for value in parameter_names)
            or len(parameter_names) != len(set(parameter_names))
            or any(value not in self.nodes for value in parameter_node_ids)
        ):
            self._error(
                "PYC2912",
                "Eligible target signature has incomplete keyword-only evidence",
                target,
            )

        positional_ids = tuple(fields.get("args", ()))
        keyword_ids = tuple(fields.get("keywords", ()))
        if any(not isinstance(item, str) for item in (*positional_ids, *keyword_ids)):
            self._malformed("Call argument identities are malformed", call)
        keyword_nodes: list[dict[str, Any]] = []
        for keyword_id in keyword_ids:
            self._check_cancellation()
            keyword = self.nodes.get(keyword_id)
            keyword_fields = keyword.get("fields") if isinstance(keyword, Mapping) else None
            if not keyword or keyword.get("kind") != "keyword" or not isinstance(
                keyword_fields,
                Mapping,
            ):
                self._error(
                    "PYC2912",
                    "Call contains malformed normalized keyword evidence",
                    call,
                )
            value_id = keyword_fields.get("value")
            if not isinstance(value_id, str) or value_id not in self.nodes:
                self._error(
                    "PYC2912",
                    "Call keyword has no normalized value expression",
                    keyword,
                )
            keyword_nodes.append(keyword)

        positional_entries: list[dict[str, Any]] = []
        for position, argument_id in enumerate(positional_ids):
            self._check_cancellation()
            if argument_id not in self.nodes:
                self._error("PYC2912", "Call argument node is absent", call)
            positional_entries.append(
                {
                    "entry_kind": "positional",
                    "list_ordinal": position,
                    "source_argument_node_id": argument_id,
                    "keyword_node_id": None,
                    "keyword_name": None,
                    "order_node_id": argument_id,
                }
            )
        keyword_entries = [
            {
                "entry_kind": "keyword",
                "list_ordinal": position,
                "source_argument_node_id": keyword["fields"]["value"],
                "keyword_node_id": keyword["node_id"],
                "keyword_name": keyword["fields"].get("arg"),
                "order_node_id": keyword["node_id"],
            }
            for position, keyword in enumerate(keyword_nodes)
        ]
        source_entries = self._merge_source_entries(
            positional_entries,
            keyword_entries,
        )
        for source_ordinal, entry in enumerate(source_entries):
            entry["source_ordinal"] = source_ordinal
        entry_by_position = {
            (item["entry_kind"], item["list_ordinal"]): item
            for item in source_entries
        }

        positional_capacity = len(posonly_ids) + len(positional_or_keyword_ids)
        parameter_by_name = {
            name: ordinal
            for ordinal, name in enumerate(parameter_names)
            if ordinal >= len(posonly_ids)
        }
        parameter_argument_ids: list[str | None] = [None] * len(parameters)
        parameter_source_ordinals: list[int | None] = [None] * len(parameters)
        source_parameter_ordinals: dict[tuple[str, int], int | None] = {}
        binding_problems: list[tuple[int, str, str]] = []
        unpacking: list[tuple[int, str]] = []
        excess: list[tuple[int, str]] = []

        saw_starred = False
        for position, argument_id in enumerate(positional_ids):
            self._check_cancellation()
            entry = entry_by_position[("positional", position)]
            argument = self.nodes[argument_id]
            if argument.get("kind") == "Starred":
                saw_starred = True
                source_parameter_ordinals[("positional", position)] = None
                unpacking.append((entry["source_ordinal"], argument_id))
                continue
            if saw_starred:
                source_parameter_ordinals[("positional", position)] = None
                continue
            if position >= positional_capacity:
                source_parameter_ordinals[("positional", position)] = None
                excess.append((entry["source_ordinal"], argument_id))
                continue
            source_parameter_ordinals[("positional", position)] = position
            parameter_argument_ids[position] = argument_id
            parameter_source_ordinals[position] = entry["source_ordinal"]

        all_parameter_names = {
            name: ordinal for ordinal, name in enumerate(parameter_names)
        }
        for position, keyword in enumerate(keyword_nodes):
            self._check_cancellation()
            entry = entry_by_position[("keyword", position)]
            keyword_id = keyword["node_id"]
            name = keyword["fields"].get("arg")
            if name is None:
                source_parameter_ordinals[("keyword", position)] = None
                unpacking.append((entry["source_ordinal"], keyword_id))
                continue
            parameter_ordinal = parameter_by_name.get(name)
            if parameter_ordinal is None:
                source_parameter_ordinals[("keyword", position)] = None
                reason = (
                    f"Positional-only parameter cannot be bound by keyword: {name}"
                    if name in all_parameter_names
                    else f"Unknown keyword argument: {name}"
                )
                binding_problems.append((entry["source_ordinal"], keyword_id, reason))
                continue
            source_parameter_ordinals[("keyword", position)] = parameter_ordinal
            if parameter_argument_ids[parameter_ordinal] is not None:
                prior_source = parameter_source_ordinals[parameter_ordinal]
                prior_entry = (
                    source_entries[prior_source]
                    if isinstance(prior_source, int)
                    and 0 <= prior_source < len(source_entries)
                    else None
                )
                reason = (
                    f"Keyword argument duplicates a positionally bound parameter: {name}"
                    if prior_entry and prior_entry["entry_kind"] == "positional"
                    else f"Duplicate keyword argument: {name}"
                )
                binding_problems.append((entry["source_ordinal"], keyword_id, reason))
                continue
            parameter_argument_ids[parameter_ordinal] = keyword["fields"]["value"]
            parameter_source_ordinals[parameter_ordinal] = entry["source_ordinal"]

        argument_bindings: list[KeywordOnlyArgumentBindingFact] = []
        for entry in source_entries:
            self._check_cancellation()
            ordinal = source_parameter_ordinals.get(
                (entry["entry_kind"], entry["list_ordinal"])
            )
            valid_ordinal = isinstance(ordinal, int) and 0 <= ordinal < len(parameters)
            argument_id = entry["source_argument_node_id"]
            argument_bindings.append(
                KeywordOnlyArgumentBindingFact(
                    argument_id,
                    entry["keyword_node_id"],
                    entry["keyword_name"],
                    entry["source_ordinal"],
                    parameter_node_ids[ordinal] if valid_ordinal else None,
                    parameter_names[ordinal] if valid_ordinal else None,
                    parameter_kinds[ordinal] if valid_ordinal else None,
                    ordinal,
                    self.categories.get(argument_id, "unknown"),
                    parameter_categories[ordinal] if valid_ordinal else None,
                )
            )

        missing_ordinals = [
            ordinal
            for ordinal, argument_id in enumerate(parameter_argument_ids)
            if argument_id is None
        ]
        missing = [parameter_names[ordinal] for ordinal in missing_ordinals]
        mismatches = [
            item
            for item in argument_bindings
            if item.parameter_ordinal is not None
            and item.expected_category is not None
            and item.category != item.expected_category
            and parameter_source_ordinals[item.parameter_ordinal]
            == item.source_ordinal
        ]
        keyword_only_coverage_exact = all(
            parameter_argument_ids[ordinal] is not None
            for ordinal in range(positional_capacity, len(parameters))
        )
        parameter_coverage_exact = bool(
            not unpacking
            and not excess
            and not binding_problems
            and not missing
            and all(value is not None for value in parameter_argument_ids)
            and len(source_entries) == len(parameters)
        )

        code: str | None = None
        reason: str | None = None
        rejection_node_id: str | None = None
        if unpacking:
            _, rejection_node_id = min(unpacking, key=lambda item: item[0])
            code = "PYC2910"
            reason = (
                "Starred and unpacked arguments are unsupported by the exact "
                "required keyword-only profile"
            )
        elif excess:
            _, rejection_node_id = min(excess, key=lambda item: item[0])
            code, reason = "PYC2904", (
                "Positional argument count exceeds the positional portion of "
                "the target signature"
            )
        elif binding_problems:
            _, rejection_node_id, reason = min(
                binding_problems,
                key=lambda item: item[0],
            )
            code = "PYC2912"
        elif missing:
            rejection_node_id = call_id
            code, reason = "PYC2904", (
                "Every target parameter must be supplied exactly once; missing: "
                + ", ".join(missing)
            )
        elif mismatches:
            mismatch = mismatches[0]
            rejection_node_id = (
                mismatch.keyword_node_id or mismatch.source_argument_node_id
            )
            code, reason = "PYC2905", (
                "Argument representation does not match parameter "
                f"{mismatch.parameter_name}"
            )
        supported = (
            code is None
            and parameter_coverage_exact
            and keyword_only_coverage_exact
        )
        if code is None and not supported:
            code, reason, rejection_node_id = (
                "PYC2904",
                "Arguments do not exactly cover the required keyword-only signature",
                call_id,
            )

        source_argument_ids = tuple(
            item.source_argument_node_id for item in argument_bindings
        )
        source_categories = tuple(item.category for item in argument_bindings)
        return KeywordOnlyCallBindingFact(
            keyword_only_call_binding_id(call_id, target_binding_id),
            call_id,
            callee_id,
            target_function_id,
            target_binding_id,
            str(_value(signature, "source_name", target_fields.get("name", ""))),
            len(posonly_ids),
            len(positional_or_keyword_ids),
            len(keyword_only_ids),
            parameter_node_ids,
            parameter_names,
            parameter_kinds,
            parameter_categories,
            parameter_node_ids[positional_capacity:],
            parameter_names[positional_capacity:],
            parameter_categories[positional_capacity:],
            positional_ids,
            keyword_ids,
            tuple(item["fields"].get("arg") for item in keyword_nodes),
            tuple(item["fields"]["value"] for item in keyword_nodes),
            tuple(argument_bindings),
            source_argument_ids,
            source_categories,
            tuple(item.parameter_ordinal for item in argument_bindings),
            tuple(parameter_argument_ids),
            tuple(parameter_source_ordinals),
            source_argument_ids,
            True,
            parameter_coverage_exact,
            keyword_only_coverage_exact,
            KEYWORD_ONLY_CALL_LOWERING_SHAPE,
            "none",
            "none",
            "proved-absent" if supported else "compile-time-rejected",
            supported,
            code,
            reason,
            rejection_node_id,
        )

    def _merge_source_entries(
        self,
        positional: list[dict[str, Any]],
        keywords: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        positional_index = 0
        keyword_index = 0
        while positional_index < len(positional) and keyword_index < len(keywords):
            self._check_cancellation()
            positional_item = positional[positional_index]
            keyword_item = keywords[keyword_index]
            if self._source_key(positional_item["order_node_id"]) <= self._source_key(
                keyword_item["order_node_id"]
            ):
                merged.append(positional_item)
                positional_index += 1
            else:
                merged.append(keyword_item)
                keyword_index += 1
        merged.extend(positional[positional_index:])
        merged.extend(keywords[keyword_index:])
        return merged

    def _source_key(self, node_id: str) -> tuple[int, int]:
        node = self.nodes.get(node_id, {})
        provenance = node.get("provenance")
        span = provenance.get("source_span") if isinstance(provenance, Mapping) else None
        start = span.get("start") if isinstance(span, Mapping) else None
        offset = start.get("offset") if isinstance(start, Mapping) else None
        return (
            offset if isinstance(offset, int) else 2**63 - 1,
            self.node_order.get(node_id, 2**63 - 1),
        )

    def _check_cancellation(self) -> None:
        if self.cancellation is not None and bool(
            getattr(self.cancellation, "is_canceled", False)
        ):
            raise KeywordOnlyCallAnalysisCanceled

    def _error(self, code: str, message: str, node: dict[str, Any]) -> None:
        raise KeywordOnlyCallAnalysisError(
            code,
            message,
            str(node.get("node_id", "")),
            _source_span(node),
        )

    def _malformed(self, message: str, node: Any) -> None:
        value = node if isinstance(node, Mapping) else {}
        raise KeywordOnlyCallAnalysisError(
            "PYC2912",
            message,
            str(value.get("node_id") or self.module.get("root_node_id") or ""),
            _source_span(value),
        )


__all__ = ["KeywordOnlyCallAnalyzer"]
