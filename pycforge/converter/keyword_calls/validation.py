"""Independent reconstruction of exact direct keyword-call binding facts."""

from __future__ import annotations

from typing import Any, Mapping

from pycforge.converter.ir.python_ir import python_ir_reference_ids

from .model import (
    CUMULATIVE_KEYWORD_TARGET_DIAGNOSTIC_CODE,
    CUMULATIVE_KEYWORD_TARGET_REASON,
    KEYWORD_CALL_FACT_SCHEMA,
    KEYWORD_CALL_KEY_DOMAIN,
    KEYWORD_CALL_LOWERING_SHAPE,
    KEYWORD_CALL_OBLIGATIONS,
    KEYWORD_CALL_PROVENANCE_EVIDENCE,
    KEYWORD_CALL_RULE_ID,
    KEYWORD_CALL_RULE_VERSION,
    KEYWORD_CALL_TABLE_DEPENDENCIES,
    KEYWORD_CALL_TABLE_ID,
    KeywordCallValidationCanceled,
    keyword_call_binding_id,
)


class _MalformedKeywordEvidence(ValueError):
    """Internal sentinel for hostile or structurally invalid evidence."""


def _sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple))


def _check(cancellation: Any) -> None:
    if cancellation is not None and bool(getattr(cancellation, "is_canceled", False)):
        raise KeywordCallValidationCanceled


def _category(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value or "unknown")


