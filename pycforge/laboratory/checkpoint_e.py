"""Independent Checkpoint E source-only audits.

The fuzz audit drives the public converter and inspects emitted text with the
independent C-text conformance parser.  It deliberately does not invoke a C
compiler, linker, loader, debugger, or generated program.
"""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import random
import re
import tomllib
from types import MappingProxyType
from typing import Any

from pycforge import (
    ConversionRequest,
    PythonToCConverter,
    ResultStatus,
    SourceBundle,
    SourceDocumentInput,
)
from pycforge.converter.c_output import validate_c_text
from pycforge.converter.contracts.configuration import (
    DEFAULT_CONTAINER_POLICY,
    DEFAULT_HELPER_POLICY,
    DEFAULT_MODULE_POLICY,
    DEFAULT_NUMERIC_POLICY,
    DEFAULT_RECORD_POLICY,
    DEFAULT_RENDERER,
    DEFAULT_RULE_SET,
    DEFAULT_SEMANTIC_POLICY,
    DEFAULT_TARGET_CONTRACT,
    PHASE9_RULE_SET,
)
from pycforge.converter.contracts.versions import (
    C_IR_SCHEMA,
    CONDITIONAL_FACT_SCHEMA,
    CONTAINER_FACT_SCHEMA,
    CONVERSION_PLAN_SCHEMA,
    CONVERSION_SUMMARY_SCHEMA,
    CONVERTER_CONTRACT_VERSION,
    DECISION_TRACE_SCHEMA,
    GENERATED_C_SCHEMA,
    KEYWORD_CALL_FACT_SCHEMA,
    KEYWORD_ONLY_CALL_FACT_SCHEMA,
    MODULE_FACT_SCHEMA,
    NUMERIC_FACT_SCHEMA,
    PYTHON_IR_BUNDLE_SCHEMA,
    RECORD_FACT_SCHEMA,
    RESULT_SCHEMA_VERSION,
    SOURCE_BUNDLE_SCHEMA,
)
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.core.serialization import result_to_json
from pycforge.converter.keyword_calls import KEYWORD_CALL_RULE_ID
from pycforge.converter.keyword_only_calls import KEYWORD_ONLY_CALL_RULE_ID


FUZZ_SEED = 0x14E2026
DEFAULT_FUZZ_CASE_COUNT = 64
FEATURE_MATRIX_SCHEMA = "pycforge.feature-matrix/0.14.3"
FEATURE_MATRIX_ENTRY_COUNT = 69
FEATURE_MATRIX_SHA256 = (
    "ca78dff3ea203130781f5e0fde879c0ca9d7b7a0e550a05ab5d46ea3432cc01a"
)

EXPECTED_CONTRACT_IDENTITIES: dict[str, str] = {
    "converter_contract": "0.14.3",
    "source_bundle": "source-bundle/0.2",
    "python_ir_bundle": "python-ir/0.4",
    "container_facts": "fact-table/0.11",
    "module_facts": "fact-table/0.12",
    "record_facts": "fact-table/0.13",
    "numeric_facts": "fact-table/0.14",
    "conditional_facts": "fact-table/0.14.1",
    "keyword_call_facts": "fact-table/0.14.2",
    "keyword_only_call_facts": "fact-table/0.14.3",
    "conversion_plan": "conversion-plan/0.14.3",
    "c_ir": "c-ir/0.14.3",
    "generated_c": "generated-c/0.14.3",
    "conversion_summary": "pycforge.conversion-summary/0.14.3",
    "decision_trace": "pycforge.decision-trace/0.14.3",
    "result": "0.5",
    "rule_set": "phase14-required-keyword-only-calls-v0.14.3",
    "renderer": "c-renderer-v0.14.3",
    "keyword_call_rule": "phase14.keyword_call.exact_binding",
    "keyword_only_call_rule": "phase14.keyword_only_call.exact_binding",
    "target_contract": "c11-portable-fixed-v1",
    "semantic_policy": "strict-source-v1",
    "helper_policy": "phase10-support-templates-v0.10",
    "container_policy": "phase11-fixed-local-containers-v0.11",
    "module_policy": "phase13-explicit-record-modules-v0.13",
    "record_policy": "phase13-immutable-automatic-records-v0.13",
    "numeric_policy": "phase14-proved-floor-arithmetic-v0.14",
}

SUPPORTED_SUBSET_FAMILIES = frozenset(
    {
        "literals",
        "assignments-and-arithmetic",
        "functions-and-positional-calls",
        "if-else",
        "while-break-continue",
        "bounded-range-for",
        "list",
        "tuple",
        "dict",
        "explicit-module-bundle",
        "static-record",
        "bounded-floor-arithmetic",
        "boolean-conditional-region",
        "comparison-conditional-region",
        "direct-keyword-call",
        "required-keyword-only-call",
    }
)


@dataclass(frozen=True, slots=True)
class SupportedSubsetCase:
    """One deterministic public-converter witness."""

    case_id: str
    family: str
    primary_text: str
    primary_name: str = "main.py"
    primary_module: str = "main"
    companions: tuple[tuple[str, str, str], ...] = ()

    def request(self) -> ConversionRequest:
        return ConversionRequest(
            SourceBundle(
                SourceDocumentInput(
                    self.primary_name,
                    self.primary_text,
                    self.primary_module,
                ),
                tuple(
                    SourceDocumentInput(logical_name, text, module_id)
                    for module_id, logical_name, text in self.companions
                ),
            )
        )

    def manifest(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "family": self.family,
            "primary": {
                "logical_name": self.primary_name,
                "module_id": self.primary_module,
                "text": self.primary_text,
            },
            "companions": [
                {
                    "module_id": module_id,
                    "logical_name": logical_name,
                    "text": text,
                }
                for module_id, logical_name, text in self.companions
            ],
        }


@dataclass(frozen=True, slots=True)
class FeatureMatrixExecutionProfile:
    """One explicit public-request profile for a matrix witness."""

    profile_id: str
    request_options: tuple[tuple[str, object], ...] = ()
    expected_diagnostic: str | None = None
    reason_contains: str | None = None

    def options(self) -> dict[str, object]:
        return dict(self.request_options)


@dataclass(frozen=True, slots=True)
class FeatureMatrixWitness:
    """Executable evidence for one exact frozen feature-matrix row."""

    witness_id: str
    construct: str
    context: str
    state: str
    source: str
    exercise: str
    diagnostic: str | None = None
    actual_diagnostic: str | None = None
    actual_reason_contains: str | None = None
    required_ast_kinds: tuple[str, ...] = ()
    logical_name: str = "main.py"
    module_id: str = "main"
    companions: tuple[tuple[str, str, str], ...] = ()
    request_options: tuple[tuple[str, object], ...] = ()
    precedence_profiles: tuple[FeatureMatrixExecutionProfile, ...] = ()

    @property
    def key(self) -> tuple[str, str]:
        return self.construct, self.context

    @property
    def expected_diagnostic(self) -> str | None:
        return self.actual_diagnostic or self.diagnostic

    def request(
        self,
        options: Mapping[str, object] | None = None,
    ) -> ConversionRequest:
        request_options = (
            dict(self.request_options) if options is None else dict(options)
        )
        return ConversionRequest(
            SourceBundle(
                SourceDocumentInput(
                    self.logical_name,
                    self.source,
                    self.module_id,
                ),
                tuple(
                    SourceDocumentInput(logical_name, text, module_id)
                    for module_id, logical_name, text in self.companions
                ),
            ),
            **request_options,
        )

    def manifest(self) -> dict[str, object]:
        return {
            "witness_id": self.witness_id,
            "construct": self.construct,
            "context": self.context,
            "state": self.state,
            "diagnostic": self.diagnostic,
            "actual_diagnostic": self.expected_diagnostic,
            "actual_reason_contains": self.actual_reason_contains,
            "exercise": self.exercise,
            "required_ast_kinds": list(self.required_ast_kinds),
            "request_options": [
                [key, value] for key, value in self.request_options
            ],
            "primary": {
                "logical_name": self.logical_name,
                "module_id": self.module_id,
                "source_sha256": hashlib.sha256(
                    self.source.encode("utf-8")
                ).hexdigest(),
            },
            "companions": [
                {
                    "module_id": module_id,
                    "logical_name": logical_name,
                    "source_sha256": hashlib.sha256(
                        text.encode("utf-8")
                    ).hexdigest(),
                }
                for module_id, logical_name, text in self.companions
            ],
            "precedence_profiles": [
                {
                    "profile_id": profile.profile_id,
                    "request_options": [
                        [key, value] for key, value in profile.request_options
                    ],
                    "expected_diagnostic": profile.expected_diagnostic,
                    "reason_contains": profile.reason_contains,
                }
                for profile in self.precedence_profiles
            ],
        }


