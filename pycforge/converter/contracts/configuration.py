"""Versioned public configuration identities for the promoted converter.

The constants in this module are deliberately data-only so the public request,
CLI, workspace, analysis, and lowering layers cannot drift to different phase
identities.
"""

from __future__ import annotations

DEFAULT_TARGET_CONTRACT = "c11-portable-fixed-v1"
DEFAULT_SEMANTIC_POLICY = "strict-source-v1"
PHASE9_RULE_SET = "phase9-functions-calls-v0.9"
PHASE11_RULE_SET = "phase11-bounded-containers-v0.11"
PHASE12_RULE_SET = "phase12-explicit-module-bundles-v0.12"
PHASE12_RENDERER = "c-renderer-v0.12"
PHASE12_MODULE_POLICY = "phase12-explicit-sourcebundle-modules-v0.12"
PHASE13_RULE_SET = "phase13-static-records-v0.13"
PHASE13_RENDERER = "c-renderer-v0.13"
# Phase 14A remains an explicit historical request profile after 14B becomes
# active.  Keep these identities named rather than deriving them from the
# defaults so a historical request cannot be silently relabeled.
PHASE14A_RULE_SET = "phase14-bounded-numeric-v0.14"
PHASE14A_RENDERER = "c-renderer-v0.14"
PHASE14_RULE_SET = PHASE14A_RULE_SET
PHASE14_RENDERER = PHASE14A_RENDERER
PHASE14B_RULE_SET = "phase14-conditional-regions-v0.14.1"
PHASE14B_RENDERER = "c-renderer-v0.14.1"
PHASE14C_RULE_SET = "phase14-direct-keyword-calls-v0.14.2"
PHASE14C_RENDERER = "c-renderer-v0.14.2"
DEFAULT_RULE_SET = "phase14-required-keyword-only-calls-v0.14.3"
DEFAULT_RENDERER = "c-renderer-v0.14.3"
DEFAULT_HELPER_POLICY = "phase10-support-templates-v0.10"
DEFAULT_CONTAINER_POLICY = "phase11-fixed-local-containers-v0.11"
# Module, record, and numeric policies are deliberately unchanged in Phase 14B.
DEFAULT_MODULE_POLICY = "phase13-explicit-record-modules-v0.13"
DEFAULT_RECORD_POLICY = "phase13-immutable-automatic-records-v0.13"
PHASE14A_NUMERIC_POLICY = "phase14-proved-floor-arithmetic-v0.14"
DEFAULT_NUMERIC_POLICY = PHASE14A_NUMERIC_POLICY
MAX_CONTAINER_ELEMENTS = 64
MAX_SOURCE_DOCUMENTS = 64
MAX_IMPORT_ITEMS = 4_096

SUPPORTED_TARGET_CONTRACTS = frozenset(
    {
        DEFAULT_TARGET_CONTRACT,
        # Read-compatible identity used by the earliest public request object.
        "pycforge-c11-int64-v0.1",
    }
)
SUPPORTED_SEMANTIC_POLICIES = frozenset(
    {
        DEFAULT_SEMANTIC_POLICY,
        # Read-compatible identity used by the earliest public request object.
        "strict-v0.1",
    }
)
SUPPORTED_RULE_SETS = frozenset(
    {
        "phase3-frontend-v0.3",
        "phase5-planning-v0.5",
        "phase6-first-slice-v0.6",
        "phase8-control-flow-v0.8",
        PHASE9_RULE_SET,
        PHASE11_RULE_SET,
        PHASE12_RULE_SET,
        PHASE13_RULE_SET,
        PHASE14A_RULE_SET,
        PHASE14B_RULE_SET,
        PHASE14C_RULE_SET,
        DEFAULT_RULE_SET,
    }
)
SUPPORTED_RENDERERS = frozenset(
    {
        "phase3-none-v0.3",
        "c-renderer-v0.6",
        "c-renderer-v0.8",
        "c-renderer-v0.9",
        "c-renderer-v0.11",
        PHASE12_RENDERER,
        PHASE13_RENDERER,
        PHASE14A_RENDERER,
        PHASE14B_RENDERER,
        PHASE14C_RENDERER,
        DEFAULT_RENDERER,
    }
)

