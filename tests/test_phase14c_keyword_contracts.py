from __future__ import annotations

from dataclasses import fields
import hashlib
import unittest

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus, __version__
from pycforge.converter.analysis.planning import default_registry
from pycforge.converter.contracts.configuration import (
    DEFAULT_RENDERER,
    DEFAULT_RULE_SET,
    PHASE14B_RENDERER,
    PHASE14B_RULE_SET,
    supports_conditional_regions,
    supports_containers,
    supports_functions,
    supports_keyword_calls,
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
    PHASE14B_C_IR_SCHEMA,
    PHASE14B_CONVERSION_PLAN_SCHEMA,
    PHASE14B_CONVERSION_SUMMARY_SCHEMA,
    PHASE14B_DECISION_TRACE_SCHEMA,
    PHASE14B_GENERATED_C_SCHEMA,
    RESULT_SCHEMA_VERSION,
)
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.support_templates import default_helper_registry


KEYWORD_SOURCE = (
    "def choose(left: int, flag: bool) -> int:\n"
    "    return left\n\n"
    "def run(value: int, flag: bool) -> int:\n"
    "    return choose(flag=flag, left=value)\n"
)

POSITIONAL_SOURCE = (
    "def choose(left: int, flag: bool) -> int:\n"
    "    return left\n\n"
    "def run(value: int, flag: bool) -> int:\n"
    "    return choose(value, flag)\n"
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
            rule_set_version=PHASE14B_RULE_SET,
            renderer_version=PHASE14B_RENDERER,
        )
    return PythonToCConverter().convert(
        ConversionRequest.from_source(source, **options),
        observation=ObservationOptions("Full" if full else "None", False),
    )


def table(payload: dict, table_id: str) -> dict:
    return next(item for item in payload["fact_tables"] if item["table_id"] == table_id)


