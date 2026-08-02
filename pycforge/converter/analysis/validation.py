from __future__ import annotations
from collections import deque
import hashlib
import re
from typing import Any

from pycforge.converter.contracts.configuration import (
    DEFAULT_MODULE_POLICY,
    DEFAULT_NUMERIC_POLICY,
    DEFAULT_RECORD_POLICY,
    PHASE12_MODULE_POLICY,
)
from pycforge.converter.contracts.identifiers import (
    C11_EXTERNAL_IDENTIFIERS,
    C_KEYWORDS,
    TARGET_RESERVED_NAMES,
)
from pycforge.converter.contracts.versions import (
    CONDITIONAL_FACT_SCHEMA,
    CONVERSION_PLAN_SCHEMA,
    KEYWORD_CALL_FACT_SCHEMA,
    KEYWORD_ONLY_CALL_FACT_SCHEMA,
    MODULE_FACT_SCHEMA,
    NUMERIC_FACT_SCHEMA,
    PHASE14A_CONVERSION_PLAN_SCHEMA,
    PHASE14B_CONVERSION_PLAN_SCHEMA,
    PHASE14C_CONVERSION_PLAN_SCHEMA,
    PHASE13_CONVERSION_PLAN_SCHEMA,
    PHASE12_CONVERSION_PLAN_SCHEMA,
    RECORD_FACT_SCHEMA,
)
from pycforge.converter.conditional_regions.validation import (
    validate_conditional_region_facts,
)
from pycforge.converter.keyword_calls.validation import (
    validate_keyword_call_binding_facts,
)
from pycforge.converter.keyword_calls.model import KeywordCallValidationCanceled
from pycforge.converter.keyword_only_calls.validation import (
    validate_keyword_only_call_binding_facts,
)
from pycforge.converter.ir.python_ir import python_ir_reference_ids


_HELPER_REQUIREMENT = re.compile(
    r"^pycf(?:\.[a-z][a-z0-9_]*)+@(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_RECORD_TABLE_CONTRACTS = {
    "record-definition-facts": ("record-id", "record_id"),
    "record-field-facts": ("record-field-id", "field_id"),
    "record-initializer-facts": ("record-initializer-id", "initializer_id"),
    "record-instance-facts": ("record-instance-id", "instance_id"),
    "record-binding-facts": ("binding-id", "binding_id"),
    "record-access-facts": ("attribute-node-id", "access_node_id"),
}

_RECORD_FIELD_CATEGORIES = {
    "integer-like": "int",
    "floating-like": "float",
    "boolean-like": "bool",
}


def _cumulatively_ineligible_target_function_node_ids(
    payload: dict[str, Any],
    tables: list[dict[str, Any]],
    cancellation: Any = None,
) -> frozenset[str]:
    def check_cancellation() -> None:
        if cancellation is not None and bool(
            getattr(cancellation, "is_canceled", False)
        ):
            raise KeywordCallValidationCanceled

    check_cancellation()
    table_map = {
        table.get("table_id"): table
        for table in tables
        if isinstance(table, dict) and isinstance(table.get("table_id"), str)
    }

    def values(table_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            record["value"]
            for record in table_map.get(table_id, {}).get("records", ())
            if isinstance(record, dict) and isinstance(record.get("value"), dict)
        )

    signatures = {
        item.get("function_node_id"): item
        for item in values("function-signature-facts")
        if isinstance(item.get("function_node_id"), str)
    }
    returns = {
        item.get("function_node_id"): item
        for item in values("return-path-facts")
        if isinstance(item.get("function_node_id"), str)
    }
    locals_by_function = {
        item.get("function_node_id"): item
        for item in values("local-declaration-facts")
        if isinstance(item.get("function_node_id"), str)
    }
    calls = values("call-target-facts")
    graph_values = values("call-graph-facts")
    recursive_functions = set(
        graph_values[0].get("recursive_function_node_ids", ())
        if graph_values
        else ()
    )

    module = payload.get("python_ir")
    node_values = module.get("nodes") if isinstance(module, dict) else None
    if not isinstance(node_values, list):
        return frozenset(signatures)
    nodes = {
        node.get("node_id"): node
        for node in node_values
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }
    parent_by_node: dict[str, str] = {}
    for parent in node_values:
        check_cancellation()
        if not isinstance(parent, dict) or parent.get("node_id") not in nodes:
            continue
        for field, value in parent.get("fields", {}).items():
            check_cancellation()
            for child in python_ir_reference_ids(
                parent.get("kind"),
                field,
                value,
                nodes,
            ):
                parent_by_node.setdefault(child, parent["node_id"])

    owner_cache: dict[str, str | None] = {}

    def owner(node_id: str) -> str | None:
        cached = owner_cache.get(node_id)
        if cached is not None or node_id in owner_cache:
            return cached
        current = node_id
        path: list[str] = []
        seen: set[str] = set()
        while current not in seen:
            check_cancellation()
            seen.add(current)
            path.append(current)
            if current in owner_cache:
                result = owner_cache[current]
                break
            parent_id = parent_by_node.get(current)
            if parent_id is None:
                result = None
                break
            if nodes.get(parent_id, {}).get("kind") == "FunctionDef":
                result = parent_id
                break
            current = parent_id
        else:
            result = None
        for item in path:
            owner_cache[item] = result
        return result

    calls_by_owner: dict[str, list[dict[str, Any]]] = {}
    callers_by_target: dict[str, list[str]] = {}
    for call in calls:
        check_cancellation()
        call_node_id = call.get("call_node_id")
        if not isinstance(call_node_id, str):
            continue
        function_id = owner(call_node_id)
        if function_id is not None:
            calls_by_owner.setdefault(function_id, []).append(call)
            target_function_id = call.get("target_function_node_id")
            if target_function_id in signatures:
                callers_by_target.setdefault(target_function_id, []).append(
                    function_id
                )

    local_failure_fields = (
        "use_before_binding_node_ids",
        "loop_target_escape_node_ids",
        "first_definitions_in_control_node_ids",
        "representation_conflict_node_ids",
        "loop_target_rebind_node_ids",
        "loop_target_mutation_node_ids",
    )
    eligible: dict[str, bool] = {}
    for function_id, signature in signatures.items():
        check_cancellation()
        path = returns.get(function_id, {})
        local = locals_by_function.get(function_id, {})
        eligible[function_id] = bool(
            signature.get("eligible") is True
            and path.get("compatible") is True
            and path.get("fallthrough_possible") is False
            and local.get("valid") is True
            and not any(local.get(field) for field in local_failure_fields)
            and function_id not in recursive_functions
            and all(
                call.get("supported") is True
                for call in calls_by_owner.get(function_id, ())
            )
        )

    pending = deque(
        function_id
        for function_id, supported in eligible.items()
        if not supported
    )
    while pending:
        check_cancellation()
        target = pending.popleft()
        for caller in callers_by_target.get(target, ()):
            if eligible.get(caller, False):
                eligible[caller] = False
                pending.append(caller)
    return frozenset(
        function_id for function_id, supported in eligible.items() if not supported
    )