def _validate_keyword_call_binding_facts(
    payload: Mapping[str, Any],
    tables: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    *,
    expected_fact_schema: str = KEYWORD_CALL_FACT_SCHEMA,
    require_table: bool = True,
    require_plans: bool = True,
    ignored_call_node_ids: frozenset[str] = frozenset(),
    cumulatively_ineligible_target_function_node_ids: frozenset[str] = frozenset(),
    cancellation: Any = None,
) -> tuple[bool, str]:
    """Require exact table coverage, independently rebuilt facts, and plans."""

    _check(cancellation)
    raw_tables = tables if tables is not None else payload.get("fact_tables")
    if not _sequence(raw_tables) or any(not isinstance(item, dict) for item in raw_tables):
        return False, "keyword-call fact tables are malformed"
    table_values = tuple(raw_tables)
    table = next((item for item in table_values if item.get("table_id") == KEYWORD_CALL_TABLE_ID), None)
    if table is None:
        return (False, "keyword-call binding fact table is absent") if require_table else (True, "")
    dependencies = table.get("invalidation_dependencies")
    if (
        table.get("schema_version") != expected_fact_schema
        or table.get("producer_stage") != "analysis.plan"
        or table.get("key_domain") != KEYWORD_CALL_KEY_DOMAIN
        or table.get("completeness") != "complete"
        or not _sequence(dependencies)
        or tuple(dependencies) != KEYWORD_CALL_TABLE_DEPENDENCIES
    ):
        return False, "keyword-call binding fact schema is invalid"

    module = payload.get("python_ir")
    node_values = module.get("nodes") if isinstance(module, dict) else None
    if not isinstance(node_values, list):
        return False, "keyword-call validation lacks normalized Python IR"
    nodes: dict[str, dict[str, Any]] = {}
    node_order: dict[str, int] = {}
    for ordinal, node in enumerate(node_values):
        _check(cancellation)
        node_id = node.get("node_id") if isinstance(node, dict) else None
        if not isinstance(node_id, str) or node_id in nodes:
            return False, "keyword-call Python IR identities are invalid"
        nodes[node_id] = node
        node_order[node_id] = ordinal

    table_map: dict[str, dict[str, Any]] = {}
    for item in table_values:
        table_id = item.get("table_id")
        if not isinstance(table_id, str) or table_id in table_map:
            return False, "keyword-call fact-table identities are malformed"
        table_map[table_id] = item
    required = {
        "binding-facts",
        "function-signature-facts",
        "value-category-facts",
        "call-target-facts",
    }
    if not required.issubset(table_map):
        return False, "keyword-call proof dependencies are absent"

    def record_values(table_id: str) -> tuple[dict[str, Any], ...]:
        result: list[dict[str, Any]] = []
        records = table_map[table_id].get("records")
        if not isinstance(records, list):
            raise _MalformedKeywordEvidence(
                f"keyword-call dependency {table_id!r} records are malformed"
            )
        for record in records:
            _check(cancellation)
            value = record.get("value") if isinstance(record, dict) else None
            if not isinstance(value, dict):
                raise _MalformedKeywordEvidence(
                    f"keyword-call dependency {table_id!r} contains a malformed record"
                )
            result.append(value)
        return tuple(result)

    occurrence_bindings: dict[str, str] = {}
    for binding in record_values("binding-facts"):
        _check(cancellation)
        binding_id = binding.get("binding_id")
        occurrences = binding.get("occurrence_node_ids")
        if (
            not isinstance(binding_id, str)
            or not _sequence(occurrences)
            or any(not isinstance(item, str) for item in occurrences)
        ):
            raise _MalformedKeywordEvidence("keyword-call binding evidence is malformed")
        for occurrence in occurrences:
            existing = occurrence_bindings.get(occurrence)
            if existing is not None and existing != binding_id:
                raise _MalformedKeywordEvidence(
                    "keyword-call occurrence has conflicting binding evidence"
                )
            occurrence_bindings[occurrence] = binding_id
    signatures: dict[str, dict[str, Any]] = {}
    for item in record_values("function-signature-facts"):
        binding_id = item.get("binding_id")
        parameters = item.get("parameters")
        if (
            not isinstance(binding_id, str)
            or not _sequence(parameters)
            or binding_id in signatures
        ):
            raise _MalformedKeywordEvidence("keyword-call signature evidence is malformed")
        signatures[binding_id] = item
    categories: dict[Any, str] = {}
    category_records = table_map["value-category-facts"].get("records")
    if not isinstance(category_records, list):
        raise _MalformedKeywordEvidence("keyword-call category evidence is malformed")
    for record in category_records:
        _check(cancellation)
        if not isinstance(record, dict) or not isinstance(record.get("key"), str):
            raise _MalformedKeywordEvidence("keyword-call category record is malformed")
        categories[record["key"]] = _category(record.get("value"))
    call_targets: dict[str, dict[str, Any]] = {}
    for item in record_values("call-target-facts"):
        call_id = item.get("call_node_id")
        if not isinstance(call_id, str) or call_id in call_targets:
            raise _MalformedKeywordEvidence("keyword-call target evidence is malformed")
        call_targets[call_id] = item

    reconstruction = _IndependentKeywordReconstruction(
        node_values,
        nodes=nodes,
        node_order=node_order,
        occurrence_bindings=occurrence_bindings,
        signatures=signatures,
        categories=categories,
        ignored_call_node_ids=ignored_call_node_ids,
        cancellation=cancellation,
    )
    expected = reconstruction.expected()
    for call_id, fact in tuple(expected.items()):
        _check(cancellation)
        if (
            fact.get("supported") is True
            and fact.get("target_function_node_id")
            in cumulatively_ineligible_target_function_node_ids
        ):
            expected[call_id] = {
                **fact,
                "runtime_binding_failure": "compile-time-rejected",
                "supported": False,
                "diagnostic_code": CUMULATIVE_KEYWORD_TARGET_DIAGNOSTIC_CODE,
                "reason": CUMULATIVE_KEYWORD_TARGET_REASON,
                "rejection_node_id": fact["target_function_node_id"],
            }

    records = table.get("records")
    if not isinstance(records, list):
        return False, "keyword-call binding records are malformed"
    keys = [record.get("key") if isinstance(record, dict) else None for record in records]
    if (
        any(not isinstance(key, str) for key in keys)
        or any(keys[index - 1] >= keys[index] for index in range(1, len(keys)))
    ):
        return False, "keyword-call binding keys are not unique and sorted"
    found: dict[str, dict[str, Any]] = {}
    provenance: dict[str, Any] = {}
    for record in records:
        _check(cancellation)
        key, value = record.get("key"), record.get("value")
        if not isinstance(value, dict) or value.get("call_node_id") != key:
            return False, "keyword-call binding record identity is malformed"
        found[key] = value
        provenance[key] = record.get("provenance")
    if set(found) != set(expected):
        return False, "keyword-call facts do not exactly cover eligible direct keyword calls"
    for call_id, fact in expected.items():
        _check(cancellation)
        if found[call_id] != fact:
            return False, "keyword-call fact disagrees with independent reconstruction"
        proof = provenance.get(call_id)
        if (
            not isinstance(proof, dict)
            or proof.get("source_node_ids") != _provenance_ids(fact)
            or proof.get("evidence") != list(KEYWORD_CALL_PROVENANCE_EVIDENCE)
        ):
            return False, "keyword-call fact provenance is incomplete"
        target = call_targets.get(call_id)
        if not isinstance(target, dict) or any(
            target.get(name) != value
            for name, value in {
                "callee_node_id": fact["callee_node_id"],
                "target_function_node_id": fact["target_function_node_id"],
                "target_binding_id": fact["target_binding_id"],
                "argument_node_ids": fact["source_argument_node_ids"],
                "argument_categories": fact["source_argument_categories"],
                "evaluation_order": fact["evaluation_order"],
                "arguments_evaluated_once": True,
            }.items()
        ):
            return False, "keyword-call fact disagrees with call-target evidence"
        recursive_override = bool(
            fact["supported"]
            and target.get("resolution") == "recursive-target"
            and target.get("supported") is False
            and target.get("diagnostic_code") == "PYC2920"
            and target.get("reason")
            == "Direct and mutual recursion are unsupported in Phase 9"
        )
        if not recursive_override and any(
            target.get(name) != value
            for name, value in {
                "resolution": "understood-source-function" if fact["supported"] else "ineligible-source-function",
                "supported": fact["supported"],
                "diagnostic_code": fact["diagnostic_code"],
                "reason": fact["reason"],
            }.items()
        ):
            return False, "keyword-call fact disagrees with call-target support state"

    if require_plans:
        valid, reason = _validate_plans(payload, expected, cancellation)
        if not valid:
            return valid, reason
    return True, ""


