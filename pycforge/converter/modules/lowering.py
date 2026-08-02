"""Module-bundle coordination for the single C translation unit."""

from __future__ import annotations

import hashlib
from typing import Any


def enrich_source_output_mappings(
    payload: dict[str, Any],
    mappings: tuple[Any, ...],
) -> list[dict[str, Any]]:
    """Attach closed-bundle source identity without changing the renderer API."""

    tables = {item.get("table_id"): item for item in payload.get("fact_tables", ())}
    sources = {}
    sources_by_module = {}
    for record in tables.get("module-source-facts", {}).get("records", ()):
        value = record.get("value", {})
        document_id = value.get("source_document_id")
        if document_id:
            sources[document_id] = (
                value.get("module_id"),
                value.get("logical_source_name"),
            )
            sources_by_module[value.get("module_id")] = (
                document_id,
                value.get("logical_source_name"),
            )
    result = []
    for mapping in mappings:
        item = {key: getattr(mapping, key) for key in mapping.__slots__}
        module_id, logical_name = sources.get(item.get("source_document_id"), (None, None))
        item["module_id"] = module_id
        item["logical_source_name"] = logical_name
        result.append(item)

    # Imports have no rendered token of their own.  Publish separate symbol
    # relationships whose source endpoint is the alias span and whose output
    # endpoints are the already-rendered target prototype and definition.
    nodes = {
        node["node_id"]: node for node in payload.get("python_ir", {}).get("nodes", ())
    }
    plans = {
        plan.get("source_node_id"): plan.get("plan_id")
        for plan in payload.get("rule_plans", ())
    }
    bindings = {
        value.get("declaration_node_id"): value.get("binding_id")
        for record in tables.get("binding-facts", {}).get("records", ())
        for value in (record.get("value", {}),)
    }
    module_functions = {
        value.get("function_node_id"): value
        for record in tables.get("module-function-facts", {}).get("records", ())
        for value in (record.get("value", {}),)
    }
    target_outputs: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for mapping in result:
        c_node_id = mapping.get("c_node_id", "")
        relation = (
            "prototype"
            if isinstance(c_node_id, str) and c_node_id.startswith("c-prototype-")
            else "definition"
            if isinstance(c_node_id, str) and c_node_id.startswith("c-fn-")
            else None
        )
        if relation is None:
            continue
        for source_node_id in mapping.get("source_node_ids", ()):
            if source_node_id in module_functions:
                target_outputs.setdefault(source_node_id, []).append((relation, mapping))

    import_records = tables.get("module-import-facts", {}).get("records", ())
    for record in import_records:
        value = record.get("value", {})
        alias_node_id = value.get("alias_node_id")
        import_node_id = value.get("import_node_id")
        target_function_node_id = value.get("target_function_node_id")
        importer_module_id = value.get("importer_module_id")
        target_module_id = value.get("target_module_id")
        importer_document_id, importer_logical_name = sources_by_module.get(
            importer_module_id, (None, None)
        )
        target_document_id, target_logical_name = sources_by_module.get(
            target_module_id, (None, None)
        )
        alias_span = nodes.get(alias_node_id, {}).get("provenance", {}).get("source_span")
        outputs = sorted(
            target_outputs.get(target_function_node_id, ()),
            key=lambda item: (0 if item[0] == "prototype" else 1, item[1].get("c_node_id", "")),
        )
        prototype_id = next(
            (item.get("c_node_id") for relation, item in outputs if relation == "prototype"),
            None,
        )
        definition_id = next(
            (item.get("c_node_id") for relation, item in outputs if relation == "definition"),
            None,
        )
        for relation, target_mapping in outputs:
            relationship_seed = "\x1f".join(
                str(item)
                for item in (
                    value.get("import_item_id"),
                    relation,
                    target_mapping.get("c_node_id"),
                )
            ).encode("utf-8")
            relationship = {
                **{
                    key: target_mapping[key]
                    for key in (
                        "start_byte",
                        "end_byte",
                        "start_line",
                        "start_column",
                        "end_line",
                        "end_column",
                    )
                },
                "mapping_kind": "imported-function-alias-relationship",
                "relationship_id": "maprel-" + hashlib.sha256(relationship_seed).hexdigest()[:20],
                "c_node_id": target_mapping.get("c_node_id"),
                "origin_kind": "source-symbol-relationship",
                "source_document_id": importer_document_id,
                "source_node_ids": tuple(
                    item for item in (import_node_id, alias_node_id) if isinstance(item, str)
                ),
                "source_span": alias_span,
                "rule_plan_id": plans.get(alias_node_id),
                "module_id": importer_module_id,
                "logical_source_name": importer_logical_name,
                "import_item_id": value.get("import_item_id"),
                "import_node_id": import_node_id,
                "alias_node_id": alias_node_id,
                "imported_name": value.get("imported_name"),
                "local_name": value.get("local_name"),
                "target_binding_id": bindings.get(target_function_node_id),
                "target_function_node_id": target_function_node_id,
                "target_module_id": target_module_id,
                "target_source_document_id": target_document_id,
                "target_logical_source_name": target_logical_name,
                "target_generated_name": module_functions.get(target_function_node_id, {}).get(
                    "flattened_name"
                ),
                "target_output_kind": relation,
                "target_c_node_id": target_mapping.get("c_node_id"),
                "target_prototype_c_node_id": prototype_id,
                "target_definition_c_node_id": definition_id,
            }
            result.append(relationship)
    return result


def ordered_function_ids(
    payload: dict[str, Any],
    root: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    *,
    imports_allowed: bool,
    records_allowed: bool = False,
) -> tuple[tuple[str, ...], str | None]:
    """Keep the validated flattened-bundle order and erase import directives.

    ImportFrom nodes are analysis inputs only. They never become C declarations;
    the frontend's flattened root already records the deterministic dependency-
    first module and source-function order consumed here.
    """

    functions: list[str] = []
    for node_id in root["fields"].get("body", ()):
        kind = nodes[node_id]["kind"]
        if kind == "FunctionDef":
            functions.append(node_id)
        elif not (
            (imports_allowed and kind == "ImportFrom")
            or (records_allowed and kind == "ClassDef")
        ):
            return tuple(functions), node_id
    if not imports_allowed:
        return tuple(functions), None

    tables = {item.get("table_id"): item for item in payload.get("fact_tables", ())}
    function_records = tables.get("module-function-facts", {}).get("records", ())
    root_position = {node_id: ordinal for ordinal, node_id in enumerate(functions)}
    ordered = tuple(
        item["value"]["function_node_id"]
        for item in sorted(
            function_records,
            key=lambda item: (
                item["value"].get(
                    "bundle_function_ordinal",
                    root_position.get(item["value"].get("function_node_id"), 2**31 - 1),
                ),
                item["value"].get("function_node_id", ""),
            ),
        )
    )
    return (ordered if ordered and set(ordered) == set(functions) else tuple(functions)), None