_SIMPLE_FUNCTION = (
    "def identity(value: int, /) -> int:\n"
    "    result = value\n"
    "    return result\n"
)
_POSITIONAL_CALL = (
    "def add(left: int, right: int) -> int:\n"
    "    return left + right\n\n"
    "def run(value: int) -> int:\n"
    "    return add(value, 3)\n"
)
_RANGE_LOOP = (
    "def total() -> int:\n"
    "    value = 0\n"
    "    for item in range(1, 6, 2):\n"
    "        value = value + item\n"
    "    return value\n"
)
_KEYWORD_CALL = (
    "def choose(left: int, middle: int, flag: bool) -> int:\n"
    "    if flag:\n"
    "        return left\n"
    "    return middle\n\n"
    "def run(value: int, flag: bool) -> int:\n"
    "    return choose(value, flag=flag, middle=2)\n"
)
_KEYWORD_ONLY_CALL = (
    "def choose(left: int, /, middle: int, *, scale: int) -> int:\n"
    "    return (left + middle) * scale\n\n"
    "def run() -> int:\n"
    "    return choose(1, middle=2, scale=3)\n"
)
_LITERALS = (
    "def integer_value() -> int:\n"
    "    return 7\n\n"
    "def real_value() -> float:\n"
    "    return 1.5\n\n"
    "def flag_value() -> bool:\n"
    "    return True\n\n"
    "def text_value() -> str:\n"
    '    return "PyCForge"\n'
)
_FLOATING_ARITHMETIC = (
    "def arithmetic(left: float, right: float) -> float:\n"
    "    value = left + right\n"
    "    value = value - 1.0\n"
    "    value = value * 2.0\n"
    "    return value / 3.0\n"
)
_FLOOR_DIV = (
    "def floor_value(value: int) -> int:\n"
    "    return value // -3\n"
)
_FLOOR_MOD = (
    "def mod_value(value: int) -> int:\n"
    "    return value % 5\n"
)
_BOOL_DIRECT = (
    "def both(left: bool, right: bool) -> bool:\n"
    "    return left and right\n"
)
_BOOL_GUARDED = (
    "def flag(value: bool) -> bool:\n"
    "    return value\n\n"
    "def decide(left: bool, right: bool) -> bool:\n"
    "    return left and flag(right)\n"
)
_COMPARE_DIRECT = (
    "def compare(left: int, right: int) -> bool:\n"
    "    return left <= right\n"
)
_COMPARE_GUARDED = (
    "def identity(value: int) -> int:\n"
    "    return value\n\n"
    "def compare(left: int, middle: int, right: int) -> bool:\n"
    "    return left < middle < identity(right)\n"
)
_IF_STATEMENT = (
    "def choose(value: int, flag: bool) -> int:\n"
    "    if flag:\n"
    "        value = value + 1\n"
    "    else:\n"
    "        value = value - 1\n"
    "    return value\n"
)
_WHILE_STATEMENT = (
    "def scan(limit: int) -> int:\n"
    "    value = 0\n"
    "    while value < limit:\n"
    "        value = value + 1\n"
    "        if value == 2:\n"
    "            continue\n"
    "        if value == 5:\n"
    "            break\n"
    "    return value\n"
)
_LIST_VALUE = (
    "def pick() -> int:\n"
    "    values = [1, 2, 3]\n"
    "    return values[-1]\n"
)
_TUPLE_VALUE = (
    "def pick() -> str:\n"
    '    values = ("a", "b")\n'
    "    return values[0]\n"
)
_DICT_VALUE = (
    "def pick() -> int:\n"
    '    values = {"a": 1, "b": 2}\n'
    '    return values["b"]\n'
)
_CONTAINER_ITERATION = (
    "def last() -> int:\n"
    "    values = [2, 4, 6]\n"
    "    result = 0\n"
    "    for item in values:\n"
    "        result = item\n"
    "    return result\n"
)
_MODULE_PRIMARY = (
    "from lib import increment as step\n\n"
    "class Point:\n"
    "    x: int\n"
    "    def __init__(self, x: int) -> None:\n"
    "        self.x = x\n\n"
    "def run(value: int) -> int:\n"
    "    point = Point(step(value))\n"
    "    return point.x\n"
)
_MODULE_COMPANIONS = (
    (
        "lib",
        "lib.py",
        "def increment(value: int) -> int:\n"
        "    return value + 1\n",
    ),
)
_RECORD = (
    "class Sample:\n"
    "    count: int\n"
    "    ratio: float\n"
    "    enabled: bool\n"
    "    def __init__(self, count: int, ratio: float, enabled: bool) -> None:\n"
    "        self.count = count\n"
    "        self.ratio = ratio\n"
    "        self.enabled = enabled\n\n"
    "def read() -> int:\n"
    "    sample = Sample(7, 1.5, True)\n"
    "    return sample.count\n"
)
_POINT_RECORD = (
    "class Point:\n"
    "    x: int\n"
    "    def __init__(self, x: int) -> None:\n"
    "        self.x = x\n"
)


