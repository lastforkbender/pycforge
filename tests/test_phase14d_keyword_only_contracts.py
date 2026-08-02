from __future__ import annotations

from dataclasses import fields
import hashlib
from pathlib import Path
import unittest

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus, __version__
from pycforge.converter.analysis.planning import default_registry
from pycforge.converter.contracts.configuration import (
    DEFAULT_RENDERER,
    DEFAULT_RULE_SET,
    PHASE14C_RENDERER,
    PHASE14C_RULE_SET,
    supports_conditional_regions,
    supports_containers,
    supports_functions,
    supports_keyword_calls,
    supports_keyword_only_calls,
    supports_modules,
    supports_numeric,
    supports_records,
)
from pycforge.converter.contracts.versions import (
    C_IR_SCHEMA,
    CONVERSION_PLAN_SCHEMA,
    CONVERSION_SUMMARY_SCHEMA,
    DECISION_TRACE_SCHEMA,
    GENERATED_C_SCHEMA,
    KEYWORD_CALL_FACT_SCHEMA,
    KEYWORD_ONLY_CALL_FACT_SCHEMA,
    PHASE14C_C_IR_SCHEMA,
    PHASE14C_CONVERSION_PLAN_SCHEMA,
    PHASE14C_CONVERSION_SUMMARY_SCHEMA,
    PHASE14C_DECISION_TRACE_SCHEMA,
    PHASE14C_GENERATED_C_SCHEMA,
    RESULT_SCHEMA_VERSION,
)
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.keyword_only_calls import (
    KEYWORD_ONLY_CALL_LOWERING_SHAPE,
    KEYWORD_ONLY_CALL_RULE_ID,
    KEYWORD_ONLY_CALL_TABLE_ID,
)
from pycforge.converter.support_templates import default_helper_registry
from pycforge.laboratory.audits import audit_transition


ROOT = Path(__file__).resolve().parents[1]


KEYWORD_ONLY_SOURCE = (
    "def choose(left: int, *, flag: bool, ratio: float) -> int:\n"
    "    return left\n\n"
    "def run(value: int, flag: bool, ratio: float) -> int:\n"
    "    return choose(ratio=ratio, left=value, flag=flag)\n"
)

HISTORICAL_KEYWORD_ONLY_SOURCE = (
    "def choose(left: int, *, flag: bool, ratio: float) -> int:\n"
    "    return left\n\n"
    "def run(x: int, y: bool, z: float) -> int:\n"
    "    return choose(ratio=z, left=x, flag=y)\n"
)

PHASE14C_KEYWORD_SOURCE = (
    "def choose(left: int, flag: bool) -> int:\n"
    "    return left\n\n"
    "def run(value: int, flag: bool) -> int:\n"
    "    return choose(flag=flag, left=value)\n"
)


def convert(
    source: str,
    *,
    full: bool = False,
    historical: bool = False,
):
    options: dict[str, object] = {}
    if historical:
        options.update(
            rule_set_version=PHASE14C_RULE_SET,
            renderer_version=PHASE14C_RENDERER,
        )
    return PythonToCConverter().convert(
        ConversionRequest.from_source(source, **options),
        observation=ObservationOptions("Full" if full else "None", False),
    )


def table(payload: dict, table_id: str) -> dict:
    return next(item for item in payload["fact_tables"] if item["table_id"] == table_id)


