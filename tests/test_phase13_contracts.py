from __future__ import annotations

import unittest

from pycforge import ConversionRequest, PythonToCConverter, __version__
from pycforge.converter.contracts.configuration import (
    DEFAULT_MODULE_POLICY,
    DEFAULT_NUMERIC_POLICY,
    DEFAULT_RECORD_POLICY,
    DEFAULT_RENDERER,
    DEFAULT_RULE_SET,
    PHASE12_MODULE_POLICY,
    PHASE12_RENDERER,
    PHASE12_RULE_SET,
    PHASE13_RENDERER,
    PHASE13_RULE_SET,
    supports_containers,
    supports_functions,
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
    NUMERIC_FACT_SCHEMA,
    PHASE12_C_IR_SCHEMA,
    PHASE12_CONVERSION_PLAN_SCHEMA,
    PHASE12_CONVERSION_SUMMARY_SCHEMA,
    PHASE12_DECISION_TRACE_SCHEMA,
    PHASE12_GENERATED_C_SCHEMA,
    RECORD_FACT_SCHEMA,
    RESULT_SCHEMA_VERSION,
)
from pycforge.converter.core.canonicalization import canonicalize
from pycforge.converter.core.enums import ResultStatus
from pycforge.converter.core.result import ConversionResult
from pycforge.converter.core.serialization import result_to_text