def _feature_matrix_witness_rows() -> tuple[FeatureMatrixWitness, ...]:
    """Return the ordered executable closure of the frozen 69-row matrix."""

    def witness(
        ordinal: int,
        construct: str,
        context: str,
        state: str,
        source: str,
        exercise: str,
        *,
        diagnostic: str | None = None,
        actual_diagnostic: str | None = None,
        actual_reason_contains: str | None = None,
        ast_kinds: tuple[str, ...] = (),
        logical_name: str = "main.py",
        module_id: str = "main",
        companions: tuple[tuple[str, str, str], ...] = (),
        request_options: tuple[tuple[str, object], ...] = (),
        precedence_profiles: tuple[FeatureMatrixExecutionProfile, ...] = (),
    ) -> FeatureMatrixWitness:
        return FeatureMatrixWitness(
            f"feature-matrix-{ordinal:02d}",
            construct,
            context,
            state,
            source,
            exercise,
            diagnostic,
            actual_diagnostic,
            actual_reason_contains,
            ast_kinds,
            logical_name,
            module_id,
            companions,
            request_options,
            precedence_profiles,
        )

    return (
        witness(
            0,
            "Module",
            "explicit-1-to-64-document-bundle/import-preamble-then-records-then-top-level-functions",
            "supported",
            _MODULE_PRIMARY,
            "A two-document explicit bundle places an absolute import first, a static record second, and an annotated top-level function last.",
            ast_kinds=("Module", "ImportFrom", "ClassDef", "FunctionDef"),
            logical_name="app.py",
            module_id="app",
            companions=_MODULE_COMPANIONS,
        ),
        witness(
            1,
            "FunctionDef",
            "top-level/exact-annotated-signature",
            "supported",
            _SIMPLE_FUNCTION,
            "The module contains one top-level function whose parameter and return are exactly annotated.",
            ast_kinds=("FunctionDef",),
        ),
        witness(
            2,
            "FunctionDef",
            "nested-or-closure",
            "unsupported",
            (
                "def outer(value: int) -> int:\n"
                "    def nested(other: int) -> int:\n"
                "        return value + other\n"
                "    return nested(value)\n"
            ),
            "The inner FunctionDef closes over the outer parameter.",
            diagnostic="PYC2915",
            ast_kinds=("FunctionDef",),
        ),
        witness(
            3,
            "arguments",
            "positional-or-positional-only/no-default",
            "supported",
            _SIMPLE_FUNCTION,
            "The identity signature has one positional-only parameter and no default.",
            ast_kinds=("arguments", "arg"),
        ),
        witness(
            4,
            "arguments",
            "required-keyword-only/exact-annotations/no-defaults-or-variadics",
            "supported",
            _KEYWORD_ONLY_CALL,
            "The choose signature includes an exactly annotated required keyword-only scale parameter with no default or variadic.",
            ast_kinds=("arguments", "arg"),
        ),
        witness(
            5,
            "arguments",
            "positional-default-keyword-only-default-variadic-or-keyword-only-outside-required-profile",
            "unsupported",
            (
                "def choose(value: int, *, flag: bool = True) -> int:\n"
                "    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return choose(value, flag=flag)\n"
            ),
            "The keyword-only flag formal has a default, placing the signature outside the required-only profile.",
            diagnostic="PYC2911",
            ast_kinds=("arguments",),
        ),
        witness(
            6,
            "Call",
            "direct-understood-source-function/exact-positional-signature",
            "supported",
            _POSITIONAL_CALL,
            "run directly calls the understood add definition with two exact positional arguments.",
            ast_kinds=("Call",),
        ),
        witness(
            7,
            "Call",
            "unshadowed-range-for-iterator",
            "supported",
            _RANGE_LOOP,
            "The For iterator is a direct call to the unshadowed built-in range.",
            ast_kinds=("Call", "For"),
        ),
        witness(
            8,
            "Call",
            "unknown-indirect-aliased-dynamic",
            "unsupported",
            (
                "def run(target: int, value: int) -> int:\n"
                "    return target(value)\n"
            ),
            "The call target is a parameter value rather than a direct understood source function.",
            diagnostic="PYC2901",
            ast_kinds=("Call",),
        ),
        witness(
            9,
            "Call",
            "direct-understood-source-function/leading-positional-then-explicit-keywords/exact-required-parameter-coverage",
            "supported",
            _KEYWORD_CALL,
            "run binds choose with one leading positional argument followed by explicit keywords that cover every remaining required parameter.",
            ast_kinds=("Call", "keyword"),
        ),
        witness(
            10,
            "Call",
            "direct-understood-source-function/required-keyword-only-formals/exact-positional-and-named-coverage",
            "supported",
            _KEYWORD_ONLY_CALL,
            "run calls choose with its positional-only, positional-or-keyword, and required keyword-only formals covered exactly.",
            ast_kinds=("Call", "keyword"),
        ),
        witness(
            11,
            "Call",
            "missing-required-keyword-only-or-positional-overflow-into-keyword-only-range",
            "unsupported",
            (
                "def sink(value: int, *, flag: bool) -> int:\n"
                "    return value\n\n"
                "def run(value: int) -> int:\n"
                "    return sink(value)\n"
            ),
            "The direct sink call omits its required keyword-only flag.",
            diagnostic="PYC2904",
            ast_kinds=("Call",),
        ),
        witness(
            12,
            "Call",
            "starred-or-unpacked-keywords",
            "unsupported",
            (
                "def sink(value: int, *, flag: bool) -> int:\n"
                "    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(*value, flag=flag)\n"
            ),
            "The sink call contains a starred positional argument.",
            diagnostic="PYC2910",
            ast_kinds=("Call", "Starred"),
        ),
        witness(
            13,
            "Call",
            "unknown-duplicate-colliding-or-positional-only-keyword-name",
            "unsupported",
            (
                "def sink(value: int, /, *, flag: bool) -> int:\n"
                "    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value=value, flag=flag)\n"
            ),
            "The call illegally names the positional-only value formal as a keyword.",
            diagnostic="PYC2912",
            ast_kinds=("Call", "keyword"),
        ),
        witness(
            14,
            "Return",
            "explicit-compatible-all-paths",
            "supported",
            _IF_STATEMENT,
            "choose has an explicit compatible return after its exhaustive conditional assignment.",
            ast_kinds=("Return",),
        ),
        witness(
            15,
            "Return",
            "mismatch",
            "unsupported",
            "def run() -> int:\n    return True\n",
            "The explicit Boolean return conflicts with the annotated integer representation.",
            diagnostic="PYC2930",
            ast_kinds=("Return",),
        ),
        witness(
            16,
            "FunctionFallthrough",
            "annotated-non-none",
            "unsupported",
            (
                "def run(flag: bool) -> int:\n"
                "    if flag:\n"
                "        return 1\n"
            ),
            "The annotated non-None function has a reachable implicit-None fallthrough path.",
            diagnostic="PYC2931",
            ast_kinds=("FunctionDef", "If"),
        ),
        witness(
            17,
            "Assign",
            "single-local-name/stable-representation",
            "supported",
            _SIMPLE_FUNCTION,
            "result is bound once as a direct function-local integer-like name.",
            ast_kinds=("Assign", "Name"),
        ),
        witness(
            18,
            "Assign",
            "representation-conflict",
            "unsupported",
            (
                "def run() -> int:\n"
                "    value = 1\n"
                "    value = True\n"
                "    return 0\n"
            ),
            "The same local is assigned integer-like and Boolean-like representations.",
            diagnostic="PYC2943",
            ast_kinds=("Assign",),
        ),
        witness(
            19,
            "Name",
            "resolved-parameter-local-or-function",
            "supported",
            _POSITIONAL_CALL,
            "The witness resolves parameter names, the local function binding add, and their return use.",
            ast_kinds=("Name",),
        ),
        witness(
            20,
            "Name",
            "local-use-before-binding",
            "unsupported",
            (
                "def run(value: int) -> int:\n"
                "    result = result + value\n"
                "    return result\n"
            ),
            "result is read on the right-hand side before its first local binding.",
            diagnostic="PYC2940",
            ast_kinds=("Name",),
        ),
        witness(
            21,
            "Constant",
            "bounded-int-finite-float-bool-utf8-string",
            "supported",
            _LITERALS,
            "Four functions exercise bounded int, finite float, bool, and UTF-8 string constants.",
            ast_kinds=("Constant",),
        ),
        witness(
            22,
            "BinOp",
            "selected-stable-numeric-plus-minus-multiply-and-floating-divide",
            "supported",
            _FLOATING_ARITHMETIC,
            "The floating-like function exercises plus, minus, multiply, and true division with stable representations.",
            ast_kinds=("BinOp", "Div", "Add", "Sub", "Mult"),
        ),
        witness(
            23,
            "BinOp.FloorDiv",
            "integer-like-left/direct-safe-signed-int64-literal-divisor",
            "supported",
            _FLOOR_DIV,
            "The integer-like left operand uses a direct safe signed int64 literal divisor of -3.",
            ast_kinds=("BinOp", "FloorDiv"),
        ),
        witness(
            24,
            "BinOp.Mod",
            "integer-like-left/direct-safe-signed-int64-literal-divisor",
            "supported",
            _FLOOR_MOD,
            "The integer-like left operand uses a direct safe signed int64 literal divisor of 5.",
            ast_kinds=("BinOp", "Mod"),
        ),
        witness(
            25,
            "BinOp.FloorDivOrMod",
            "noninteger-or-unsupported-expression-context",
            "unsupported",
            "def run(value: float) -> float:\n    return value // 2\n",
            "Floor division is applied to a floating-like left operand.",
            diagnostic="PYC3701",
            ast_kinds=("BinOp", "FloorDiv"),
        ),
        witness(
            26,
            "BinOp.FloorDivOrMod",
            "zero-negative-one-INT64_MIN-dynamic-calculated-or-out-of-range-divisor",
            "unsupported",
            (
                "def run(value: int, divisor: int) -> int:\n"
                "    return value // divisor\n"
            ),
            "The divisor is dynamic rather than a directly proved safe signed int64 literal.",
            diagnostic="PYC3702",
            ast_kinds=("BinOp", "FloorDiv"),
        ),
        witness(
            27,
            "BoolOp",
            "boolean-represented/direct-expression-form",
            "supported",
            _BOOL_DIRECT,
            "A direct and-expression combines two already Boolean-represented parameters.",
            ast_kinds=("BoolOp", "And"),
        ),
        witness(
            28,
            "BoolOp",
            "boolean-represented/already-supported-scalar-prerequisites/flat-guarded-placement",
            "supported",
            _BOOL_GUARDED,
            "The later Boolean operand is an understood scalar function call placed in one flat guarded region.",
            ast_kinds=("BoolOp", "Call"),
        ),
        witness(
            29,
            "Compare",
            "numeric-or-boolean/direct-sequence-preservable",
            "supported",
            _COMPARE_DIRECT,
            "A direct numeric comparison has a trivially preservable operand sequence.",
            ast_kinds=("Compare",),
        ),
        witness(
            30,
            "Compare",
            "chained-numeric-or-boolean/already-supported-later-scalar-prerequisites/flat-guarded-placement",
            "supported",
            _COMPARE_GUARDED,
            "The chained numeric comparison places an understood later scalar call in a flat guarded region.",
            ast_kinds=("Compare", "Call"),
        ),
        witness(
            31,
            "If",
            "supported-truthiness",
            "supported",
            _IF_STATEMENT,
            "The If condition is an exactly Boolean-represented parameter.",
            ast_kinds=("If",),
        ),
        witness(
            32,
            "While",
            "supported-truthiness/no-else",
            "supported",
            _WHILE_STATEMENT,
            "The While condition is a supported numeric comparison and the loop has no else.",
            ast_kinds=("While",),
        ),
        witness(
            33,
            "For",
            "unshadowed-builtin-range/bounded-policy",
            "supported",
            _RANGE_LOOP,
            "The For loop iterates an unshadowed range with direct bounded start, stop, and step.",
            ast_kinds=("For", "Call"),
        ),
        witness(
            34,
            "Break",
            "supported-loop",
            "supported",
            _WHILE_STATEMENT,
            "Break occurs lexically inside the supported no-else While loop.",
            ast_kinds=("Break", "While"),
        ),
        witness(
            35,
            "Continue",
            "supported-loop",
            "supported",
            _WHILE_STATEMENT,
            "Continue occurs lexically inside the supported no-else While loop.",
            ast_kinds=("Continue", "While"),
        ),
        witness(
            36,
            "List",
            "nonempty-1-to-64/homogeneous-scalar/direct-local-single-binding",
            "supported",
            _LIST_VALUE,
            "A nonempty three-element homogeneous integer list has one direct local binding.",
            ast_kinds=("List", "Assign"),
        ),
        witness(
            37,
            "Tuple",
            "nonempty-1-to-64/homogeneous-scalar/direct-local-single-binding",
            "supported",
            _TUPLE_VALUE,
            "A nonempty two-element homogeneous string tuple has one direct local binding.",
            ast_kinds=("Tuple", "Assign"),
        ),
        witness(
            38,
            "Dict",
            "nonempty-1-to-64/distinct-homogeneous-literal-int-or-str-keys/homogeneous-scalar-values",
            "supported",
            _DICT_VALUE,
            "A nonempty dictionary has distinct homogeneous literal string keys and homogeneous integer values.",
            ast_kinds=("Dict", "Assign"),
        ),
        witness(
            39,
            "Subscript",
            "fixed-list-or-tuple/signed-literal-in-bounds",
            "supported",
            _LIST_VALUE,
            "The fixed list is indexed by the signed literal -1, proved in bounds.",
            ast_kinds=("Subscript", "List"),
        ),
        witness(
            40,
            "Subscript",
            "fixed-dict/present-literal-key",
            "supported",
            _DICT_VALUE,
            "The fixed dictionary is indexed by its present literal key 'b'.",
            ast_kinds=("Subscript", "Dict"),
        ),
        witness(
            41,
            "For",
            "direct-fixed-container-name/single-target/no-else",
            "supported",
            _CONTAINER_ITERATION,
            "The loop directly names a fixed list, has one target, and has no else.",
            ast_kinds=("For", "List"),
        ),
        witness(
            42,
            "ContainerMutation",
            "any",
            "unsupported",
            (
                "def run() -> int:\n"
                "    values = [1, 2]\n"
                "    values[0] = 3\n"
                "    return values[0]\n"
            ),
            "A subscript assignment mutates a fixed list after binding.",
            diagnostic="PYC3406",
            ast_kinds=("Assign", "Subscript", "List"),
        ),
        witness(
            43,
            "ContainerAliasOrEscape",
            "any",
            "unsupported",
            (
                "def run() -> int:\n"
                "    values = [1, 2]\n"
                "    alias = values\n"
                "    return alias[0]\n"
            ),
            "The fixed list escapes its single-binding proof through a second local alias.",
            diagnostic="PYC3403",
            ast_kinds=("Assign", "List", "Name"),
        ),
        witness(
            44,
            "Comprehension",
            "any",
            "unsupported",
            (
                "def run() -> int:\n"
                "    values = [item for item in range(3)]\n"
                "    return 1\n"
            ),
            "A ListComp attempts to construct a container dynamically.",
            diagnostic="PYC3406",
            ast_kinds=("ListComp", "comprehension"),
        ),
        witness(
            45,
            "ImportFrom",
            "absolute-exact-sourcebundle-module/direct-eligible-functions/optional-aliases/preamble",
            "supported",
            (
                "from lib import increment as step\n\n"
                "def run(value: int) -> int:\n"
                "    return step(value)\n"
            ),
            "An absolute preamble import resolves an optionally aliased eligible function from the explicit companion.",
            ast_kinds=("ImportFrom", "alias"),
            logical_name="app.py",
            module_id="app",
            companions=_MODULE_COMPANIONS,
        ),
        witness(
            46,
            "Import",
            "plain-module-import",
            "unsupported",
            "import lib\n\ndef run() -> int:\n    return 1\n",
            "A plain Import statement names an otherwise explicit companion module.",
            diagnostic="PYC3504",
            ast_kinds=("Import",),
            logical_name="app.py",
            module_id="app",
            companions=_MODULE_COMPANIONS,
        ),
        witness(
            47,
            "ImportFrom",
            "relative-star-late-local-conditional-or-dynamic",
            "unsupported",
            (
                "if True:\n"
                "    from lib import increment\n\n"
                "def run() -> int:\n"
                "    return 1\n"
            ),
            "The ImportFrom is conditional instead of an unconditional module preamble item.",
            diagnostic="PYC3504",
            ast_kinds=("ImportFrom", "If"),
            logical_name="app.py",
            module_id="app",
            companions=_MODULE_COMPANIONS,
        ),
        witness(
            48,
            "ImportFrom",
            "missing-explicit-module",
            "unsupported",
            (
                "from absent import value\n\n"
                "def run() -> int:\n"
                "    return value()\n"
            ),
            "The absolute import target absent is not present in the explicit source bundle.",
            diagnostic="PYC3503",
            ast_kinds=("ImportFrom",),
            logical_name="app.py",
            module_id="app",
        ),
        witness(
            49,
            "ImportFrom",
            "missing-or-ineligible-direct-member",
            "unsupported",
            (
                "from lib import absent\n\n"
                "def run() -> int:\n"
                "    return 1\n"
            ),
            "The explicit companion exists but does not define the directly imported member absent.",
            diagnostic="PYC3505",
            ast_kinds=("ImportFrom",),
            logical_name="app.py",
            module_id="app",
            companions=_MODULE_COMPANIONS,
        ),
        witness(
            50,
            "ModuleDependency",
            "self-or-strongly-connected-cycle",
            "unsupported",
            (
                "from lib import increment\n\n"
                "def run(value: int) -> int:\n"
                "    return increment(value)\n"
            ),
            "The app-to-lib and lib-to-app imports form a two-module strongly connected dependency cycle.",
            diagnostic="PYC3507",
            ast_kinds=("ImportFrom",),
            logical_name="app.py",
            module_id="app",
            companions=(
                (
                    "lib",
                    "lib.py",
                    (
                        "from app import run\n\n"
                        "def increment(value: int) -> int:\n"
                        "    return run(value)\n"
                    ),
                ),
            ),
        ),
        witness(
            51,
            "ModuleInitialization",
            "compile-time-namespace-only",
            "supported",
            _MODULE_PRIMARY,
            "The module body contains only namespace-defining imports, a record declaration, and function declarations.",
            ast_kinds=("Module", "ImportFrom", "ClassDef", "FunctionDef"),
            logical_name="app.py",
            module_id="app",
            companions=_MODULE_COMPANIONS,
        ),
        witness(
            52,
            "ModuleInitialization",
            "executable-top-level-state",
            "unsupported",
            (
                "value = 1\n\n"
                "def run() -> int:\n"
                "    return value\n"
            ),
            "The top-level assignment creates executable module initialization state.",
            diagnostic="PYC3509",
            ast_kinds=("Assign", "Module"),
        ),
        witness(
            53,
            "ClassDef",
            "top-level-undecorated-base-free-static-record-before-functions",
            "supported",
            _RECORD,
            "Sample is a top-level undecorated base-free static record placed before the read function.",
            ast_kinds=("ClassDef",),
        ),
        witness(
            54,
            "ClassDef",
            "nested-decorated-inherited-keyworded-or-general-class",
            "unsupported",
            (
                "class Point(Base):\n"
                "    x: int\n"
                "    def __init__(self, x: int) -> None:\n"
                "        self.x = x\n\n"
                "def run() -> int:\n"
                "    return 1\n"
            ),
            "Point has an inherited base and therefore is outside the base-free static-record profile.",
            diagnostic="PYC3601",
            ast_kinds=("ClassDef",),
        ),
        witness(
            55,
            "AnnAssign",
            "record-value-less-distinct-int-float-bool-field/1-to-64",
            "supported",
            _RECORD,
            "Sample declares three distinct value-less int, float, and bool record fields within capacity.",
            ast_kinds=("AnnAssign",),
        ),
        witness(
            56,
            "AnnAssign",
            "record-default-unsupported-type-duplicate-or-capacity",
            "unsupported",
            (
                "class Point:\n"
                "    x: str\n"
                "    def __init__(self, x: str) -> None:\n"
                "        self.x = x\n\n"
                "def run() -> int:\n"
                "    return 1\n"
            ),
            "The value-less record field uses unsupported str storage.",
            diagnostic="PYC3602",
            ast_kinds=("AnnAssign",),
        ),
        witness(
            57,
            "FunctionDef",
            "record-exact-structural-__init__",
            "supported",
            _RECORD,
            "Sample.__init__ exactly assigns every declared field from its corresponding annotated parameter.",
            ast_kinds=("FunctionDef", "Attribute"),
        ),
        witness(
            58,
            "FunctionDef",
            "record-nonstructural-__init__",
            "unsupported",
            (
                "class Point:\n"
                "    x: int\n"
                "    def __init__(self, x: int) -> int:\n"
                "        self.x = x\n\n"
                "def run() -> int:\n"
                "    return 1\n"
            ),
            "Point.__init__ declares int rather than the exact structural None return.",
            diagnostic="PYC3603",
            ast_kinds=("FunctionDef",),
        ),
        witness(
            59,
            "FunctionDef",
            "ordinary-record-method",
            "unsupported",
            (
                _POINT_RECORD
                + "    def get(self) -> int:\n"
                "        return self.x\n\n"
                "def run() -> int:\n"
                "    return 1\n"
            ),
            "The record class declares an ordinary get method in addition to structural __init__.",
            diagnostic="PYC3604",
            ast_kinds=("FunctionDef",),
        ),
        witness(
            60,
            "Call",
            "same-module-record-direct-positional-fresh-local-construction",
            "supported",
            _RECORD,
            "read directly constructs same-module Sample positionally into a fresh local.",
            ast_kinds=("Call", "ClassDef"),
        ),
        witness(
            61,
            "Call",
            "record-indirect-keyword-nested-conditional-returned-or-mismatched-construction",
            "unsupported",
            (
                _POINT_RECORD
                + "\ndef run() -> int:\n"
                "    point = Point(x=1)\n"
                "    return point.x\n"
            ),
            "The record constructor is invoked with a keyword rather than the exact direct positional profile.",
            diagnostic="PYC3605",
            ast_kinds=("Call", "keyword"),
        ),
        witness(
            62,
            "RecordValue",
            "alias-rebind-copy-escape-parameter-return-call-container-identity-or-truth",
            "unsupported",
            (
                _POINT_RECORD
                + "\ndef run() -> int:\n"
                "    point = Point(1)\n"
                "    alias = point\n"
                "    return point.x\n"
            ),
            "The fresh record value is copied into alias, violating immutable no-alias ownership.",
            diagnostic="PYC3606",
            ast_kinds=("Assign", "Call"),
        ),
        witness(
            63,
            "Attribute",
            "direct-statically-bound-record-field-read",
            "supported",
            _RECORD,
            "read returns sample.count through a direct statically bound field access.",
            ast_kinds=("Attribute",),
        ),
        witness(
            64,
            "Attribute",
            "record-mutation-unknown-dynamic-or-chained-attribute",
            "unsupported",
            (
                _POINT_RECORD
                + "\ndef run() -> int:\n"
                "    point = Point(1)\n"
                "    point.x = 2\n"
                "    return point.x\n"
            ),
            "An Attribute target mutates the immutable record field point.x.",
            diagnostic="PYC3607",
            ast_kinds=("Attribute", "Assign"),
        ),
        witness(
            65,
            "ImportFrom",
            "record-class-import",
            "unsupported",
            (
                "from records import Point\n\n"
                "def run() -> int:\n"
                "    point = Point(1)\n"
                "    return point.x\n"
            ),
            "The ImportFrom attempts to import a record class across module boundaries.",
            diagnostic="PYC3610",
            ast_kinds=("ImportFrom",),
            logical_name="app.py",
            module_id="app",
            companions=(
                (
                    "records",
                    "records.py",
                    (
                        _POINT_RECORD
                        + "\ndef local() -> int:\n"
                        "    point = Point(2)\n"
                        "    return point.x\n"
                    ),
                ),
            ),
        ),
        witness(
            66,
            "Lambda",
            "call-target-or-value",
            "unsupported",
            (
                "def run(value: int) -> int:\n"
                "    target = lambda item: item\n"
                "    return target(value)\n"
            ),
            "A Lambda is bound as an indirect call target value.",
            diagnostic="PYC2901",
            ast_kinds=("Lambda", "Call"),
        ),
        witness(
            67,
            "AsyncFunctionDef",
            "any",
            "unsupported",
            "async def run() -> int:\n    return 1\n",
            "The Phase 9 profile owns the original AsyncFunctionDef boundary and emits PYC2902; the current module profile rejects it earlier as ineligible module initialization.",
            diagnostic="PYC2902",
            ast_kinds=("AsyncFunctionDef",),
            request_options=(
                ("rule_set_version", PHASE9_RULE_SET),
                ("renderer_version", "c-renderer-v0.9"),
            ),
            precedence_profiles=(
                FeatureMatrixExecutionProfile(
                    "current-default-precedence",
                    (),
                    "PYC3509",
                    "Only eligible synchronous top-level functions",
                ),
            ),
        ),
        witness(
            68,
            "Match",
            "any",
            "deferred",
            (
                "def run(value: int) -> int:\n"
                "    result = 0\n"
                "    match value:\n"
                "        case 1:\n"
                "            result = 1\n"
                "    return result\n"
            ),
            "A Match statement is present while an explicit trailing return prevents fallthrough from masking the deferred boundary.",
            actual_diagnostic="PYC2812",
            actual_reason_contains="Unsupported statement in the selected subset: Match",
            ast_kinds=("Match",),
        ),
    )