class Phase14CKeywordContractTests(unittest.TestCase):
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
        self.assertEqual(CONVERSION_PLAN_SCHEMA, "conversion-plan/0.14.3")
        self.assertEqual(C_IR_SCHEMA, "c-ir/0.14.3")
        self.assertEqual(GENERATED_C_SCHEMA, "generated-c/0.14.3")
        self.assertEqual(
            CONVERSION_SUMMARY_SCHEMA,
            "pycforge.conversion-summary/0.14.3",
        )
        self.assertEqual(DECISION_TRACE_SCHEMA, "pycforge.decision-trace/0.14.3")
        self.assertEqual(RESULT_SCHEMA_VERSION, "0.5")

    def test_phase14b_is_an_explicit_historical_profile(self) -> None:
        self.assertEqual(PHASE14B_RULE_SET, "phase14-conditional-regions-v0.14.1")
        self.assertEqual(PHASE14B_RENDERER, "c-renderer-v0.14.1")
        self.assertEqual(PHASE14B_CONVERSION_PLAN_SCHEMA, "conversion-plan/0.14.1")
        self.assertEqual(PHASE14B_C_IR_SCHEMA, "c-ir/0.14.1")
        self.assertEqual(PHASE14B_GENERATED_C_SCHEMA, "generated-c/0.14.1")
        self.assertEqual(
            PHASE14B_CONVERSION_SUMMARY_SCHEMA,
            "pycforge.conversion-summary/0.14.1",
        )
        self.assertEqual(
            PHASE14B_DECISION_TRACE_SCHEMA,
            "pycforge.decision-trace/0.14.1",
        )
        self.assertFalse(supports_keyword_calls(PHASE14B_RULE_SET))
        self.assertTrue(supports_keyword_calls(DEFAULT_RULE_SET))
        for capability in (
            supports_functions,
            supports_containers,
            supports_modules,
            supports_records,
            supports_numeric,
            supports_conditional_regions,
        ):
            self.assertTrue(capability(PHASE14B_RULE_SET), capability.__name__)
            self.assertTrue(capability(DEFAULT_RULE_SET), capability.__name__)

    def test_keyword_calls_add_no_request_policy_or_helper_contract(self) -> None:
        request_fields = {item.name for item in fields(ConversionRequest)}
        self.assertNotIn("keyword_call_policy_version", request_fields)
        self.assertNotIn("keyword_binding_policy_version", request_fields)
        registry = default_helper_registry()
        self.assertEqual(
            registry.fingerprint,
            "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98",
        )

    def test_exact_keyword_rule_and_fact_table_contract_are_published(self) -> None:
        manifest = default_registry(
            include_records=True,
            include_numeric=True,
            include_conditional_regions=True,
            include_keyword_calls=True,
        ).manifest
        keyword_rules = [
            item for item in manifest if item["rule_id"].startswith("phase14.keyword_call.")
        ]
        self.assertEqual(
            keyword_rules,
            [
                {
                    "rule_id": "phase14.keyword_call.exact_binding",
                    "rule_version": "0.14.2",
                    "node_kind": "Call",
                    "specificity": [80],
                }
            ],
        )

        result = convert(KEYWORD_SOURCE, full=True)
        self.assertEqual(result.status, ResultStatus.CONVERTED, result.diagnostics)
        payload = result.stage_artifact.payload
        facts = table(payload, "keyword-call-binding-facts")
        self.assertEqual(facts["schema_version"], KEYWORD_CALL_FACT_SCHEMA)
        self.assertEqual(facts["producer_stage"], "analysis.plan")
        self.assertEqual(facts["key_domain"], "keyword-call-node-id")
        self.assertEqual(facts["completeness"], "complete")
        self.assertEqual(len(facts["records"]), 1)
        fact = facts["records"][0]["value"]
        self.assertEqual(facts["records"][0]["key"], fact["call_node_id"])
        self.assertTrue(fact["supported"])
        self.assertTrue(fact["parameter_coverage_exact"])
        self.assertTrue(fact["arguments_evaluated_once"])
        self.assertEqual(fact["runtime_binding_failure"], "proved-absent")
        self.assertEqual(fact["allocation_model"], "none")
        self.assertEqual(fact["cleanup_model"], "none")

        plans = [
            item
            for item in payload["rule_plans"]
            if item["rule_id"] == "phase14.keyword_call.exact_binding"
        ]
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["rule_version"], "0.14.2")
        self.assertEqual(plans[0]["source_node_id"], fact["call_node_id"])
        self.assertEqual(plans[0]["helper_requirements"], [])
        self.assertEqual(
            plans[0]["resolved_obligations"],
            plans[0]["semantic_obligations"],
        )
        self.assertEqual(plans[0]["unresolved_obligations"], [])

    def test_explicit_phase14b_keyword_rejection_keeps_exact_envelope(self) -> None:
        result = convert(KEYWORD_SOURCE, full=True, historical=True)
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC2910"])
        self.assertEqual(
            [item.diagnostic_id for item in result.diagnostics],
            ["diag-33b10f68721e38b3e960"],
        )
        self.assertEqual(
            result.request_fingerprint.value,
            "c447d082bb1b12228b0e7fd80ed17c438063f0591ffee2b4b240031fc6d9187f",
        )
        self.assertEqual(result.stage_artifact.kind, "conversion_plan")
        self.assertEqual(result.stage_artifact.schema_version, "0.14.1")
        self.assertEqual(
            result.stage_artifact.artifact_fingerprint.value,
            "8daf5c369e7ea4e61521bebbae32efccd4ede450e375b09bc44f37ed9d0540c5",
        )
        self.assertEqual(
            result.stage_artifact.payload["schema_version"],
            PHASE14B_CONVERSION_PLAN_SCHEMA,
        )
        self.assertEqual(
            result.conversion_summary["schema_version"],
            PHASE14B_CONVERSION_SUMMARY_SCHEMA,
        )
        self.assertEqual(
            result.decision_trace["schema_version"],
            PHASE14B_DECISION_TRACE_SCHEMA,
        )
        self.assertNotIn(
            "keyword-call-binding-facts",
            {item["table_id"] for item in result.stage_artifact.payload["fact_tables"]},
        )
        self.assertIsNone(result.generated_c)
        self.assertIsNone(result.output_fingerprint)

    def test_active_no_keyword_output_is_byte_identical_to_phase14b(self) -> None:
        active = convert(POSITIONAL_SOURCE, full=True)
        historical = convert(POSITIONAL_SOURCE, full=True, historical=True)
        self.assertEqual(active.status, ResultStatus.CONVERTED, active.diagnostics)
        self.assertEqual(historical.status, ResultStatus.CONVERTED, historical.diagnostics)
        self.assertEqual(active.generated_c, historical.generated_c)
        self.assertEqual(active.output_fingerprint, historical.output_fingerprint)
        self.assertEqual(
            hashlib.sha256((active.generated_c or "").encode("utf-8")).hexdigest(),
            "36528709609e8b53a06fff4739dfa1ae5f1568d27daa0838a03315ecf701fb7e",
        )
        self.assertEqual(
            active.output_fingerprint.value,
            "a30db4341270842057a722c41d5a88e9599aff0a6992cf058aad642f7a724300",
        )
        self.assertEqual(active.stage_artifact.schema_version, "0.14.3")
        self.assertEqual(historical.stage_artifact.schema_version, "0.14.1")
        self.assertEqual(
            table(active.stage_artifact.payload, "keyword-call-binding-facts")["records"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