class Phase13ContractTests(unittest.TestCase):
    def test_active_phase14_identities_are_explicit_and_record_contracts_stay_frozen(self) -> None:
        request = ConversionRequest.from_source("def run() -> int:\n    return 1\n")

        self.assertEqual(__version__, "0.15.2")
        self.assertEqual(
            request.rule_set_version,
            "phase14-required-keyword-only-calls-v0.14.3",
        )
        self.assertEqual(request.renderer_version, "c-renderer-v0.14.3")
        self.assertEqual(
            request.module_policy_version,
            "phase13-explicit-record-modules-v0.13",
        )
        self.assertEqual(
            request.record_policy_version,
            "phase13-immutable-automatic-records-v0.13",
        )
        self.assertEqual(
            request.numeric_policy_version,
            "phase14-proved-floor-arithmetic-v0.14",
        )
        self.assertEqual(request.numeric_policy_version, DEFAULT_NUMERIC_POLICY)
        self.assertEqual(CONVERSION_PLAN_SCHEMA, "conversion-plan/0.14.3")
        self.assertEqual(C_IR_SCHEMA, "c-ir/0.14.3")
        self.assertEqual(GENERATED_C_SCHEMA, "generated-c/0.14.3")
        self.assertEqual(CONVERSION_SUMMARY_SCHEMA, "pycforge.conversion-summary/0.14.3")
        self.assertEqual(DECISION_TRACE_SCHEMA, "pycforge.decision-trace/0.14.3")
        self.assertEqual(RECORD_FACT_SCHEMA, "fact-table/0.13")
        self.assertEqual(NUMERIC_FACT_SCHEMA, "fact-table/0.14")

    def test_phase14_capability_predicates_are_additive(self) -> None:
        for rule_set in (PHASE12_RULE_SET, PHASE13_RULE_SET, DEFAULT_RULE_SET):
            self.assertTrue(supports_functions(rule_set))
            self.assertTrue(supports_containers(rule_set))
            self.assertTrue(supports_modules(rule_set))
        self.assertFalse(supports_records(PHASE12_RULE_SET))
        self.assertTrue(supports_records(PHASE13_RULE_SET))
        self.assertTrue(supports_records(DEFAULT_RULE_SET))
        self.assertFalse(supports_numeric(PHASE13_RULE_SET))
        self.assertTrue(supports_numeric(DEFAULT_RULE_SET))

        self.assertEqual(PHASE13_RULE_SET, "phase13-static-records-v0.13")
        self.assertEqual(PHASE13_RENDERER, "c-renderer-v0.13")

    def test_phase12_identities_remain_read_compatible_without_relabeling(self) -> None:
        request = ConversionRequest.from_source(
            "def run() -> int:\n    return 1\n",
            rule_set_version=PHASE12_RULE_SET,
            renderer_version=PHASE12_RENDERER,
            module_policy_version=PHASE12_MODULE_POLICY,
        )
        canonical, diagnostics = canonicalize(request)

        self.assertEqual(diagnostics, ())
        self.assertIsNotNone(canonical)
        assert canonical is not None
        self.assertEqual(canonical.request.rule_set_version, PHASE12_RULE_SET)
        self.assertEqual(canonical.request.renderer_version, PHASE12_RENDERER)
        self.assertEqual(canonical.request.module_policy_version, PHASE12_MODULE_POLICY)
        self.assertEqual(canonical.request.record_policy_version, DEFAULT_RECORD_POLICY)
        self.assertNotIn("record_policy_version", canonical.semantic_dict())

        self.assertEqual(PHASE12_CONVERSION_PLAN_SCHEMA, "conversion-plan/0.12")
        self.assertEqual(PHASE12_C_IR_SCHEMA, "c-ir/0.12")
        self.assertEqual(PHASE12_GENERATED_C_SCHEMA, "generated-c/0.12")
        self.assertEqual(
            PHASE12_CONVERSION_SUMMARY_SCHEMA,
            "pycforge.conversion-summary/0.12",
        )
        self.assertEqual(
            PHASE12_DECISION_TRACE_SCHEMA,
            "pycforge.decision-trace/0.12",
        )

    def test_unknown_record_policy_rejects_with_stable_request_diagnostic(self) -> None:
        canonical, diagnostics = canonicalize(
            ConversionRequest.from_source(
                "def run() -> int:\n    return 1\n",
                record_policy_version="unknown-record-policy",
            )
        )

        self.assertIsNone(canonical)
        self.assertEqual([item.code for item in diagnostics], ["PYC1017"])

    def test_record_policy_participates_in_canonical_request_identity(self) -> None:
        canonical, diagnostics = canonicalize(
            ConversionRequest.from_source("def run() -> int:\n    return 1\n")
        )

        self.assertEqual(diagnostics, ())
        self.assertIsNotNone(canonical)
        assert canonical is not None
        self.assertEqual(canonical.request.module_policy_version, DEFAULT_MODULE_POLICY)
        self.assertEqual(canonical.request.renderer_version, DEFAULT_RENDERER)
        self.assertEqual(canonical.request.rule_set_version, DEFAULT_RULE_SET)
        self.assertIn("record_policy_version", canonical.semantic_dict())

    def test_phase13_does_not_repurpose_phase12_module_fact_shapes(self) -> None:
        source = "def run(value: int) -> int:\n    return value + 1\n"
        converter = PythonToCConverter()
        active = converter.convert(ConversionRequest.from_source(source))
        historical = converter.convert(
            ConversionRequest.from_source(
                source,
                rule_set_version=PHASE12_RULE_SET,
                renderer_version=PHASE12_RENDERER,
                module_policy_version=PHASE12_MODULE_POLICY,
            )
        )
        self.assertEqual(active.status, ResultStatus.CONVERTED)
        self.assertEqual(historical.status, ResultStatus.CONVERTED)
        assert active.stage_artifact is not None
        assert historical.stage_artifact is not None
        table_ids = {
            "module-identity-facts",
            "module-import-facts",
            "module-function-facts",
            "module-initialization-facts",
            "module-namespace-facts",
            "module-source-facts",
        }
        active_tables = [
            item
            for item in active.stage_artifact.payload["fact_tables"]
            if item["table_id"] in table_ids
        ]
        historical_tables = [
            item
            for item in historical.stage_artifact.payload["fact_tables"]
            if item["table_id"] in table_ids
        ]
        self.assertEqual(
            [
                {key: value for key, value in table.items() if key != "invalidation_dependencies"}
                for table in active_tables
            ],
            [
                {key: value for key, value in table.items() if key != "invalidation_dependencies"}
                for table in historical_tables
            ],
        )

    def test_result_envelope_remains_05(self) -> None:
        # Phase 13 changes independently versioned nested artifacts, not the
        # stable outer ConversionResult serialization key set.
        self.assertEqual(RESULT_SCHEMA_VERSION, "0.5")

    def test_text_result_reports_record_summary(self) -> None:
        result = ConversionResult(
            status=ResultStatus.CONVERTED,
            generated_c="",
            diagnostics=(),
            request_fingerprint=None,
            resource_fingerprint=None,
            output_fingerprint=None,
            last_completed_stage="lowering",
            stage_order=("lowering",),
            conversion_summary={"records": ({"class_name": "Point"},)},
        )

        self.assertIn("records: 1\n", result_to_text(result))


if __name__ == "__main__":
    unittest.main()
