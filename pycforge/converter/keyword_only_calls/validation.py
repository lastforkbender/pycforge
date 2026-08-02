"""Independent reconstruction of required keyword-only binding evidence."""

from __future__ import annotations

from typing import Any, Mapping

from .model import (
    CUMULATIVE_KEYWORD_ONLY_TARGET_DIAGNOSTIC_CODE,
    CUMULATIVE_KEYWORD_ONLY_TARGET_REASON,
    KEYWORD_ONLY_CALL_FACT_SCHEMA,
    KEYWORD_ONLY_CALL_KEY_DOMAIN,
    KEYWORD_ONLY_CALL_LOWERING_SHAPE,
    KEYWORD_ONLY_CALL_OBLIGATIONS,
    KEYWORD_ONLY_CALL_PROVENANCE_EVIDENCE,
    KEYWORD_ONLY_CALL_RULE_ID,
    KEYWORD_ONLY_CALL_RULE_VERSION,
    KEYWORD_ONLY_CALL_TABLE_DEPENDENCIES,
    KEYWORD_ONLY_CALL_TABLE_ID,
    KeywordOnlyCallValidationCanceled,
    keyword_only_call_binding_id,
)


class _MalformedKeywordOnlyEvidence(ValueError):
    pass


_ANNOTATION_CONTRACTS = {
    "int": (
        "integer-like",
        "int64_t",
        "by-value",
        "not-applicable",
        "callee-activation",
    ),
    "float": (
        "floating-like",
        "double",
        "by-value",
        "not-applicable",
        "callee-activation",
    ),
    "bool": (
        "boolean-like",
        "bool",
        "by-value",
        "not-applicable",
        "callee-activation",
    ),
    "str": (
        "string-like",
        "const char *",
        "borrowed-pointer",
        "borrowed",
        "caller-managed-valid-for-call",
    ),
}


def _sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple))


def _category(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value or "unknown")


def _check(cancellation: Any) -> None:
    if cancellation is not None and bool(
        getattr(cancellation, "is_canceled", False)
    ):
        raise KeywordOnlyCallValidationCanceled


def _record_values(
    table: Mapping[str, Any],
    cancellation: Any,
) -> tuple[dict[str, Any], ...]:
    records = table.get("records")
    if not isinstance(records, list):
        raise _MalformedKeywordOnlyEvidence("keyword-only dependency records are malformed")
    result: list[dict[str, Any]] = []
    for record in records:
        _check(cancellation)
        value = record.get("value") if isinstance(record, dict) else None
        if not isinstance(value, dict):
            raise _MalformedKeywordOnlyEvidence(
                "keyword-only dependency contains a malformed record"
            )
        result.append(value)
    return tuple(result)


