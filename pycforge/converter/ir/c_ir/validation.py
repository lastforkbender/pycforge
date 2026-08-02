from __future__ import annotations

import math
import re
from dataclasses import dataclass

from pycforge.converter.contracts.identifiers import (
    C11_EXTERNAL_IDENTIFIERS as _C11_EXTERNAL_IDENTIFIERS,
    C_KEYWORDS as _C_KEYWORDS,
    TARGET_RESERVED_NAMES as _TARGET_RESERVED_NAMES,
)
from pycforge.converter.contracts.configuration import MAX_CONTAINER_ELEMENTS

from .model import *

_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_BASES = {"void","char","int","long","int8_t","uint8_t","int16_t","uint16_t","int32_t","uint32_t","int64_t","uint64_t","bool","double"}
_LOGICAL = {CBinaryOp.LOGICAL_AND, CBinaryOp.LOGICAL_OR}
_COMPARISONS = {CBinaryOp.EQUAL, CBinaryOp.NOT_EQUAL, CBinaryOp.LESS, CBinaryOp.LESS_EQUAL, CBinaryOp.GREATER, CBinaryOp.GREATER_EQUAL}
_NUMERIC = {"int8_t","uint8_t","int16_t","uint16_t","int32_t","uint32_t","int64_t","uint64_t","int","long","double"}
_INTEGER = _NUMERIC - {"double"}
_INTEGER_ONLY = {CBinaryOp.REMAINDER, CBinaryOp.SHIFT_LEFT, CBinaryOp.SHIFT_RIGHT, CBinaryOp.BIT_AND, CBinaryOp.BIT_XOR, CBinaryOp.BIT_OR}
_HEADER = re.compile(r"^[A-Za-z0-9_./-]+$")
_REGISTERED_HEADERS = {("stdint.h", True), ("stdbool.h", True)}
_STDINT_BASES = {"int8_t","uint8_t","int16_t","uint16_t","int32_t","uint32_t","int64_t","uint64_t"}
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_MODULE_AWARE_SCHEMAS = {
    MODULE_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    NUMERIC_SCHEMA_VERSION,
    CONDITIONAL_SCHEMA_VERSION,
    KEYWORD_CALL_SCHEMA_VERSION,
    KEYWORD_ONLY_CALL_SCHEMA_VERSION,
}
_RECORD_AWARE_SCHEMAS = {
    RECORD_SCHEMA_VERSION,
    NUMERIC_SCHEMA_VERSION,
    CONDITIONAL_SCHEMA_VERSION,
    KEYWORD_CALL_SCHEMA_VERSION,
    KEYWORD_ONLY_CALL_SCHEMA_VERSION,
}
_CONTAINER_AWARE_SCHEMAS = {
    CONTAINER_SCHEMA_VERSION,
    MODULE_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    NUMERIC_SCHEMA_VERSION,
    CONDITIONAL_SCHEMA_VERSION,
    KEYWORD_CALL_SCHEMA_VERSION,
    KEYWORD_ONLY_CALL_SCHEMA_VERSION,
}
_HELPER_AWARE_SCHEMAS = {
    HELPER_SCHEMA_VERSION,
    CONTAINER_SCHEMA_VERSION,
    MODULE_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    NUMERIC_SCHEMA_VERSION,
    CONDITIONAL_SCHEMA_VERSION,
    KEYWORD_CALL_SCHEMA_VERSION,
    KEYWORD_ONLY_CALL_SCHEMA_VERSION,
}


@dataclass(frozen=True, slots=True)
class CIRValidationResult:
    accepted: bool
    errors: tuple[str, ...]


def _identifier_error(name: str, *, file_scope: bool = False) -> str | None:
    if not _ID.fullmatch(name): return f"invalid C identifier: {name}"
    if name in _C_KEYWORDS or name in _TARGET_RESERVED_NAMES: return f"reserved target name cannot be an identifier: {name}"
    if name.startswith("_"): return f"implementation-reserved identifier: {name}"
    if file_scope and name in _C11_EXTERNAL_IDENTIFIERS: return f"reserved C11 external identifier: {name}"
    return None


