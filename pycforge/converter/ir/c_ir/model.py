from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

LEGACY_SCHEMA_VERSION = "c-ir/0.8"
SCHEMA_VERSION = "c-ir/0.9"
HELPER_SCHEMA_VERSION = "c-ir/0.10"
CONTAINER_SCHEMA_VERSION = "c-ir/0.11"
MODULE_SCHEMA_VERSION = "c-ir/0.12"
RECORD_SCHEMA_VERSION = "c-ir/0.13"
NUMERIC_SCHEMA_VERSION = "c-ir/0.14"
CONDITIONAL_SCHEMA_VERSION = "c-ir/0.14.1"
KEYWORD_CALL_SCHEMA_VERSION = "c-ir/0.14.2"
KEYWORD_ONLY_CALL_SCHEMA_VERSION = "c-ir/0.14.3"
SUPPORTED_SCHEMA_VERSIONS = (
    LEGACY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    HELPER_SCHEMA_VERSION,
    CONTAINER_SCHEMA_VERSION,
    MODULE_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    NUMERIC_SCHEMA_VERSION,
    CONDITIONAL_SCHEMA_VERSION,
    KEYWORD_CALL_SCHEMA_VERSION,
    KEYWORD_ONLY_CALL_SCHEMA_VERSION,
)

class CStorage(str, Enum):
    NONE = "none"
    STATIC = "static"
    EXTERN = "extern"

class CQualifier(str, Enum):
    CONST = "const"
    VOLATILE = "volatile"

class CUnaryOp(str, Enum):
    NEGATE = "-"
    LOGICAL_NOT = "!"
    BITWISE_NOT = "~"
    ADDRESS_OF = "&"
    DEREFERENCE = "*"

class CBinaryOp(str, Enum):
    MULTIPLY = "*"
    DIVIDE = "/"
    REMAINDER = "%"
    ADD = "+"
    SUBTRACT = "-"
    SHIFT_LEFT = "<<"
    SHIFT_RIGHT = ">>"
    LESS = "<"
    LESS_EQUAL = "<="
    GREATER = ">"
    GREATER_EQUAL = ">="
    EQUAL = "=="
    NOT_EQUAL = "!="
    BIT_AND = "&"
    BIT_XOR = "^"
    BIT_OR = "|"
    LOGICAL_AND = "&&"
    LOGICAL_OR = "||"

class CMemberAccessMode(str, Enum):
    DIRECT = "direct"
    POINTER = "pointer"

@dataclass(frozen=True, slots=True)
class CProvenance:
    origin_kind: str
    source_document_id: str | None = None
    source_node_ids: tuple[str, ...] = ()
    source_span: dict[str, object] | None = None
    rule_plan_id: str | None = None

@dataclass(frozen=True, slots=True)
class CType:
    base: str
    qualifiers: tuple[CQualifier, ...] = ()
    pointer_depth: int = 0
    array_extents: tuple[int, ...] = ()
    object_const: bool = False

@dataclass(frozen=True, slots=True)
class CIdentifier:
    binding_id: str
    spelling: str
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CIntegerLiteral:
    node_id: str
    value: int
    suffix: str = ""
    provenance: CProvenance = CProvenance("synthetic")

@dataclass(frozen=True, slots=True)
class CFloatLiteral:
    node_id: str
    value: float
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CBooleanLiteral:
    node_id: str
    value: bool
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CStringLiteral:
    node_id: str
    value: str
    encoding: str
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CIdentifierRef:
    node_id: str
    binding_id: str
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CUnaryExpr:
    node_id: str
    op: CUnaryOp
    operand: "CExpression"
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CBinaryExpr:
    node_id: str
    op: CBinaryOp
    left: "CExpression"
    right: "CExpression"
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CCallExpr:
    node_id: str
    callee: CIdentifierRef
    arguments: tuple["CExpression", ...]
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CInitializerList:
    node_id: str
    elements: tuple["CExpression", ...]
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CRecordInitializer:
    node_id: str
    record_type: CType
    elements: tuple["CExpression", ...]
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CSubscriptExpr:
    node_id: str
    container: "CExpression"
    index: "CExpression"
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CMemberAccessExpr:
    node_id: str
    receiver: "CExpression"
    field_binding_id: str
    mode: CMemberAccessMode
    provenance: CProvenance