FEATURE_MATRIX_WITNESS_ORDER = _feature_matrix_witness_rows()
FEATURE_MATRIX_WITNESSES: Mapping[
    tuple[str, str], FeatureMatrixWitness
] = MappingProxyType({item.key: item for item in FEATURE_MATRIX_WITNESS_ORDER})

UNLISTED_DEFAULT_WITNESS = FeatureMatrixWitness(
    "feature-matrix-unlisted-default",
    "Try",
    "unlisted-node/default-unsupported",
    "unsupported",
    (
        "def run() -> int:\n"
        "    result = 0\n"
        "    try:\n"
        "        result = 1\n"
        "    except Exception:\n"
        "        result = 2\n"
        "    return result\n"
    ),
    "Try is intentionally absent from the 69-entry matrix; an explicit trailing return prevents fallthrough from masking the default unsupported boundary.",
    actual_diagnostic="PYC2812",
    actual_reason_contains="Unsupported statement in the selected subset: Try",
    required_ast_kinds=("Try",),
)


def current_contract_identities() -> dict[str, str]:
    """Return the converter identities that Checkpoint E must not churn."""

    return {
        "converter_contract": CONVERTER_CONTRACT_VERSION,
        "source_bundle": SOURCE_BUNDLE_SCHEMA,
        "python_ir_bundle": PYTHON_IR_BUNDLE_SCHEMA,
        "container_facts": CONTAINER_FACT_SCHEMA,
        "module_facts": MODULE_FACT_SCHEMA,
        "record_facts": RECORD_FACT_SCHEMA,
        "numeric_facts": NUMERIC_FACT_SCHEMA,
        "conditional_facts": CONDITIONAL_FACT_SCHEMA,
        "keyword_call_facts": KEYWORD_CALL_FACT_SCHEMA,
        "keyword_only_call_facts": KEYWORD_ONLY_CALL_FACT_SCHEMA,
        "conversion_plan": CONVERSION_PLAN_SCHEMA,
        "c_ir": C_IR_SCHEMA,
        "generated_c": GENERATED_C_SCHEMA,
        "conversion_summary": CONVERSION_SUMMARY_SCHEMA,
        "decision_trace": DECISION_TRACE_SCHEMA,
        "result": RESULT_SCHEMA_VERSION,
        "rule_set": DEFAULT_RULE_SET,
        "renderer": DEFAULT_RENDERER,
        "keyword_call_rule": KEYWORD_CALL_RULE_ID,
        "keyword_only_call_rule": KEYWORD_ONLY_CALL_RULE_ID,
        "target_contract": DEFAULT_TARGET_CONTRACT,
        "semantic_policy": DEFAULT_SEMANTIC_POLICY,
        "helper_policy": DEFAULT_HELPER_POLICY,
        "container_policy": DEFAULT_CONTAINER_POLICY,
        "module_policy": DEFAULT_MODULE_POLICY,
        "record_policy": DEFAULT_RECORD_POLICY,
        "numeric_policy": DEFAULT_NUMERIC_POLICY,
    }


