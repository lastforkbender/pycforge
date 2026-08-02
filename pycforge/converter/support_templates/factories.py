"""Project-owned structured C IR factories for accepted Phase 10 fixtures."""

from __future__ import annotations

import hashlib

from pycforge.converter.ir.c_ir import (
    CAssignmentStatement,
    CBinaryExpr,
    CBinaryOp,
    CBlock,
    CFunctionDefinition,
    CFunctionPrototype,
    CIdentifier,
    CIdentifierRef,
    CIfStatement,
    CInclude,
    CIntegerLiteral,
    CParameter,
    CProvenance,
    CReturnStatement,
    CStorage,
    CType,
    CVariableDeclaration,
)

from .model import (
    HELPER_INTERFACE_ID,
    HelperCIRAsset,
    HelperDefinition,
    HelperFailureContract,
    HelperOwnershipContract,
    HelperReference,
)


FLOOR_DIV_REFERENCE = HelperReference("pycf.i64.floor_div", "1.0.0")
FLOOR_MOD_REFERENCE = HelperReference("pycf.i64.floor_mod", "1.0.0")

_TARGETS = ("c11-portable-fixed-v1",)
_OWNERSHIP = HelperOwnershipContract(
    parameter_ownership="scalar values passed by value",
    return_ownership="scalar value returned by value",
    allocation="none",
    lifetime="automatic call lifetime only",
    cleanup="none",
)
_FAILURE = HelperFailureContract(
    strategy="caller-proved preconditions",
    preconditions=(
        "divisor is nonzero",
        "dividend is not INT64_MIN when divisor is -1",
    ),
    violation_policy=(
        "the prospective RulePlan must reject conversion or select a separately "
        "approved checked-failure contract before helper lowering"
    ),
    runtime_failure_channel="none",
)


def _sid(reference: HelperReference, role: str) -> str:
    digest = hashlib.sha256(f"{reference.canonical}\x1f{role}".encode("utf-8")).hexdigest()[:20]
    return f"c-helper-{role}-{digest}"


def _binding(reference: HelperReference, role: str) -> str:
    return f"helper-binding:{reference.canonical}:{role}"


def _ref(
    reference: HelperReference,
    binding_role: str,
    occurrence: str,
    provenance: CProvenance,
) -> CIdentifierRef:
    return CIdentifierRef(
        _sid(reference, f"ref-{occurrence}"),
        _binding(reference, binding_role),
        provenance,
    )


def _zero(reference: HelperReference, role: str, provenance: CProvenance) -> CIntegerLiteral:
    return CIntegerLiteral(_sid(reference, f"zero-{role}"), 0, "LL", provenance)


def _one(reference: HelperReference, role: str, provenance: CProvenance) -> CIntegerLiteral:
    return CIntegerLiteral(_sid(reference, f"one-{role}"), 1, "LL", provenance)


def _common_parts(reference: HelperReference, spelling: str):
    provenance = CProvenance("support-template")
    function_id = CIdentifier(_binding(reference, "function"), spelling, provenance)
    dividend_id = CIdentifier(_binding(reference, "dividend"), "pycf_dividend", provenance)
    divisor_id = CIdentifier(_binding(reference, "divisor"), "pycf_divisor", provenance)
    quotient_id = CIdentifier(_binding(reference, "quotient"), "pycf_quotient", provenance)
    remainder_id = CIdentifier(_binding(reference, "remainder"), "pycf_remainder", provenance)
    value_type = CType("int64_t")
    prototype_parameters = (
        CParameter(_sid(reference, "prototype-param-dividend"), dividend_id, value_type, provenance),
        CParameter(_sid(reference, "prototype-param-divisor"), divisor_id, value_type, provenance),
    )
    definition_parameters = (
        CParameter(_sid(reference, "definition-param-dividend"), dividend_id, value_type, provenance),
        CParameter(_sid(reference, "definition-param-divisor"), divisor_id, value_type, provenance),
    )
    prototype = CFunctionPrototype(
        _sid(reference, "prototype"),
        function_id,
        value_type,
        prototype_parameters,
        CStorage.STATIC,
        provenance,
    )
    include = CInclude(_sid(reference, "include-stdint"), "stdint.h", True, provenance)
    return (
        provenance,
        function_id,
        dividend_id,
        divisor_id,
        quotient_id,
        remainder_id,
        value_type,
        prototype,
        definition_parameters,
        include,
    )