CExpression: TypeAlias = CIntegerLiteral | CFloatLiteral | CBooleanLiteral | CStringLiteral | CIdentifierRef | CUnaryExpr | CBinaryExpr | CCallExpr | CInitializerList | CRecordInitializer | CSubscriptExpr | CMemberAccessExpr

@dataclass(frozen=True, slots=True)
class CParameter:
    node_id: str
    identifier: CIdentifier
    type_ref: CType
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CVariableDeclaration:
    node_id: str
    identifier: CIdentifier
    type_ref: CType
    initializer: CExpression | None
    storage: CStorage
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CExpressionStatement:
    node_id: str
    expression: CExpression
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CReturnStatement:
    node_id: str
    expression: CExpression | None
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CAssignmentStatement:
    node_id: str
    target: CIdentifierRef | CSubscriptExpr | CMemberAccessExpr
    value: CExpression
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CIfStatement:
    node_id: str
    condition: CExpression
    then_block: "CBlock"
    else_block: "CBlock | None"
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CWhileStatement:
    node_id: str
    condition: CExpression
    body: "CBlock"
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CForStatement:
    node_id: str
    initializer: CVariableDeclaration
    condition: CExpression
    update: CAssignmentStatement
    body: "CBlock"
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CBreakStatement:
    node_id: str
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CContinueStatement:
    node_id: str
    provenance: CProvenance

CStatement: TypeAlias = CVariableDeclaration | CExpressionStatement | CReturnStatement | CAssignmentStatement | CIfStatement | CWhileStatement | CForStatement | CBreakStatement | CContinueStatement

@dataclass(frozen=True, slots=True)
class CBlock:
    node_id: str
    statements: tuple[CStatement, ...]
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CFunctionDefinition:
    node_id: str
    identifier: CIdentifier
    return_type: CType
    parameters: tuple[CParameter, ...]
    body: CBlock
    storage: CStorage
    provenance: CProvenance
    owner_module_id: str | None = None
    owner_document_id: str | None = None
    bundle_function_ordinal: int | None = None

@dataclass(frozen=True, slots=True)
class CFunctionPrototype:
    node_id: str
    identifier: CIdentifier
    return_type: CType
    parameters: tuple[CParameter, ...]
    storage: CStorage
    provenance: CProvenance
    owner_module_id: str | None = None
    owner_document_id: str | None = None
    bundle_function_ordinal: int | None = None

@dataclass(frozen=True, slots=True)
class CInclude:
    node_id: str
    header: str
    system: bool
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CRecordField:
    node_id: str
    identifier: CIdentifier
    type_ref: CType
    provenance: CProvenance

@dataclass(frozen=True, slots=True)
class CRecordDefinition:
    node_id: str
    identifier: CIdentifier
    fields: tuple[CRecordField, ...]
    provenance: CProvenance

CExternalDeclaration: TypeAlias = CRecordDefinition | CFunctionPrototype | CFunctionDefinition | CVariableDeclaration

@dataclass(frozen=True, slots=True)
class CModuleManifestEntry:
    module_id: str
    document_id: str
    logical_name: str
    bundle_ordinal: int
    is_primary: bool

@dataclass(frozen=True, slots=True)
class CTranslationUnit:
    schema_version: str
    node_id: str
    target_contract: str
    includes: tuple[CInclude, ...]
    declarations: tuple[CExternalDeclaration, ...]
    provenance: CProvenance
    module_manifest: tuple[CModuleManifestEntry, ...] = ()
    module_order: tuple[str, ...] = ()
    module_dependencies: tuple[tuple[str, str], ...] = ()