def fixed_supported_subset_cases() -> tuple[SupportedSubsetCase, ...]:
    """Return one positive witness for every promoted construct family."""

    return (
        SupportedSubsetCase(
            "fixed-literals",
            "literals",
            (
                "def integer_value() -> int:\n"
                "    return 7\n\n"
                "def real_value() -> float:\n"
                "    return 1.5\n\n"
                "def flag_value() -> bool:\n"
                "    return True\n\n"
                "def text_value() -> str:\n"
                '    return "PyCForge"\n'
            ),
        ),
        SupportedSubsetCase(
            "fixed-arithmetic",
            "assignments-and-arithmetic",
            (
                "def calculate(a: int, b: int) -> int:\n"
                "    value = a + b * 2\n"
                "    value = value - 1\n"
                "    return value\n\n"
                "def ratio(value: float) -> float:\n"
                "    return value / 2.0\n"
            ),
        ),
        SupportedSubsetCase(
            "fixed-positional-call",
            "functions-and-positional-calls",
            (
                "def add(a: int, b: int) -> int:\n"
                "    return a + b\n\n"
                "def run(value: int) -> int:\n"
                "    return add(value, 3)\n"
            ),
        ),
        SupportedSubsetCase(
            "fixed-if-else",
            "if-else",
            (
                "def choose(value: int, flag: bool) -> int:\n"
                "    if flag:\n"
                "        value = value + 1\n"
                "    else:\n"
                "        value = value - 1\n"
                "    return value\n"
            ),
        ),
        SupportedSubsetCase(
            "fixed-while",
            "while-break-continue",
            (
                "def scan(limit: int) -> int:\n"
                "    value = 0\n"
                "    while value < limit:\n"
                "        value = value + 1\n"
                "        if value == 2:\n"
                "            continue\n"
                "        if value == 5:\n"
                "            break\n"
                "    return value\n"
            ),
        ),
        SupportedSubsetCase(
            "fixed-range-for",
            "bounded-range-for",
            (
                "def total() -> int:\n"
                "    value = 0\n"
                "    for item in range(1, 6, 2):\n"
                "        value = value + item\n"
                "    return value\n"
            ),
        ),
        SupportedSubsetCase(
            "fixed-list",
            "list",
            (
                "def pick() -> int:\n"
                "    values = [1, 2, 3]\n"
                "    return values[-1]\n\n"
                "def iterate() -> int:\n"
                "    values = [2, 4, 6]\n"
                "    result = 0\n"
                "    for item in values:\n"
                "        result = item\n"
                "    return result\n"
            ),
        ),
        SupportedSubsetCase(
            "fixed-tuple",
            "tuple",
            (
                "def pick() -> str:\n"
                '    values = ("a", "b")\n'
                "    return values[0]\n"
            ),
        ),
        SupportedSubsetCase(
            "fixed-dict",
            "dict",
            (
                "def pick() -> int:\n"
                '    values = {"a": 1, "b": 2}\n'
                '    return values["b"]\n'
            ),
        ),
        SupportedSubsetCase(
            "fixed-module-bundle",
            "explicit-module-bundle",
            (
                "from lib import increment\n\n"
                "def run(value: int) -> int:\n"
                "    return increment(value)\n"
            ),
            primary_name="app.py",
            primary_module="app",
            companions=(
                (
                    "lib",
                    "lib.py",
                    (
                        "def increment(value: int) -> int:\n"
                        "    return value + 1\n"
                    ),
                ),
            ),
        ),
        SupportedSubsetCase(
            "fixed-record",
            "static-record",
            (
                "class Point:\n"
                "    x: int\n"
                "    y: int\n"
                "    def __init__(self, x: int, y: int) -> None:\n"
                "        self.x = x\n"
                "        self.y = y\n\n"
                "def read() -> int:\n"
                "    point = Point(2, 3)\n"
                "    return point.x\n"
            ),
        ),
        SupportedSubsetCase(
            "fixed-floor-arithmetic",
            "bounded-floor-arithmetic",
            (
                "def arithmetic(value: int) -> int:\n"
                "    return (value // -3) + (value % 5)\n"
            ),
        ),
        SupportedSubsetCase(
            "fixed-boolean-region",
            "boolean-conditional-region",
            (
                "def flag(value: bool) -> bool:\n"
                "    return value\n\n"
                "def decide(a: bool, b: bool) -> bool:\n"
                "    return a and flag(b)\n"
            ),
        ),
        SupportedSubsetCase(
            "fixed-comparison-region",
            "comparison-conditional-region",
            (
                "def identity(value: int) -> int:\n"
                "    return value\n\n"
                "def compare(a: int, b: int, c: int) -> bool:\n"
                "    return a < b < identity(c)\n"
            ),
        ),
        SupportedSubsetCase(
            "fixed-keyword-call",
            "direct-keyword-call",
            (
                "def choose(left: int, flag: bool) -> int:\n"
                "    return left\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return choose(flag=flag, left=value)\n"
            ),
        ),
        SupportedSubsetCase(
            "fixed-keyword-only-call",
            "required-keyword-only-call",
            (
                "def choose(left: int, /, middle: int, *, scale: int) -> int:\n"
                "    return (left + middle) * scale\n\n"
                "def run() -> int:\n"
                "    return choose(1, middle=2, scale=3)\n"
            ),
        ),
    )


def generated_fuzz_cases(
    *,
    seed: int = FUZZ_SEED,
    count: int = DEFAULT_FUZZ_CASE_COUNT,
) -> tuple[SupportedSubsetCase, ...]:
    """Generate bounded, reproducible cases across every promoted family.

    Each complete 16-case cycle contains every member of
    :data:`SUPPORTED_SUBSET_FAMILIES` exactly once in a seeded shuffled order.
    The family templates perturb safe constants, names, keys, bounds, and
    operator choices without crossing the frozen subset boundary.
    """

    if count < 0:
        raise ValueError("count must be non-negative")
    rng = random.Random(seed)
    cases: list[SupportedSubsetCase] = []
    family_cycle: list[str] = []

    def next_family() -> str:
        nonlocal family_cycle
        if not family_cycle:
            family_cycle = sorted(SUPPORTED_SUBSET_FAMILIES)
            rng.shuffle(family_cycle)
        return family_cycle.pop()

    for ordinal in range(count):
        family = next_family()
        first = rng.randint(1, 31)
        second = rng.randint(1, 31)
        third = rng.randint(1, 15)
        primary_name = "main.py"
        primary_module = "main"
        companions: tuple[tuple[str, str, str], ...] = ()
        if family == "literals":
            source = (
                f"def integer_{ordinal:03d}() -> int:\n"
                f"    return {first}\n\n"
                f"def real_{ordinal:03d}() -> float:\n"
                f"    return {second}.{third}\n\n"
                f"def flag_{ordinal:03d}() -> bool:\n"
                f"    return {'True' if first % 2 else 'False'}\n\n"
                f"def text_{ordinal:03d}() -> str:\n"
                f'    return "fuzz-{ordinal:03d}-{third}"\n'
            )
        elif family == "assignments-and-arithmetic":
            divisor = rng.randint(2, 9)
            source = (
                f"def arithmetic_{ordinal:03d}(value: int) -> int:\n"
                f"    result = value + {first}\n"
                f"    result = result * {third}\n"
                f"    return result - {second}\n\n"
                f"def divide_{ordinal:03d}(value: float) -> float:\n"
                f"    return value / {divisor}.0\n"
            )
        elif family == "functions-and-positional-calls":
            source = (
                f"def add_{ordinal:03d}(left: int, right: int) -> int:\n"
                "    return left + right\n\n"
                f"def run_{ordinal:03d}(value: int) -> int:\n"
                f"    return add_{ordinal:03d}(value, {first})\n"
            )
        elif family == "if-else":
            source = (
                f"def choose_{ordinal:03d}(value: int, flag: bool) -> int:\n"
                "    if flag:\n"
                f"        value = value + {first}\n"
                "    else:\n"
                f"        value = value - {second}\n"
                "    return value\n"
            )
        elif family == "while-break-continue":
            continue_at = rng.randint(1, 3)
            break_at = rng.randint(4, 8)
            source = (
                f"def scan_{ordinal:03d}(limit: int) -> int:\n"
                "    value = 0\n"
                "    while value < limit:\n"
                "        value = value + 1\n"
                f"        if value == {continue_at}:\n"
                "            continue\n"
                f"        if value == {break_at}:\n"
                "            break\n"
                "    return value\n"
            )
        elif family == "bounded-range-for":
            start = rng.randint(0, 3)
            step = rng.randint(1, 3)
            stop = start + step * rng.randint(2, 7)
            source = (
                f"def total_{ordinal:03d}() -> int:\n"
                "    result = 0\n"
                f"    for item in range({start}, {stop}, {step}):\n"
                "        result = result + item\n"
                "    return result\n"
            )
        elif family == "list":
            values = (first, second, third)
            source = (
                f"def list_{ordinal:03d}() -> int:\n"
                f"    values = [{values[0]}, {values[1]}, {values[2]}]\n"
                "    result = 0\n"
                "    for item in values:\n"
                "        result = item\n"
                "    return result\n"
            )
        elif family == "tuple":
            source = (
                f"def tuple_{ordinal:03d}() -> str:\n"
                f'    values = ("left-{first}", "right-{second}")\n'
                f"    return values[{ordinal % 2}]\n"
            )
        elif family == "dict":
            source = (
                f"def dict_{ordinal:03d}() -> str:\n"
                f'    values = {{"left-{first}": {first}, '
                f'"right-{second}": {second}}}\n'
                '    result = ""\n'
                "    for key in values:\n"
                "        result = key\n"
                "    return result\n"
            )
        elif family == "explicit-module-bundle":
            primary_name = f"app_{ordinal:03d}.py"
            primary_module = f"app_{ordinal:03d}"
            companion_module = f"lib_{ordinal:03d}"
            companion_name = f"{companion_module}.py"
            helper_name = f"increment_{ordinal:03d}"
            source = (
                f"from {companion_module} import {helper_name}\n\n"
                f"def run_{ordinal:03d}(value: int) -> int:\n"
                f"    return {helper_name}(value)\n"
            )
            companions = (
                (
                    companion_module,
                    companion_name,
                    (
                        f"def {helper_name}(value: int) -> int:\n"
                        f"    return value + {first}\n"
                    ),
                ),
            )
        elif family == "static-record":
            class_name = f"Sample{ordinal:03d}"
            source = (
                f"class {class_name}:\n"
                "    value: int\n"
                "    def __init__(self, value: int) -> None:\n"
                "        self.value = value\n\n"
                f"def record_{ordinal:03d}() -> int:\n"
                f"    sample = {class_name}({first})\n"
                "    return sample.value\n"
            )
        elif family == "bounded-floor-arithmetic":
            safe_divisors = (-9, -7, -5, -3, 2, 3, 5, 7, 9)
            floor_divisor = rng.choice(safe_divisors)
            mod_divisor = rng.choice(safe_divisors)
            source = (
                f"def floor_{ordinal:03d}(value: int) -> int:\n"
                f"    return (value // {floor_divisor}) + "
                f"(value % {mod_divisor})\n"
            )
        elif family == "boolean-conditional-region":
            operator = "and" if ordinal % 2 else "or"
            source = (
                f"def flag_{ordinal:03d}(value: bool) -> bool:\n"
                "    return value\n\n"
                f"def boolean_{ordinal:03d}(left: bool, right: bool) -> bool:\n"
                f"    return left {operator} flag_{ordinal:03d}(right)\n"
            )
        elif family == "comparison-conditional-region":
            source = (
                f"def identity_{ordinal:03d}(value: int) -> int:\n"
                "    return value\n\n"
                f"def compare_{ordinal:03d}("
                "left: int, middle: int, right: int) -> bool:\n"
                f"    return left < middle < identity_{ordinal:03d}(right)\n"
            )
        elif family == "direct-keyword-call":
            source = (
                f"def choose_{ordinal:03d}("
                "left: int, middle: int, flag: bool) -> int:\n"
                "    if flag:\n"
                "        return left\n"
                "    return middle\n\n"
                f"def keyword_{ordinal:03d}(value: int, flag: bool) -> int:\n"
                f"    return choose_{ordinal:03d}("
                f"value, flag=flag, middle={first})\n"
            )
        elif family == "required-keyword-only-call":
            source = (
                f"def scale_{ordinal:03d}("
                "left: int, /, middle: int, *, factor: int) -> int:\n"
                "    return (left + middle) * factor\n\n"
                f"def keyword_only_{ordinal:03d}() -> int:\n"
                f"    return scale_{ordinal:03d}("
                f"{first}, middle={second}, factor={third})\n"
            )
        else:  # pragma: no cover - the frozen family set is exhaustively routed.
            raise AssertionError(f"unrouted generated family: {family}")
        cases.append(
            SupportedSubsetCase(
                f"fuzz-{ordinal:03d}",
                family,
                source,
                primary_name,
                primary_module,
                companions,
            )
        )
    return tuple(cases)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _ast_kinds_for_witness(witness: FeatureMatrixWitness) -> set[str]:
    kinds: set[str] = set()
    documents = (
        (witness.logical_name, witness.source),
        *((logical_name, text) for _, logical_name, text in witness.companions),
    )
    for logical_name, source in documents:
        tree = ast.parse(source, filename=logical_name, mode="exec")
        kinds.update(type(node).__name__ for node in ast.walk(tree))
    return kinds