def _adjustment_condition(reference: HelperReference, provenance: CProvenance) -> CBinaryExpr:
    remainder_nonzero = CBinaryExpr(
        _sid(reference, "condition-remainder-nonzero"),
        CBinaryOp.NOT_EQUAL,
        _ref(reference, "remainder", "condition-nonzero-remainder", provenance),
        _zero(reference, "condition-remainder", provenance),
        provenance,
    )
    remainder_negative = CBinaryExpr(
        _sid(reference, "condition-remainder-negative"),
        CBinaryOp.LESS,
        _ref(reference, "remainder", "condition-negative-remainder", provenance),
        _zero(reference, "condition-remainder-sign", provenance),
        provenance,
    )
    divisor_negative = CBinaryExpr(
        _sid(reference, "condition-divisor-negative"),
        CBinaryOp.LESS,
        _ref(reference, "divisor", "condition-negative-divisor", provenance),
        _zero(reference, "condition-divisor-sign", provenance),
        provenance,
    )
    signs_differ = CBinaryExpr(
        _sid(reference, "condition-signs-differ"),
        CBinaryOp.NOT_EQUAL,
        remainder_negative,
        divisor_negative,
        provenance,
    )
    return CBinaryExpr(
        _sid(reference, "condition-adjustment"),
        CBinaryOp.LOGICAL_AND,
        remainder_nonzero,
        signs_differ,
        provenance,
    )


def floor_div_asset() -> HelperCIRAsset:
    reference = FLOOR_DIV_REFERENCE
    (
        provenance,
        function_id,
        _dividend_id,
        _divisor_id,
        quotient_id,
        remainder_id,
        value_type,
        prototype,
        parameters,
        include,
    ) = _common_parts(reference, "pycf_i64_floor_div_v1")
    quotient = CVariableDeclaration(
        _sid(reference, "declaration-quotient"),
        quotient_id,
        value_type,
        CBinaryExpr(
            _sid(reference, "expression-quotient"),
            CBinaryOp.DIVIDE,
            _ref(reference, "dividend", "quotient-dividend", provenance),
            _ref(reference, "divisor", "quotient-divisor", provenance),
            provenance,
        ),
        CStorage.NONE,
        provenance,
    )
    remainder = CVariableDeclaration(
        _sid(reference, "declaration-remainder"),
        remainder_id,
        value_type,
        CBinaryExpr(
            _sid(reference, "expression-remainder"),
            CBinaryOp.REMAINDER,
            _ref(reference, "dividend", "remainder-dividend", provenance),
            _ref(reference, "divisor", "remainder-divisor", provenance),
            provenance,
        ),
        CStorage.NONE,
        provenance,
    )
    adjustment = CAssignmentStatement(
        _sid(reference, "assignment-adjustment"),
        _ref(reference, "quotient", "adjustment-target", provenance),
        CBinaryExpr(
            _sid(reference, "expression-adjustment"),
            CBinaryOp.SUBTRACT,
            _ref(reference, "quotient", "adjustment-left", provenance),
            _one(reference, "adjustment", provenance),
            provenance,
        ),
        provenance,
    )
    condition = CIfStatement(
        _sid(reference, "if-adjustment"),
        _adjustment_condition(reference, provenance),
        CBlock(_sid(reference, "if-adjustment-body"), (adjustment,), provenance),
        None,
        provenance,
    )
    result = CReturnStatement(
        _sid(reference, "return"),
        _ref(reference, "quotient", "return-quotient", provenance),
        provenance,
    )
    definition = CFunctionDefinition(
        _sid(reference, "definition"),
        function_id,
        value_type,
        parameters,
        CBlock(_sid(reference, "body"), (quotient, remainder, condition, result), provenance),
        CStorage.STATIC,
        provenance,
    )
    return HelperCIRAsset(reference, (include,), prototype, definition)