def _provenance_ids(fact: dict[str, Any]) -> list[str]:
    values = (
        fact["call_node_id"], fact["callee_node_id"], fact["target_function_node_id"],
        *fact["parameter_node_ids"], *fact["positional_argument_node_ids"],
        *fact["keyword_node_ids"], *fact["keyword_value_node_ids"],
    )
    return list(dict.fromkeys(values))


class _IndependentKeywordReconstruction:
    """A producer-independent implementation of the closed binding algorithm."""

    def __init__(
        self,
        node_values: list[dict[str, Any]],
        *,
        nodes: Mapping[str, dict[str, Any]],
        node_order: Mapping[str, int],
        occurrence_bindings: Mapping[str, str],
        signatures: Mapping[str, dict[str, Any]],
        categories: Mapping[str, str],
        ignored_call_node_ids: frozenset[str],
        cancellation: Any,
    ) -> None:
        self.node_values = node_values
        self.nodes = nodes
        self.node_order = node_order
        self.occurrence_bindings = occurrence_bindings
        self.signatures = signatures
        self.categories = categories
        self.ignored = ignored_call_node_ids
        self.cancellation = cancellation

    def expected(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for call in self.node_values:
            _check(self.cancellation)
            if call.get("kind") != "Call" or call.get("node_id") in self.ignored:
                continue
            fields = call.get("fields")
            if not isinstance(fields, dict) or not _sequence(fields.get("keywords")):
                raise _MalformedKeywordEvidence("keyword-call Python IR fields are malformed")
            if not fields["keywords"]:
                continue
            callee_id = fields.get("func")
            callee = self.nodes.get(callee_id)
            binding_id = self.occurrence_bindings.get(callee_id)
            signature = self.signatures.get(binding_id)
            if (
                not callee or callee.get("kind") != "Name"
                or not isinstance(signature, dict)
                or signature.get("eligible") is not True
            ):
                continue
            target = self.nodes.get(signature.get("function_node_id"))
            target_fields = target.get("fields") if isinstance(target, dict) else None
            arguments = (
                self.nodes.get(target_fields.get("args"))
                if isinstance(target_fields, dict)
                else None
            )
            argument_fields = (
                arguments.get("fields") if isinstance(arguments, dict) else None
            )
            if (
                isinstance(argument_fields, dict)
                and argument_fields.get("kwonlyargs")
            ):
                continue
            result[call["node_id"]] = self._fact(call, signature, str(binding_id))
        return result

    def _fact(self, call: dict[str, Any], signature: dict[str, Any], target_binding_id: str) -> dict[str, Any]:
        _check(self.cancellation)
        fields, call_id = call.get("fields"), call.get("node_id")
        if not isinstance(fields, dict) or not isinstance(call_id, str):
            raise _MalformedKeywordEvidence("keyword-call Python IR call is malformed")
        target_id = signature.get("function_node_id")
        target = self.nodes.get(target_id)
        target_fields = target.get("fields") if isinstance(target, dict) else None
        if (
            not isinstance(target_id, str)
            or not isinstance(target, dict)
            or target.get("kind") != "FunctionDef"
            or not isinstance(target_fields, dict)
        ):
            raise _MalformedKeywordEvidence("keyword-call target evidence is malformed")
        arguments = self.nodes.get(target_fields.get("args"))
        argument_fields = arguments.get("fields") if isinstance(arguments, dict) else None
        parameters_value = signature.get("parameters")
        if (
            not isinstance(arguments, dict)
            or arguments.get("kind") != "arguments"
            or not isinstance(argument_fields, dict)
            or not _sequence(argument_fields.get("posonlyargs"))
            or not _sequence(parameters_value)
        ):
            raise _MalformedKeywordEvidence("keyword-call signature evidence is malformed")
        parameters = tuple(parameters_value)
        if any(not isinstance(item, dict) for item in parameters):
            raise _MalformedKeywordEvidence("keyword-call parameters are malformed")
        parameter_node_ids = tuple(str(item.get("parameter_node_id", "")) for item in parameters)
        parameter_names = tuple(str(item.get("source_name", "")) for item in parameters)
        parameter_categories = tuple(_category(item.get("category")) for item in parameters)
        if (
            any(not item for item in parameter_node_ids)
            or any(not item for item in parameter_names)
            or len(parameter_names) != len(set(parameter_names))
            or any(item not in self.nodes for item in parameter_node_ids)
        ):
            raise _MalformedKeywordEvidence("keyword-call parameter identities are malformed")
        positional_only_count = len(argument_fields["posonlyargs"])
        if positional_only_count > len(parameters):
            raise _MalformedKeywordEvidence("keyword-call positional-only evidence is malformed")
        if not _sequence(fields.get("args")) or not _sequence(fields.get("keywords")):
            raise _MalformedKeywordEvidence("keyword-call argument sequences are malformed")
        positional_ids = tuple(fields["args"])
        keyword_ids = tuple(fields["keywords"])
        if any(not isinstance(item, str) for item in (*positional_ids, *keyword_ids)):
            raise _MalformedKeywordEvidence("keyword-call argument identities are malformed")
        keyword_nodes: list[dict[str, Any]] = []
        for keyword_id in keyword_ids:
            keyword = self.nodes.get(keyword_id)
            keyword_fields = keyword.get("fields") if isinstance(keyword, dict) else None
            if (
                not isinstance(keyword, dict)
                or keyword.get("kind") != "keyword"
                or not isinstance(keyword_fields, dict)
                or not isinstance(keyword_fields.get("value"), str)
                or keyword_fields["value"] not in self.nodes
            ):
                raise _MalformedKeywordEvidence("keyword-call keyword evidence is malformed")
            keyword_nodes.append(keyword)

        positional_entries: list[dict[str, Any]] = []
        for position, argument_id in enumerate(positional_ids):
            _check(self.cancellation)
            if argument_id not in self.nodes:
                raise _MalformedKeywordEvidence("keyword-call argument node is absent")
            positional_entries.append({"kind": "positional", "position": position, "argument": argument_id, "keyword": None, "name": None, "order_node_id": argument_id})
        keyword_entries: list[dict[str, Any]] = []
        for position, keyword in enumerate(keyword_nodes):
            _check(self.cancellation)
            keyword_fields = keyword["fields"]
            keyword_entries.append({"kind": "keyword", "position": position, "argument": keyword_fields["value"], "keyword": keyword["node_id"], "name": keyword_fields.get("arg"), "order_node_id": keyword["node_id"]})
        entries = self._merge_source_entries(positional_entries, keyword_entries)
        for ordinal, entry in enumerate(entries):
            entry["ordinal"] = ordinal
        by_position = {(item["kind"], item["position"]): item for item in entries}

        parameter_by_name = {name: ordinal for ordinal, name in enumerate(parameter_names)}
        parameter_arguments: list[str | None] = [None] * len(parameters)
        parameter_sources: list[int | None] = [None] * len(parameters)
        source_parameters: dict[tuple[str, int], int | None] = {}
        unpacking: list[tuple[int, str]] = []
        excess: list[tuple[int, str]] = []
        problems: list[tuple[str, str]] = []
        saw_starred = False
        for position, argument_id in enumerate(positional_ids):
            _check(self.cancellation)
            entry = by_position[("positional", position)]
            if self.nodes.get(argument_id, {}).get("kind") == "Starred":
                saw_starred = True
                source_parameters[("positional", position)] = None
                unpacking.append((entry["ordinal"], argument_id))
            elif saw_starred:
                source_parameters[("positional", position)] = None
            elif position >= len(parameters):
                source_parameters[("positional", position)] = None
                excess.append((entry["ordinal"], argument_id))
            else:
                source_parameters[("positional", position)] = position
                parameter_arguments[position] = argument_id
                parameter_sources[position] = entry["ordinal"]
        for position, keyword in enumerate(keyword_nodes):
            _check(self.cancellation)
            entry = by_position[("keyword", position)]
            keyword_id, name = keyword["node_id"], keyword.get("fields", {}).get("arg")
            if name is None:
                source_parameters[("keyword", position)] = None
                unpacking.append((entry["ordinal"], keyword_id))
                continue
            parameter_ordinal = parameter_by_name.get(name)
            if parameter_ordinal is None:
                source_parameters[("keyword", position)] = None
                problems.append((keyword_id, f"Unknown keyword argument: {name}"))
                continue
            source_parameters[("keyword", position)] = parameter_ordinal
            if parameter_ordinal < positional_only_count:
                problems.append((keyword_id, f"Positional-only parameter cannot be bound by keyword: {name}"))
            elif parameter_arguments[parameter_ordinal] is not None:
                prior = parameter_sources[parameter_ordinal]
                prior_entry = entries[prior] if isinstance(prior, int) else None
                reason = f"Keyword argument duplicates a positionally bound parameter: {name}" if prior_entry and prior_entry["kind"] == "positional" else f"Duplicate keyword argument: {name}"
                problems.append((keyword_id, reason))
            else:
                parameter_arguments[parameter_ordinal] = keyword.get("fields", {}).get("value")
                parameter_sources[parameter_ordinal] = entry["ordinal"]

        argument_bindings: list[dict[str, Any]] = []
        for entry in entries:
            _check(self.cancellation)
            parameter_ordinal = source_parameters.get((entry["kind"], entry["position"]))
            valid = isinstance(parameter_ordinal, int) and 0 <= parameter_ordinal < len(parameters)
            argument_id = entry["argument"]
            argument_bindings.append({
                "source_argument_node_id": argument_id,
                "keyword_node_id": entry["keyword"], "keyword_name": entry["name"],
                "source_ordinal": entry["ordinal"],
                "parameter_node_id": parameter_node_ids[parameter_ordinal] if valid else None,
                "parameter_name": parameter_names[parameter_ordinal] if valid else None,
                "parameter_ordinal": parameter_ordinal,
                "category": self.categories.get(argument_id, "unknown"),
                "expected_category": parameter_categories[parameter_ordinal] if valid else None,
            })
        missing = [parameter_names[i] for i, value in enumerate(parameter_arguments) if value is None]
        mismatches = [item for item in argument_bindings if item["parameter_ordinal"] is not None and item["expected_category"] is not None and item["category"] != item["expected_category"] and parameter_sources[item["parameter_ordinal"]] == item["source_ordinal"]]
        coverage = bool(not unpacking and not excess and not problems and not missing and all(value is not None for value in parameter_arguments) and len(entries) == len(parameters))

        code = reason = rejection = None
        if unpacking:
            _, rejection = min(unpacking, key=lambda item: item[0]); code, reason = "PYC2910", "Starred and unpacked call arguments are unsupported by the exact keyword profile"
        elif excess:
            _, rejection = min(excess, key=lambda item: item[0]); code, reason = "PYC2904", "Argument count exceeds the target signature"
        elif problems:
            rejection, reason = problems[0]; code = "PYC2912"
        elif missing:
            rejection, code, reason = call_id, "PYC2904", "Every target parameter must be supplied exactly once; missing: " + ", ".join(missing)
        elif mismatches:
            mismatch = mismatches[0]
            rejection = mismatch["keyword_node_id"] or mismatch["source_argument_node_id"]
            code, reason = "PYC2905", f"Argument representation does not match parameter {mismatch['parameter_name']}"
        supported = code is None and coverage
        if not supported and code is None:
            rejection, code, reason = call_id, "PYC2904", "Keyword arguments do not exactly cover the target signature"
        source_ids = tuple(item["source_argument_node_id"] for item in argument_bindings)
        source_categories = tuple(item["category"] for item in argument_bindings)
        return {
            "binding_id": keyword_call_binding_id(call_id, target_binding_id),
            "call_node_id": call_id, "callee_node_id": fields["func"],
            "target_function_node_id": target_id, "target_binding_id": target_binding_id,
            "target_name": str(signature.get("source_name", target_fields.get("name", ""))),
            "positional_only_parameter_count": positional_only_count,
            "parameter_node_ids": list(parameter_node_ids), "parameter_names": list(parameter_names),
            "parameter_categories": list(parameter_categories),
            "positional_argument_node_ids": list(positional_ids), "keyword_node_ids": list(keyword_ids),
            "keyword_names": [item.get("fields", {}).get("arg") for item in keyword_nodes],
            "keyword_value_node_ids": [item.get("fields", {}).get("value") for item in keyword_nodes],
            "argument_bindings": argument_bindings,
            "source_argument_node_ids": list(source_ids), "source_argument_categories": list(source_categories),
            "source_to_parameter_ordinals": [item["parameter_ordinal"] for item in argument_bindings],
            "parameter_argument_node_ids": list(parameter_arguments), "parameter_to_source_ordinals": list(parameter_sources),
            "evaluation_order": list(source_ids), "arguments_evaluated_once": True,
            "parameter_coverage_exact": coverage, "lowering_shape": KEYWORD_CALL_LOWERING_SHAPE,
            "allocation_model": "none", "cleanup_model": "none",
            "runtime_binding_failure": "proved-absent" if supported else "compile-time-rejected",
            "supported": supported, "diagnostic_code": code, "reason": reason, "rejection_node_id": rejection,
        }

    def _merge_source_entries(
        self,
        positional: list[dict[str, Any]],
        keywords: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Linearly merge normalized source-ordered positional/keyword lists."""

        merged: list[dict[str, Any]] = []
        positional_index = 0
        keyword_index = 0
        while positional_index < len(positional) and keyword_index < len(keywords):
            _check(self.cancellation)
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
        span = provenance.get("source_span") if isinstance(provenance, dict) else None
        start = span.get("start") if isinstance(span, dict) else None
        offset = start.get("offset") if isinstance(start, dict) else None
        return (
            offset if isinstance(offset, int) else 2**63 - 1,
            self.node_order.get(node_id, 2**63 - 1),
        )

def _validate_plans(payload: Mapping[str, Any], expected: dict[str, dict[str, Any]], cancellation: Any) -> tuple[bool, str]:
    plan_values = payload.get("rule_plans")
    if not isinstance(plan_values, list):
        return False, "keyword-call RulePlans are malformed"
    plans_by_source: dict[str, dict[str, Any]] = {}
    for item in plan_values:
        _check(cancellation)
        if not isinstance(item, dict):
            return False, "keyword-call RulePlans are malformed"
        if item.get("rule_id") != KEYWORD_CALL_RULE_ID:
            continue
        source_id = item.get("source_node_id")
        if not isinstance(source_id, str) or source_id in plans_by_source:
            return False, "keyword-call RulePlans have duplicate or invalid sources"
        plans_by_source[source_id] = item

    table_values = payload.get("fact_tables")
    if not isinstance(table_values, list):
        return False, "keyword-call RulePlan dependencies are malformed"
    tables: dict[str, dict[str, Any]] = {}
    for item in table_values:
        if not isinstance(item, dict) or not isinstance(item.get("table_id"), str):
            return False, "keyword-call RulePlan dependencies are malformed"
        table_id = item["table_id"]
        if table_id in tables:
            return False, "keyword-call RulePlan dependencies have duplicate identities"
        tables[table_id] = item

    def values(table_id: str) -> tuple[dict[str, Any], ...]:
        table = tables.get(table_id)
        records = table.get("records") if isinstance(table, dict) else None
        if not isinstance(records, list):
            raise _MalformedKeywordEvidence(
                f"keyword-call RulePlan dependency {table_id!r} is malformed"
            )
        result: list[dict[str, Any]] = []
        for record in records:
            value = record.get("value") if isinstance(record, dict) else None
            if not isinstance(value, dict):
                raise _MalformedKeywordEvidence(
                    f"keyword-call RulePlan dependency {table_id!r} is malformed"
                )
            result.append(value)
        return tuple(result)

    call_targets = {item.get("call_node_id"): item for item in values("call-target-facts")}
    supported = {
        key: value
        for key, value in expected.items()
        if value["supported"] and call_targets.get(key, {}).get("supported") is True
    }
    if set(plans_by_source) != set(supported):
        return False, "keyword-call RulePlans do not exactly cover cumulatively supported facts"
    decision_values = payload.get("support_decisions")
    if not isinstance(decision_values, list):
        return False, "keyword-call support decisions are malformed"
    decisions: dict[str, dict[str, Any]] = {}
    for item in decision_values:
        node_id = item.get("node_id") if isinstance(item, dict) else None
        if not isinstance(node_id, str) or node_id in decisions:
            return False, "keyword-call support decisions are malformed"
        decisions[node_id] = item
    category_records = tables.get("value-category-facts", {}).get("records")
    if not isinstance(category_records, list):
        return False, "keyword-call RulePlan categories are malformed"
    categories = {
        record.get("key"): _category(record.get("value"))
        for record in category_records
        if isinstance(record, dict)
    }
    module_functions = {item.get("function_node_id"): item for item in values("module-function-facts")}
    module = payload.get("python_ir")
    node_values = module.get("nodes") if isinstance(module, dict) else None
    if not isinstance(node_values, list):
        return False, "keyword-call RulePlan Python IR is malformed"
    nodes = {
        item.get("node_id"): item
        for item in node_values
        if isinstance(item, dict) and isinstance(item.get("node_id"), str)
    }
    parents: dict[str, list[str]] = {}
    for parent in node_values:
        _check(cancellation)
        fields = parent.get("fields") if isinstance(parent, dict) else None
        if (
            not isinstance(fields, dict)
            or not isinstance(parent.get("kind"), str)
            or not isinstance(parent.get("node_id"), str)
        ):
            return False, "keyword-call RulePlan Python IR is malformed"
        for field, value in fields.items():
            for child in python_ir_reference_ids(parent["kind"], field, value, nodes):
                parents.setdefault(child, []).append(parent["node_id"])
    def owner(node_id: str) -> str | None:
        seen: set[str] = set()
        current = node_id
        while current not in seen:
            seen.add(current)
            candidates = parents.get(current, ())
            if not candidates:
                return None
            current = candidates[0]
            if nodes.get(current, {}).get("kind") == "FunctionDef":
                return current
        return None
    for call_id, fact in supported.items():
        _check(cancellation)
        plan = plans_by_source[call_id]
        feature_facts = {
            f"keyword-call-binding:{fact['binding_id']}", f"keyword-call:{call_id}",
            f"keyword-call-target:{fact['target_binding_id']}",
            f"keyword-source-argument-count:{len(fact['source_argument_node_ids'])}",
            f"keyword-parameter-count:{len(fact['parameter_node_ids'])}",
            f"keyword-call-lowering-shape:{fact['lowering_shape']}",
        }
        facts_used = plan.get("facts_used")
        if not isinstance(facts_used, list) or any(
            not isinstance(item, str) for item in facts_used
        ):
            return False, "keyword-call RulePlan facts are malformed"
        actual_feature_facts = {
            item for item in facts_used if item.startswith("keyword-")
        }
        call = call_targets.get(call_id, {})
        annotation_evidence = call.get("annotation_evidence")
        argument_categories = call.get("argument_categories")
        if not _sequence(annotation_evidence) or not _sequence(argument_categories):
            return False, "keyword-call RulePlan call-target evidence is malformed"
        expected_facts = {
            f"value-category:{categories.get(call_id, 'unknown')}",
            f"call-target:{fact['target_binding_id']}",
            *(f"annotation-evidence:{item}" for item in annotation_evidence),
            *(f"argument-category:{item}" for item in argument_categories),
            *feature_facts,
        }
        expected_obligations = [
            *KEYWORD_CALL_OBLIGATIONS,
            "call-result-representation-known",
            "source-output-call-mapping-required",
        ]
        expected_explanation = [
            "selected", KEYWORD_CALL_RULE_ID, "for", "Call",
            "resolved-target", fact["target_name"], "argument-order",
            *fact["evaluation_order"],
        ]
        caller = module_functions.get(owner(call_id), {})
        callee = module_functions.get(fact["target_function_node_id"], {})
        caller_module = caller.get("module_id")
        callee_module = callee.get("module_id")
        if caller_module and callee_module and caller_module != callee_module:
            expected_facts.update({
                f"caller-module:{caller_module}",
                f"callee-module:{callee_module}",
                f"target-function:{fact['target_function_node_id']}",
            })
            expected_obligations.extend((
                "cross-module-call-uses-target-binding",
                "bundle-wide-recursion-policy-explicit",
            ))
            expected_explanation.extend((
                "cross-module-direct-call", str(caller_module), "to", str(callee_module),
            ))
        expected_explanation.extend((
            "keyword-call-binding", fact["target_name"],
            "source-order-arguments", str(len(fact["source_argument_node_ids"])),
            "formal-order-parameters", str(len(fact["parameter_node_ids"])),
            "lowered-as", fact["lowering_shape"],
        ))
        decision = decisions.get(call_id)
        facts_are_sorted_unique = all(
            facts_used[index - 1] < facts_used[index]
            for index in range(1, len(facts_used))
        )
        if (
            plan.get("rule_version") != KEYWORD_CALL_RULE_VERSION
            or plan.get("support_state") != "SupportedDirect"
            or plan.get("helper_requirements") != []
            or plan.get("unresolved_obligations") != []
            or actual_feature_facts != feature_facts
            or not facts_are_sorted_unique
            or set(facts_used) != expected_facts
            or plan.get("semantic_obligations") != expected_obligations
            or plan.get("resolved_obligations") != expected_obligations
            or plan.get("explanation_tokens") != expected_explanation
            or not isinstance(decision, dict)
            or decision.get("state") != "SupportedDirect"
            or decision.get("rule_plan_id") != plan.get("plan_id")
        ):
            return False, "keyword-call RulePlan does not close its exact proof"
    return True, ""


def validate_keyword_call_binding_facts(
    payload: Mapping[str, Any],
    tables: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    *,
    expected_fact_schema: str = KEYWORD_CALL_FACT_SCHEMA,
    require_table: bool = True,
    require_plans: bool = True,
    ignored_call_node_ids: frozenset[str] = frozenset(),
    cumulatively_ineligible_target_function_node_ids: frozenset[str] = frozenset(),
    cancellation: Any = None,
) -> tuple[bool, str]:
    """Fail closed on malformed evidence while preserving cancellation."""

    _check(cancellation)
    if not isinstance(payload, Mapping):
        return False, "keyword-call validation payload is malformed"
    if tables is not None and not _sequence(tables):
        return False, "keyword-call fact tables are malformed"
    if (
        not isinstance(ignored_call_node_ids, (set, frozenset))
        or any(not isinstance(item, str) for item in ignored_call_node_ids)
        or not isinstance(
            cumulatively_ineligible_target_function_node_ids,
            (set, frozenset),
        )
        or any(
            not isinstance(item, str)
            for item in cumulatively_ineligible_target_function_node_ids
        )
    ):
        return False, "keyword-call validation exclusions are malformed"
    try:
        return _validate_keyword_call_binding_facts(
            payload,
            tables,
            expected_fact_schema=expected_fact_schema,
            require_table=require_table,
            require_plans=require_plans,
            ignored_call_node_ids=frozenset(ignored_call_node_ids),
            cumulatively_ineligible_target_function_node_ids=frozenset(
                cumulatively_ineligible_target_function_node_ids
            ),
            cancellation=cancellation,
        )
    except _MalformedKeywordEvidence as exc:
        return False, str(exc) or "keyword-call evidence is malformed"
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return False, "keyword-call evidence is malformed"


__all__ = ["validate_keyword_call_binding_facts"]