def _feature_matrix_entry_contract(
    entry: Mapping[str, object],
) -> dict[str, object]:
    return {
        "construct": entry.get("construct"),
        "context": entry.get("context"),
        "state": entry.get("state"),
        "diagnostic": entry.get("diagnostic"),
    }


def _execute_feature_matrix_witness(
    converter: PythonToCConverter,
    witness: FeatureMatrixWitness,
    *,
    profile_id: str,
    request_options: Mapping[str, object] | None,
    expected_diagnostic: str | None,
    reason_contains: str | None,
) -> tuple[dict[str, object], list[str]]:
    """Execute one profile twice and return closed, source-only evidence."""

    errors: list[str] = []
    request = witness.request(request_options)
    first = converter.convert(request)
    repeated = converter.convert(request)
    first_json = result_to_json(first)
    repeated_json = result_to_json(repeated)
    deterministic = first_json == repeated_json
    if not deterministic:
        errors.append(
            f"{witness.witness_id}/{profile_id}: repeated conversion is not "
            "byte-stable"
        )

    diagnostic_codes = [item.code for item in first.diagnostics]
    diagnostic_messages = [item.message for item in first.diagnostics]
    expected_status = (
        ResultStatus.CONVERTED
        if witness.state == "supported"
        else ResultStatus.REJECTED
    )
    if first.status is not expected_status:
        errors.append(
            f"{witness.witness_id}/{profile_id}: expected "
            f"{expected_status.value}, got {first.status.value}"
        )

    c_conformance_accepted: bool | None = None
    c_conformance_message: str | None = None
    if witness.state == "supported":
        if first.generated_c is None:
            errors.append(
                f"{witness.witness_id}/{profile_id}: supported witness did "
                "not publish C source"
            )
        else:
            conformance = validate_c_text(first.generated_c)
            c_conformance_accepted = conformance.accepted
            c_conformance_message = conformance.message
            if not conformance.accepted:
                errors.append(
                    f"{witness.witness_id}/{profile_id}: emitted C source "
                    f"failed independent conformance: {conformance.message}"
                )
        if first.diagnostics:
            errors.append(
                f"{witness.witness_id}/{profile_id}: supported witness "
                f"published diagnostics {diagnostic_codes}"
            )
    else:
        if first.generated_c is not None:
            errors.append(
                f"{witness.witness_id}/{profile_id}: rejected witness "
                "published C source"
            )
        if first.output_fingerprint is not None:
            errors.append(
                f"{witness.witness_id}/{profile_id}: rejected witness "
                "published an output fingerprint"
            )
        if expected_diagnostic is not None and expected_diagnostic not in diagnostic_codes:
            errors.append(
                f"{witness.witness_id}/{profile_id}: expected diagnostic "
                f"{expected_diagnostic}, got {diagnostic_codes}"
            )
        if reason_contains is not None and not any(
            reason_contains in message for message in diagnostic_messages
        ):
            errors.append(
                f"{witness.witness_id}/{profile_id}: no diagnostic reason "
                f"contained {reason_contains!r}"
            )

    evidence: dict[str, object] = {
        "profile_id": profile_id,
        "request_options": dict(request_options or {}),
        "expected_status": expected_status.value,
        "actual_status": first.status.value,
        "expected_diagnostic": expected_diagnostic,
        "actual_diagnostics": diagnostic_codes,
        "actual_reasons": diagnostic_messages,
        "deterministic": deterministic,
        "generated_c_published": first.generated_c is not None,
        "output_fingerprint_published": first.output_fingerprint is not None,
        "independent_c_conformance_accepted": c_conformance_accepted,
        "independent_c_conformance_message": c_conformance_message,
        "result_sha256": hashlib.sha256(first_json.encode("utf-8")).hexdigest(),
    }
    return evidence, errors


