"""Deterministic translation-unit assembly for resolved helper plans."""

from __future__ import annotations

from pycforge.converter.ir.c_ir import (
    CFunctionDefinition,
    CFunctionPrototype,
    CRecordDefinition,
    CTranslationUnit,
    CTranslationUnitBuilder,
    CONDITIONAL_SCHEMA_VERSION,
    CONTAINER_SCHEMA_VERSION,
    HELPER_SCHEMA_VERSION,
    MODULE_SCHEMA_VERSION,
    NUMERIC_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    KEYWORD_CALL_SCHEMA_VERSION,
    KEYWORD_ONLY_CALL_SCHEMA_VERSION,
    validate_translation_unit,
)

from .model import ResolvedHelperPlan
from .registry import HelperRegistryError


def assemble_translation_unit(
    source_unit: CTranslationUnit,
    plan: ResolvedHelperPlan,
) -> CTranslationUnit:
    """Insert each resolved helper once without changing an empty-plan unit."""

    if source_unit.target_contract != plan.target_contract:
        raise HelperRegistryError(
            "PYC3304",
            "resolved helper target does not match the source translation unit",
        )
    if not plan.assets:
        return source_unit

    includes_by_key = {}
    for include in sorted(
        source_unit.includes + tuple(item for asset in plan.assets for item in asset.includes),
        key=lambda item: (not item.system, item.header, item.node_id),
    ):
        includes_by_key.setdefault((include.header, include.system), include)

    source_prototypes = tuple(
        item for item in source_unit.declarations if isinstance(item, CFunctionPrototype)
    )
    source_definitions = tuple(
        item for item in source_unit.declarations if isinstance(item, CFunctionDefinition)
    )
    source_other = tuple(
        item
        for item in source_unit.declarations
        if not isinstance(item, (CFunctionPrototype, CFunctionDefinition))
    )
    source_records = tuple(
        item for item in source_other if isinstance(item, CRecordDefinition)
    )
    source_variables = tuple(
        item for item in source_other if not isinstance(item, CRecordDefinition)
    )
    helper_prototypes = tuple(asset.prototype for asset in plan.assets)
    helper_definitions = tuple(asset.definition for asset in plan.assets)

    builder = CTranslationUnitBuilder(
        source_unit.target_contract,
        node_id=source_unit.node_id,
        provenance=source_unit.provenance,
        schema_version=(
            source_unit.schema_version
            if source_unit.schema_version in {
                CONTAINER_SCHEMA_VERSION,
                MODULE_SCHEMA_VERSION,
                RECORD_SCHEMA_VERSION,
                NUMERIC_SCHEMA_VERSION,
                CONDITIONAL_SCHEMA_VERSION,
                KEYWORD_CALL_SCHEMA_VERSION,
                KEYWORD_ONLY_CALL_SCHEMA_VERSION,
            }
            else HELPER_SCHEMA_VERSION
        ),
        module_manifest=source_unit.module_manifest,
        module_order=source_unit.module_order,
        module_dependencies=source_unit.module_dependencies,
    )
    for include in includes_by_key.values():
        builder.add_include(include)
    for declaration in (
        source_records
        + helper_prototypes
        + source_prototypes
        + source_variables
        + helper_definitions
        + source_definitions
    ):
        builder.add_declaration(declaration)
    assembled = builder.build()
    validation = validate_translation_unit(assembled)
    if not validation.accepted:
        raise HelperRegistryError(
            "PYC3306",
            "helper assembly produced invalid C IR: " + "; ".join(validation.errors),
        )
    return assembled