def _module_function_name(module_id: str, source_name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", source_name)
    if not base or not (base[0].isalpha() or base[0] == "_"):
        base = "py_" + base
    if base.startswith("_"):
        base = "py" + base
    if (
        base in C_KEYWORDS
        or base in TARGET_RESERVED_NAMES
        or base in C11_EXTERNAL_IDENTIFIERS
        or base.startswith(("pycf_", "pycm_"))
    ):
        base = "py_" + base
    digest = hashlib.sha256(f"{module_id}.{source_name}".encode("utf-8")).hexdigest()
    module_token = module_id.replace("_", "_u").replace(".", "_d")
    return f"pycm_{digest}__{module_token}__{base}"


def _dependency_first_order(
    module_ids: set[str],
    edges: set[tuple[str, str]],
) -> list[str] | None:
    dependencies = {module_id: set() for module_id in module_ids}
    dependents = {module_id: set() for module_id in module_ids}
    for importer, target in edges:
        if importer not in dependencies or target not in dependencies or importer == target:
            return None
        dependencies[importer].add(target)
        dependents[target].add(importer)
    ready = sorted(
        (module_id for module_id, values in dependencies.items() if not values),
        key=lambda item: item.encode("utf-8"),
    )
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for dependent in sorted(dependents[current], key=lambda item: item.encode("utf-8")):
            dependencies[dependent].discard(current)
            if not dependencies[dependent] and dependent not in ready and dependent not in order:
                ready.append(dependent)
                ready.sort(key=lambda item: item.encode("utf-8"))
    return order if len(order) == len(module_ids) else None


def _validate_record_fact_tables(
    payload: dict[str, Any],
    tables: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Validate the closed Phase 13 immutable static-record evidence.

    This validator intentionally consumes only serialized facts and normalized
    Python IR.  It therefore acts as an independent boundary check between
    analysis and lowering rather than trusting analyzer implementation types.
    """

    if payload.get("record_policy_version") != DEFAULT_RECORD_POLICY:
        return False, "Phase 13 conversion plan has an unknown record_policy_version"

    table_by_id = {table.get("table_id"): table for table in tables}
    if not set(_RECORD_TABLE_CONTRACTS).issubset(table_by_id):
        return False, "Phase 13 conversion plan omits required static-record fact tables"
    record_tables = {
        table_id: table_by_id[table_id] for table_id in _RECORD_TABLE_CONTRACTS
    }
    for table_id, (key_domain, key_field) in _RECORD_TABLE_CONTRACTS.items():
        table = record_tables[table_id]
        if (
            table.get("schema_version") != RECORD_FACT_SCHEMA
            or table.get("producer_stage") != "analysis.plan"
            or table.get("key_domain") != key_domain
            or table.get("completeness") != "complete"
        ):
            return False, f"Phase 13 {table_id} contract identity is invalid"
        for record in table.get("records", ()):
            value = record.get("value")
            if (
                not isinstance(value, dict)
                or not isinstance(record.get("key"), str)
                or not record["key"]
                or record["key"] != value.get(key_field)
            ):
                return False, f"Phase 13 {table_id} key disagrees with its value identity"

    python_ir = payload.get("python_ir")
    node_values = python_ir.get("nodes") if isinstance(python_ir, dict) else None
    if not isinstance(node_values, list):
        return False, "Phase 13 conversion plan lacks flattened Python IR"
    nodes = {
        node.get("node_id"): node
        for node in node_values
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }
    if len(nodes) != len(node_values):
        return False, "Phase 13 flattened Python IR has missing or duplicate node identities"

    node_ordinals = {
        node["node_id"]: ordinal for ordinal, node in enumerate(node_values)
    }
    parents: dict[str, list[tuple[str, str]]] = {}
    for parent in node_values:
        for field_name, field_value in parent.get("fields", {}).items():
            for child_id in python_ir_reference_ids(
                parent["kind"], field_name, field_value, nodes
            ):
                parents.setdefault(child_id, []).append(
                    (parent["node_id"], field_name)
                )

    def _parent(node_id: str) -> tuple[str, str] | None:
        values = parents.get(node_id, ())
        if not values:
            return None
        return min(
            values,
            key=lambda item: (node_ordinals.get(item[0], 2**63 - 1), item[1]),
        )

    def _enclosing_function(node_id: str) -> str | None:
        current = node_id
        seen: set[str] = set()
        while current not in seen:
            seen.add(current)
            parent = _parent(current)
            if parent is None:
                return None
            candidate = nodes[parent[0]]
            if candidate.get("kind") in {"FunctionDef", "AsyncFunctionDef"}:
                return parent[0]
            current = parent[0]
        return None

    def _owner_body_position(node_id: str, owner_id: str) -> int | None:
        body = nodes.get(owner_id, {}).get("fields", {}).get("body")
        if not isinstance(body, list):
            return None
        current = node_id
        seen: set[str] = set()
        while current not in seen:
            seen.add(current)
            parent = _parent(current)
            if parent is None:
                return None
            if parent == (owner_id, "body"):
                try:
                    return body.index(current)
                except ValueError:
                    return None
            current = parent[0]
        return None

    store_parent_slots = {
        ("Assign", "targets"),
        ("AnnAssign", "target"),
        ("AugAssign", "target"),
        ("Delete", "targets"),
        ("NamedExpr", "target"),
        ("For", "target"),
        ("AsyncFor", "target"),
        ("comprehension", "target"),
        ("withitem", "optional_vars"),
    }

    def _is_store_target(node_id: str) -> bool:
        current = node_id
        while True:
            parent = _parent(current)
            if parent is None:
                return False
            parent_node = nodes[parent[0]]
            if (parent_node.get("kind"), parent[1]) in store_parent_slots:
                return True
            if (
                parent_node.get("kind") in {"Tuple", "List", "Starred"}
                and parent[1] in {"elts", "value"}
            ):
                current = parent[0]
                continue
            return False

    def _crosses_class_or_lambda(node_id: str, owner_id: str) -> bool:
        current = node_id
        seen: set[str] = set()
        while current not in seen:
            seen.add(current)
            parent = _parent(current)
            if parent is None or parent[0] == owner_id:
                return False
            if nodes[parent[0]].get("kind") in {"ClassDef", "Lambda"}:
                return True
            current = parent[0]
        return True

    def _comprehension_target(node_id: str) -> bool:
        current = node_id
        seen: set[str] = set()
        while current not in seen:
            seen.add(current)
            parent = _parent(current)
            if parent is None:
                return False
            parent_node = nodes[parent[0]]
            if parent_node.get("kind") == "comprehension":
                return parent[1] == "target"
            if parent_node.get("kind") not in {"Tuple", "List", "Starred"}:
                return False
            current = parent[0]
        return False

    def _owner_binding_conflict(
        owner_id: str,
        source_name: str,
        declaration_node_id: str,
    ) -> bool:
        for node in node_values:
            node_id = node["node_id"]
            if node_id == declaration_node_id:
                continue
            if _enclosing_function(node_id) != owner_id:
                continue
            if _crosses_class_or_lambda(node_id, owner_id):
                continue
            kind = node.get("kind")
            fields = node.get("fields", {})
            if kind == "Name" and fields.get("id") == source_name:
                if not _comprehension_target(node_id) and _is_store_target(node_id):
                    return True
            elif kind in {"Global", "Nonlocal"} and source_name in fields.get("names", ()):
                return True
            elif kind == "ExceptHandler" and fields.get("name") == source_name:
                return True
            elif kind in {"MatchAs", "MatchStar"} and fields.get("name") == source_name:
                return True
            elif kind == "MatchMapping" and fields.get("rest") == source_name:
                return True
            elif (
                kind in {"FunctionDef", "AsyncFunctionDef", "ClassDef"}
                and node_id != owner_id
                and fields.get("name") == source_name
            ):
                return True
            elif kind == "alias":
                imported = str(fields.get("name") or "")
                bound_name = str(fields.get("asname") or imported.split(".", 1)[0])
                if bound_name == source_name:
                    return True
        return False

    def _table_values(table_id: str, key_field: str) -> dict[str, dict[str, Any]]:
        table = table_by_id.get(table_id, {})
        result: dict[str, dict[str, Any]] = {}
        for record in table.get("records", ()):
            value = record.get("value")
            if isinstance(value, dict) and isinstance(value.get(key_field), str):
                result[value[key_field]] = value
        return result

    lexical_bindings = _table_values("binding-facts", "binding_id")
    lexical_scopes = _table_values("scope-facts", "scope_id")
    module_identities = _table_values("module-identity-facts", "module_id")
    module_sources = _table_values("module-source-facts", "module_id")
    module_functions = _table_values("module-function-facts", "function_node_id")
    value_categories = {
        record.get("key"): record.get("value")
        for record in table_by_id.get("value-category-facts", {}).get("records", ())
        if isinstance(record.get("key"), str)
    }
    module_records = payload.get("module_record_by_node")
    if (
        not lexical_bindings
        or not lexical_scopes
        or not module_identities
        or not module_sources
        or not isinstance(module_records, dict)
    ):
        return False, "Phase 13 record proof lacks lexical or module identity evidence"

    required_provenance: dict[tuple[str, str], set[str]] = {}
    for table_id, table in record_tables.items():
        for record in table["records"]:
            provenance = record.get("provenance")
            source_node_ids = (
                provenance.get("source_node_ids")
                if isinstance(provenance, dict)
                else None
            )
            if (
                not isinstance(source_node_ids, list)
                or not source_node_ids
                or any(
                    not isinstance(node_id, str) or node_id not in nodes
                    for node_id in source_node_ids
                )
            ):
                return False, "Phase 13 record fact provenance references an absent node"
            required_provenance[(table_id, record["key"])] = set(source_node_ids)

    values = {
        table_id: {
            record["key"]: record["value"] for record in table["records"]
        }
        for table_id, table in record_tables.items()
    }
    definitions = values["record-definition-facts"]
    fields = values["record-field-facts"]
    initializers = values["record-initializer-facts"]
    instances = values["record-instance-facts"]
    bindings = values["record-binding-facts"]
    accesses = values["record-access-facts"]
    generated_names = payload.get("generated_name_plans")
    if not isinstance(generated_names, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("binding_id"), str)
        or not item["binding_id"]
        or not isinstance(item.get("generated_name"), str)
        or not item["generated_name"]
        for item in generated_names
    ):
        return False, "Phase 13 generated-name plans are malformed"
    generated_name_ids = [item["binding_id"] for item in generated_names]
    if len(generated_name_ids) != len(set(generated_name_ids)):
        return False, "Phase 13 generated-name plan bindings are not unique"
    required_generated_name_ids = {
        item.get("class_binding_id") for item in definitions.values()
    } | set(fields) | set(bindings)
    if not required_generated_name_ids.issubset(generated_name_ids):
        return False, "Phase 13 record lowering lacks a required generated-name plan"

    def _node_is(node_id: Any, kind: str) -> bool:
        return isinstance(node_id, str) and nodes.get(node_id, {}).get("kind") == kind

    def _identity(value: dict[str, Any]) -> tuple[Any, Any, Any]:
        return value.get("module_id"), value.get("document_id"), value.get("logical_name")

    class_node_ids = {
        node_id for node_id, node in nodes.items() if node.get("kind") == "ClassDef"
    }
    if {item.get("class_node_id") for item in definitions.values()} != class_node_ids:
        return False, "Phase 13 record definitions do not completely cover flattened classes"

    definition_class_bindings: set[str] = set()
    definition_names: set[tuple[str, str]] = set()
    for record_id, definition in definitions.items():
        field_ids = definition.get("field_ids")
        class_node_id = definition.get("class_node_id")
        class_binding_id = definition.get("class_binding_id")
        identity = _identity(definition)
        module_record = module_records.get(class_node_id)
        module_identity = module_identities.get(identity[0])
        module_source = module_sources.get(identity[0])
        lexical_class = lexical_bindings.get(class_binding_id)
        if (
            not _node_is(class_node_id, "ClassDef")
            or not isinstance(class_binding_id, str)
            or not class_binding_id
            or class_binding_id in definition_class_bindings
            or not all(isinstance(item, str) and item for item in identity)
            or not isinstance(definition.get("source_name"), str)
            or not definition["source_name"]
            or definition["source_name"] in {"int", "float", "bool", "str"}
            or not isinstance(definition.get("flattened_name"), str)
            or not definition["flattened_name"]
            or (identity[0], definition["flattened_name"]) in definition_names
            or not isinstance(field_ids, list)
            or not 1 <= len(field_ids) <= 64
            or len(field_ids) != len(set(field_ids))
            or not isinstance(definition.get("initializer_id"), str)
            or definition.get("category") != "immutable-static-record-definition"
            or definition.get("storage_model") != "automatic-inline-record"
            or definition.get("ownership_model") != "unique-lexical-owner"
            or definition.get("lifetime_model") != "enclosing-function-activation"
            or definition.get("aliasing_model") != "forbidden"
            or definition.get("cleanup_model") != "none"
            or definition.get("nullability_model") != "non-null-by-construction"
            or definition.get("mutable") is not False
            or not isinstance(module_record, dict)
            or module_record.get("class_node_id") != class_node_id
            or module_record.get("module_id") != identity[0]
            or module_record.get("document_id") != identity[1]
            or module_record.get("source_name") != definition.get("source_name")
            or module_record.get("flattened_name") != definition.get("flattened_name")
            or not isinstance(module_identity, dict)
            or module_identity.get("document_id") != identity[1]
            or module_identity.get("logical_name") != identity[2]
            or not isinstance(module_source, dict)
            or module_source.get("document_id") != identity[1]
            or module_source.get("logical_name") != identity[2]
            or not isinstance(lexical_class, dict)
            or lexical_class.get("binding_kind") != "record-class"
            or lexical_class.get("declaration_node_id") != class_node_id
            or lexical_class.get("source_name") != definition.get("flattened_name")
        ):
            return False, "Phase 13 record definition violates the closed representation contract"
        class_node = nodes[class_node_id]
        class_fields = class_node.get("fields", {})
        if (
            class_fields.get("name") != definition["flattened_name"]
            or class_fields.get("bases")
            or class_fields.get("keywords")
            or class_fields.get("decorator_list")
        ):
            return False, "Phase 13 record definition name disagrees with flattened Python IR"
        if class_node_id not in required_provenance[("record-definition-facts", record_id)]:
            return False, "Phase 13 record definition provenance is incomplete"
        definition_class_bindings.add(class_binding_id)
        definition_names.add((identity[0], definition["flattened_name"]))

    fields_by_record: dict[str, list[dict[str, Any]]] = {
        record_id: [] for record_id in definitions
    }
    for field_id, field in fields.items():
        definition = definitions.get(field.get("record_id"))
        declaration_id = field.get("declaration_node_id")
        target_id = field.get("target_node_id")
        annotation_id = field.get("annotation_node_id")
        ordinal = field.get("ordinal")
        category = field.get("category")
        if (
            definition is None
            or field.get("class_node_id") != definition.get("class_node_id")
            or _identity(field) != _identity(definition)
            or not _node_is(declaration_id, "AnnAssign")
            or not _node_is(target_id, "Name")
            or not _node_is(annotation_id, "Name")
            or not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or ordinal < 0
            or category not in _RECORD_FIELD_CATEGORIES
            or not isinstance(field.get("source_name"), str)
            or not field["source_name"]
            or (
                field["source_name"].startswith("__")
                and field["source_name"].endswith("__")
            )
            or field.get("mutable") is not False
        ):
            return False, "Phase 13 record field violates the closed field contract"
        declaration = nodes[declaration_id]
        target = nodes[target_id]
        annotation = nodes[annotation_id]
        if (
            declaration.get("fields", {}).get("target") != target_id
            or declaration.get("fields", {}).get("annotation") != annotation_id
            or declaration.get("fields", {}).get("value") is not None
            or declaration.get("fields", {}).get("simple") != 1
            or target.get("fields", {}).get("id") != field["source_name"]
            or annotation.get("fields", {}).get("id") != _RECORD_FIELD_CATEGORIES[category]
        ):
            return False, "Phase 13 record field disagrees with flattened Python IR"
        if not {declaration_id, target_id, annotation_id}.issubset(
            required_provenance[("record-field-facts", field_id)]
        ):
            return False, "Phase 13 record field provenance is incomplete"
        fields_by_record[field["record_id"]].append(field)

    for record_id, definition in definitions.items():
        ordered_fields = sorted(fields_by_record[record_id], key=lambda item: item["ordinal"])
        if (
            [item["ordinal"] for item in ordered_fields] != list(range(len(ordered_fields)))
            or [item["field_id"] for item in ordered_fields] != definition["field_ids"]
            or len({item["source_name"] for item in ordered_fields}) != len(ordered_fields)
        ):
            return False, "Phase 13 record field coverage, identity, or ordinal order is incomplete"

    if {item.get("initializer_id") for item in definitions.values()} != set(initializers):
        return False, "Phase 13 record initializer coverage is not exactly one per definition"
    for initializer_id, initializer in initializers.items():
        definition = definitions.get(initializer.get("record_id"))
        function_id = initializer.get("function_node_id")
        arguments_id = initializer.get("arguments_node_id")
        self_id = initializer.get("self_parameter_node_id")
        parameter_ids = initializer.get("parameter_node_ids")
        assignment_ids = initializer.get("assignment_node_ids")
        if (
            definition is None
            or definition.get("initializer_id") != initializer_id
            or _identity(initializer) != _identity(definition)
            or not _node_is(function_id, "FunctionDef")
            or not _node_is(arguments_id, "arguments")
            or not _node_is(self_id, "arg")
            or not isinstance(parameter_ids, list)
            or not isinstance(assignment_ids, list)
            or initializer.get("field_ids") != definition.get("field_ids")
            or len(parameter_ids) != len(definition["field_ids"])
            or len(assignment_ids) != len(definition["field_ids"])
            or len(parameter_ids) != len(set(parameter_ids))
            or len(assignment_ids) != len(set(assignment_ids))
            or any(not _node_is(item, "arg") for item in parameter_ids)
            or any(not _node_is(item, "Assign") for item in assignment_ids)
            or initializer.get("receiver_model") != "direct-addressed-initialization-receiver"
            or initializer.get("evaluation_order")
            != "field-declaration-order-left-to-right-once"
            or initializer.get("initialization_completeness") != "all-fields-exactly-once"
        ):
            return False, "Phase 13 record initializer violates exact field coverage"
        function = nodes[function_id]
        arguments = nodes[arguments_id]
        ordered_fields = sorted(
            fields_by_record[initializer["record_id"]], key=lambda item: item["ordinal"]
        )
        return_annotation = nodes.get(function.get("fields", {}).get("returns"), {})
        if (
            function.get("fields", {}).get("name") != "__init__"
            or function.get("fields", {}).get("args") != arguments_id
            or function.get("fields", {}).get("body") != assignment_ids
            or function.get("fields", {}).get("decorator_list")
            or function.get("fields", {}).get("type_comment") is not None
            or arguments.get("fields", {}).get("args") != [self_id] + parameter_ids
            or any(
                arguments.get("fields", {}).get(field)
                for field in ("posonlyargs", "kwonlyargs", "kw_defaults", "defaults")
            )
            or arguments.get("fields", {}).get("vararg") is not None
            or arguments.get("fields", {}).get("kwarg") is not None
            or nodes[self_id].get("fields", {}).get("arg") != "self"
            or nodes[self_id].get("fields", {}).get("annotation") is not None
            or nodes[self_id].get("fields", {}).get("type_comment") is not None
            or return_annotation.get("kind") != "Constant"
            or return_annotation.get("fields", {}).get("value") is not None
        ):
            return False, "Phase 13 record initializer disagrees with flattened Python IR"
        for parameter_id, assignment_id, field in zip(
            parameter_ids, assignment_ids, ordered_fields
        ):
            parameter = nodes[parameter_id]
            parameter_annotation = nodes.get(
                parameter.get("fields", {}).get("annotation"), {}
            )
            assignment = nodes[assignment_id]
            assignment_targets = assignment.get("fields", {}).get("targets")
            target = (
                nodes.get(assignment_targets[0], {})
                if isinstance(assignment_targets, list) and len(assignment_targets) == 1
                else {}
            )
            receiver = nodes.get(target.get("fields", {}).get("value"), {})
            source = nodes.get(assignment.get("fields", {}).get("value"), {})
            if (
                parameter.get("fields", {}).get("arg") != field["source_name"]
                or parameter.get("fields", {}).get("type_comment") is not None
                or parameter_annotation.get("kind") != "Name"
                or parameter_annotation.get("fields", {}).get("id")
                != _RECORD_FIELD_CATEGORIES[field["category"]]
                or target.get("kind") != "Attribute"
                or target.get("fields", {}).get("attr") != field["source_name"]
                or receiver.get("kind") != "Name"
                or receiver.get("fields", {}).get("id") != "self"
                or source.get("kind") != "Name"
                or source.get("fields", {}).get("id") != field["source_name"]
                or assignment.get("fields", {}).get("type_comment") is not None
            ):
                return False, "Phase 13 record initializer field copies are not exact"
        class_body = nodes[definition["class_node_id"]].get("fields", {}).get("body")
        if class_body != [item["declaration_node_id"] for item in ordered_fields] + [function_id]:
            return False, "Phase 13 record class body exceeds the closed record surface"
        initializer_nodes = {
            function_id,
            arguments_id,
            self_id,
            *parameter_ids,
            *assignment_ids,
        }
        if not initializer_nodes.issubset(
            required_provenance[("record-initializer-facts", initializer_id)]
        ):
            return False, "Phase 13 record initializer provenance is incomplete"

    if {item.get("binding_id") for item in instances.values()} != set(bindings):
        return False, "Phase 13 record instance bindings are not one-to-one"
    if {item.get("instance_id") for item in bindings.values()} != set(instances):
        return False, "Phase 13 record instance coverage is not one-to-one"
    for instance_id, instance in instances.items():
        definition = definitions.get(instance.get("record_id"))
        binding = bindings.get(instance.get("binding_id"))
        construction_id = instance.get("construction_node_id")
        assignment_id = instance.get("assignment_node_id")
        target_id = instance.get("target_node_id")
        owner_id = instance.get("owner_function_node_id")
        argument_ids = instance.get("argument_node_ids")
        lexical_instance = lexical_bindings.get(instance.get("binding_id"))
        lexical_scope = (
            lexical_scopes.get(lexical_instance.get("scope_id"))
            if isinstance(lexical_instance, dict)
            else None
        )
        module_function = module_functions.get(owner_id)
        module_identity = module_identities.get(instance.get("module_id"))
        module_source = module_sources.get(instance.get("module_id"))
        if (
            definition is None
            or binding is None
            or instance.get("class_node_id") != definition.get("class_node_id")
            or _identity(instance) != _identity(definition)
            or not _node_is(owner_id, "FunctionDef")
            or not _node_is(construction_id, "Call")
            or not _node_is(assignment_id, "Assign")
            or not _node_is(target_id, "Name")
            or not isinstance(argument_ids, list)
            or len(argument_ids) != len(definition["field_ids"])
            or any(item not in nodes for item in argument_ids)
            or instance.get("category") != "immutable-static-record-like"
            or instance.get("storage_model") != "automatic-inline-record"
            or instance.get("ownership_model") != "unique-lexical-owner"
            or instance.get("lifetime_model") != "enclosing-function-activation"
            or instance.get("aliasing_model") != "forbidden"
            or instance.get("cleanup_model") != "none"
            or instance.get("nullability_model") != "non-null-by-construction"
            or instance.get("allocation_model") != "none"
            or instance.get("mutable") is not False
            or not isinstance(lexical_instance, dict)
            or lexical_instance.get("binding_kind") != "local"
            or lexical_instance.get("declaration_node_id") != target_id
            or lexical_instance.get("source_name") != instance.get("source_name")
            or not isinstance(lexical_scope, dict)
            or lexical_scope.get("scope_kind") != "function"
            or lexical_scope.get("owner_node_id") != owner_id
            or not isinstance(module_function, dict)
            or module_function.get("module_id") != instance.get("module_id")
            or module_function.get("document_id") != instance.get("document_id")
            or not isinstance(module_identity, dict)
            or owner_id not in module_identity.get("function_node_ids", ())
            or module_identity.get("document_id") != instance.get("document_id")
            or module_identity.get("logical_name") != instance.get("logical_name")
            or not isinstance(module_source, dict)
            or owner_id not in module_source.get("function_node_ids", ())
            or module_source.get("document_id") != instance.get("document_id")
            or module_source.get("logical_name") != instance.get("logical_name")
        ):
            return False, "Phase 13 record instance violates automatic immutable ownership"
        construction = nodes[construction_id]
        assignment = nodes[assignment_id]
        target = nodes[target_id]
        constructor_name = nodes.get(construction.get("fields", {}).get("func"), {})
        lexical_class = lexical_bindings.get(definition.get("class_binding_id"), {})
        ordered_fields = sorted(
            fields_by_record[instance["record_id"]], key=lambda item: item["ordinal"]
        )
        if (
            construction.get("fields", {}).get("args") != argument_ids
            or construction.get("fields", {}).get("keywords")
            or constructor_name.get("kind") != "Name"
            or constructor_name.get("fields", {}).get("id")
            != definition.get("flattened_name")
            or constructor_name.get("node_id")
            not in lexical_class.get("occurrence_node_ids", ())
            or assignment.get("fields", {}).get("value") != construction_id
            or assignment.get("fields", {}).get("targets") != [target_id]
            or assignment.get("fields", {}).get("type_comment") is not None
            or target.get("fields", {}).get("id") != instance.get("source_name")
            or assignment_id not in nodes[owner_id].get("fields", {}).get("body", ())
            or [value_categories.get(item) for item in argument_ids]
            != [item["category"] for item in ordered_fields]
            or _owner_binding_conflict(
                owner_id,
                instance.get("source_name"),
                target_id,
            )
        ):
            return False, "Phase 13 record construction disagrees with flattened Python IR"
        instance_nodes = {construction_id, assignment_id, target_id, *argument_ids}
        if not instance_nodes.issubset(
            required_provenance[("record-instance-facts", instance_id)]
        ):
            return False, "Phase 13 record instance provenance is incomplete"

    for definition in definitions.values():
        lexical_class = lexical_bindings[definition["class_binding_id"]]
        expected_constructor_names = {
            nodes[instance["construction_node_id"]]["fields"]["func"]
            for instance in instances.values()
            if instance.get("record_id") == definition.get("record_id")
        }
        if set(lexical_class.get("occurrence_node_ids", ())) != expected_constructor_names:
            return False, "Phase 13 record class binding has an indirect or unproved use"

    accesses_by_binding: dict[str, set[str]] = {binding_id: set() for binding_id in bindings}
    for access_id, access in accesses.items():
        instance = instances.get(access.get("instance_id"))
        binding = bindings.get(access.get("binding_id"))
        definition = definitions.get(access.get("record_id"))
        field = fields.get(access.get("field_id"))
        if (
            instance is None
            or binding is None
            or definition is None
            or field is None
            or access.get("instance_id") != binding.get("instance_id")
            or access.get("binding_id") != instance.get("binding_id")
            or access.get("record_id") != instance.get("record_id")
            or field.get("record_id") != access.get("record_id")
            or access.get("field_name") != field.get("source_name")
            or access.get("field_category") != field.get("category")
            or access.get("owner_function_node_id") != instance.get("owner_function_node_id")
            or _identity(access) != _identity(instance)
            or not _node_is(access_id, "Attribute")
            or access.get("access_mode") != "read"
            or access.get("statically_bound") is not True
        ):
            return False, "Phase 13 record field access lacks an exact static relationship"
        access_node = nodes[access_id]
        receiver_id = access_node.get("fields", {}).get("value")
        access_position = _owner_body_position(
            access_id,
            instance["owner_function_node_id"],
        )
        construction_position = _owner_body_position(
            instance["assignment_node_id"],
            instance["owner_function_node_id"],
        )
        if (
            access_node.get("fields", {}).get("attr") != field["source_name"]
            or not _node_is(receiver_id, "Name")
            or receiver_id not in binding.get("occurrence_node_ids", ())
            or nodes[receiver_id].get("fields", {}).get("id")
            != binding.get("source_name")
            or _is_store_target(access_id)
            or access_position is None
            or construction_position is None
            or access_position <= construction_position
        ):
            return False, "Phase 13 record field access disagrees with flattened Python IR"
        if access_id not in required_provenance[("record-access-facts", access_id)]:
            return False, "Phase 13 record access provenance is incomplete"
        accesses_by_binding[access["binding_id"]].add(access_id)

    for binding_id, binding in bindings.items():
        instance = instances.get(binding.get("instance_id"))
        occurrence_ids = binding.get("occurrence_node_ids")
        allowed_access_ids = binding.get("allowed_field_access_node_ids")
        if (
            instance is None
            or binding.get("record_id") != instance.get("record_id")
            or binding.get("source_name") != instance.get("source_name")
            or binding.get("declaration_node_id") != instance.get("target_node_id")
            or binding.get("owner_function_node_id") != instance.get("owner_function_node_id")
            or _identity(binding) != _identity(instance)
            or binding.get("category") != "immutable-static-record-like"
            or binding.get("single_assignment") is not True
            or binding.get("noalias") is not True
            or binding.get("escapes") is not False
            or not isinstance(occurrence_ids, list)
            or not occurrence_ids
            or len(occurrence_ids) != len(set(occurrence_ids))
            or instance.get("target_node_id") not in occurrence_ids
            or any(not _node_is(item, "Name") for item in occurrence_ids)
            or not isinstance(allowed_access_ids, list)
            or len(allowed_access_ids) != len(set(allowed_access_ids))
            or set(allowed_access_ids) != accesses_by_binding[binding_id]
            or set(occurrence_ids)
            != {
                instance.get("target_node_id"),
                *(
                    nodes[access_id].get("fields", {}).get("value")
                    for access_id in allowed_access_ids
                ),
            }
        ):
            return False, "Phase 13 record binding violates no-alias/no-escape ownership"
        lexical_binding = lexical_bindings.get(binding_id)
        if (
            not isinstance(lexical_binding, dict)
            or lexical_binding.get("binding_kind") != "local"
            or lexical_binding.get("declaration_node_id")
            != binding.get("declaration_node_id")
            or lexical_binding.get("source_name") != binding.get("source_name")
            or set(lexical_binding.get("occurrence_node_ids", ()))
            != set(occurrence_ids)
        ):
            return False, "Phase 13 record binding disagrees with lexical binding facts"
        binding_nodes = {
            binding["declaration_node_id"],
            *occurrence_ids,
            *allowed_access_ids,
        }
        if not binding_nodes.issubset(
            required_provenance[("record-binding-facts", binding_id)]
        ):
            return False, "Phase 13 record binding provenance is incomplete"

    return True, ""


def _validate_numeric_fact_table(
    payload: dict[str, Any],
    tables: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Re-prove Phase 14A facts from serialized Python IR and plan data."""

    if payload.get("numeric_policy_version") != DEFAULT_NUMERIC_POLICY:
        return False, "Phase 14 conversion plan has an unknown numeric_policy_version"
    if payload.get("target_contract") != "c11-portable-fixed-v1":
        return False, "Phase 14 numeric proof has an inexact target contract"
    table = next(
        (item for item in tables if item.get("table_id") == "numeric-operation-facts"),
        None,
    )
    if not isinstance(table, dict):
        return False, "Phase 14 conversion plan omits numeric-operation-facts"
    if (
        table.get("schema_version") != NUMERIC_FACT_SCHEMA
        or table.get("producer_stage") != "analysis.plan"
        or table.get("key_domain") != "binop-node-id"
        or table.get("completeness") != "complete"
        or table.get("invalidation_dependencies")
        != ["value-category-facts", "evaluation-order-facts"]
    ):
        return False, "Phase 14 numeric fact-table contract identity is invalid"

    python_ir = payload.get("python_ir")
    node_values = python_ir.get("nodes") if isinstance(python_ir, dict) else None
    if not isinstance(node_values, list):
        return False, "Phase 14 numeric proof lacks flattened Python IR"
    nodes = {
        item.get("node_id"): item
        for item in node_values
        if isinstance(item, dict) and isinstance(item.get("node_id"), str)
    }
    if len(nodes) != len(node_values):
        return False, "Phase 14 numeric proof has duplicate or absent Python node IDs"
    ordinals = {item["node_id"]: index for index, item in enumerate(node_values)}
    parents: dict[str, list[tuple[str, str]]] = {}
    for parent in node_values:
        for field_name, value in parent.get("fields", {}).items():
            for child_id in python_ir_reference_ids(
                parent["kind"], field_name, value, nodes
            ):
                parents.setdefault(child_id, []).append(
                    (parent["node_id"], field_name)
                )

    module_functions = {
        record.get("value", {}).get("function_node_id"): record.get("value")
        for module_table in tables
        if module_table.get("table_id") == "module-function-facts"
        for record in module_table.get("records", ())
        if isinstance(record.get("value"), dict)
    }
    module_identities = {
        record.get("value", {}).get("module_id"): record.get("value")
        for module_table in tables
        if module_table.get("table_id") == "module-identity-facts"
        for record in module_table.get("records", ())
        if isinstance(record.get("value"), dict)
    }
    module_sources = {
        record.get("value", {}).get("module_id"): record.get("value")
        for module_table in tables
        if module_table.get("table_id") == "module-source-facts"
        for record in module_table.get("records", ())
        if isinstance(record.get("value"), dict)
    }
    prohibited_contexts = {
        "AsyncFor",
        "AsyncFunctionDef",
        "AsyncWith",
        "Await",
        "DictComp",
        "FormattedValue",
        "GeneratorExp",
        "JoinedStr",
        "Lambda",
        "ListComp",
        "Match",
        "NamedExpr",
        "SetComp",
        "Try",
        "TryStar",
        "With",
        "Yield",
        "YieldFrom",
        "comprehension",
    }

    def approved_context(node_id: str) -> str | None:
        current = node_id
        seen: set[str] = set()
        while current not in seen:
            seen.add(current)
            candidates = parents.get(current, ())
            if not candidates:
                return None
            parent_id, field_name = min(
                candidates,
                key=lambda item: (ordinals.get(item[0], 2**63 - 1), item[1]),
            )
            parent = nodes[parent_id]
            if parent.get("kind") == "FunctionDef":
                return parent_id if field_name == "body" and parent_id in module_functions else None
            if parent.get("kind") in prohibited_contexts or parent.get("kind") == "ClassDef":
                return None
            current = parent_id
        return None

    def signed_literal(node: dict[str, Any]) -> tuple[int, tuple[str, ...], str] | None:
        if node.get("kind") == "Constant":
            value = node.get("fields", {}).get("value")
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and 0 <= value <= 2**63 - 1
            ):
                return value, (node["node_id"],), "constant"
            return None
        if node.get("kind") != "UnaryOp":
            return None
        operator = nodes.get(node.get("fields", {}).get("op"), {})
        operand = nodes.get(node.get("fields", {}).get("operand"), {})
        value = operand.get("fields", {}).get("value")
        if (
            operator.get("kind") not in {"UAdd", "USub"}
            or operand.get("kind") != "Constant"
            or not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= 2**63 - 1
        ):
            return None
        return (
            -value if operator["kind"] == "USub" else value,
            (node["node_id"], operator["node_id"], operand["node_id"]),
            "unary-minus" if operator["kind"] == "USub" else "unary-plus",
        )

    category_table = next(
        (item for item in tables if item.get("table_id") == "value-category-facts"),
        {},
    )
    categories = {
        record.get("key"): record.get("value")
        for record in category_table.get("records", ())
    }
    numeric_nodes: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for node in node_values:
        if node.get("kind") != "BinOp":
            continue
        operator = nodes.get(node.get("fields", {}).get("op"), {})
        if operator.get("kind") in {"FloorDiv", "Mod"}:
            numeric_nodes[node["node_id"]] = (node, operator)

    supported_calls = {
        record.get("value", {}).get("call_node_id")
        for candidate in tables
        if candidate.get("table_id") == "call-target-facts"
        for record in candidate.get("records", ())
        if isinstance(record.get("value"), dict)
        and record["value"].get("supported") is True
    }
    supported_container_accesses = {
        record.get("value", {}).get("subscript_node_id")
        for candidate in tables
        if candidate.get("table_id") == "container-access-facts"
        for record in candidate.get("records", ())
        if isinstance(record.get("value"), dict)
        and record["value"].get("supported") is True
    }
    supported_record_accesses = {
        record.get("value", {}).get("access_node_id")
        for candidate in tables
        if candidate.get("table_id") == "record-access-facts"
        for record in candidate.get("records", ())
        if isinstance(record.get("value"), dict)
    }
    integer_expression_cache: dict[str, bool] = {}

    def approved_integer_expression(
        node_id: str,
        active: frozenset[str] = frozenset(),
    ) -> bool:
        if node_id in integer_expression_cache:
            return integer_expression_cache[node_id]
        if node_id in active or categories.get(node_id) != "integer-like":
            return False
        node = nodes[node_id]
        kind = node.get("kind")
        fields = node.get("fields", {})
        next_active = active | {node_id}
        accepted = False
        if kind == "Name":
            accepted = True
        elif kind == "Constant":
            value = fields.get("value")
            accepted = (
                isinstance(value, int)
                and not isinstance(value, bool)
                and 0 <= value <= 2**63 - 1
            )
        elif kind == "UnaryOp":
            operator = nodes.get(fields.get("op"), {})
            operand_id = fields.get("operand")
            accepted = (
                operator.get("kind") in {"UAdd", "USub"}
                and isinstance(operand_id, str)
                and operand_id in nodes
                and approved_integer_expression(operand_id, next_active)
            )
        elif kind == "BinOp":
            operator = nodes.get(fields.get("op"), {})
            left_id = fields.get("left")
            right_id = fields.get("right")
            if operator.get("kind") in {"FloorDiv", "Mod"}:
                accepted = node_id in numeric_nodes
            else:
                accepted = (
                    operator.get("kind") in {"Add", "Sub", "Mult"}
                    and isinstance(left_id, str)
                    and isinstance(right_id, str)
                    and left_id in nodes
                    and right_id in nodes
                    and approved_integer_expression(left_id, next_active)
                    and approved_integer_expression(right_id, next_active)
                )
        elif kind == "Call":
            accepted = node_id in supported_calls
        elif kind == "Subscript":
            accepted = node_id in supported_container_accesses
        elif kind == "Attribute":
            accepted = node_id in supported_record_accesses
        integer_expression_cache[node_id] = accepted
        return accepted

    records = table.get("records")
    if not isinstance(records, list):
        return False, "Phase 14 numeric fact table records are malformed"
    facts: dict[str, dict[str, Any]] = {}
    provenance_by_node: dict[str, set[str]] = {}
    for record in records:
        value = record.get("value")
        key = record.get("key")
        provenance = record.get("provenance")
        source_ids = provenance.get("source_node_ids") if isinstance(provenance, dict) else None
        if (
            not isinstance(key, str)
            or not isinstance(value, dict)
            or value.get("binop_node_id") != key
            or not isinstance(source_ids, list)
            or any(item not in nodes for item in source_ids)
        ):
            return False, "Phase 14 numeric fact identity or provenance is invalid"
        facts[key] = value
        provenance_by_node[key] = set(source_ids)
    if set(facts) != set(numeric_nodes):
        return False, "Phase 14 numeric facts do not exactly cover // and % nodes"

    plans = payload.get("rule_plans", [])
    support = {
        item.get("node_id"): item
        for item in payload.get("support_decisions", [])
        if isinstance(item, dict)
    }
    numeric_helpers = {
        "pycf.i64.floor_div@1.0.0",
        "pycf.i64.floor_mod@1.0.0",
    }
    numeric_obligations = [
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
        "operands-materialized-left-to-right-once",
        "helper-result-materialized-once",
        "zero-and-negative-one-divisors-excluded",
    ]
    for plan in plans:
        if plan.get("rule_id") != "phase14.numeric.floor_arithmetic" and numeric_helpers.intersection(
            plan.get("helper_requirements", ())
        ):
            return False, "A non-numeric RulePlan claims a floor-arithmetic helper"

    for node_id, (node, operator) in sorted(numeric_nodes.items()):
        fact = facts[node_id]
        left_id = node.get("fields", {}).get("left")
        right_id = node.get("fields", {}).get("right")
        function_node_id = approved_context(node_id)
        if (
            left_id not in nodes
            or right_id not in nodes
            or function_node_id is None
            or categories.get(left_id) != "integer-like"
            or categories.get(right_id) != "integer-like"
            or categories.get(node_id) != "integer-like"
            or not approved_integer_expression(left_id)
        ):
            return False, "Phase 14 numeric fact lacks exact category or context proof"
        literal = signed_literal(nodes[right_id])
        if literal is None or literal[0] in {0, -1}:
            return False, "Phase 14 numeric divisor proof is unsafe"
        divisor, literal_ids, literal_shape = literal
        is_division = operator["kind"] == "FloorDiv"
        operation_kind = "floor-divide" if is_division else "floor-modulo"
        helper = (
            "pycf.i64.floor_div@1.0.0"
            if is_division
            else "pycf.i64.floor_mod@1.0.0"
        )
        operation_id = "numeric-op-" + hashlib.sha256(
            f"{node_id}\x1f{operation_kind}".encode("utf-8")
        ).hexdigest()[:20]
        owner = module_functions.get(function_node_id, {})
        identity = module_identities.get(owner.get("module_id"), {})
        source = module_sources.get(owner.get("module_id"), {})
        if (
            not isinstance(owner.get("module_id"), str)
            or not owner.get("module_id")
            or owner.get("document_id") != identity.get("document_id")
            or owner.get("document_id") != source.get("document_id")
            or identity.get("logical_name") != source.get("logical_name")
            or function_node_id not in identity.get("function_node_ids", ())
            or function_node_id not in source.get("function_node_ids", ())
        ):
            return False, "Phase 14 numeric ownership evidence is inconsistent"
        expected = {
            "operation_id": operation_id,
            "binop_node_id": node_id,
            "function_node_id": function_node_id,
            "module_id": owner.get("module_id"),
            "document_id": owner.get("document_id"),
            "logical_name": source.get("logical_name"),
            "operator_node_id": operator["node_id"],
            "operator_kind": operation_kind,
            "left_node_id": left_id,
            "right_node_id": right_id,
            "left_category": "integer-like",
            "right_category": "integer-like",
            "result_category": "integer-like",
            "left_c_type": "int64_t",
            "right_c_type": "int64_t",
            "result_c_type": "int64_t",
            "divisor_value": divisor,
            "divisor_literal_node_ids": list(literal_ids),
            "literal_shape": literal_shape,
            "divisor_in_admitted_domain": True,
            "divisor_nonzero_proved": True,
            "negative_one_divisor_excluded": True,
            "minimum_signed_divisor_excluded": True,
            "helper_requirement": helper,
            "evaluation_order": [left_id, right_id],
            "operands_evaluated_once": True,
            "c_type": "int64_t",
            "failure_policy": "caller-proved-no-runtime-failure-channel",
            "support_state": "SupportedWithHelper",
            "parameter_ownership": "scalar-values-by-value",
            "result_ownership": "scalar-value-by-value",
            "allocation_model": "none",
            "cleanup_model": "none",
            "runtime_failure_channel": "none",
            "target_contract": "c11-portable-fixed-v1",
        }
        if fact != expected:
            return False, "Phase 14 numeric fact disagrees with independent proof"
        if not ({node_id, function_node_id, operator["node_id"], left_id, *literal_ids}).issubset(
            provenance_by_node[node_id]
        ):
            return False, "Phase 14 numeric fact provenance is incomplete"
        node_plans = [item for item in plans if item.get("source_node_id") == node_id]
        if len(node_plans) != 1:
            return False, "Phase 14 numeric operation lacks exactly one RulePlan"
        plan = node_plans[0]
        decision = support.get(node_id)
        expected_facts = {
            f"numeric-operation:{node_id}",
            f"numeric-divisor:{divisor}",
            f"numeric-helper:{helper}",
            "numeric-target:c11-portable-fixed-v1",
            "value-category:integer-like",
        }
        expected_explanation = [
            "selected",
            "phase14.numeric.floor_arithmetic",
            "for",
            "BinOp",
            operation_kind,
            "via",
            helper,
        ]
        if (
            plan.get("rule_id") != "phase14.numeric.floor_arithmetic"
            or plan.get("rule_version") != "0.14"
            or plan.get("support_state") != "SupportedWithHelper"
            or plan.get("helper_requirements") != [helper]
            or set(plan.get("facts_used", ())) != expected_facts
            or plan.get("semantic_obligations") != numeric_obligations
            or plan.get("resolved_obligations") != numeric_obligations
            or plan.get("unresolved_obligations") != []
            or plan.get("explanation_tokens") != expected_explanation
            or not isinstance(decision, dict)
            or decision.get("state") != "SupportedWithHelper"
            or decision.get("rule_plan_id") != plan.get("plan_id")
        ):
            return False, "Phase 14 numeric RulePlan does not close its helper proof"
    return True, ""


def validate_analysis_payload(
    payload: dict[str, Any],
    cancellation: Any = None,
) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "analysis payload is malformed"
    schema = payload.get("schema_version")
    if schema not in {
        "conversion-plan/0.5",
        "conversion-plan/0.9",
        "conversion-plan/0.11",
        PHASE12_CONVERSION_PLAN_SCHEMA,
        PHASE13_CONVERSION_PLAN_SCHEMA,
        PHASE14A_CONVERSION_PLAN_SCHEMA,
        PHASE14B_CONVERSION_PLAN_SCHEMA,
        PHASE14C_CONVERSION_PLAN_SCHEMA,
        CONVERSION_PLAN_SCHEMA,
    }:
        return False, "unsupported conversion-plan schema"
    tables = payload.get("fact_tables")
    if not isinstance(tables, list) or any(
        not isinstance(table, dict) for table in tables
    ):
        return False, "fact tables are malformed"
    table_ids = [table.get("table_id") for table in tables]
    if any(not isinstance(table_id, str) or not table_id for table_id in table_ids):
        return False, "fact-table IDs are malformed"
    if len(table_ids) != len(set(table_ids)):
        return False, "duplicate fact-table IDs"
    for table in tables:
        required = {"schema_version", "table_id", "producer_stage", "key_domain", "completeness", "invalidation_dependencies", "records"}
        if not required.issubset(table):
            return False, "fact table omits required contract fields"
        records = table["records"]
        if (
            not all(
                isinstance(table.get(field), str) and table.get(field)
                for field in (
                    "schema_version",
                    "producer_stage",
                    "key_domain",
                    "completeness",
                )
            )
            or not isinstance(table.get("invalidation_dependencies"), list)
        ):
            return False, "fact-table contract fields are malformed"
        if not isinstance(records, list) or any(
            not isinstance(record, dict) for record in records
        ):
            return False, "fact-table records are malformed"
        keys = [record.get("key") for record in records]
        if any(not isinstance(key, str) or not key for key in keys):
            return False, "fact record keys are malformed"
        if any(left >= right for left, right in zip(keys, keys[1:])):
            return False, f"fact table {table['table_id']} keys are not unique and sorted"
        if any(
            not isinstance(record.get("provenance"), dict) for record in records
        ):
            return False, "fact record without provenance"
    plans = payload.get("rule_plans")
    if not isinstance(plans, list) or any(
        not isinstance(plan, dict) for plan in plans
    ):
        return False, "RulePlans are malformed"
    plan_ids = [plan.get("plan_id") for plan in plans]
    if any(not isinstance(plan_id, str) or not plan_id for plan_id in plan_ids):
        return False, "RulePlan IDs are malformed"
    if len(plan_ids) != len(set(plan_ids)):
        return False, "duplicate RulePlan IDs"
    plan_by_id = {plan["plan_id"]: plan for plan in plans}
    decisions = payload.get("support_decisions")
    if not isinstance(decisions, list) or any(
        not isinstance(item, dict) for item in decisions
    ):
        return False, "support decisions are malformed"
    decision_keys = [item.get("decision_key") for item in decisions]
    if any(not isinstance(key, str) or not key for key in decision_keys):
        return False, "support decision keys are malformed"
    if len(decision_keys) != len(set(decision_keys)):
        return False, "duplicate support decision keys"
    for decision in decisions:
        state = decision.get("state")
        if not isinstance(state, str):
            return False, "support decision state is malformed"
        plan_id = decision.get("rule_plan_id")
        if plan_id is not None and not isinstance(plan_id, str):
            return False, "support decision RulePlan identity is malformed"
        if state.startswith("Supported") and plan_id not in plan_by_id:
            return False, "supported decision lacks exactly one RulePlan"
        if not state.startswith("Supported") and plan_id is not None:
            return False, "unsupported decision references RulePlan"
        if plan_id is not None:
            plan = plan_by_id[plan_id]
            if plan.get("decision_key") != decision.get("decision_key") or plan.get("source_node_id") != decision.get("node_id"):
                return False, "support decision and RulePlan identity disagree"
    for plan in plans:
        unresolved = plan.get("unresolved_obligations")
        semantic = plan.get("semantic_obligations")
        resolved = plan.get("resolved_obligations")
        if not all(
            isinstance(value, list) for value in (unresolved, semantic, resolved)
        ) or any(
            not isinstance(item, str)
            for value in (unresolved, semantic, resolved)
            for item in value
        ):
            return False, "RulePlan obligations are malformed"
        if unresolved:
            return False, "published RulePlan has unresolved obligations"
        if sorted(semantic) != sorted(resolved):
            return False, "RulePlan obligations are not closed"
        plan_helpers = plan.get("helper_requirements", [])
        if not isinstance(plan_helpers, list) or any(
            not isinstance(item, str) for item in plan_helpers
        ):
            return False, "RulePlan helper requirements are malformed"
        if any(
            left >= right
            for left, right in zip(plan_helpers, plan_helpers[1:])
        ) or any(
            not isinstance(item, str) or not _HELPER_REQUIREMENT.fullmatch(item)
            for item in plan_helpers
        ):
            return False, "RulePlan helper requirements are not exact, unique, and sorted"
        if plan.get("support_state") == "SupportedWithHelper" and not plan_helpers:
            return False, "helper-backed RulePlan lacks a helper requirement"
    helper_requirements = payload.get("helper_requirements")
    if not isinstance(helper_requirements, list) or any(
        not isinstance(item, str) for item in helper_requirements
    ):
        return False, "conversion-plan helper requirements are malformed"
    expected_helpers = sorted(
        {
            item
            for plan in plans
            for item in plan.get("helper_requirements", [])
        }
    )
    if helper_requirements != expected_helpers:
        return False, "conversion-plan helper requirements disagree with RulePlans"
    generated_names = payload.get("generated_name_plans")
    if not isinstance(generated_names, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("generated_name"), str)
        for item in generated_names
    ):
        return False, "generated-name plans are malformed"
    names = [item["generated_name"] for item in generated_names]
    if len(names) != len(set(names)):
        return False, "generated name collision"
    representation_values = payload.get("representation_plans")
    if not isinstance(representation_values, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("decision_key"), str)
        for item in representation_values
    ):
        return False, "representation plans are malformed"
    representations = {
        item["decision_key"]: item for item in representation_values
    }
    non_value_rules = {
        "phase8.if.control",
        "phase8.while.control",
        "phase8.for.range",
        "phase8.break.control",
        "phase8.continue.control",
        "phase8.range.bound",
        "phase11.container.for.bounded",
        "phase12.module.import_from",
        "phase12.module.document",
        "phase12.module.imported_binding",
        "phase12.module.initialization",
        "phase12.module.bundle_assembly",
        "phase13.record.class",
        "phase13.record.field",
        "phase13.record.initializer",
        "phase13.record.binding",
    }
    for decision in decisions:
        if decision["state"].startswith("Supported"):
            representation = representations.get(decision["decision_key"])
            plan = plan_by_id[decision["rule_plan_id"]]
            if not representation or (plan.get("rule_id") not in non_value_rules and (representation.get("c_type") is None or representation.get("unresolved_obligations"))):
                return False, "supported decision lacks a closed representation plan"
    if schema in {
        "conversion-plan/0.9",
        "conversion-plan/0.11",
        PHASE12_CONVERSION_PLAN_SCHEMA,
        PHASE13_CONVERSION_PLAN_SCHEMA,
        PHASE14A_CONVERSION_PLAN_SCHEMA,
        PHASE14B_CONVERSION_PLAN_SCHEMA,
        PHASE14C_CONVERSION_PLAN_SCHEMA,
        CONVERSION_PLAN_SCHEMA,
    }:
        required_tables = {"function-signature-facts", "call-target-facts", "return-path-facts", "local-declaration-facts", "call-graph-facts"}
        if not required_tables.issubset(table_ids):
            return False, "Phase 9 conversion plan omits required function/call fact tables"
        for field in ("target_contract", "semantic_policy", "rule_set_version", "renderer_version", "helper_policy_version"):
            if not isinstance(payload.get(field), str) or not payload[field]:
                return False, f"Phase 9 conversion plan omits {field}"
    if schema in {
        "conversion-plan/0.11",
        PHASE12_CONVERSION_PLAN_SCHEMA,
        PHASE13_CONVERSION_PLAN_SCHEMA,
        PHASE14A_CONVERSION_PLAN_SCHEMA,
        PHASE14B_CONVERSION_PLAN_SCHEMA,
        PHASE14C_CONVERSION_PLAN_SCHEMA,
        CONVERSION_PLAN_SCHEMA,
    }:
        required_tables = {
            "container-shape-facts",
            "container-binding-facts",
            "container-access-facts",
            "container-iteration-facts",
        }
        if not required_tables.issubset(table_ids):
            return False, "Phase 11 conversion plan omits required container fact tables"
        if not isinstance(payload.get("container_policy_version"), str) or not payload["container_policy_version"]:
            return False, "Phase 11 conversion plan omits container_policy_version"
        records = {
            table["table_id"]: {
                record["key"]: record["value"]
                for record in table["records"]
            }
            for table in tables
            if table["table_id"] in required_tables
        }
        bindings = records["container-binding-facts"]
        for access in records["container-access-facts"].values():
            binding = bindings.get(access.get("binding_id"))
            if access.get("supported") and binding is None:
                return False, "supported container access references an absent binding fact"
            if access.get("supported") and not binding.get("valid"):
                return False, "supported container access references an invalid binding fact"
            if access.get("supported") and not isinstance(access.get("resolved_offset"), int):
                return False, "supported container access lacks a resolved offset"
        for iteration in records["container-iteration-facts"].values():
            binding = bindings.get(iteration.get("binding_id"))
            if iteration.get("supported") and binding is None:
                return False, "supported container iteration references an absent binding fact"
            if iteration.get("supported") and not binding.get("valid"):
                return False, "supported container iteration references an invalid binding fact"
            if iteration.get("supported") and (
                not isinstance(iteration.get("capacity"), int)
                or iteration["capacity"] <= 0
            ):
                return False, "supported container iteration lacks a positive fixed bound"
    if schema in {
        PHASE13_CONVERSION_PLAN_SCHEMA,
        PHASE14A_CONVERSION_PLAN_SCHEMA,
        PHASE14B_CONVERSION_PLAN_SCHEMA,
        PHASE14C_CONVERSION_PLAN_SCHEMA,
        CONVERSION_PLAN_SCHEMA,
    }:
        valid, reason = _validate_record_fact_tables(payload, tables)
        if not valid:
            return valid, reason
    if schema in {PHASE14A_CONVERSION_PLAN_SCHEMA, PHASE14B_CONVERSION_PLAN_SCHEMA, PHASE14C_CONVERSION_PLAN_SCHEMA, CONVERSION_PLAN_SCHEMA}:
        valid, reason = _validate_numeric_fact_table(payload, tables)
        if not valid:
            return valid, reason
    if schema in {PHASE14B_CONVERSION_PLAN_SCHEMA, PHASE14C_CONVERSION_PLAN_SCHEMA, CONVERSION_PLAN_SCHEMA}:
        valid, reason = validate_conditional_region_facts(
            payload,
            tables,
            expected_fact_schema=CONDITIONAL_FACT_SCHEMA,
            require_table=True,
            cancellation=cancellation,
        )
        if not valid:
            return valid, reason
    if schema in {PHASE14C_CONVERSION_PLAN_SCHEMA, CONVERSION_PLAN_SCHEMA}:
        cumulatively_ineligible_targets = (
            _cumulatively_ineligible_target_function_node_ids(
                payload,
                tables,
                cancellation,
            )
        )
        valid, reason = validate_keyword_call_binding_facts(
            payload,
            tables,
            expected_fact_schema=KEYWORD_CALL_FACT_SCHEMA,
            require_table=True,
            require_plans=True,
            cumulatively_ineligible_target_function_node_ids=(
                cumulatively_ineligible_targets
            ),
            cancellation=cancellation,
        )
        if not valid:
            return valid, reason
    if schema == CONVERSION_PLAN_SCHEMA:
        valid, reason = validate_keyword_only_call_binding_facts(
            payload,
            tables,
            expected_fact_schema=KEYWORD_ONLY_CALL_FACT_SCHEMA,
            require_table=True,
            require_plans=True,
            cumulatively_ineligible_target_function_node_ids=(
                cumulatively_ineligible_targets
            ),
            cancellation=cancellation,
        )
        if not valid:
            return valid, reason
    if schema in {
        PHASE12_CONVERSION_PLAN_SCHEMA,
        PHASE13_CONVERSION_PLAN_SCHEMA,
        PHASE14A_CONVERSION_PLAN_SCHEMA,
        PHASE14B_CONVERSION_PLAN_SCHEMA,
        PHASE14C_CONVERSION_PLAN_SCHEMA,
        CONVERSION_PLAN_SCHEMA,
    }:
        required_module_tables = {
            "module-identity-facts",
            "module-import-facts",
            "module-function-facts",
            "module-initialization-facts",
            "module-namespace-facts",
            "module-source-facts",
        }
        if not required_module_tables.issubset(table_ids):
            return False, "Phase 12 conversion plan omits required module fact tables"
        expected_module_policy = (
            DEFAULT_MODULE_POLICY
            if schema in {
                PHASE13_CONVERSION_PLAN_SCHEMA,
                PHASE14A_CONVERSION_PLAN_SCHEMA,
                PHASE14B_CONVERSION_PLAN_SCHEMA,
                PHASE14C_CONVERSION_PLAN_SCHEMA,
                CONVERSION_PLAN_SCHEMA,
            }
            else PHASE12_MODULE_POLICY
        )
        if payload.get("module_policy_version") != expected_module_policy:
            return False, "module conversion plan has an unknown module_policy_version"
        module_tables = {table["table_id"]: table for table in tables if table["table_id"] in required_module_tables}
        if any(
            table.get("schema_version") != MODULE_FACT_SCHEMA
            or table.get("completeness") != "complete"
            or table.get("producer_stage") != "modules.resolve"
            for table in module_tables.values()
        ):
            return False, "Phase 12 module fact table contract identity is invalid"
        module_key_fields = {
            "module-identity-facts": "module_id",
            "module-import-facts": "import_item_id",
            "module-function-facts": "function_node_id",
            "module-initialization-facts": "initialization_node_id",
            "module-namespace-facts": "module_id",
            "module-source-facts": "module_id",
        }
        for table_id, table in module_tables.items():
            key_field = module_key_fields[table_id]
            if any(
                not isinstance(record.get("value"), dict)
                or record.get("key") != record["value"].get(key_field)
                for record in table["records"]
            ):
                return False, "Phase 12 module fact record key disagrees with its value identity"
        values = {
            table_id: [record["value"] for record in table["records"]]
            for table_id, table in module_tables.items()
        }
        identities = values["module-identity-facts"]
        module_id_values = [item.get("module_id") for item in identities]
        module_ids = set(module_id_values)
        if (
            not identities
            or any(not isinstance(item, str) or not item for item in module_id_values)
            or len(module_ids) != len(identities)
        ):
            return False, "Phase 12 module identities are incomplete or duplicated"
        bundle_ordinal_values = [item.get("bundle_ordinal") for item in identities]
        if any(
            not isinstance(item, int) or isinstance(item, bool) or item < 0
            for item in bundle_ordinal_values
        ):
            return False, "Phase 12 bundle ordinals or primary identity are invalid"
        bundle_ordinals = sorted(bundle_ordinal_values)
        if (
            bundle_ordinals != list(range(len(identities)))
            or any(not isinstance(item.get("is_primary"), bool) for item in identities)
            or any(
                item.get("is_primary") is not (item.get("bundle_ordinal") == 0)
                for item in identities
            )
        ):
            return False, "Phase 12 bundle ordinals or primary identity are invalid"
        identity_by_module = {item["module_id"]: item for item in identities}
        primary_module_id = next(
            item["module_id"] for item in identities if item["is_primary"]
        )

        module_bundle = payload.get("module_bundle")
        bundle_documents = (
            module_bundle.get("documents") if isinstance(module_bundle, dict) else None
        )
        if (
            not isinstance(module_bundle, dict)
            or module_bundle.get("schema_version") != "python-ir-bundle/0.4"
            or module_bundle.get("primary_module_id") != primary_module_id
            or not isinstance(bundle_documents, list)
            or len(bundle_documents) != len(identities)
        ):
            return False, "Phase 12 module identities disagree with the closed source bundle"
        source_module_order = [item.get("module_id") for item in bundle_documents]
        expected_source_module_order = [
            item["module_id"]
            for item in sorted(identities, key=lambda item: item["bundle_ordinal"])
        ]
        if source_module_order != expected_source_module_order:
            return False, "Phase 12 source-bundle order disagrees with bundle ordinals"
        bundle_by_module = {
            item.get("module_id"): item
            for item in bundle_documents
            if isinstance(item, dict)
        }
        if set(bundle_by_module) != module_ids:
            return False, "Phase 12 module identities disagree with the closed source bundle"

        original_nodes_by_module: dict[str, dict[str, dict[str, Any]]] = {}
        original_import_items: dict[str, list[dict[str, Any]]] = {}
        for module_id in expected_source_module_order:
            identity = identity_by_module[module_id]
            document = bundle_by_module[module_id]
            if any(
                document.get(field) != identity.get(field)
                for field in (
                    "document_id",
                    "logical_name",
                    "bundle_ordinal",
                    "is_primary",
                )
            ):
                return False, "Phase 12 module identity fields disagree with the closed source bundle"
            python_ir = document.get("python_ir")
            if (
                not isinstance(python_ir, dict)
                or python_ir.get("document_id") != identity.get("document_id")
                or not isinstance(python_ir.get("nodes"), list)
            ):
                return False, "Phase 12 module identity lacks its exact source Python IR"
            node_values = python_ir["nodes"]
            nodes = {
                node.get("node_id"): node
                for node in node_values
                if isinstance(node, dict) and isinstance(node.get("node_id"), str)
            }
            if len(nodes) != len(node_values):
                return False, "Phase 12 source Python IR has missing or duplicate node identities"
            root = nodes.get(python_ir.get("root_node_id"))
            body = root.get("fields", {}).get("body") if root else None
            if not isinstance(body, list):
                return False, "Phase 12 source Python IR lacks an ordered module body"
            import_node_ids = [
                node_id for node_id in body if nodes.get(node_id, {}).get("kind") == "ImportFrom"
            ]
            function_node_ids = [
                node_id for node_id in body if nodes.get(node_id, {}).get("kind") == "FunctionDef"
            ]
            if (
                not function_node_ids
                or identity.get("import_node_ids") != import_node_ids
                or identity.get("function_node_ids") != function_node_ids
            ):
                return False, "Phase 12 module ownership lists disagree with source order"
            original_nodes_by_module[module_id] = nodes
            import_items: list[dict[str, Any]] = []
            source_ordinal = 0
            for import_node_id in import_node_ids:
                import_node = nodes[import_node_id]
                target_module_id = import_node.get("fields", {}).get("module")
                alias_ids = import_node.get("fields", {}).get("names")
                if not isinstance(target_module_id, str) or not isinstance(alias_ids, list):
                    return False, "Phase 12 source import lacks an exact ordered alias list"
                for alias_node_id in alias_ids:
                    alias = nodes.get(alias_node_id)
                    if alias is None or alias.get("kind") != "alias":
                        return False, "Phase 12 source import references an absent alias node"
                    imported_name = alias.get("fields", {}).get("name")
                    asname = alias.get("fields", {}).get("asname")
                    if not isinstance(imported_name, str) or not imported_name:
                        return False, "Phase 12 source import has an invalid imported spelling"
                    import_items.append(
                        {
                            "import_node_id": import_node_id,
                            "alias_node_id": alias_node_id,
                            "target_module_id": target_module_id,
                            "imported_name": imported_name,
                            "local_name": asname or imported_name,
                            "source_ordinal": source_ordinal,
                        }
                    )
                    source_ordinal += 1
            original_import_items[module_id] = import_items

        functions = values["module-function-facts"]
        function_by_node = {item.get("function_node_id"): item for item in functions}
        flattened_names = [item.get("flattened_name") for item in functions]
        significant_external_prefixes = [str(name)[:31] for name in flattened_names]
        function_ordinal_values = [item.get("bundle_function_ordinal") for item in functions]
        if any(
            not isinstance(item, int) or isinstance(item, bool) or item < 0
            for item in function_ordinal_values
        ):
            return False, "Phase 12 module function identities, names, or order are invalid"
        function_ordinals = sorted(function_ordinal_values)
        if (
            not functions
            or None in function_by_node
            or len(function_by_node) != len(functions)
            or None in flattened_names
            or len(flattened_names) != len(set(flattened_names))
            or len(significant_external_prefixes) != len(set(significant_external_prefixes))
            or function_ordinals != list(range(len(functions)))
        ):
            return False, "Phase 12 module function identities, names, or order are invalid"
        multi_document = len(module_ids) > 1
        for item in functions:
            identity = identity_by_module.get(item.get("module_id"))
            source_node = original_nodes_by_module.get(item.get("module_id"), {}).get(
                item.get("function_node_id")
            )
            source_name = (
                source_node.get("fields", {}).get("name") if source_node else None
            )
            expected_name = (
                _module_function_name(item["module_id"], source_name)
                if multi_document and identity is not None and isinstance(source_name, str)
                else source_name
            )
            if (
                identity is None
                or item.get("document_id") != identity.get("document_id")
                or source_node is None
                or source_node.get("kind") != "FunctionDef"
                or item.get("function_node_id") not in identity.get("function_node_ids", ())
                or item.get("source_name") != source_name
                or item.get("flattened_name") != expected_name
                or item.get("linkage") != "external"
                or item.get("module_generated_name") is not multi_document
            ):
                return False, "Phase 12 module function linkage or namespace contract is invalid"

        imports = values["module-import-facts"]
        import_edges: set[tuple[str, str]] = set()
        source_ordinals: dict[str, list[int]] = {}
        imports_by_module: dict[str, list[dict[str, Any]]] = {
            module_id: [] for module_id in module_ids
        }
        for value in imports:
            target = function_by_node.get(value.get("target_function_node_id"))
            importer = value.get("importer_module_id")
            target_module = value.get("target_module_id")
            if (
                value.get("supported") is not True
                or importer not in module_ids
                or target_module not in module_ids
                or importer == target_module
                or not value.get("import_node_id")
                or not value.get("alias_node_id")
                or not value.get("import_item_id")
                or not value.get("imported_name")
                or not value.get("local_name")
                or target is None
                or target.get("module_id") != target_module
                or target.get("source_name") != value.get("imported_name")
            ):
                return False, "supported module import lacks an exact direct target"
            ordinal = value.get("source_ordinal")
            if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
                return False, "supported module import lacks a normalized source ordinal"
            source_ordinals.setdefault(importer, []).append(ordinal)
            imports_by_module[importer].append(value)
            import_edges.add((importer, target_module))
        if any(sorted(ordinals) != list(range(len(ordinals))) for ordinals in source_ordinals.values()):
            return False, "Phase 12 import ordinals are not contiguous within the importer"
        for module_id in module_ids:
            published = sorted(
                imports_by_module[module_id], key=lambda item: item["source_ordinal"]
            )
            expected = original_import_items[module_id]
            if len(published) != len(expected):
                return False, "Phase 12 import facts do not cover every normalized source alias"
            for value, source_item in zip(published, expected):
                if any(value.get(field) != source_item[field] for field in source_item):
                    return False, "Phase 12 import fact disagrees with its source alias"

        initialization = module_tables["module-initialization-facts"]
        if len(initialization["records"]) != 1:
            return False, "Phase 12 conversion plan lacks one closed initialization-order fact"
        init_value = initialization["records"][0]["value"]
        if init_value.get("cycle_policy") != "reject-all-cycles":
            return False, "Phase 12 initialization fact lacks the closed cycle policy"
        if init_value.get("runtime_initialization") != "none":
            return False, "Phase 12 module profile cannot publish runtime initialization"
        module_order = init_value.get("module_order")
        if not isinstance(module_order, list) or len(module_order) != len(module_ids) or set(module_order) != module_ids:
            return False, "Phase 12 initialization order is not a permutation of bundle modules"
        declared_edges = init_value.get("dependency_edges")
        if not isinstance(declared_edges, list):
            return False, "Phase 12 initialization fact omits dependency edges"
        declared_edge_values = [
            (item.get("importer_module_id"), item.get("target_module_id"))
            for item in declared_edges
            if isinstance(item, dict)
        ]
        edge_values = set(declared_edge_values)
        expected_edge_values = sorted(import_edges)
        if (
            len(declared_edge_values) != len(declared_edges)
            or declared_edge_values != expected_edge_values
        ):
            return False, "Phase 12 initialization edges disagree with resolved imports"
        expected_module_order = _dependency_first_order(module_ids, edge_values)
        if expected_module_order is None or module_order != expected_module_order:
            return False, "Phase 12 initialization order violates deterministic dependency ordering"

        expected_function_ids = [
            function_node_id
            for module_id in module_order
            for function_node_id in identity_by_module[module_id]["function_node_ids"]
        ]
        published_function_ids = [
            item["function_node_id"]
            for item in sorted(functions, key=lambda item: item["bundle_function_ordinal"])
        ]
        if published_function_ids != expected_function_ids:
            return False, "Phase 12 bundle function order disagrees with module and source order"

        sources = values["module-source-facts"]
        source_by_module = {item.get("module_id"): item for item in sources}
        namespaces = values["module-namespace-facts"]
        namespace_by_module = {item.get("module_id"): item for item in namespaces}
        if (
            len(source_by_module) != len(sources)
            or len(namespace_by_module) != len(namespaces)
            or set(source_by_module) != module_ids
            or set(namespace_by_module) != module_ids
        ):
            return False, "Phase 12 source or namespace coverage is incomplete"
        for module_id, identity in identity_by_module.items():
            source = source_by_module[module_id]
            namespace = namespace_by_module[module_id]
            module_functions = [function_by_node[node_id] for node_id in identity["function_node_ids"]]
            module_imports = sorted(
                imports_by_module[module_id], key=lambda item: item["source_ordinal"]
            )
            if (
                source.get("source_document_id") != identity.get("document_id")
                or source.get("logical_source_name") != identity.get("logical_name")
                or source.get("document_id") != identity.get("document_id")
                or source.get("logical_name") != identity.get("logical_name")
                or source.get("bundle_ordinal") != identity.get("bundle_ordinal")
                or source.get("is_primary") is not identity.get("is_primary")
                or source.get("document_plan_node_id") != identity.get("document_plan_node_id")
                or source.get("import_node_ids") != identity.get("import_node_ids")
                or source.get("function_node_ids") != identity.get("function_node_ids")
                or not isinstance(source.get("content_fingerprint"), str)
                or not _SHA256.fullmatch(source["content_fingerprint"])
                or source.get("eligible") is not True
                or source.get("diagnostic_code") is not None
                or source.get("reason") is not None
            ):
                return False, "Phase 12 source facts disagree with module identity"
            expected_imported_bindings = [
                {
                    "local_name": item["local_name"],
                    "target_module_id": item["target_module_id"],
                    "target_function_node_id": item["target_function_node_id"],
                }
                for item in module_imports
            ]
            if (
                namespace.get("document_plan_node_id") != identity.get("document_plan_node_id")
                or namespace.get("import_node_ids") != identity.get("import_node_ids")
                or namespace.get("function_node_ids") != identity.get("function_node_ids")
                or namespace.get("local_function_names")
                != [item["source_name"] for item in module_functions]
                or namespace.get("imported_bindings") != expected_imported_bindings
                or namespace.get("generated_function_names")
                != [item["flattened_name"] for item in module_functions]
            ):
                return False, "Phase 12 namespace facts disagree with owned functions or imports"

        flattened_python_ir = payload.get("python_ir")
        flattened_nodes = (
            flattened_python_ir.get("nodes")
            if isinstance(flattened_python_ir, dict)
            else None
        )
        if not isinstance(flattened_nodes, list):
            return False, "Phase 12 conversion plan lacks flattened Python IR"
        flattened_node_ids = {
            item.get("node_id") for item in flattened_nodes if isinstance(item, dict)
        }
        if None in flattened_node_ids or len(flattened_node_ids) != len(flattened_nodes):
            return False, "Phase 12 flattened Python IR has invalid node identities"
        if any(
            not record.get("provenance", {}).get("source_node_ids")
            or any(
                node_id not in flattened_node_ids
                for node_id in record["provenance"]["source_node_ids"]
            )
            for table in module_tables.values()
            for record in table["records"]
        ):
            return False, "Phase 12 module fact provenance references an absent node"

        resolution = payload.get("module_resolution")
        expected_renames = [
            {
                "function_node_id": function_by_node[node_id]["function_node_id"],
                "source_name": function_by_node[node_id]["source_name"],
                "flattened_name": function_by_node[node_id]["flattened_name"],
            }
            for node_id in expected_function_ids
        ]
        expected_edges = [
            {"importer_module_id": importer, "target_module_id": target}
            for importer, target in expected_edge_values
        ]
        if (
            not isinstance(resolution, dict)
            or resolution.get("schema_version") != "module-resolution/0.12"
            or resolution.get("primary_module_id") != primary_module_id
            or resolution.get("source_module_order") != expected_source_module_order
            or resolution.get("module_order") != module_order
            or resolution.get("dependency_edges") != expected_edges
            or resolution.get("import_item_count") != len(imports)
            or resolution.get("function_renames") != expected_renames
            or resolution.get("initialization_node_id") != init_value.get("initialization_node_id")
            or resolution.get("flattened_root_node_id") != flattened_python_ir.get("root_node_id")
            or resolution.get("bundle_document_id") != flattened_python_ir.get("document_id")
            or resolution.get("module_bundle_assembly_node_id")
            != payload.get("module_bundle_assembly_node_id")
        ):
            return False, "Phase 12 resolution summary disagrees with closed module facts"
    return True, ""