def audit_feature_matrix(root: Path) -> dict[str, object]:
    """Execute all 69 frozen rows and the unlisted-node default.

    Every row is driven through :class:`PythonToCConverter`.  The one
    cumulative diagnostic whose owning profile differs from the current
    default (``AsyncFunctionDef``) names its Phase 9 request explicitly and
    also runs the current-profile precedence companion.
    """

    matrix_path = root / "specifications" / "feature_matrix.json"
    errors: list[str] = []
    matrix_contract_mismatches: list[dict[str, object]] = []
    raw_matrix = b""
    matrix: dict[str, object] = {}
    if not matrix_path.is_file():
        errors.append(f"feature matrix is missing: {matrix_path}")
    else:
        raw_matrix = matrix_path.read_bytes()
        try:
            loaded = json.loads(raw_matrix.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"feature matrix is not valid canonical UTF-8 JSON: {exc}")
        else:
            if not isinstance(loaded, dict):
                errors.append("feature matrix root must be an object")
            else:
                matrix = loaded

    matrix_sha256 = hashlib.sha256(raw_matrix).hexdigest()
    if matrix_sha256 != FEATURE_MATRIX_SHA256:
        errors.append(
            "feature matrix SHA-256 drift: expected "
            f"{FEATURE_MATRIX_SHA256}, got {matrix_sha256}"
        )
    if matrix.get("schema") != FEATURE_MATRIX_SCHEMA:
        errors.append(
            "feature matrix schema drift: expected "
            f"{FEATURE_MATRIX_SCHEMA!r}, got {matrix.get('schema')!r}"
        )
    expected_metadata = {
        "grammar": "python-3.11",
        "rule_set": EXPECTED_CONTRACT_IDENTITIES["rule_set"],
        "renderer": EXPECTED_CONTRACT_IDENTITIES["renderer"],
        "helper_policy": EXPECTED_CONTRACT_IDENTITIES["helper_policy"],
        "container_policy": EXPECTED_CONTRACT_IDENTITIES["container_policy"],
        "module_policy": EXPECTED_CONTRACT_IDENTITIES["module_policy"],
        "record_policy": EXPECTED_CONTRACT_IDENTITIES["record_policy"],
        "numeric_policy": EXPECTED_CONTRACT_IDENTITIES["numeric_policy"],
        "conditional_fact_schema": EXPECTED_CONTRACT_IDENTITIES[
            "conditional_facts"
        ],
        "keyword_call_fact_schema": EXPECTED_CONTRACT_IDENTITIES[
            "keyword_call_facts"
        ],
        "keyword_only_call_fact_schema": EXPECTED_CONTRACT_IDENTITIES[
            "keyword_only_call_facts"
        ],
        "default_state": "unsupported",
    }
    for key, expected in expected_metadata.items():
        actual = matrix.get(key)
        if actual != expected:
            errors.append(
                f"feature matrix {key} drift: expected {expected!r}, "
                f"got {actual!r}"
            )

    raw_entries = matrix.get("entries", ())
    entries: list[Mapping[str, object]] = []
    if not isinstance(raw_entries, list):
        errors.append("feature matrix entries must be an array")
    else:
        for ordinal, entry in enumerate(raw_entries):
            if not isinstance(entry, Mapping):
                errors.append(
                    f"feature matrix entry {ordinal} must be an object"
                )
            else:
                entries.append(entry)
    if len(entries) != FEATURE_MATRIX_ENTRY_COUNT:
        errors.append(
            "feature matrix entry-count drift: expected "
            f"{FEATURE_MATRIX_ENTRY_COUNT}, got {len(entries)}"
        )

    witnesses = FEATURE_MATRIX_WITNESS_ORDER
    witness_keys = [item.key for item in witnesses]
    if len(witnesses) != FEATURE_MATRIX_ENTRY_COUNT:
        errors.append(
            "feature witness count drift: expected "
            f"{FEATURE_MATRIX_ENTRY_COUNT}, got {len(witnesses)}"
        )
    if len(FEATURE_MATRIX_WITNESSES) != len(witnesses):
        errors.append("feature witness keys are not unique")

    actual_keys = [
        (str(entry.get("construct")), str(entry.get("context")))
        for entry in entries
    ]
    if actual_keys != witness_keys:
        matrix_contract_mismatches.append(
            {
                "kind": "order-or-key-drift",
                "expected": [list(key) for key in witness_keys],
                "actual": [list(key) for key in actual_keys],
            }
        )

    entry_by_key: dict[tuple[str, str], Mapping[str, object]] = {}
    for entry in entries:
        key = (str(entry.get("construct")), str(entry.get("context")))
        if key in entry_by_key:
            matrix_contract_mismatches.append(
                {
                    "kind": "duplicate-entry-key",
                    "key": list(key),
                }
            )
        entry_by_key[key] = entry

    for witness in witnesses:
        entry = entry_by_key.get(witness.key)
        if entry is None:
            matrix_contract_mismatches.append(
                {
                    "kind": "missing-entry",
                    "key": list(witness.key),
                }
            )
            continue
        expected_contract = {
            "construct": witness.construct,
            "context": witness.context,
            "state": witness.state,
            "diagnostic": witness.diagnostic,
        }
        actual_contract = _feature_matrix_entry_contract(entry)
        if actual_contract != expected_contract:
            matrix_contract_mismatches.append(
                {
                    "kind": "entry-contract-drift",
                    "key": list(witness.key),
                    "expected": expected_contract,
                    "actual": actual_contract,
                }
            )
    unexpected_keys = sorted(set(entry_by_key) - set(witness_keys))
    for key in unexpected_keys:
        matrix_contract_mismatches.append(
            {
                "kind": "unexpected-entry",
                "key": list(key),
            }
        )

    converter = PythonToCConverter()
    execution_rows: list[dict[str, object]] = []
    witness_errors: list[str] = []
    diagnostic_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter(item.state for item in witnesses)
    actual_status_counts: Counter[str] = Counter()
    for witness in (*witnesses, UNLISTED_DEFAULT_WITNESS):
        try:
            ast_kinds = _ast_kinds_for_witness(witness)
        except SyntaxError as exc:
            witness_errors.append(
                f"{witness.witness_id}: witness source is invalid Python: {exc}"
            )
            ast_kinds = set()
        missing_ast_kinds = sorted(
            set(witness.required_ast_kinds) - ast_kinds
        )
        if missing_ast_kinds:
            witness_errors.append(
                f"{witness.witness_id}: source does not contain required AST "
                f"kinds {missing_ast_kinds}"
            )

        primary, primary_errors = _execute_feature_matrix_witness(
            converter,
            witness,
            profile_id="matrix-owner",
            request_options=dict(witness.request_options),
            expected_diagnostic=witness.expected_diagnostic,
            reason_contains=witness.actual_reason_contains,
        )
        witness_errors.extend(primary_errors)
        actual_status_counts[str(primary["actual_status"])] += 1
        diagnostic_counts.update(
            str(item) for item in primary["actual_diagnostics"]
        )
        profiles = [primary]
        for profile in witness.precedence_profiles:
            evidence, profile_errors = _execute_feature_matrix_witness(
                converter,
                witness,
                profile_id=profile.profile_id,
                request_options=profile.options(),
                expected_diagnostic=profile.expected_diagnostic,
                reason_contains=profile.reason_contains,
            )
            profiles.append(evidence)
            witness_errors.extend(profile_errors)

        if (
            witness.diagnostic is not None
            and witness.diagnostic
            not in set(str(item) for item in primary["actual_diagnostics"])
        ):
            matrix_contract_mismatches.append(
                {
                    "kind": "declared-diagnostic-drift",
                    "key": list(witness.key),
                    "profile_id": "matrix-owner",
                    "expected": witness.diagnostic,
                    "actual": primary["actual_diagnostics"],
                    "actual_reasons": primary["actual_reasons"],
                }
            )
        execution_rows.append(
            {
                "witness_id": witness.witness_id,
                "matrix_key": list(witness.key),
                "state": witness.state,
                "exercise": witness.exercise,
                "required_ast_kinds": list(witness.required_ast_kinds),
                "observed_ast_kinds_sha256": _sha256_json(
                    sorted(ast_kinds)
                ),
                "profiles": profiles,
            }
        )

    if matrix_contract_mismatches:
        errors.append(
            "feature matrix contract mismatches were found: "
            f"{len(matrix_contract_mismatches)}"
        )
    errors.extend(witness_errors)
    witness_manifest = [item.manifest() for item in witnesses]
    report: dict[str, object] = {
        "audit": "checkpoint-e-executable-feature-matrix",
        "passed": not errors,
        "errors": errors,
        "matrix_path": "specifications/feature_matrix.json",
        "matrix_schema": matrix.get("schema"),
        "matrix_sha256": matrix_sha256,
        "expected_matrix_sha256": FEATURE_MATRIX_SHA256,
        "matrix_entry_count": len(entries),
        "expected_matrix_entry_count": FEATURE_MATRIX_ENTRY_COUNT,
        "matrix_state_counts": dict(sorted(state_counts.items())),
        "matrix_witness_count": len(witnesses),
        "unlisted_default_witness_count": 1,
        "total_primary_execution_count": len(execution_rows),
        "precedence_profile_execution_count": sum(
            len(row["profiles"]) - 1 for row in execution_rows
        ),
        "actual_status_counts": dict(sorted(actual_status_counts.items())),
        "actual_diagnostic_counts": dict(sorted(diagnostic_counts.items())),
        "matrix_contract_mismatches": matrix_contract_mismatches,
        "witness_errors": witness_errors,
        "witness_manifest_sha256": _sha256_json(witness_manifest),
        "execution_rows": execution_rows,
        "execution_sha256": _sha256_json(execution_rows),
        "coverage_complete": (
            len(witnesses) == FEATURE_MATRIX_ENTRY_COUNT
            and len(FEATURE_MATRIX_WITNESSES) == FEATURE_MATRIX_ENTRY_COUNT
            and not matrix_contract_mismatches
            and not witness_errors
        ),
        "c_toolchain_invoked": False,
        "generated_c_compiled_or_executed": False,
    }
    report["report_sha256"] = _sha256_json(report)
    return report