def validate_translation_unit(unit: CTranslationUnit) -> CIRValidationResult:
    errors: list[str] = []
    node_ids: set[str] = set()
    globals_by_binding: dict[str, tuple[CIdentifier, CType | None]] = {}
    global_spelling: dict[str, str] = {}
    signatures: dict[str, tuple[CType, tuple[CType, ...]]] = {}
    parameter_identities: dict[str, tuple[tuple[str, str], ...]] = {}
    function_storage: dict[str, CStorage] = {}
    function_origins: dict[str, str] = {}
    external_significant_prefixes: dict[str, str] = {}
    function_ownership: dict[str, tuple[str | None, str | None, int | None]] = {}
    represented_cross_module_calls: set[tuple[str, str]] = set()
    active_source_owner: str | None = None
    active_source_document: str | None = None
    prototype_bindings: set[str] = set()
    definition_bindings: set[str] = set()
    used_bases: set[str] = set()
    record_definitions: dict[str, CRecordDefinition] = {}
    record_bindings: dict[str, CRecordDefinition] = {}
    record_fields: dict[str, tuple[CRecordDefinition, CRecordField]] = {}

    if unit.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append("unsupported C IR schema")
    if not unit.target_contract:
        errors.append("missing Target C Source Contract")

    module_by_id: dict[str, CModuleManifestEntry] = {}
    module_by_document: dict[str, CModuleManifestEntry] = {}
    module_order_index: dict[str, int] = {}
    if unit.schema_version in _MODULE_AWARE_SCHEMAS:
        module_ids = [item.module_id for item in unit.module_manifest]
        document_ids = [item.document_id for item in unit.module_manifest]
        bundle_ordinals = sorted(item.bundle_ordinal for item in unit.module_manifest)
        if not unit.module_manifest:
            errors.append("C IR 0.12+ requires a nonempty module manifest")
        if len(module_ids) != len(set(module_ids)) or any(not item for item in module_ids):
            errors.append("module manifest IDs must be nonempty and unique")
        if len(document_ids) != len(set(document_ids)) or any(not item for item in document_ids):
            errors.append("module manifest document IDs must be nonempty and unique")
        if bundle_ordinals != list(range(len(unit.module_manifest))):
            errors.append("module manifest bundle ordinals must be contiguous")
        if sum(item.is_primary is True for item in unit.module_manifest) != 1:
            errors.append("module manifest requires exactly one primary document")
        if any(item.is_primary is not (item.bundle_ordinal == 0) for item in unit.module_manifest):
            errors.append("module manifest primary marker must identify bundle ordinal zero")
        if any(not item.logical_name for item in unit.module_manifest):
            errors.append("module manifest logical source names must be nonempty")
        if tuple(module_ids) != unit.module_order or len(unit.module_order) != len(set(unit.module_order)):
            errors.append("module manifest and module order disagree")
        module_by_id = {item.module_id: item for item in unit.module_manifest}
        module_by_document = {item.document_id: item for item in unit.module_manifest}
        module_order_index = {module_id: ordinal for ordinal, module_id in enumerate(unit.module_order)}
        if unit.module_dependencies != tuple(sorted(set(unit.module_dependencies))):
            errors.append("module dependency edges must be unique and sorted")
        for importer, target in unit.module_dependencies:
            if importer not in module_by_id or target not in module_by_id or importer == target:
                errors.append("module dependency edge references an invalid module")
            elif module_order_index[target] >= module_order_index[importer]:
                errors.append("C IR module order is not dependency-first")
    elif unit.module_manifest or unit.module_order or unit.module_dependencies:
        errors.append("module metadata requires C IR schema 0.12 or later")

    def node(node_id: str) -> None:
        if not node_id: errors.append("empty C IR node id")
        elif node_id in node_ids: errors.append(f"duplicate C IR node id: {node_id}")
        else: node_ids.add(node_id)

    def record_source_document(
        provenance: CProvenance,
        subject: str,
        *,
        expected: str | None = None,
    ) -> str | None:
        """Validate the document anchor for a Phase 13 record C IR node."""

        if unit.schema_version not in _RECORD_AWARE_SCHEMAS:
            return provenance.source_document_id
        document_id = provenance.source_document_id
        if not isinstance(document_id, str) or document_id not in module_by_document:
            errors.append(
                f"{subject} provenance must reference a document in the module manifest"
            )
            return None
        if expected is not None and document_id != expected:
            errors.append(f"{subject} provenance disagrees with its owning source document")
        return document_id

    def typ(value: CType, *, allow_void: bool = False) -> None:
        used_bases.add(value.base)
        if value.base not in _ALLOWED_BASES and value.base not in record_definitions:
            errors.append(f"unsupported C base type: {value.base}")
        if value.base in record_definitions and unit.schema_version not in _RECORD_AWARE_SCHEMAS:
            errors.append(f"record types require C IR schema 0.13: {value.base}")
        if value.base == "void" and value.pointer_depth == 0 and not allow_void: errors.append("void object type is invalid")
        if value.base == "void" and value.array_extents: errors.append("array element type cannot be void")
        if not isinstance(value.pointer_depth, int) or isinstance(value.pointer_depth, bool) or value.pointer_depth < 0: errors.append("invalid pointer depth")
        if any(not isinstance(item, CQualifier) for item in value.qualifiers): errors.append("invalid type qualifier")
        if len(set(value.qualifiers)) != len(value.qualifiers): errors.append("duplicate type qualifier")
        if not isinstance(value.object_const, bool): errors.append("invalid object-const marker")
        if value.object_const and not value.array_extents: errors.append("object-const is reserved for fixed-array elements")
        if value.array_extents:
            if unit.schema_version not in _CONTAINER_AWARE_SCHEMAS:
                errors.append("array types require C IR schema 0.11")
            if len(value.array_extents) != 1:
                errors.append("only one-dimensional fixed arrays are supported")
            if any(
                not isinstance(item, int)
                or isinstance(item, bool)
                or not 1 <= item <= MAX_CONTAINER_ELEMENTS
                for item in value.array_extents
            ):
                errors.append("array extent must be an integer from 1 through 64")

    def identifier(value: CIdentifier, *, file_scope: bool = False) -> None:
        if not value.binding_id: errors.append("empty C binding id")
        problem = _identifier_error(value.spelling, file_scope=file_scope)
        if problem: errors.append(problem)

    def declare_global(value: CIdentifier, type_ref: CType | None) -> None:
        identifier(value, file_scope=True)
        if value.binding_id in record_bindings:
            errors.append(f"binding ID is shared by a record type and an object: {value.binding_id}")
        old = globals_by_binding.get(value.binding_id)
        if old and old[0].spelling != value.spelling: errors.append(f"binding spelling mismatch: {value.binding_id}")
        elif old and old[1] != type_ref: errors.append(f"binding type mismatch: {value.binding_id}")
        else: globals_by_binding.setdefault(value.binding_id, (value, type_ref))
        other = global_spelling.get(value.spelling)
        if other and other != value.binding_id: errors.append(f"duplicate global identifier spelling: {value.spelling}")
        global_spelling.setdefault(value.spelling, value.binding_id)

    def register_function(value: CFunctionPrototype | CFunctionDefinition) -> None:
        helper = value.provenance.origin_kind == "support-template"
        if not isinstance(value.storage, CStorage):
            errors.append(f"invalid function storage for {value.identifier.spelling}")
        elif helper:
            if unit.schema_version not in _HELPER_AWARE_SCHEMAS:
                errors.append(f"support-template function requires C IR schema 0.10 or later: {value.identifier.spelling}")
            if value.storage is not CStorage.STATIC:
                errors.append(f"support-template function requires static linkage: {value.identifier.spelling}")
            if not value.identifier.spelling.startswith("pycf_"):
                errors.append(f"support-template function requires reserved pycf_ spelling: {value.identifier.spelling}")
        elif value.storage is not CStorage.NONE:
            errors.append(f"source function requires default external linkage: {value.identifier.spelling}")
        elif not helper:
            significant_prefix=value.identifier.spelling[:31]
            previous=external_significant_prefixes.get(significant_prefix)
            if previous is not None and previous != value.identifier.binding_id:
                errors.append(f"external identifiers collide within the C11 31-character significant prefix: {value.identifier.spelling}")
            external_significant_prefixes.setdefault(significant_prefix,value.identifier.binding_id)
        if unit.schema_version in _MODULE_AWARE_SCHEMAS and not helper:
            owner = module_by_id.get(value.owner_module_id or "")
            if (
                owner is None
                or value.owner_document_id != owner.document_id
                or not isinstance(value.bundle_function_ordinal, int)
                or isinstance(value.bundle_function_ordinal, bool)
                or value.bundle_function_ordinal < 0
            ):
                errors.append(f"source function has invalid module ownership: {value.identifier.spelling}")
            if len(unit.module_manifest) > 1 and not value.identifier.spelling.startswith("pycm_"):
                errors.append(f"multi-document source function requires reserved pycm_ spelling: {value.identifier.spelling}")
            elif len(unit.module_manifest) > 1:
                digest_start = len("pycm_")
                digest_end = digest_start + 64
                digest = value.identifier.spelling[digest_start:digest_end]
                escaped_owner = (value.owner_module_id or "").replace("_", "_u").replace(".", "_d")
                readable_suffix = value.identifier.spelling[digest_end:]
                expected_prefix = f"__{escaped_owner}__"
                if (
                    not _SHA256_HEX.fullmatch(digest)
                    or not readable_suffix.startswith(expected_prefix)
                    or not readable_suffix.removeprefix(expected_prefix)
                ):
                    errors.append(
                        f"multi-document source function requires digest-first module-qualified spelling: {value.identifier.spelling}"
                    )
            if len(unit.module_manifest) == 1 and value.identifier.spelling.startswith("pycm_"):
                errors.append(f"singleton source function must retain its legacy spelling: {value.identifier.spelling}")
            if value.provenance.source_document_id != value.owner_document_id:
                errors.append(f"source function provenance disagrees with module ownership: {value.identifier.spelling}")
        elif unit.schema_version not in _MODULE_AWARE_SCHEMAS and any(
            item is not None
            for item in (value.owner_module_id, value.owner_document_id, value.bundle_function_ordinal)
        ):
            errors.append(f"module ownership metadata requires C IR schema 0.12 or later: {value.identifier.spelling}")
        typ(value.return_type, allow_void=True)
        if value.return_type.array_extents:
            errors.append(f"function return types cannot be arrays: {value.identifier.spelling}")
        returned_record = record_definitions.get(value.return_type.base)
        if (
            returned_record is not None
            and not helper
            and returned_record.provenance.source_document_id != value.owner_document_id
        ):
            errors.append(
                f"record return type belongs to a foreign source document: {value.identifier.spelling}"
            )
        for parameter in value.parameters:
            node(parameter.node_id); typ(parameter.type_ref); identifier(parameter.identifier)
            if parameter.type_ref.array_extents:
                errors.append(f"array parameters are outside the fixed local-container profile: {value.identifier.spelling}")
            parameter_record = record_definitions.get(parameter.type_ref.base)
            if parameter_record is not None and not helper:
                record_source_document(
                    parameter.provenance,
                    f"record parameter {parameter.identifier.spelling}",
                    expected=value.owner_document_id,
                )
                record_source_document(
                    parameter.identifier.provenance,
                    f"record parameter identifier {parameter.identifier.spelling}",
                    expected=value.owner_document_id,
                )
                if (
                    parameter_record.provenance.source_document_id
                    != value.owner_document_id
                ):
                    errors.append(
                        "record parameter type belongs to a foreign source document: "
                        f"{parameter.identifier.spelling}"
                    )
        parameter_spellings = [item.identifier.spelling for item in value.parameters]
        if len(parameter_spellings) != len(set(parameter_spellings)): errors.append(f"duplicate parameter spelling in {value.identifier.spelling}")
        signature = (value.return_type, tuple(item.type_ref for item in value.parameters))
        declare_global(value.identifier, None)
        old = signatures.get(value.identifier.binding_id)
        if old and old != signature: errors.append(f"inconsistent function signature: {value.identifier.spelling}")
        signatures.setdefault(value.identifier.binding_id, signature)
        old_storage = function_storage.get(value.identifier.binding_id)
        if old_storage is not None and old_storage is not value.storage:
            errors.append(f"prototype/definition storage mismatch: {value.identifier.spelling}")
        function_storage.setdefault(value.identifier.binding_id, value.storage)
        origin = value.provenance.origin_kind
        old_origin = function_origins.get(value.identifier.binding_id)
        if old_origin is not None and old_origin != origin and "support-template" in {old_origin, origin}:
            errors.append(f"prototype/definition provenance mismatch: {value.identifier.spelling}")
        function_origins.setdefault(value.identifier.binding_id, origin)
        ownership = (value.owner_module_id, value.owner_document_id, value.bundle_function_ordinal)
        old_ownership = function_ownership.get(value.identifier.binding_id)
        if old_ownership is not None and old_ownership != ownership:
            errors.append(f"prototype/definition module ownership mismatch: {value.identifier.spelling}")
        function_ownership.setdefault(value.identifier.binding_id, ownership)
        identities = tuple((item.identifier.binding_id, item.identifier.spelling) for item in value.parameters)
        old_identities = parameter_identities.get(value.identifier.binding_id)
        if old_identities and old_identities != identities: errors.append(f"prototype/definition parameter identity mismatch: {value.identifier.spelling}")
        parameter_identities.setdefault(value.identifier.binding_id, identities)
        declaration_set = prototype_bindings if isinstance(value, CFunctionPrototype) else definition_bindings
        if value.identifier.binding_id in declaration_set: errors.append(f"duplicate function {'prototype' if isinstance(value,CFunctionPrototype) else 'definition'}: {value.identifier.spelling}")
        declaration_set.add(value.identifier.binding_id)

    node(unit.node_id)
    headers: set[tuple[str, bool]] = set()
    for include in unit.includes:
        node(include.node_id)
        if not include.header or not _HEADER.fullmatch(include.header) or include.header.startswith("/") or ".." in include.header.split("/"): errors.append(f"invalid include header: {include.header}")
        key = (include.header, include.system)
        if key in headers: errors.append(f"duplicate include: {include.header}")
        if key not in _REGISTERED_HEADERS: errors.append(f"unregistered include: {include.header}")
        headers.add(key)

    # Register typedef names before validating any use so record types are
    # structural and independent of declaration traversal during validation.
    for declaration in unit.declarations:
        if not isinstance(declaration, CRecordDefinition):
            continue
        if unit.schema_version not in _RECORD_AWARE_SCHEMAS:
            errors.append("record definitions require C IR schema 0.13")
        identifier(declaration.identifier, file_scope=True)
        record_document = record_source_document(
            declaration.provenance,
            f"record definition {declaration.identifier.spelling}",
        )
        record_source_document(
            declaration.identifier.provenance,
            f"record type identifier {declaration.identifier.spelling}",
            expected=record_document,
        )
        previous_binding = record_bindings.get(declaration.identifier.binding_id)
        if previous_binding is not None:
            errors.append(f"duplicate record type binding: {declaration.identifier.binding_id}")
        else:
            record_bindings[declaration.identifier.binding_id] = declaration
        previous_spelling = record_definitions.get(declaration.identifier.spelling)
        if previous_spelling is not None:
            errors.append(f"duplicate record type spelling: {declaration.identifier.spelling}")
        else:
            record_definitions[declaration.identifier.spelling] = declaration
        other = global_spelling.get(declaration.identifier.spelling)
        if other is not None and other != declaration.identifier.binding_id:
            errors.append(f"duplicate global identifier spelling: {declaration.identifier.spelling}")
        global_spelling.setdefault(declaration.identifier.spelling, declaration.identifier.binding_id)

    # Register all external names and signatures before validating bodies so
    # forward calls are structural and never depend on declaration order.
    for declaration in unit.declarations:
        node(declaration.node_id)
        if isinstance(declaration, CRecordDefinition):
            if not declaration.fields:
                errors.append(f"record definition requires at least one field: {declaration.identifier.spelling}")
            if len(declaration.fields) > MAX_CONTAINER_ELEMENTS:
                errors.append(f"record definition exceeds the 64-field limit: {declaration.identifier.spelling}")
            record_document = declaration.provenance.source_document_id
            field_spellings: set[str] = set()
            for field in declaration.fields:
                node(field.node_id)
                identifier(field.identifier)
                field_document = record_source_document(
                    field.provenance,
                    f"record field {field.identifier.spelling}",
                    expected=record_document,
                )
                record_source_document(
                    field.identifier.provenance,
                    f"record field identifier {field.identifier.spelling}",
                    expected=field_document or record_document,
                )
                typ(field.type_ref)
                if field.type_ref not in (
                    CType("int64_t"),
                    CType("double"),
                    CType("bool"),
                ):
                    errors.append(
                        "record fields require an exact unqualified int64_t, "
                        f"double, or bool type: {field.identifier.spelling}"
                    )
                if field.type_ref.base in record_definitions:
                    errors.append(f"nested record fields are outside the C IR 0.13 profile: {field.identifier.spelling}")
                if field.type_ref.array_extents:
                    errors.append(f"record fields must be scalar: {field.identifier.spelling}")
                if field.identifier.spelling in field_spellings:
                    errors.append(f"duplicate record field spelling: {field.identifier.spelling}")
                field_spellings.add(field.identifier.spelling)
                if field.identifier.binding_id in record_bindings:
                    errors.append(f"binding ID is shared by a record type and field: {field.identifier.binding_id}")
                previous_field = record_fields.get(field.identifier.binding_id)
                if previous_field is not None:
                    errors.append(f"duplicate record field binding: {field.identifier.binding_id}")
                else:
                    record_fields[field.identifier.binding_id] = (declaration, field)
        elif isinstance(declaration, (CFunctionPrototype, CFunctionDefinition)):
            if isinstance(declaration, CFunctionPrototype) and unit.schema_version == LEGACY_SCHEMA_VERSION:
                errors.append("function prototypes require C IR schema 0.9")
            register_function(declaration)
        elif isinstance(declaration, CVariableDeclaration):
            typ(declaration.type_ref); declare_global(declaration.identifier, declaration.type_ref)
            if declaration.type_ref.array_extents:
                errors.append("fixed arrays must have automatic function-local storage")
        else:
            errors.append(f"unknown external declaration: {type(declaration).__name__}")

    if unit.schema_version in {
        SCHEMA_VERSION,
        HELPER_SCHEMA_VERSION,
        CONTAINER_SCHEMA_VERSION,
        MODULE_SCHEMA_VERSION,
        RECORD_SCHEMA_VERSION,
        NUMERIC_SCHEMA_VERSION,
        CONDITIONAL_SCHEMA_VERSION,
        KEYWORD_CALL_SCHEMA_VERSION,
        KEYWORD_ONLY_CALL_SCHEMA_VERSION,
    }:
        if prototype_bindings != definition_bindings:
            errors.append("C IR 0.9+ requires exactly one prototype for every function definition")
        definition_seen = False
        for declaration in unit.declarations:
            if isinstance(declaration, CFunctionDefinition):
                definition_seen = True
            elif isinstance(declaration, CFunctionPrototype) and definition_seen:
                errors.append("function prototypes must precede function definitions")
                break
    if unit.schema_version in _MODULE_AWARE_SCHEMAS:
        def declaration_category(value: CExternalDeclaration) -> int:
            if isinstance(value, CRecordDefinition):
                return 0
            helper = value.provenance.origin_kind == "support-template"
            if isinstance(value, CFunctionPrototype):
                return 1 if helper else 2
            if isinstance(value, CVariableDeclaration):
                return 3
            return 4 if helper else 5

        categories = [declaration_category(item) for item in unit.declarations]
        if categories != sorted(categories):
            errors.append("C IR 0.12+ declaration categories are not in assembly order")
        source_prototypes = [
            item for item in unit.declarations
            if isinstance(item, CFunctionPrototype) and item.provenance.origin_kind != "support-template"
        ]
        source_definitions = [
            item for item in unit.declarations
            if isinstance(item, CFunctionDefinition) and item.provenance.origin_kind != "support-template"
        ]
        expected_ordinals = list(range(len(source_prototypes)))
        if [item.bundle_function_ordinal for item in source_prototypes] != expected_ordinals:
            errors.append("source prototypes are not in module/function order")
        if [item.bundle_function_ordinal for item in source_definitions] != expected_ordinals:
            errors.append("source definitions are not in module/function order")

    scopes: list[dict[str, tuple[CIdentifier, CType]]] = []
    spellings: list[dict[str, str]] = []

    def push_scope() -> None:
        scopes.append({}); spellings.append({})

    def pop_scope() -> None:
        scopes.pop(); spellings.pop()

    def declare_local(value: CIdentifier, type_ref: CType) -> None:
        identifier(value); typ(type_ref)
        if value.binding_id in record_bindings or value.binding_id in record_fields:
            errors.append(f"local binding ID collides with a record binding: {value.binding_id}")
        if value.binding_id in scopes[-1]: errors.append(f"duplicate local binding declaration: {value.binding_id}")
        other = spellings[-1].get(value.spelling)
        if other and other != value.binding_id: errors.append(f"duplicate local identifier spelling: {value.spelling}")
        scopes[-1][value.binding_id] = (value, type_ref)
        spellings[-1][value.spelling] = value.binding_id

    def lookup(binding_id: str) -> tuple[CIdentifier, CType | None] | None:
        for scope in reversed(scopes):
            if binding_id in scope: return scope[binding_id]
        return globals_by_binding.get(binding_id)

    def initializer_type_matches(declared: CType, actual: CType) -> bool:
        if declared == actual:
            return True
        # An aggregate initializer is represented by the unqualified record
        # value it constructs.  C permits that initializer for a const record
        # object; const applies to the destination after initialization.
        return (
            actual.base in record_definitions
            and actual == CType(actual.base)
            and declared == CType(actual.base, (CQualifier.CONST,))
        )

    def expression(
        value: CExpression,
        *,
        initializer: bool = False,
        assignment_target: bool = False,
    ) -> CType | None:
        node(value.node_id)
        if isinstance(value, CRecordInitializer):
            if unit.schema_version not in _RECORD_AWARE_SCHEMAS:
                errors.append("record initializers require C IR schema 0.13")
            if not initializer:
                errors.append("record initializers are valid only as variable initializers")
            typ(value.record_type)
            expected_type = CType(value.record_type.base)
            definition = record_definitions.get(value.record_type.base)
            if definition is None:
                errors.append(f"record initializer names an unknown record type: {value.record_type.base}")
                for item in value.elements:
                    expression(item)
                return None
            definition_document = definition.provenance.source_document_id
            record_source_document(
                value.provenance,
                f"record initializer for {definition.identifier.spelling}",
                expected=active_source_document or definition_document,
            )
            if (
                active_source_document is not None
                and definition_document != active_source_document
            ):
                errors.append(
                    "record initializer type belongs to a foreign source document: "
                    f"{definition.identifier.spelling}"
                )
            if value.record_type != expected_type:
                errors.append("record initializer type must be an unqualified non-pointer record type")
            actual_types = tuple(expression(item) for item in value.elements)
            expected_types = tuple(field.type_ref for field in definition.fields)
            if len(actual_types) != len(expected_types):
                errors.append(
                    f"record initializer arity mismatch for {definition.identifier.spelling}: "
                    f"expected {len(expected_types)}, found {len(actual_types)}"
                )
            elif any(actual != expected for actual, expected in zip(actual_types, expected_types)):
                errors.append(f"record initializer field type mismatch for {definition.identifier.spelling}")
            return expected_type
        if isinstance(value, CInitializerList):
            if not initializer:
                errors.append("initializer lists are valid only as variable initializers")
            if not value.elements:
                errors.append("empty initializer lists are unsupported")
                return None
            if len(value.elements) > MAX_CONTAINER_ELEMENTS:
                errors.append("initializer list exceeds the fixed capacity limit")
            element_types = tuple(expression(item) for item in value.elements)
            first = element_types[0]
            if first is None or first.array_extents or any(item != first for item in element_types):
                errors.append("initializer-list elements must have one homogeneous scalar type")
                return None
            return CType(first.base, first.qualifiers, first.pointer_depth, (len(value.elements),))
        if isinstance(value, CIdentifierRef):
            found = lookup(value.binding_id)
            if not found:
                errors.append(f"unresolved binding reference: {value.binding_id}")
                return None
            if found[1] is None:
                errors.append(f"function binding used outside a call target: {value.binding_id}")
                return None
            return found[1]
        if isinstance(value, CSubscriptExpr):
            container_type = expression(value.container)
            index_type = expression(value.index)
            if container_type is None or not container_type.array_extents:
                errors.append("subscript base must have a fixed array type")
                return None
            if index_type != CType("int64_t"):
                errors.append("subscript index must have int64_t type")
            return CType(
                container_type.base,
                container_type.qualifiers,
                container_type.pointer_depth,
                container_type.array_extents[1:],
            )
        if isinstance(value, CMemberAccessExpr):
            if unit.schema_version not in _RECORD_AWARE_SCHEMAS:
                errors.append("record member access requires C IR schema 0.13")
            receiver_type = expression(value.receiver)
            if not isinstance(value.mode, CMemberAccessMode):
                errors.append("invalid record member access mode")
                return None
            if receiver_type is None or receiver_type.array_extents:
                errors.append("record member receiver has an invalid type")
                return None
            if value.mode is CMemberAccessMode.DIRECT:
                if receiver_type.pointer_depth != 0:
                    errors.append("direct record member access requires a record object")
                    return None
            elif receiver_type.pointer_depth != 1:
                errors.append("pointer record member access requires a single-level record pointer")
                return None
            definition = record_definitions.get(receiver_type.base)
            if definition is None:
                errors.append("record member receiver must have a declared record type")
                return None
            definition_document = definition.provenance.source_document_id
            expected_document = active_source_document or definition_document
            record_source_document(
                value.provenance,
                "record member access",
                expected=expected_document,
            )
            record_source_document(
                value.receiver.provenance,
                "record member receiver",
                expected=expected_document,
            )
            if (
                active_source_document is not None
                and definition_document != active_source_document
            ):
                errors.append("record member receiver type belongs to a foreign source document")
            field_entry = record_fields.get(value.field_binding_id)
            if field_entry is None:
                errors.append(f"unresolved record field binding: {value.field_binding_id}")
                return None
            owner, field = field_entry
            if owner.identifier.binding_id != definition.identifier.binding_id:
                errors.append(
                    f"record field does not belong to receiver type: {value.field_binding_id}"
                )
                return None
            if assignment_target and CQualifier.CONST in receiver_type.qualifiers:
                errors.append("assignment target is a member of a const record object")
            return field.type_ref
        if isinstance(value, CIntegerLiteral):
            if value.suffix not in {"","L","LL","U","UL","ULL"}: errors.append(f"invalid integer suffix: {value.suffix}")
            if value.value < 0: errors.append("C integer literal nodes must be non-negative; use structured unary negation")
            if value.suffix in {"", "L", "LL"} and value.value > 2**63-1: errors.append("signed integer literal exceeds int64_t representation")
            return CType("int64_t")
        if isinstance(value, CFloatLiteral):
            if not math.isfinite(value.value): errors.append("non-finite floating literal is unsupported")
            return CType("double")
        if isinstance(value, CBooleanLiteral):
            used_bases.add("bool")
            return CType("bool")
        if isinstance(value, CStringLiteral):
            if value.encoding != "utf-8": errors.append(f"unsupported string encoding: {value.encoding}")
            if "\x00" in value.value: errors.append("embedded NUL in string literal is unsupported")
            return CType("char", (CQualifier.CONST,), 1)
        if isinstance(value, CUnaryExpr):
            operand = expression(value.operand)
            if value.op is CUnaryOp.LOGICAL_NOT:
                if operand != CType("bool"): errors.append("logical-not operand must be bool")
                return CType("bool")
            if value.op is CUnaryOp.NEGATE:
                if operand is None or operand.base not in _NUMERIC or operand.pointer_depth or operand.array_extents: errors.append("negation operand must be numeric")
                return operand
            if value.op is CUnaryOp.BITWISE_NOT:
                if operand is None or operand.base not in _INTEGER or operand.pointer_depth or operand.array_extents: errors.append("bitwise-not operand must be an integer")
                return operand
            if value.op is CUnaryOp.ADDRESS_OF:
                if operand is None: return None
                if operand.array_extents:
                    errors.append("address-of on fixed arrays is outside the C IR profile")
                    return None
                return CType(operand.base, operand.qualifiers, operand.pointer_depth + 1)
            if value.op is CUnaryOp.DEREFERENCE:
                if operand is None or operand.pointer_depth <= 0 or operand.array_extents:
                    errors.append("dereference operand must be a pointer")
                    return None
                return CType(operand.base, operand.qualifiers, operand.pointer_depth - 1)
            errors.append("unknown unary operator")
            return None
        if isinstance(value, CBinaryExpr):
            left, right = expression(value.left), expression(value.right)
            if value.op in _LOGICAL:
                if left != CType("bool") or right != CType("bool"): errors.append("logical operator operands must be bool")
                return CType("bool")
            if value.op in _COMPARISONS:
                if left is None or right is None or left != right or left.array_extents or right.array_extents: errors.append("comparison operand types are incompatible")
                return CType("bool")
            if left is None or right is None or left != right or left.base not in _NUMERIC or left.pointer_depth or left.array_extents:
                errors.append("binary arithmetic operand types are incompatible")
                return None
            if value.op in _INTEGER_ONLY and left.base not in _INTEGER:
                errors.append("integer-only binary operator has a non-integer operand")
                return None
            return left
        if isinstance(value, CCallExpr):
            node(value.callee.node_id)
            if lookup(value.callee.binding_id) is None:
                errors.append(f"unresolved call target binding: {value.callee.binding_id}")
            signature = signatures.get(value.callee.binding_id)
            if not signature:
                errors.append(f"call target is not a declared function: {value.callee.binding_id}")
                for argument in value.arguments: expression(argument)
                return None
            if unit.schema_version in _MODULE_AWARE_SCHEMAS and active_source_owner is not None:
                callee_owner = function_ownership.get(value.callee.binding_id, (None, None, None))[0]
                if callee_owner is not None and callee_owner != active_source_owner:
                    represented_cross_module_calls.add((active_source_owner, callee_owner))
            expected_return, expected_parameters = signature
            actual = tuple(expression(argument) for argument in value.arguments)
            if len(actual) != len(expected_parameters): errors.append("call argument count does not match prototype")
            elif any(left != right for left, right in zip(actual, expected_parameters)): errors.append("call argument type does not match prototype")
            return expected_return
        errors.append(f"unknown expression node: {type(value).__name__}")
        return None

    def block(value: CBlock, return_type: CType, loop_depth: int, *, own_scope: bool = True) -> None:
        node(value.node_id)
        if own_scope: push_scope()
        for item in value.statements:
            statement(item, return_type, loop_depth)
        if own_scope: pop_scope()

    def statement(value: CStatement, return_type: CType, loop_depth: int) -> None:
        node(value.node_id)
        if isinstance(value, CVariableDeclaration):
            initializer_type = expression(value.initializer, initializer=True) if value.initializer else None
            declare_local(value.identifier, value.type_ref)
            local_record = record_definitions.get(value.type_ref.base)
            if local_record is not None:
                record_document = local_record.provenance.source_document_id
                expected_document = active_source_document or record_document
                record_source_document(
                    value.provenance,
                    f"local record {value.identifier.spelling}",
                    expected=expected_document,
                )
                record_source_document(
                    value.identifier.provenance,
                    f"local record identifier {value.identifier.spelling}",
                    expected=expected_document,
                )
                if (
                    active_source_document is not None
                    and record_document != active_source_document
                ):
                    errors.append(
                        "local record type belongs to a foreign source document: "
                        f"{value.identifier.spelling}"
                    )
            expected_initializer_type = CType(
                value.type_ref.base,
                value.type_ref.qualifiers,
                value.type_ref.pointer_depth,
                value.type_ref.array_extents,
            )
            if initializer_type is not None and not initializer_type_matches(expected_initializer_type, initializer_type):
                errors.append(f"initializer type mismatch for {value.identifier.spelling}")
            if value.type_ref.array_extents and not isinstance(value.initializer, CInitializerList):
                errors.append(f"fixed array requires an initializer list: {value.identifier.spelling}")
        elif isinstance(value, CExpressionStatement):
            expression(value.expression)
        elif isinstance(value, CReturnStatement):
            actual = expression(value.expression) if value.expression else None
            if return_type.base == "void" and return_type.pointer_depth == 0:
                if actual is not None: errors.append("void function returns a value")
            elif actual != return_type: errors.append("return expression type does not match function signature")
        elif isinstance(value, CAssignmentStatement):
            target = expression(value.target, assignment_target=True)
            assigned = expression(value.value)
            if target is None or assigned is None or target != assigned: errors.append("assignment types are incompatible")
            if isinstance(value.target, CSubscriptExpr): errors.append("fixed-array element assignment is outside the C IR 0.11 profile")
        elif isinstance(value, CIfStatement):
            if expression(value.condition) != CType("bool"): errors.append("if condition must be bool C IR")
            block(value.then_block, return_type, loop_depth)
            if value.else_block: block(value.else_block, return_type, loop_depth)
        elif isinstance(value, CWhileStatement):
            if expression(value.condition) != CType("bool"): errors.append("while condition must be bool C IR")
            block(value.body, return_type, loop_depth + 1)
        elif isinstance(value, CForStatement):
            push_scope()
            if value.initializer.type_ref.array_extents:
                errors.append("for-loop initializer cannot declare a fixed array")
            statement(value.initializer, return_type, loop_depth)
            if expression(value.condition) != CType("bool"): errors.append("for condition must be bool C IR")
            statement(value.update, return_type, loop_depth)
            block(value.body, return_type, loop_depth + 1)
            pop_scope()
        elif isinstance(value, (CBreakStatement, CContinueStatement)):
            if loop_depth <= 0: errors.append(f"{type(value).__name__} requires an enclosing loop")
        else:
            errors.append(f"unknown statement node: {type(value).__name__}")

    for declaration in unit.declarations:
        if isinstance(declaration, CFunctionDefinition):
            source_function = declaration.provenance.origin_kind != "support-template"
            active_source_owner = declaration.owner_module_id if source_function else None
            active_source_document = (
                declaration.owner_document_id if source_function else None
            )
            push_scope()
            for parameter in declaration.parameters:
                declare_local(parameter.identifier, parameter.type_ref)
            block(declaration.body, declaration.return_type, 0, own_scope=False)
            pop_scope()
            active_source_owner = None
            active_source_document = None
        elif isinstance(declaration, CVariableDeclaration) and declaration.initializer is not None:
            actual = expression(declaration.initializer, initializer=True)
            expected = CType(
                declaration.type_ref.base,
                declaration.type_ref.qualifiers,
                declaration.type_ref.pointer_depth,
                declaration.type_ref.array_extents,
            )
            if actual is not None and not initializer_type_matches(expected, actual):
                errors.append(f"global initializer type mismatch for {declaration.identifier.spelling}")

    if unit.schema_version in _MODULE_AWARE_SCHEMAS:
        missing_call_edges = represented_cross_module_calls - set(unit.module_dependencies)
        if missing_call_edges:
            rendered = ", ".join(f"{importer}->{target}" for importer, target in sorted(missing_call_edges))
            errors.append(f"module dependencies omit represented cross-module calls: {rendered}")

    if used_bases & _STDINT_BASES and ("stdint.h", True) not in headers:
        errors.append("fixed-width integer types require registered system include stdint.h")
    if "bool" in used_bases and ("stdbool.h", True) not in headers:
        errors.append("Boolean types or literals require registered system include stdbool.h")

    return CIRValidationResult(not errors, tuple(errors))