def floor_mod_asset() -> HelperCIRAsset:
    reference = FLOOR_MOD_REFERENCE
    (
        provenance,
        function_id,
        _dividend_id,
        _divisor_id,
        _quotient_id,
        remainder_id,
        value_type,
        prototype,
        parameters,
        include,
    ) = _common_parts(reference, "pycf_i64_floor_mod_v1")
    remainder = CVariableDeclaration(
        _sid(reference, "declaration-remainder"),
        remainder_id,
        value_type,
        CBinaryExpr(
            _sid(reference, "expression-remainder"),
            CBinaryOp.REMAINDER,
            _ref(reference, "dividend", "remainder-dividend", provenance),
            _ref(reference, "divisor", "remainder-divisor", provenance),
            provenance,
        ),
        CStorage.NONE,
        provenance,
    )
    adjustment = CAssignmentStatement(
        _sid(reference, "assignment-adjustment"),
        _ref(reference, "remainder", "adjustment-target", provenance),
        CBinaryExpr(
            _sid(reference, "expression-adjustment"),
            CBinaryOp.ADD,
            _ref(reference, "remainder", "adjustment-left", provenance),
            _ref(reference, "divisor", "adjustment-divisor", provenance),
            provenance,
        ),
        provenance,
    )
    condition = CIfStatement(
        _sid(reference, "if-adjustment"),
        _adjustment_condition(reference, provenance),
        CBlock(_sid(reference, "if-adjustment-body"), (adjustment,), provenance),
        None,
        provenance,
    )
    result = CReturnStatement(
        _sid(reference, "return"),
        _ref(reference, "remainder", "return-remainder", provenance),
        provenance,
    )
    definition = CFunctionDefinition(
        _sid(reference, "definition"),
        function_id,
        value_type,
        parameters,
        CBlock(_sid(reference, "body"), (remainder, condition, result), provenance),
        CStorage.STATIC,
        provenance,
    )
    return HelperCIRAsset(reference, (include,), prototype, definition)


def builtin_definitions() -> tuple[HelperDefinition, ...]:
    common = {
        "interface_id": HELPER_INTERFACE_ID,
        "target_contracts": _TARGETS,
        "dependencies": (),
        "earliest_eligible_phase": "separate numeric-semantics mini-phase no earlier than Phase 14",
        "ownership": _OWNERSHIP,
        "failure": _FAILURE,
        "cancellation_policy": "bounded factory and resolver work checks the conversion cancellation token",
    }
    return (
        HelperDefinition(
            reference=FLOOR_DIV_REFERENCE,
            prospective_consumer="future bounded-int Python floor-division RulePlan",
            summary="Correct C truncating signed division to Python floor-division semantics.",
            semantic_obligations=(
                "bounded-int64-representation-proved",
                "divisor-nonzero-proved",
                "int64-minimum-divided-by-negative-one-excluded",
                "python-floor-rounding-preserved",
            ),
            factory=floor_div_asset,
            **common,
        ),
        HelperDefinition(
            reference=FLOOR_MOD_REFERENCE,
            prospective_consumer="future bounded-int Python modulo RulePlan",
            summary="Correct C signed remainder to Python divisor-sign modulo semantics.",
            semantic_obligations=(
                "bounded-int64-representation-proved",
                "divisor-nonzero-proved",
                "int64-minimum-divided-by-negative-one-excluded",
                "python-modulo-sign-preserved",
            ),
            factory=floor_mod_asset,
            **common,
        ),
    )