def _walk_mappings(value: object) -> Iterable[Mapping[str, object]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_mappings(child)


_GENERATED_TEMPORARY = re.compile(
    r"\bpycf_[A-Za-z][A-Za-z0-9_]*_[0-9a-f]{12}\b"
)
_GENERATED_COLLISION_SUFFIX = re.compile(
    r"\b([A-Za-z][A-Za-z0-9_]*)_[2-9][0-9]*\b"
)


def _normalized_generated_c(text: str | None) -> str | None:
    """Alpha-rename source-ID-derived temporaries while retaining C semantics."""

    if text is None:
        return None
    names: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        name = match.group(0)
        replacement = names.get(name)
        if replacement is None:
            prefix = name.rsplit("_", 1)[0]
            replacement = f"{prefix}_METAVAR_{len(names):04d}"
            names[name] = replacement
        return replacement

    temporaries_normalized = _GENERATED_TEMPORARY.sub(replace, text)
    return _GENERATED_COLLISION_SUFFIX.sub(r"\1", temporaries_normalized)


def _semantic_shape(result: Any) -> dict[str, object]:
    """Discard source-derived IDs while preserving observable structure."""

    summary = result.conversion_summary or {}
    artifact = result.stage_artifact
    payload = artifact.payload if artifact is not None else {}
    plans = payload.get("rule_plans", ())
    tables = payload.get("fact_tables", ())
    c_ir = payload.get("c_ir", {})
    plan_counts = Counter(
        (
            str(item.get("rule_id")),
            str(item.get("rule_version")),
            str(item.get("support_state")),
        )
        for item in plans
        if isinstance(item, Mapping)
    )
    c_ir_kinds = Counter(
        str(item["kind"])
        for item in _walk_mappings(c_ir)
        if isinstance(item.get("kind"), str)
    )
    feature_names = (
        "helpers",
        "functions",
        "calls",
        "containers",
        "container_accesses",
        "container_iterations",
        "modules",
        "module_imports",
        "records",
        "record_fields",
        "record_initializers",
        "record_instances",
        "record_bindings",
        "record_accesses",
        "numeric_operations",
        "conditional_regions",
        "keyword_calls",
        "keyword_only_calls",
    )
    return {
        "status": result.status.value,
        "diagnostics": [
            (item.code, item.severity.value, item.stage) for item in result.diagnostics
        ],
        "last_completed_stage": result.last_completed_stage,
        "stage_order": list(result.stage_order),
        "normalized_generated_c_sha256": (
            None
            if result.generated_c is None
            else hashlib.sha256(
                _normalized_generated_c(result.generated_c).encode("utf-8")
            ).hexdigest()
        ),
        "summary_contracts": {
            key: summary.get(key)
            for key in (
                "schema_version",
                "target_contract",
                "semantic_policy",
                "rule_set_version",
                "renderer_version",
                "helper_policy_version",
                "container_policy_version",
                "module_policy_version",
                "record_policy_version",
                "numeric_policy_version",
                "translation_unit_count",
            )
        },
        "feature_counts": {
            name: len(summary.get(name, ())) for name in feature_names
        },
        "artifact": None
        if artifact is None
        else {
            "kind": artifact.kind,
            "schema_version": artifact.schema_version,
            "payload_schema": payload.get("schema_version"),
            "c_ir_schema": payload.get("c_ir_schema"),
        },
        "helpers": list(payload.get("helper_requirements", ())),
        "rule_plan_counts": [
            [*key, count] for key, count in sorted(plan_counts.items())
        ],
        "fact_tables": sorted(
            [
                [
                    str(item.get("table_id")),
                    str(item.get("schema_version")),
                    len(item.get("records", ())),
                ]
                for item in tables
                if isinstance(item, Mapping)
            ]
        ),
        "c_ir_kind_counts": [
            [kind, count] for kind, count in sorted(c_ir_kinds.items())
        ],
    }


def _transform_case(
    case: SupportedSubsetCase,
    transformation: str,
) -> SupportedSubsetCase:
    def transform(text: str) -> str:
        if transformation == "leading-comment":
            return "# Checkpoint E metamorphic witness\n" + text
        if transformation == "crlf":
            return text.replace("\n", "\r\n")
        if transformation == "blank-lines":
            return text.replace("\n\n", "\n\n\n") + "\n"
        raise ValueError(f"unknown transformation: {transformation}")

    return SupportedSubsetCase(
        case_id=f"{case.case_id}:{transformation}",
        family=case.family,
        primary_text=transform(case.primary_text),
        primary_name=case.primary_name,
        primary_module=case.primary_module,
        companions=tuple(
            (module_id, logical_name, transform(text))
            for module_id, logical_name, text in case.companions
        ),
    )


def audit_full_supported_subset(
    *,
    seed: int = FUZZ_SEED,
    fuzz_case_count: int = DEFAULT_FUZZ_CASE_COUNT,
) -> dict[str, object]:
    """Run deterministic, observer-invariant, metamorphic source-only checks."""

    fixed = fixed_supported_subset_cases()
    generated = generated_fuzz_cases(seed=seed, count=fuzz_case_count)
    cases = (*fixed, *generated)
    errors: list[str] = []
    families = {case.family for case in fixed}
    generated_family_counts = Counter(case.family for case in generated)
    generated_missing_families = sorted(
        SUPPORTED_SUBSET_FAMILIES - set(generated_family_counts)
    )
    missing_families = sorted(SUPPORTED_SUBSET_FAMILIES - families)
    if missing_families:
        errors.append(
            "fixed corpus lacks supported families: " + ", ".join(missing_families)
        )
    if (
        fuzz_case_count >= len(SUPPORTED_SUBSET_FAMILIES)
        and generated_missing_families
    ):
        errors.append(
            "generated corpus lacks promoted families despite a complete "
            "family cycle: " + ", ".join(generated_missing_families)
        )

    converter = PythonToCConverter()
    transformations = ("leading-comment", "crlf", "blank-lines")
    case_digests: list[dict[str, str]] = []
    for case in cases:
        full_observation = ObservationOptions("Full", True)
        none_observation = ObservationOptions("None", False)
        first = converter.convert(case.request(), observation=full_observation)
        repeated = converter.convert(case.request(), observation=full_observation)
        first_json = result_to_json(first)
        repeated_json = result_to_json(repeated)
        if first_json != repeated_json:
            errors.append(f"{case.case_id}: repeated conversion is not byte-stable")
        if first.status is not ResultStatus.CONVERTED:
            errors.append(
                f"{case.case_id}: expected Converted, got {first.status.value} "
                f"({','.join(item.code for item in first.diagnostics)})"
            )
        if first.generated_c is None:
            errors.append(f"{case.case_id}: converted result did not publish C text")
        else:
            conformance = validate_c_text(first.generated_c)
            if not conformance.accepted:
                errors.append(
                    f"{case.case_id}: emitted C text failed source conformance: "
                    f"{conformance.message}"
                )

        unobserved = converter.convert(case.request(), observation=none_observation)
        if (
            result_to_json(first, include_observers=False)
            != result_to_json(unobserved, include_observers=False)
        ):
            errors.append(f"{case.case_id}: observer settings changed semantics")

        base_shape = _semantic_shape(first)
        for transformation in transformations:
            variant = _transform_case(case, transformation)
            transformed = converter.convert(
                variant.request(),
                observation=full_observation,
            )
            if _semantic_shape(transformed) != base_shape:
                errors.append(
                    f"{case.case_id}: {transformation} changed semantic shape"
                )
            if transformed.generated_c is not None:
                conformance = validate_c_text(transformed.generated_c)
                if not conformance.accepted:
                    errors.append(
                        f"{case.case_id}: {transformation} emitted "
                        f"nonconforming C text: {conformance.message}"
                    )
        case_digests.append(
            {
                "case_id": case.case_id,
                "result_sha256": hashlib.sha256(
                    first_json.encode("utf-8")
                ).hexdigest(),
                "shape_sha256": _sha256_json(base_shape),
            }
        )

    corpus_manifest = [case.manifest() for case in cases]
    report: dict[str, object] = {
        "audit": "checkpoint-e-full-supported-subset",
        "passed": not errors,
        "errors": errors,
        "seed": seed,
        "fixed_case_count": len(fixed),
        "generated_case_count": len(generated),
        "case_count": len(cases),
        "metamorphic_transformations": list(transformations),
        "metamorphic_conversion_count": len(cases) * len(transformations),
        "supported_families": sorted(families),
        "missing_supported_families": missing_families,
        "generated_family_counts": dict(sorted(generated_family_counts.items())),
        "generated_missing_families": generated_missing_families,
        "generated_complete_family_cycles": (
            fuzz_case_count // len(SUPPORTED_SUBSET_FAMILIES)
        ),
        "generated_feature_counts": {
            "fixed-container-iteration": sum(
                count
                for family, count in generated_family_counts.items()
                if family in {"dict", "list"}
            ),
            "floating-division": generated_family_counts.get(
                "assignments-and-arithmetic",
                0,
            ),
        },
        "fixed_feature_witnesses": {
            "fixed-container-iteration": "fixed-list",
            "floating-division": "fixed-arithmetic",
        },
        "corpus_sha256": _sha256_json(corpus_manifest),
        "case_digests": case_digests,
        "c_toolchain_invoked": False,
        "generated_c_compiled_or_executed": False,
    }
    report["report_sha256"] = _sha256_json(report)
    return report


_FORBIDDEN_IMPORT_ROOTS = {
    "cffi",
    "ctypes",
    "pexpect",
    "subprocess",
}
_FORBIDDEN_BUILTIN_CALL_NAMES = {
    "compile",
    "eval",
    "exec",
}
_FORBIDDEN_ATTRIBUTE_CALL_NAMES = {
    "popen",
    "system",
}
_FORBIDDEN_ACTION_LABELS = {
    "Build",
    "Debug",
    "Plugin Marketplace",
    "Project Explorer",
    "Run",
    "Terminal",
}
_EXTERNAL_BRANDS = {
    "chatgpt",
    "codex",
    "jetbrains",
    "openai",
    "pycharm",
    "visual studio code",
    "vscode",
}
def scan_product_boundary(root: Path) -> list[str]:
    """Find runtime imports, calls, labels, and brands outside product scope."""

    violations: list[str] = []
    runtime_roots = (
        root / "pycforge" / "converter",
        root / "pycforge" / "ide",
    )
    for runtime_root in runtime_roots:
        if not runtime_root.exists():
            continue
        for path in sorted(runtime_root.rglob("*.py")):
            relative = path.relative_to(root).as_posix()
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            except (OSError, SyntaxError) as exc:
                violations.append(f"{relative}: cannot inspect source: {exc}")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported = [node.module]
                else:
                    imported = []
                for name in imported:
                    if name.split(".", 1)[0] in _FORBIDDEN_IMPORT_ROOTS:
                        violations.append(
                            f"{relative}:{node.lineno}: forbidden runtime import {name}"
                        )
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        call_name = node.func.id
                        forbidden_call = (
                            call_name in _FORBIDDEN_BUILTIN_CALL_NAMES
                        )
                    elif isinstance(node.func, ast.Attribute):
                        call_name = node.func.attr
                        forbidden_call = (
                            call_name.casefold()
                            in _FORBIDDEN_ATTRIBUTE_CALL_NAMES
                        )
                    else:
                        call_name = ""
                        forbidden_call = False
                    if forbidden_call:
                        violations.append(
                            f"{relative}:{node.lineno}: forbidden runtime call "
                            f"{call_name}"
                        )
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    normalized = " ".join(node.value.split()).casefold()
                    if node.value.strip() in _FORBIDDEN_ACTION_LABELS:
                        violations.append(
                            f"{relative}:{node.lineno}: out-of-scope action label "
                            f"{node.value!r}"
                        )
                    for brand in sorted(_EXTERNAL_BRANDS):
                        if brand in normalized:
                            violations.append(
                                f"{relative}:{node.lineno}: external brand {brand!r}"
                            )
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        violations.append("missing pyproject.toml")
    else:
        try:
            metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            violations.append(f"pyproject.toml cannot be inspected: {exc}")
        else:
            project = metadata.get("project", {})
            if project.get("name") != "pycforge":
                violations.append("project name is not exactly pycforge")
            scripts = project.get("scripts", {})
            if not isinstance(scripts, dict):
                violations.append("project scripts are not a TOML table")
            else:
                allowed_scripts = {"pycforge", "pycforge-workspace"}
                unexpected = sorted(set(scripts) - allowed_scripts)
                if unexpected:
                    violations.append(
                        "out-of-scope project scripts: " + ", ".join(unexpected)
                    )
    return sorted(set(violations))


def audit_architecture_branding_product_boundary(root: Path) -> dict[str, object]:
    """Combine the cumulative architecture gate with Checkpoint E boundaries."""

    from pycforge.laboratory.audits import audit_architecture

    cumulative = audit_architecture(root)
    identities = current_contract_identities()
    identity_mismatches = {
        key: {"expected": expected, "actual": identities.get(key)}
        for key, expected in EXPECTED_CONTRACT_IDENTITIES.items()
        if identities.get(key) != expected
    }
    boundary_violations = scan_product_boundary(root)
    errors = [
        *(
            ["cumulative architecture audit failed"]
            if not cumulative.get("passed")
            else []
        ),
        *(
            ["frozen 0.14.3 identities changed"]
            if identity_mismatches
            else []
        ),
        *boundary_violations,
    ]
    return {
        "audit": "checkpoint-e-architecture-branding-product-boundary",
        "passed": not errors,
        "errors": errors,
        "identity_mismatches": identity_mismatches,
        "contract_identities": identities,
        "cumulative_architecture": cumulative,
        "boundary_violations": boundary_violations,
        "front_facing_brand": "PyCForge",
        "product_boundary": "deterministic Python-to-C source transpiler",
        "c_toolchain_invoked": False,
        "generated_c_compiled_or_executed": False,
    }