# Rule-set and renderer identities are a paired compatibility profile.  Phase 5
# is planning-only and therefore keeps the current request default renderer;
# every rendering phase requires its exact historical renderer.
COMPATIBLE_RENDERERS_BY_RULE_SET = {
    "phase3-frontend-v0.3": frozenset({"phase3-none-v0.3"}),
    "phase5-planning-v0.5": frozenset({DEFAULT_RENDERER}),
    "phase6-first-slice-v0.6": frozenset({"c-renderer-v0.6"}),
    "phase8-control-flow-v0.8": frozenset({"c-renderer-v0.8"}),
    PHASE9_RULE_SET: frozenset({"c-renderer-v0.9"}),
    PHASE11_RULE_SET: frozenset({"c-renderer-v0.11"}),
    PHASE12_RULE_SET: frozenset({PHASE12_RENDERER}),
    PHASE13_RULE_SET: frozenset({PHASE13_RENDERER}),
    PHASE14A_RULE_SET: frozenset({PHASE14A_RENDERER}),
    PHASE14B_RULE_SET: frozenset({PHASE14B_RENDERER}),
    PHASE14C_RULE_SET: frozenset({PHASE14C_RENDERER}),
    DEFAULT_RULE_SET: frozenset({DEFAULT_RENDERER}),
}

SUPPORTED_HELPER_POLICIES = frozenset({DEFAULT_HELPER_POLICY})
SUPPORTED_CONTAINER_POLICIES = frozenset({DEFAULT_CONTAINER_POLICY})
SUPPORTED_MODULE_POLICIES = frozenset({PHASE12_MODULE_POLICY, DEFAULT_MODULE_POLICY})
SUPPORTED_RECORD_POLICIES = frozenset({DEFAULT_RECORD_POLICY})
SUPPORTED_NUMERIC_POLICIES = frozenset({DEFAULT_NUMERIC_POLICY})


def supports_functions(rule_set: str) -> bool:
    return rule_set in {
        PHASE9_RULE_SET,
        PHASE11_RULE_SET,
        PHASE12_RULE_SET,
        PHASE13_RULE_SET,
        PHASE14A_RULE_SET,
        PHASE14B_RULE_SET,
        PHASE14C_RULE_SET,
        DEFAULT_RULE_SET,
    }


def supports_containers(rule_set: str) -> bool:
    return rule_set in {
        PHASE11_RULE_SET,
        PHASE12_RULE_SET,
        PHASE13_RULE_SET,
        PHASE14A_RULE_SET,
        PHASE14B_RULE_SET,
        PHASE14C_RULE_SET,
        DEFAULT_RULE_SET,
    }


def supports_modules(rule_set: str) -> bool:
    return rule_set in {
        PHASE12_RULE_SET,
        PHASE13_RULE_SET,
        PHASE14A_RULE_SET,
        PHASE14B_RULE_SET,
        PHASE14C_RULE_SET,
        DEFAULT_RULE_SET,
    }


def supports_records(rule_set: str) -> bool:
    return rule_set in {
        PHASE13_RULE_SET,
        PHASE14A_RULE_SET,
        PHASE14B_RULE_SET,
        PHASE14C_RULE_SET,
        DEFAULT_RULE_SET,
    }


def supports_numeric(rule_set: str) -> bool:
    return rule_set in {
        PHASE14A_RULE_SET,
        PHASE14B_RULE_SET,
        PHASE14C_RULE_SET,
        DEFAULT_RULE_SET,
    }


def supports_conditional_regions(rule_set: str) -> bool:
    return rule_set in {PHASE14B_RULE_SET, PHASE14C_RULE_SET, DEFAULT_RULE_SET}


def supports_keyword_calls(rule_set: str) -> bool:
    return rule_set in {PHASE14C_RULE_SET, DEFAULT_RULE_SET}


def supports_keyword_only_calls(rule_set: str) -> bool:
    return rule_set == DEFAULT_RULE_SET