class _IndependentKeywordOnlyReconstruction:
    """Producer-independent implementation of the bounded binding algorithm."""

    def __init__(
        self,
        *,
        node_values: list[dict[str, Any]],
        nodes: Mapping[str, dict[str, Any]],
        node_order: Mapping[str, int],
        occurrence_bindings: Mapping[str, str],
        binding_by_declaration: Mapping[str, str],
        declaration_by_binding: Mapping[str, str],
        signatures: Mapping[str, dict[str, Any]],
        categories: Mapping[str, str],
        ignored_call_node_ids: frozenset[str],
        cancellation: Any,
    ) -> None:
        self.node_values = node_values
        self.nodes = nodes
        self.node_order = node_order
        self.occurrence_bindings = occurrence_bindings
        self.binding_by_declaration = binding_by_declaration
        self.declaration_by_binding = declaration_by_binding
        self.signatures = signatures
        self.categories = categories
        self.ignored = ignored_call_node_ids
        self.cancellation = cancellation
        self.call_target_contracts: dict[str, dict[str, Any]] = {}

    def expected(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for call in self.node_values:
            _check(self.cancellation)
            if call.get("kind") != "Call" or call.get("node_id") in self.ignored:
                continue
            fields = call.get("fields")
            if (
                not isinstance(fields, dict)
                or not _sequence(fields.get("args"))
                or not _sequence(fields.get("keywords"))
            ):
                raise _MalformedKeywordOnlyEvidence(
                    "keyword-only Python IR call fields are malformed"
                )
            callee_id = fields.get("func")
            callee = self.nodes.get(callee_id)
            binding_id = self.occurrence_bindings.get(callee_id)
            signature = self.signatures.get(binding_id)
            if (
                not isinstance(callee, dict)
                or callee.get("kind") != "Name"
                or not isinstance(signature, dict)
                or signature.get("eligible") is not True
            ):
                continue
            shape = self._signature_shape(signature)
            if shape is None:
                continue
            result[call["node_id"]] = self._fact(
                call,
                signature,
                str(binding_id),
                shape,
            )
        return result

    def _signature_shape(
        self,
        signature: dict[str, Any],
    ) -> tuple[
        dict[str, Any],
        tuple[str, ...],
        tuple[str, ...],
        tuple[str, ...],
    ] | None:
        target = self.nodes.get(signature.get("function_node_id"))
        target_fields = target.get("fields") if isinstance(target, dict) else None
        arguments = (
            self.nodes.get(target_fields.get("args"))
            if isinstance(target_fields, dict)
            else None
        )
        fields = arguments.get("fields") if isinstance(arguments, dict) else None
        if not isinstance(fields, dict):
            raise _MalformedKeywordOnlyEvidence(
                "keyword-only signature Python IR is malformed"
            )
        for name in (
            "posonlyargs",
            "args",
            "kwonlyargs",
            "kw_defaults",
            "defaults",
        ):
            if not _sequence(fields.get(name)):
                raise _MalformedKeywordOnlyEvidence(
                    "keyword-only signature sequences are malformed"
                )
        posonly = tuple(fields["posonlyargs"])
        positional = tuple(fields["args"])
        keyword_only = tuple(fields["kwonlyargs"])
        if not keyword_only:
            return None
        if (
            len(fields["kw_defaults"]) != len(keyword_only)
            or any(item is not None for item in fields["kw_defaults"])
            or fields["defaults"]
            or fields.get("vararg")
            or fields.get("kwarg")
        ):
            return None
        return fields, posonly, positional, keyword_only

    def _fact(
        self,
        call: dict[str, Any],
        signature: dict[str, Any],
        target_binding_id: str,
        shape: tuple[
            dict[str, Any],
            tuple[str, ...],
            tuple[str, ...],
            tuple[str, ...],
        ],
    ) -> dict[str, Any]:
        fields = call["fields"]
        call_id = call["node_id"]
        _, posonly, positional, keyword_only = shape
        formal_ids = posonly + positional + keyword_only
        parameters_value = signature.get("parameters")
        if not _sequence(parameters_value) or any(
            not isinstance(item, dict) for item in parameters_value
        ):
            raise _MalformedKeywordOnlyEvidence(
                "keyword-only signature facts are malformed"
            )
        parameters = tuple(parameters_value)
        target_id = signature.get("function_node_id")
        target = self.nodes.get(target_id)
        target_fields = target.get("fields") if isinstance(target, dict) else None
        if (
            not isinstance(target_id, str)
            or not isinstance(target, dict)
            or target.get("kind") != "FunctionDef"
            or not isinstance(target_fields, dict)
            or self.binding_by_declaration.get(target_id) != target_binding_id
        ):
            raise _MalformedKeywordOnlyEvidence(
                "keyword-only target signature identity is malformed"
            )
        target_name = target_fields.get("name")
        if not isinstance(target_name, str) or not target_name:
            raise _MalformedKeywordOnlyEvidence(
                "keyword-only target function name is malformed"
            )
        return_contract = self._annotation_contract(target_fields.get("returns"))
        return_annotation_id = target_fields.get("returns")
        return_spelling = self.nodes[return_annotation_id]["fields"]["id"]
        expected_signature = {
            "function_node_id": target_id,
            "binding_id": target_binding_id,
            "source_name": target_name,
            "return_category": return_contract[0],
            "return_c_type": return_contract[1],
            "return_annotation_node_id": return_annotation_id,
            "return_annotation_spelling": return_spelling,
            "return_passing": return_contract[2],
            "return_ownership": return_contract[3],
            "return_lifetime": return_contract[4],
            "prototype_required": True,
            "eligible": True,
            "rejection_reason": None,
        }
        if any(
            signature.get(name) != value
            for name, value in expected_signature.items()
        ):
            raise _MalformedKeywordOnlyEvidence(
                "keyword-only signature facts disagree with Python IR annotations"
            )
        if len(parameters) != len(formal_ids):
            raise _MalformedKeywordOnlyEvidence(
                "keyword-only signature parameter coverage is malformed"
            )
        parameter_names: list[str] = []
        parameter_categories: list[str] = []
        ownership_boundary: list[str] = []
        annotation_evidence: list[str] = []
        for ordinal, (parameter_id, parameter_fact) in enumerate(
            zip(formal_ids, parameters)
        ):
            _check(self.cancellation)
            parameter = self.nodes.get(parameter_id)
            parameter_fields = (
                parameter.get("fields") if isinstance(parameter, dict) else None
            )
            if (
                not isinstance(parameter_id, str)
                or not isinstance(parameter, dict)
                or parameter.get("kind") != "arg"
                or not isinstance(parameter_fields, dict)
            ):
                raise _MalformedKeywordOnlyEvidence(
                    "keyword-only formal Python IR is malformed"
                )
            parameter_name = parameter_fields.get("arg")
            annotation_id = parameter_fields.get("annotation")
            if not isinstance(parameter_name, str) or not parameter_name:
                raise _MalformedKeywordOnlyEvidence(
                    "keyword-only formal name is malformed"
                )
            contract = self._annotation_contract(annotation_id)
            spelling = self.nodes[annotation_id]["fields"]["id"]
            expected_parameter = {
                "parameter_node_id": parameter_id,
                "binding_id": self.binding_by_declaration.get(parameter_id),
                "source_name": parameter_name,
                "ordinal": ordinal,
                "category": contract[0],
                "c_type": contract[1],
                "annotation_node_id": annotation_id,
                "annotation_spelling": spelling,
                "passing": contract[2],
                "ownership": contract[3],
                "lifetime": contract[4],
            }
            if (
                not isinstance(expected_parameter["binding_id"], str)
                or any(
                    parameter_fact.get(name) != value
                    for name, value in expected_parameter.items()
                )
            ):
                raise _MalformedKeywordOnlyEvidence(
                    "keyword-only parameter facts disagree with Python IR annotations"
                )
            parameter_names.append(parameter_name)
            parameter_categories.append(contract[0])
            ownership_boundary.append(":".join(contract[2:]))
            annotation_evidence.append(annotation_id)
        parameter_node_ids = formal_ids
        parameter_names_tuple = tuple(parameter_names)
        parameter_categories_tuple = tuple(parameter_categories)
        parameter_kinds = (
            ("positional-only",) * len(posonly)
            + ("positional-or-keyword",) * len(positional)
            + ("keyword-only",) * len(keyword_only)
        )
        if (
            parameter_node_ids != formal_ids
            or len(parameter_names_tuple) != len(set(parameter_names_tuple))
        ):
            raise _MalformedKeywordOnlyEvidence(
                "keyword-only formal identities are malformed"
            )
        positional_ids = tuple(fields["args"])
        keyword_ids = tuple(fields["keywords"])
        if any(not isinstance(item, str) for item in (*positional_ids, *keyword_ids)):
            raise _MalformedKeywordOnlyEvidence(
                "keyword-only actual identities are malformed"
            )
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
                raise _MalformedKeywordOnlyEvidence(
                    "keyword-only keyword evidence is malformed"
                )
            keyword_nodes.append(keyword)
        positional_entries = [
            {
                "kind": "positional",
                "position": position,
                "argument": argument_id,
                "keyword": None,
                "name": None,
                "order_node_id": argument_id,
            }
            for position, argument_id in enumerate(positional_ids)
        ]
        if any(item["argument"] not in self.nodes for item in positional_entries):
            raise _MalformedKeywordOnlyEvidence(
                "keyword-only positional actual is absent"
            )
        keyword_entries = [
            {
                "kind": "keyword",
                "position": position,
                "argument": keyword["fields"]["value"],
                "keyword": keyword["node_id"],
                "name": keyword["fields"].get("arg"),
                "order_node_id": keyword["node_id"],
            }
            for position, keyword in enumerate(keyword_nodes)
        ]
        entries = self._merge(positional_entries, keyword_entries)
        for ordinal, entry in enumerate(entries):
            entry["ordinal"] = ordinal
        by_position = {
            (item["kind"], item["position"]): item for item in entries
        }

        positional_capacity = len(posonly) + len(positional)
        addressable = {
            name: ordinal
            for ordinal, name in enumerate(parameter_names_tuple)
            if ordinal >= len(posonly)
        }
        all_names = {
            name: ordinal for ordinal, name in enumerate(parameter_names_tuple)
        }
        parameter_arguments: list[str | None] = [None] * len(parameters)
        parameter_sources: list[int | None] = [None] * len(parameters)
        source_parameters: dict[tuple[str, int], int | None] = {}
        unpacking: list[tuple[int, str]] = []
        excess: list[tuple[int, str]] = []
        problems: list[tuple[int, str, str]] = []
        saw_starred = False
        for position, argument_id in enumerate(positional_ids):
            _check(self.cancellation)
            entry = by_position[("positional", position)]
            if self.nodes[argument_id].get("kind") == "Starred":
                saw_starred = True
                source_parameters[("positional", position)] = None
                unpacking.append((entry["ordinal"], argument_id))
            elif saw_starred:
                source_parameters[("positional", position)] = None
            elif position >= positional_capacity:
                source_parameters[("positional", position)] = None
                excess.append((entry["ordinal"], argument_id))
            else:
                source_parameters[("positional", position)] = position
                parameter_arguments[position] = argument_id
                parameter_sources[position] = entry["ordinal"]
        for position, keyword in enumerate(keyword_nodes):
            _check(self.cancellation)
            entry = by_position[("keyword", position)]
            keyword_id = keyword["node_id"]
            name = keyword["fields"].get("arg")
            if name is None:
                source_parameters[("keyword", position)] = None
                unpacking.append((entry["ordinal"], keyword_id))
                continue
            parameter_ordinal = addressable.get(name)
            if parameter_ordinal is None:
                source_parameters[("keyword", position)] = None
                reason = (
                    f"Positional-only parameter cannot be bound by keyword: {name}"
                    if name in all_names
                    else f"Unknown keyword argument: {name}"
                )
                problems.append((entry["ordinal"], keyword_id, reason))
                continue
            source_parameters[("keyword", position)] = parameter_ordinal
            if parameter_arguments[parameter_ordinal] is not None:
                prior = parameter_sources[parameter_ordinal]
                prior_entry = (
                    entries[prior]
                    if isinstance(prior, int) and 0 <= prior < len(entries)
                    else None
                )
                reason = (
                    f"Keyword argument duplicates a positionally bound parameter: {name}"
                    if prior_entry and prior_entry["kind"] == "positional"
                    else f"Duplicate keyword argument: {name}"
                )
                problems.append((entry["ordinal"], keyword_id, reason))
                continue
            parameter_arguments[parameter_ordinal] = keyword["fields"]["value"]
            parameter_sources[parameter_ordinal] = entry["ordinal"]

        argument_bindings: list[dict[str, Any]] = []
        for entry in entries:
            _check(self.cancellation)
            parameter_ordinal = source_parameters.get(
                (entry["kind"], entry["position"])
            )
            valid = (
                isinstance(parameter_ordinal, int)
                and 0 <= parameter_ordinal < len(parameters)
            )
            argument_id = entry["argument"]
            argument_bindings.append(
                {
                    "source_argument_node_id": argument_id,
                    "keyword_node_id": entry["keyword"],
                    "keyword_name": entry["name"],
                    "source_ordinal": entry["ordinal"],
                    "parameter_node_id": (
                        parameter_node_ids[parameter_ordinal] if valid else None
                    ),
                    "parameter_name": (
                        parameter_names_tuple[parameter_ordinal] if valid else None
                    ),
                    "parameter_kind": (
                        parameter_kinds[parameter_ordinal] if valid else None
                    ),
                    "parameter_ordinal": parameter_ordinal,
                    "category": self._actual_category(argument_id),
                    "expected_category": (
                        parameter_categories_tuple[parameter_ordinal]
                        if valid
                        else None
                    ),
                }
            )
        missing = [
            parameter_names_tuple[index]
            for index, value in enumerate(parameter_arguments)
            if value is None
        ]
        mismatches = [
            item
            for item in argument_bindings
            if item["parameter_ordinal"] is not None
            and item["expected_category"] is not None
            and item["category"] != item["expected_category"]
            and parameter_sources[item["parameter_ordinal"]]
            == item["source_ordinal"]
        ]
        keyword_only_coverage = all(
            parameter_arguments[index] is not None
            for index in range(positional_capacity, len(parameters))
        )
        coverage = bool(
            not unpacking
            and not excess
            and not problems
            and not missing
            and len(entries) == len(parameters)
        )
        code = reason = rejection = None
        if unpacking:
            _, rejection = min(unpacking, key=lambda item: item[0])
            code, reason = "PYC2910", (
                "Starred and unpacked arguments are unsupported by the exact "
                "required keyword-only profile"
            )
        elif excess:
            _, rejection = min(excess, key=lambda item: item[0])
            code, reason = "PYC2904", (
                "Positional argument count exceeds the positional portion of "
                "the target signature"
            )
        elif problems:
            _, rejection, reason = min(problems, key=lambda item: item[0])
            code = "PYC2912"
        elif missing:
            rejection, code, reason = call_id, "PYC2904", (
                "Every target parameter must be supplied exactly once; missing: "
                + ", ".join(missing)
            )
        elif mismatches:
            mismatch = mismatches[0]
            rejection = (
                mismatch["keyword_node_id"]
                or mismatch["source_argument_node_id"]
            )
            code, reason = "PYC2905", (
                "Argument representation does not match parameter "
                f"{mismatch['parameter_name']}"
            )
        supported = code is None and coverage and keyword_only_coverage
        if code is None and not supported:
            rejection, code, reason = call_id, "PYC2904", (
                "Arguments do not exactly cover the required keyword-only signature"
            )
        source_ids = [item["source_argument_node_id"] for item in argument_bindings]
        source_categories = [item["category"] for item in argument_bindings]
        self.call_target_contracts[call_id] = {
            "call_node_id": call_id,
            "callee_node_id": fields["func"],
            "target_function_node_id": target_id,
            "target_binding_id": target_binding_id,
            "target_name": target_name,
            "argument_node_ids": source_ids,
            "argument_categories": source_categories,
            "parameter_categories": list(parameter_categories_tuple),
            "return_category": return_contract[0],
            "evaluation_order": source_ids,
            "arguments_evaluated_once": True,
            "ownership_boundary": ownership_boundary,
            "annotation_evidence": annotation_evidence + [return_annotation_id],
        }
        return {
            "binding_id": keyword_only_call_binding_id(call_id, target_binding_id),
            "call_node_id": call_id,
            "callee_node_id": fields["func"],
            "target_function_node_id": target_id,
            "target_binding_id": target_binding_id,
            "target_name": target_name,
            "positional_only_parameter_count": len(posonly),
            "positional_or_keyword_parameter_count": len(positional),
            "keyword_only_parameter_count": len(keyword_only),
            "parameter_node_ids": list(parameter_node_ids),
            "parameter_names": list(parameter_names_tuple),
            "parameter_kinds": list(parameter_kinds),
            "parameter_categories": list(parameter_categories_tuple),
            "required_keyword_only_parameter_node_ids": list(
                parameter_node_ids[positional_capacity:]
            ),
            "required_keyword_only_parameter_names": list(
                parameter_names_tuple[positional_capacity:]
            ),
            "required_keyword_only_parameter_categories": list(
                parameter_categories_tuple[positional_capacity:]
            ),
            "positional_argument_node_ids": list(positional_ids),
            "keyword_node_ids": list(keyword_ids),
            "keyword_names": [
                item.get("fields", {}).get("arg") for item in keyword_nodes
            ],
            "keyword_value_node_ids": [
                item.get("fields", {}).get("value") for item in keyword_nodes
            ],
            "argument_bindings": argument_bindings,
            "source_argument_node_ids": source_ids,
            "source_argument_categories": source_categories,
            "source_to_parameter_ordinals": [
                item["parameter_ordinal"] for item in argument_bindings
            ],
            "parameter_argument_node_ids": parameter_arguments,
            "parameter_to_source_ordinals": parameter_sources,
            "evaluation_order": source_ids,
            "arguments_evaluated_once": True,
            "parameter_coverage_exact": coverage,
            "keyword_only_coverage_exact": keyword_only_coverage,
            "lowering_shape": KEYWORD_ONLY_CALL_LOWERING_SHAPE,
            "allocation_model": "none",
            "cleanup_model": "none",
            "runtime_binding_failure": (
                "proved-absent" if supported else "compile-time-rejected"
            ),
            "supported": supported,
            "diagnostic_code": code,
            "reason": reason,
            "rejection_node_id": rejection,
        }

    def expected_call_target(self, fact: Mapping[str, Any]) -> dict[str, Any]:
        contract = dict(self.call_target_contracts[fact["call_node_id"]])
        contract.update(
            {
                "resolution": (
                    "understood-source-function"
                    if fact["supported"]
                    else "ineligible-source-function"
                ),
                "supported": fact["supported"],
                "diagnostic_code": fact["diagnostic_code"],
                "reason": fact["reason"],
            }
        )
        return contract

    def _annotation_contract(
        self,
        annotation_id: Any,
    ) -> tuple[str, str, str, str, str]:
        annotation = self.nodes.get(annotation_id)
        fields = annotation.get("fields") if isinstance(annotation, dict) else None
        spelling = fields.get("id") if isinstance(fields, dict) else None
        contract = _ANNOTATION_CONTRACTS.get(spelling)
        if (
            not isinstance(annotation_id, str)
            or not isinstance(annotation, dict)
            or annotation.get("kind") != "Name"
            or contract is None
        ):
            raise _MalformedKeywordOnlyEvidence(
                "keyword-only annotation evidence is malformed"
            )
        return contract

    def _actual_category(self, node_id: str) -> str:
        independent = self._source_category(node_id, frozenset())
        recorded = self.categories.get(node_id, "unknown")
        if independent is not None and recorded != independent:
            raise _MalformedKeywordOnlyEvidence(
                "keyword-only actual category disagrees with Python IR annotations"
            )
        return independent if independent is not None else recorded

    def _source_category(
        self,
        node_id: str,
        active: frozenset[str],
    ) -> str | None:
        if node_id in active:
            return None
        node = self.nodes.get(node_id)
        fields = node.get("fields") if isinstance(node, dict) else None
        if not isinstance(node, dict) or not isinstance(fields, dict):
            return None
        kind = node.get("kind")
        if kind == "Constant":
            value = fields.get("value")
            if isinstance(value, bool):
                return "boolean-like"
            if isinstance(value, int):
                return "integer-like"
            if isinstance(value, float) or (
                _sequence(value)
                and tuple(value[:2]) == ("unsupported-python-value", "float-nonfinite")
            ):
                return "floating-like"
            if isinstance(value, str):
                return "string-like"
            return None
        if kind == "Name":
            binding_id = self.occurrence_bindings.get(node_id)
            declaration_id = self.declaration_by_binding.get(binding_id)
            declaration = self.nodes.get(declaration_id)
            declaration_fields = (
                declaration.get("fields")
                if isinstance(declaration, dict)
                else None
            )
            if (
                isinstance(declaration, dict)
                and declaration.get("kind") == "arg"
                and isinstance(declaration_fields, dict)
            ):
                annotation_id = declaration_fields.get("annotation")
                annotation = self.nodes.get(annotation_id)
                annotation_fields = (
                    annotation.get("fields")
                    if isinstance(annotation, dict)
                    else None
                )
                spelling = (
                    annotation_fields.get("id")
                    if isinstance(annotation_fields, dict)
                    and annotation.get("kind") == "Name"
                    else None
                )
                contract = _ANNOTATION_CONTRACTS.get(spelling)
                return contract[0] if contract is not None else None
            return "callable-like" if (
                isinstance(declaration, dict)
                and declaration.get("kind") == "FunctionDef"
            ) else None
        next_active = active | {node_id}
        if kind == "Call":
            callee_binding = self.occurrence_bindings.get(fields.get("func"))
            target_id = self.declaration_by_binding.get(callee_binding)
            target = self.nodes.get(target_id)
            target_fields = target.get("fields") if isinstance(target, dict) else None
            if (
                isinstance(target, dict)
                and target.get("kind") == "FunctionDef"
                and isinstance(target_fields, dict)
            ):
                annotation_id = target_fields.get("returns")
                annotation = self.nodes.get(annotation_id)
                annotation_fields = (
                    annotation.get("fields")
                    if isinstance(annotation, dict)
                    else None
                )
                spelling = (
                    annotation_fields.get("id")
                    if isinstance(annotation_fields, dict)
                    and annotation.get("kind") == "Name"
                    else None
                )
                contract = _ANNOTATION_CONTRACTS.get(spelling)
                return contract[0] if contract is not None else None
            return None
        if kind == "UnaryOp":
            operand = self._source_category(fields.get("operand"), next_active)
            operator = self.nodes.get(fields.get("op"), {}).get("kind")
            if operator == "Not" and operand in {
                "integer-like",
                "floating-like",
                "boolean-like",
            }:
                return "boolean-like"
            if operator in {"UAdd", "USub"} and operand in {
                "integer-like",
                "floating-like",
            }:
                return operand
            return None
        if kind == "BoolOp":
            values = tuple(
                self._source_category(item, next_active)
                for item in fields.get("values", ())
            )
            return "boolean-like" if values and all(
                item == "boolean-like" for item in values
            ) else None
        if kind == "Compare":
            values = (
                self._source_category(fields.get("left"), next_active),
                *(
                    self._source_category(item, next_active)
                    for item in fields.get("comparators", ())
                ),
            )
            return "boolean-like" if (
                values
                and None not in values
                and len(set(values)) == 1
                and values[0]
                in {"integer-like", "floating-like", "boolean-like"}
            ) else None
        if kind == "BinOp":
            left = self._source_category(fields.get("left"), next_active)
            right = self._source_category(fields.get("right"), next_active)
            operator = self.nodes.get(fields.get("op"), {}).get("kind")
            if operator == "Div":
                return (
                    "floating-like"
                    if left == right == "floating-like"
                    else None
                )
            if left == right and left in {
                "integer-like",
                "floating-like",
                "string-like",
            }:
                return left
        return None

    def _merge(
        self,
        positional: list[dict[str, Any]],
        keywords: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        left = right = 0
        while left < len(positional) and right < len(keywords):
            _check(self.cancellation)
            if self._source_key(
                positional[left]["order_node_id"]
            ) <= self._source_key(keywords[right]["order_node_id"]):
                result.append(positional[left])
                left += 1
            else:
                result.append(keywords[right])
                right += 1
        result.extend(positional[left:])
        result.extend(keywords[right:])
        return result

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


def _provenance_ids(fact: dict[str, Any]) -> list[str]:
    values = (
        fact["call_node_id"],
        fact["callee_node_id"],
        fact["target_function_node_id"],
        *fact["parameter_node_ids"],
        *fact["positional_argument_node_ids"],
        *fact["keyword_node_ids"],
        *fact["keyword_value_node_ids"],
    )
    return list(dict.fromkeys(values))


def _validate_plans(
    payload: Mapping[str, Any],
    expected: Mapping[str, dict[str, Any]],
    cumulatively_ineligible_target_function_node_ids: frozenset[str],
    cancellation: Any,
) -> tuple[bool, str]:
    plans = payload.get("rule_plans")
    if not isinstance(plans, list):
        return False, "keyword-only RulePlans are malformed"
    feature_plans: dict[str, dict[str, Any]] = {}
    for plan in plans:
        _check(cancellation)
        if not isinstance(plan, dict):
            return False, "keyword-only RulePlans are malformed"
        if plan.get("rule_id") != KEYWORD_ONLY_CALL_RULE_ID:
            continue
        source_id = plan.get("source_node_id")
        if not isinstance(source_id, str) or source_id in feature_plans:
            return False, "keyword-only RulePlans have invalid coverage"
        feature_plans[source_id] = plan
    tables = payload.get("fact_tables")
    if not isinstance(tables, list):
        return False, "keyword-only RulePlan dependencies are malformed"
    call_table = next(
        (
            item
            for item in tables
            if isinstance(item, dict)
            and item.get("table_id") == "call-target-facts"
        ),
        None,
    )
    if not isinstance(call_table, dict):
        return False, "keyword-only call-target facts are absent"
    calls = {
        item.get("call_node_id"): item
        for item in _record_values(call_table, cancellation)
    }
    supported = {
        call_id: fact
        for call_id, fact in expected.items()
        if fact["supported"] and calls.get(call_id, {}).get("supported") is True
    }
    if set(feature_plans) != set(supported):
        return False, "keyword-only RulePlans do not exactly cover supported facts"
    for call_id, fact in supported.items():
        _check(cancellation)
        plan = feature_plans[call_id]
        feature_facts = {
            f"keyword-only-call-binding:{fact['binding_id']}",
            f"keyword-only-call:{call_id}",
            f"keyword-only-call-target:{fact['target_binding_id']}",
            f"keyword-only-parameter-count:{fact['keyword_only_parameter_count']}",
            f"keyword-only-source-argument-count:{len(fact['source_argument_node_ids'])}",
            f"keyword-only-call-lowering-shape:{fact['lowering_shape']}",
            *(
                f"argument-category:{category}"
                for category in fact["source_argument_categories"]
            ),
        }
        facts_used = plan.get("facts_used")
        obligations = plan.get("semantic_obligations")
        if (
            plan.get("rule_version") != KEYWORD_ONLY_CALL_RULE_VERSION
            or plan.get("support_state") != "SupportedDirect"
            or plan.get("helper_requirements") != []
            or plan.get("unresolved_obligations") != []
            or not isinstance(facts_used, list)
            or not feature_facts.issubset(set(facts_used))
            or not isinstance(obligations, list)
            or obligations[: len(KEYWORD_ONLY_CALL_OBLIGATIONS)]
            != list(KEYWORD_ONLY_CALL_OBLIGATIONS)
            or plan.get("resolved_obligations") != obligations
        ):
            return False, "keyword-only RulePlan does not close its exact proof"
        explanation = plan.get("explanation_tokens")
        if (
            not isinstance(explanation, list)
            or "required-keyword-only-call-binding" not in explanation
            or fact["lowering_shape"] not in explanation
        ):
            return False, "keyword-only RulePlan explanation is incomplete"
    return _validate_declaration_plans(
        payload,
        plans,
        cumulatively_ineligible_target_function_node_ids,
        cancellation,
    )


def _validate_declaration_plans(
    payload: Mapping[str, Any],
    plans: list[dict[str, Any]],
    cumulatively_ineligible_target_function_node_ids: frozenset[str],
    cancellation: Any,
) -> tuple[bool, str]:
    """Require explicit plan evidence even when an eligible declaration is uncalled."""

    module = payload.get("python_ir")
    node_values = module.get("nodes") if isinstance(module, dict) else None
    tables = payload.get("fact_tables")
    if not isinstance(node_values, list) or not isinstance(tables, list):
        return False, "keyword-only declaration evidence dependencies are malformed"
    nodes = {
        node.get("node_id"): node
        for node in node_values
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }
    signature_table = next(
        (
            table
            for table in tables
            if isinstance(table, dict)
            and table.get("table_id") == "function-signature-facts"
        ),
        None,
    )
    if not isinstance(signature_table, dict):
        return False, "keyword-only declaration signature facts are absent"
    eligible_signatures = {
        signature.get("function_node_id"): signature
        for signature in _record_values(signature_table, cancellation)
        if signature.get("eligible") is True
    }
    plans_by_source: dict[str, list[dict[str, Any]]] = {}
    for plan in plans:
        _check(cancellation)
        source_id = plan.get("source_node_id")
        if isinstance(source_id, str):
            plans_by_source.setdefault(source_id, []).append(plan)
    for function_id, signature in eligible_signatures.items():
        _check(cancellation)
        if function_id in cumulatively_ineligible_target_function_node_ids:
            continue
        function = nodes.get(function_id)
        function_fields = (
            function.get("fields") if isinstance(function, dict) else None
        )
        arguments = (
            nodes.get(function_fields.get("args"))
            if isinstance(function_fields, dict)
            else None
        )
        fields = arguments.get("fields") if isinstance(arguments, dict) else None
        if not isinstance(fields, dict):
            return False, "keyword-only declaration Python IR is malformed"
        keyword_only_ids = fields.get("kwonlyargs")
        keyword_defaults = fields.get("kw_defaults")
        if (
            not _sequence(keyword_only_ids)
            or not keyword_only_ids
            or not _sequence(keyword_defaults)
            or tuple(keyword_defaults) != (None,) * len(keyword_only_ids)
            or fields.get("defaults")
            or fields.get("vararg")
            or fields.get("kwarg")
        ):
            continue
        keyword_only_names: list[str] = []
        for parameter_id in keyword_only_ids:
            _check(cancellation)
            parameter = nodes.get(parameter_id)
            name = (
                parameter.get("fields", {}).get("arg")
                if isinstance(parameter, dict)
                else None
            )
            if (
                not isinstance(parameter_id, str)
                or not isinstance(name, str)
                or not name
            ):
                return False, "keyword-only declaration parameter evidence is malformed"
            keyword_only_names.append(name)
        expected_parameter_ids = (
            tuple(fields.get("posonlyargs", ()))
            + tuple(fields.get("args", ()))
            + tuple(keyword_only_ids)
        )
        signature_parameters = signature.get("parameters")
        if _sequence(signature_parameters):
            for _ in signature_parameters:
                _check(cancellation)
        if (
            not _sequence(signature_parameters)
            or tuple(
                item.get("parameter_node_id")
                for item in signature_parameters
                if isinstance(item, dict)
            )
            != expected_parameter_ids
            or len(signature_parameters) != len(expected_parameter_ids)
        ):
            return False, "keyword-only declaration signature facts are incomplete"
        declaration_plans = plans_by_source.get(function_id, ())
        if len(declaration_plans) != 1:
            return False, "keyword-only declaration lacks exactly one RulePlan"
        plan = declaration_plans[0]
        required_facts = {
            f"keyword-only-signature:{function_id}",
            f"keyword-only-parameter-count:{len(keyword_only_ids)}",
            "keyword-only-c-interface:mode-erased-after-static-binding",
            *(
                f"keyword-only-parameter:{ordinal}:{parameter_id}:{name}"
                for ordinal, (parameter_id, name) in enumerate(
                    zip(keyword_only_ids, keyword_only_names)
                )
            ),
        }
        declaration_obligations = [
            "required-keyword-only-parameters-exact",
            "keyword-only-parameter-kinds-preserved",
            "c-interface-mode-erasure-after-static-binding",
            "defaults-and-variadics-absent",
        ]
        declaration_explanation = [
            "required-keyword-only-signature",
            str(len(keyword_only_ids)),
            "c-interface-mode-erasure",
            "after-static-binding",
        ]
        facts_used = plan.get("facts_used")
        obligations = plan.get("semantic_obligations")
        explanation = plan.get("explanation_tokens")
        if (
            plan.get("support_state") != "SupportedDirect"
            or not isinstance(facts_used, list)
            or not required_facts.issubset(facts_used)
            or not isinstance(obligations, list)
            or obligations[-len(declaration_obligations) :]
            != declaration_obligations
            or plan.get("resolved_obligations") != obligations
            or plan.get("unresolved_obligations") != []
            or not isinstance(explanation, list)
            or explanation[-len(declaration_explanation) :]
            != declaration_explanation
        ):
            return False, "keyword-only declaration RulePlan evidence is incomplete"
    return True, ""


def validate_keyword_only_call_binding_facts(
    payload: Mapping[str, Any],
    tables: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    *,
    expected_fact_schema: str = KEYWORD_ONLY_CALL_FACT_SCHEMA,
    require_table: bool = True,
    require_plans: bool = True,
    ignored_call_node_ids: frozenset[str] = frozenset(),
    cumulatively_ineligible_target_function_node_ids: frozenset[str] = frozenset(),
    cancellation: Any = None,
) -> tuple[bool, str]:
    """Fail closed on malformed or producer-inconsistent feature evidence."""

    _check(cancellation)
    if not isinstance(payload, Mapping):
        return False, "keyword-only validation payload is malformed"
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
        return False, "keyword-only validation exclusions are malformed"
    try:
        raw_tables = tables if tables is not None else payload.get("fact_tables")
        if not _sequence(raw_tables) or any(
            not isinstance(item, dict) for item in raw_tables
        ):
            return False, "keyword-only fact tables are malformed"
        table_values = tuple(raw_tables)
        feature_table = next(
            (
                item
                for item in table_values
                if item.get("table_id") == KEYWORD_ONLY_CALL_TABLE_ID
            ),
            None,
        )
        if feature_table is None:
            return (
                (False, "keyword-only call binding fact table is absent")
                if require_table
                else (True, "")
            )
        if (
            feature_table.get("schema_version") != expected_fact_schema
            or feature_table.get("producer_stage") != "analysis.plan"
            or feature_table.get("key_domain") != KEYWORD_ONLY_CALL_KEY_DOMAIN
            or feature_table.get("completeness") != "complete"
            or tuple(feature_table.get("invalidation_dependencies", ()))
            != KEYWORD_ONLY_CALL_TABLE_DEPENDENCIES
        ):
            return False, "keyword-only call binding fact schema is invalid"
        table_map: dict[str, dict[str, Any]] = {}
        for item in table_values:
            table_id = item.get("table_id")
            if not isinstance(table_id, str) or table_id in table_map:
                return False, "keyword-only fact-table identities are malformed"
            table_map[table_id] = item
        required = {
            "binding-facts",
            "function-signature-facts",
            "value-category-facts",
            "call-target-facts",
        }
        if not required.issubset(table_map):
            return False, "keyword-only proof dependencies are absent"
        module = payload.get("python_ir")
        node_values = module.get("nodes") if isinstance(module, dict) else None
        if not isinstance(node_values, list):
            return False, "keyword-only validation lacks normalized Python IR"
        nodes: dict[str, dict[str, Any]] = {}
        node_order: dict[str, int] = {}
        for ordinal, node in enumerate(node_values):
            _check(cancellation)
            node_id = node.get("node_id") if isinstance(node, dict) else None
            if not isinstance(node_id, str) or node_id in nodes:
                return False, "keyword-only Python IR identities are invalid"
            nodes[node_id] = node
            node_order[node_id] = ordinal
        occurrence_bindings: dict[str, str] = {}
        binding_by_declaration: dict[str, str] = {}
        declaration_by_binding: dict[str, str] = {}
        for binding in _record_values(table_map["binding-facts"], cancellation):
            binding_id = binding.get("binding_id")
            declaration_id = binding.get("declaration_node_id")
            binding_kind = binding.get("binding_kind")
            occurrences = binding.get("occurrence_node_ids")
            if (
                not isinstance(binding_id, str)
                or not isinstance(declaration_id, str)
                or declaration_id not in nodes
                or binding_id in declaration_by_binding
                or not _sequence(occurrences)
            ):
                raise _MalformedKeywordOnlyEvidence(
                    "keyword-only binding facts are malformed"
                )
            declaration_by_binding[binding_id] = declaration_id
            if binding_kind in {"function", "parameter"}:
                if declaration_id in binding_by_declaration:
                    raise _MalformedKeywordOnlyEvidence(
                        "keyword-only declaration binding conflicts"
                    )
                binding_by_declaration[declaration_id] = binding_id
            for occurrence in occurrences:
                if not isinstance(occurrence, str):
                    raise _MalformedKeywordOnlyEvidence(
                        "keyword-only binding occurrence is malformed"
                    )
                prior = occurrence_bindings.get(occurrence)
                if prior is not None and prior != binding_id:
                    raise _MalformedKeywordOnlyEvidence(
                        "keyword-only occurrence binding conflicts"
                    )
                occurrence_bindings[occurrence] = binding_id
        signatures: dict[str, dict[str, Any]] = {}
        for signature in _record_values(
            table_map["function-signature-facts"],
            cancellation,
        ):
            binding_id = signature.get("binding_id")
            if not isinstance(binding_id, str) or binding_id in signatures:
                raise _MalformedKeywordOnlyEvidence(
                    "keyword-only signatures are malformed"
                )
            signatures[binding_id] = signature
        categories: dict[str, str] = {}
        records = table_map["value-category-facts"].get("records")
        if not isinstance(records, list):
            raise _MalformedKeywordOnlyEvidence(
                "keyword-only categories are malformed"
            )
        for record in records:
            _check(cancellation)
            key = record.get("key") if isinstance(record, dict) else None
            if not isinstance(key, str) or key in categories:
                raise _MalformedKeywordOnlyEvidence(
                    "keyword-only category record is malformed"
                )
            categories[key] = _category(record.get("value"))
        reconstruction = _IndependentKeywordOnlyReconstruction(
            node_values=node_values,
            nodes=nodes,
            node_order=node_order,
            occurrence_bindings=occurrence_bindings,
            binding_by_declaration=binding_by_declaration,
            declaration_by_binding=declaration_by_binding,
            signatures=signatures,
            categories=categories,
            ignored_call_node_ids=frozenset(ignored_call_node_ids),
            cancellation=cancellation,
        )
        expected = reconstruction.expected()
        for call_id, fact in tuple(expected.items()):
            _check(cancellation)
            if (
                fact["supported"]
                and fact["target_function_node_id"]
                in cumulatively_ineligible_target_function_node_ids
            ):
                expected[call_id] = {
                    **fact,
                    "runtime_binding_failure": "compile-time-rejected",
                    "supported": False,
                    "diagnostic_code": (
                        CUMULATIVE_KEYWORD_ONLY_TARGET_DIAGNOSTIC_CODE
                    ),
                    "reason": CUMULATIVE_KEYWORD_ONLY_TARGET_REASON,
                    "rejection_node_id": fact["target_function_node_id"],
                }
        records = feature_table.get("records")
        if not isinstance(records, list):
            return False, "keyword-only binding records are malformed"
        keys = [
            record.get("key") if isinstance(record, dict) else None
            for record in records
        ]
        if (
            any(not isinstance(key, str) for key in keys)
            or any(keys[index - 1] >= keys[index] for index in range(1, len(keys)))
        ):
            return False, "keyword-only binding keys are not unique and sorted"
        found: dict[str, dict[str, Any]] = {}
        provenance: dict[str, Any] = {}
        for record in records:
            key = record["key"]
            value = record.get("value")
            if not isinstance(value, dict) or value.get("call_node_id") != key:
                return False, "keyword-only binding record identity is malformed"
            found[key] = value
            provenance[key] = record.get("provenance")
        if set(found) != set(expected):
            return False, "keyword-only facts do not exactly cover candidates"
        call_targets: dict[str, dict[str, Any]] = {}
        for item in _record_values(table_map["call-target-facts"], cancellation):
            _check(cancellation)
            call_id = item.get("call_node_id")
            if not isinstance(call_id, str) or call_id in call_targets:
                raise _MalformedKeywordOnlyEvidence(
                    "keyword-only call-target identities are malformed"
                )
            call_targets[call_id] = item
        for call_id, fact in expected.items():
            _check(cancellation)
            if found[call_id] != fact:
                return False, (
                    "keyword-only fact disagrees with independent reconstruction"
                )
            proof = provenance.get(call_id)
            if (
                not isinstance(proof, dict)
                or proof.get("source_node_ids") != _provenance_ids(fact)
                or proof.get("evidence")
                != list(KEYWORD_ONLY_CALL_PROVENANCE_EVIDENCE)
            ):
                return False, "keyword-only fact provenance is incomplete"
            target = call_targets.get(call_id)
            if target != reconstruction.expected_call_target(fact):
                return False, (
                    "keyword-only fact disagrees with call-target evidence"
                )
        if require_plans:
            valid, reason = _validate_plans(
                payload,
                expected,
                frozenset(cumulatively_ineligible_target_function_node_ids),
                cancellation,
            )
            if not valid:
                return valid, reason
        return True, ""
    except _MalformedKeywordOnlyEvidence as exc:
        return False, str(exc) or "keyword-only evidence is malformed"
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return False, "keyword-only evidence is malformed"


__all__ = ["validate_keyword_only_call_binding_facts"]
