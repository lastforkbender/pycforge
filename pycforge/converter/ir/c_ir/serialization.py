from __future__ import annotations
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any
from .model import (
    CONDITIONAL_SCHEMA_VERSION,
    CONTAINER_SCHEMA_VERSION,
    MODULE_SCHEMA_VERSION,
    NUMERIC_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    KEYWORD_CALL_SCHEMA_VERSION,
    KEYWORD_ONLY_CALL_SCHEMA_VERSION,
    CTranslationUnit,
)

def to_data(value: Any) -> Any:
    if isinstance(value, Enum): return value.value
    if is_dataclass(value):
        return {"kind": type(value).__name__, **{f.name: to_data(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, tuple): return [to_data(item) for item in value]
    if isinstance(value, dict): return {str(k): to_data(v) for k,v in sorted(value.items())}
    return value

def serialize_translation_unit(unit: CTranslationUnit) -> dict[str, Any]:
    data = to_data(unit)
    if unit.schema_version not in {RECORD_SCHEMA_VERSION, NUMERIC_SCHEMA_VERSION, CONDITIONAL_SCHEMA_VERSION, KEYWORD_CALL_SCHEMA_VERSION, KEYWORD_ONLY_CALL_SCHEMA_VERSION} and _contains_record_kind(data):
        raise ValueError("record C IR nodes require schema c-ir/0.13")
    if unit.schema_version not in {MODULE_SCHEMA_VERSION, RECORD_SCHEMA_VERSION, NUMERIC_SCHEMA_VERSION, CONDITIONAL_SCHEMA_VERSION, KEYWORD_CALL_SCHEMA_VERSION, KEYWORD_ONLY_CALL_SCHEMA_VERSION}:
        data = _without_module_fields(data)
    if unit.schema_version not in {
        CONTAINER_SCHEMA_VERSION,
        MODULE_SCHEMA_VERSION,
        RECORD_SCHEMA_VERSION,
        NUMERIC_SCHEMA_VERSION,
        CONDITIONAL_SCHEMA_VERSION,
        KEYWORD_CALL_SCHEMA_VERSION,
        KEYWORD_ONLY_CALL_SCHEMA_VERSION,
    }:
        # C IR 0.8-0.10 are StableInternal serialized contracts. New 0.11
        # array metadata must not rewrite their payloads or helper fingerprints.
        return _without_container_type_fields(data)
    return data


def _contains_record_kind(value: Any) -> bool:
    if isinstance(value, list):
        return any(_contains_record_kind(item) for item in value)
    if isinstance(value, dict):
        if value.get("kind") in {
            "CRecordDefinition",
            "CRecordField",
            "CRecordInitializer",
            "CMemberAccessExpr",
        }:
            return True
        return any(_contains_record_kind(item) for item in value.values())
    return False


def _without_module_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [_without_module_fields(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _without_module_fields(item)
            for key, item in value.items()
            if key not in {
                "module_manifest",
                "module_order",
                "module_dependencies",
                "owner_module_id",
                "owner_document_id",
                "bundle_function_ordinal",
            }
        }
    return value


def _without_container_type_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [_without_container_type_fields(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _without_container_type_fields(item)
            for key, item in value.items()
            if key not in {"array_extents", "object_const"}
        }
    return value