class Phase14DKeywordOnlyContractTests(unittest.TestCase):
    def test_active_identities_are_exact_and_cumulative(self) -> None:
        request = ConversionRequest.from_source("def run() -> int:\n    return 1\n")

        self.assertEqual(__version__, "0.15.2")
        self.assertEqual(
            DEFAULT_RULE_SET,
            "phase14-required-keyword-only-calls-v0.14.3",
        )
        self.assertEqual(DEFAULT_RENDERER, "c-renderer-v0.14.3")
        self.assertEqual(request.rule_set_version, DEFAULT_RULE_SET)
        self.assertEqual(request.renderer_version, DEFAULT_RENDERER)
        self.assertEqual(KEYWORD_CALL_FACT_SCHEMA, "fact-table/0.14.2")
        self.assertEqual(KEYWORD_ONLY_CALL_FACT_SCHEMA, "fact-table/0.14.3")
        self.assertEqual(CONVERSION_PLAN_SCHEMA, "conversion-plan/0.14.3")
        self.assertEqual(C_IR_SCHEMA, "c-ir/0.14.3")
        self.assertEqual(GENERATED_C_SCHEMA, "generated-c/0.14.3")
        self.assertEqual(
            CONVERSION_SUMMARY_SCHEMA,
            "pycforge.conversion-summary/0.14.3",
        )
        self.assertEqual(DECISION_TRACE_SCHEMA, "pycforge.decision-trace/0.14.3")
        self.assertEqual(RESULT_SCHEMA_VERSION, "0.5")

    def test_phase14c_is_an_exact_historical_profile(self) -> None:
        self.assertEqual(PHASE14C_RULE_SET, "phase14-direct-keyword-calls-v0.14.2")
        self.assertEqual(PHASE14C_RENDERER, "c-renderer-v0.14.2")
        self.assertEqual(PHASE14C_CONVERSION_PLAN_SCHEMA, "conversion-plan/0.14.2")
        self.assertEqual(PHASE14C_C_IR_SCHEMA, "c-ir/0.14.2")
        self.assertEqual(PHASE14C_GENERATED_C_SCHEMA, "generated-c/0.14.2")
        self.assertEqual(
            PHASE14C_CONVERSION_SUMMARY_SCHEMA,
            "pycforge.conversion-summary/0.14.2",
        )
        self.assertEqual(
            PHASE14C_DECISION_TRACE_SCHEMA,
            "pycforge.decision-trace/0.14.2",
        )
        self.assertTrue(supports_keyword_calls(PHASE14C_RULE_SET))
        self.assertFalse(supports_keyword_only_calls(PHASE14C_RULE_SET))
        self.assertTrue(supports_keyword_calls(DEFAULT_RULE_SET))
        self.assertTrue(supports_keyword_only_calls(DEFAULT_RULE_SET))
        for capability in (
            supports_functions,
            supports_containers,
            supports_modules,
            supports_records,
            supports_numeric,
            supports_conditional_regions,
        ):
            self.assertTrue(capability(PHASE14C_RULE_SET), capability.__name__)
            self.assertTrue(capability(DEFAULT_RULE_SET), capability.__name__)

    def test_rule_set_and_renderer_profiles_cannot_be_cross_paired(self) -> None:
        source = "def run() -> int:\n    return 1\n"
        for rule_set, renderer in (
            (DEFAULT_RULE_SET, PHASE14C_RENDERER),
            (PHASE14C_RULE_SET, DEFAULT_RENDERER),
        ):
            with self.subTest(rule_set=rule_set, renderer=renderer):
                result = PythonToCConverter().convert(
                    ConversionRequest.from_source(
                        source,
                        rule_set_version=rule_set,
                        renderer_version=renderer,
                    )
                )
                self.assertEqual(result.status, ResultStatus.REJECTED)
                self.assertEqual(
                    [item.code for item in result.diagnostics],
                    ["PYC1011"],
                )
                self.assertIsNone(result.stage_artifact)
                self.assertIsNone(result.generated_c)

    def test_phase14d_transition_audit_requires_full_promoted_packet(self) -> None:
        report = audit_transition(ROOT, "phase_14d")
        self.assertTrue(report["passed"], report)
        self.assertEqual(
            report["required_files"],
            [
                "baseline_fingerprint.json",
                "breadth_and_change_budgets.md",
                "entry_criteria.md",
                "gate_evidence.md",
                "manifest.json",
                "opening_evidence.md",
                "release_fingerprint.json",
                "required_keyword_only_calls_decision.md",
                "rollback_conditions.md",
            ],
        )
        self.assertEqual(report["minimum_tests"], 528)
        self.assertGreaterEqual(report["required_tests"], 528)

    def test_keyword_only_calls_add_no_request_policy_or_helper(self) -> None:
        request_fields = {item.name for item in fields(ConversionRequest)}
        self.assertNotIn("keyword_only_call_policy_version", request_fields)
        self.assertNotIn("argument_binding_policy_version", request_fields)
        self.assertEqual(
            default_helper_registry().fingerprint,
            "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98",
        )

    def test_exact_rule_and_fact_contract_are_published(self) -> None:
        manifest = default_registry(
            include_records=True,
            include_numeric=True,
            include_conditional_regions=True,
            include_keyword_calls=True,
            include_keyword_only_calls=True,
        ).manifest
        feature_rules = [
            item
            for item in manifest
            if item["rule_id"].startswith("phase14.keyword_only_call.")
        ]
        self.assertEqual(
            feature_rules,
            [
                {
                    "rule_id": "phase14.keyword_only_call.exact_binding",
                    "rule_version": "0.14.3",
                    "node_kind": "Call",
                    "specificity": [90],
                }
            ],
        )

        result = convert(KEYWORD_ONLY_SOURCE, full=True)
        self.assertEqual(result.status, ResultStatus.CONVERTED, result.diagnostics)
        facts = table(result.stage_artifact.payload, KEYWORD_ONLY_CALL_TABLE_ID)
        self.assertEqual(facts["schema_version"], KEYWORD_ONLY_CALL_FACT_SCHEMA)
        self.assertEqual(facts["producer_stage"], "analysis.plan")
        self.assertEqual(facts["key_domain"], "keyword-only-call-node-id")
        self.assertEqual(facts["completeness"], "complete")
        self.assertEqual(len(facts["records"]), 1)
        record = facts["records"][0]
        fact = record["value"]
        self.assertEqual(record["key"], fact["call_node_id"])
        self.assertTrue(fact["supported"])
        self.assertTrue(fact["parameter_coverage_exact"])
        self.assertTrue(fact["keyword_only_coverage_exact"])
        self.assertTrue(fact["arguments_evaluated_once"])
        self.assertEqual(fact["runtime_binding_failure"], "proved-absent")
        self.assertEqual(fact["allocation_model"], "none")
        self.assertEqual(fact["cleanup_model"], "none")
        self.assertEqual(fact["lowering_shape"], KEYWORD_ONLY_CALL_LOWERING_SHAPE)
        self.assertEqual(
            KEYWORD_ONLY_CALL_LOWERING_SHAPE,
            "source-order-actual-temporaries-formal-order-references-v1",
        )

        plans = [
            item
            for item in result.stage_artifact.payload["rule_plans"]
            if item["rule_id"] == KEYWORD_ONLY_CALL_RULE_ID
        ]
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["rule_version"], "0.14.3")
        self.assertEqual(plans[0]["source_node_id"], fact["call_node_id"])
        self.assertEqual(plans[0]["helper_requirements"], [])
        self.assertEqual(
            plans[0]["resolved_obligations"],
            plans[0]["semantic_obligations"],
        )
        self.assertEqual(plans[0]["unresolved_obligations"], [])

    def test_explicit_phase14c_keeps_exact_keyword_only_rejection(self) -> None:
        result = convert(
            HISTORICAL_KEYWORD_ONLY_SOURCE,
            full=True,
            historical=True,
        )
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC2911"])
        self.assertEqual(
            [item.diagnostic_id for item in result.diagnostics],
            ["diag-8405a8ed7e520a5f8a35"],
        )
        self.assertEqual(
            result.request_fingerprint.value,
            "f921ebf5ba65d9341678c2706cdcb9f7f8a10ee95511a0832f78ba3ce47a3db0",
        )
        self.assertEqual(result.stage_artifact.kind, "conversion_plan")
        self.assertEqual(result.stage_artifact.schema_version, "0.14.2")
        self.assertEqual(
            result.stage_artifact.artifact_fingerprint.value,
            "403374c475857731cbd3d1431b5299e9cb34768134b42c2596fe2571b32f3841",
        )
        self.assertEqual(
            result.stage_artifact.payload["schema_version"],
            PHASE14C_CONVERSION_PLAN_SCHEMA,
        )
        self.assertEqual(
            result.conversion_summary["schema_version"],
            PHASE14C_CONVERSION_SUMMARY_SCHEMA,
        )
        self.assertEqual(
            result.decision_trace["schema_version"],
            PHASE14C_DECISION_TRACE_SCHEMA,
        )
        self.assertNotIn(
            KEYWORD_ONLY_CALL_TABLE_ID,
            {item["table_id"] for item in result.stage_artifact.payload["fact_tables"]},
        )
        self.assertIsNone(result.generated_c)
        self.assertIsNone(result.output_fingerprint)

    def test_active_phase14c_source_preserves_exact_generated_bytes(self) -> None:
        active = convert(PHASE14C_KEYWORD_SOURCE, full=True)
        historical = convert(PHASE14C_KEYWORD_SOURCE, full=True, historical=True)
        self.assertEqual(active.status, ResultStatus.CONVERTED, active.diagnostics)
        self.assertEqual(historical.status, ResultStatus.CONVERTED, historical.diagnostics)
        self.assertEqual(active.generated_c, historical.generated_c)
        self.assertEqual(active.output_fingerprint, historical.output_fingerprint)
        self.assertEqual(
            hashlib.sha256((active.generated_c or "").encode("utf-8")).hexdigest(),
            "1517720ffbc3559c02ff82823cffd172585c2a31e9944f14ee25fd4189dccf35",
        )
        self.assertEqual(
            active.output_fingerprint.value,
            "3c2508b5a9523f6f0d286d73be7583f7d8dbe340a4ff4dcc6017f7cc09c788f9",
        )
        self.assertEqual(active.stage_artifact.schema_version, "0.14.3")
        self.assertEqual(historical.stage_artifact.schema_version, "0.14.2")
        self.assertEqual(
            table(
                active.stage_artifact.payload,
                KEYWORD_ONLY_CALL_TABLE_ID,
            )["records"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
