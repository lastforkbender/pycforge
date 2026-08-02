from __future__ import annotations

from dataclasses import fields
import unittest

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus, __version__
from pycforge.converter.analysis.planning import default_registry
from pycforge.converter.conditional_regions import (
    CONDITIONAL_REGION_KEY_DOMAIN,
    CONDITIONAL_REGION_LOWERING_SHAPE,
    CONDITIONAL_REGION_OBLIGATIONS,
    CONDITIONAL_REGION_TABLE_ID,
)
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
    PHASE14A_NUMERIC_POLICY,
    PHASE14A_RENDERER,
    PHASE14A_RULE_SET,
    supports_conditional_regions,
    supports_containers,
    supports_functions,
    supports_modules,
    supports_numeric,
    supports_records,
)
from pycforge.converter.contracts.versions import (
    C_IR_SCHEMA,
    CONDITIONAL_FACT_SCHEMA,
    CONVERSION_PLAN_SCHEMA,
    CONVERSION_SUMMARY_SCHEMA,
    DECISION_TRACE_SCHEMA,
    GENERATED_C_SCHEMA,
    NUMERIC_FACT_SCHEMA,
    PHASE14A_C_IR_SCHEMA,
    PHASE14A_CONVERSION_PLAN_SCHEMA,
    PHASE14A_CONVERSION_SUMMARY_SCHEMA,
    PHASE14A_DECISION_TRACE_SCHEMA,
    PHASE14A_GENERATED_C_SCHEMA,
    PYTHON_IR_BUNDLE_SCHEMA,
    RESULT_SCHEMA_VERSION,
    SOURCE_BUNDLE_SCHEMA,
)
from pycforge.converter.core.canonicalization import canonicalize
from pycforge.converter.support_templates import (
    HELPER_REGISTRY_VERSION,
    default_helper_registry,
)


BOOLEAN_REGION_SOURCE = (
    "def flag(value: bool) -> bool:\n"
    "    return value\n\n"
    "def run(a: bool, b: bool) -> bool:\n"
    "    return a and flag(b)\n"
)

COMPARISON_REGION_SOURCE = (
    "def value(item: int) -> int:\n"
    "    return item\n\n"
    "def run(a: int, b: int, c: int) -> bool:\n"
    "    return a < b < value(c)\n"
)


class Phase14BConditionalContractTests(unittest.TestCase):
    def test_active_identities_are_exact_and_additive(self) -> None:
        request = ConversionRequest.from_source("def run() -> int:\n    return 1\n")

        self.assertEqual(__version__, "0.15.2")
        self.assertEqual(
            DEFAULT_RULE_SET,
            "phase14-required-keyword-only-calls-v0.14.3",
        )
        self.assertEqual(DEFAULT_RENDERER, "c-renderer-v0.14.3")
        self.assertEqual(request.rule_set_version, DEFAULT_RULE_SET)
        self.assertEqual(request.renderer_version, DEFAULT_RENDERER)
        self.assertEqual(CONDITIONAL_FACT_SCHEMA, "fact-table/0.14.1")
        self.assertEqual(CONVERSION_PLAN_SCHEMA, "conversion-plan/0.14.3")
        self.assertEqual(C_IR_SCHEMA, "c-ir/0.14.3")
        self.assertEqual(GENERATED_C_SCHEMA, "generated-c/0.14.3")
        self.assertEqual(
            CONVERSION_SUMMARY_SCHEMA,
            "pycforge.conversion-summary/0.14.3",
        )
        self.assertEqual(DECISION_TRACE_SCHEMA, "pycforge.decision-trace/0.14.3")
        self.assertEqual(RESULT_SCHEMA_VERSION, "0.5")
        self.assertEqual(SOURCE_BUNDLE_SCHEMA, "source-bundle/0.2")
        self.assertEqual(PYTHON_IR_BUNDLE_SCHEMA, "python-ir/0.4")

    def test_no_new_policy_field_and_all_predecessor_policies_are_frozen(self) -> None:
        request_fields = {item.name for item in fields(ConversionRequest)}
        self.assertNotIn("conditional_policy_version", request_fields)
        self.assertNotIn("conditional_region_policy_version", request_fields)
        self.assertEqual(DEFAULT_TARGET_CONTRACT, "c11-portable-fixed-v1")
        self.assertEqual(DEFAULT_SEMANTIC_POLICY, "strict-source-v1")
        self.assertEqual(DEFAULT_HELPER_POLICY, "phase10-support-templates-v0.10")
        self.assertEqual(DEFAULT_CONTAINER_POLICY, "phase11-fixed-local-containers-v0.11")
        self.assertEqual(DEFAULT_MODULE_POLICY, "phase13-explicit-record-modules-v0.13")
        self.assertEqual(DEFAULT_RECORD_POLICY, "phase13-immutable-automatic-records-v0.13")
        self.assertEqual(DEFAULT_NUMERIC_POLICY, PHASE14A_NUMERIC_POLICY)
        self.assertEqual(DEFAULT_NUMERIC_POLICY, "phase14-proved-floor-arithmetic-v0.14")
        self.assertEqual(NUMERIC_FACT_SCHEMA, "fact-table/0.14")

        registry = default_helper_registry()
        self.assertEqual(HELPER_REGISTRY_VERSION, "phase10-support-templates-v0.10")
        self.assertEqual(
            registry.fingerprint,
            "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98",
        )

    def test_conditional_capability_is_active_only_and_cumulative(self) -> None:
        self.assertTrue(supports_conditional_regions(DEFAULT_RULE_SET))
        self.assertFalse(supports_conditional_regions(PHASE14A_RULE_SET))
        for capability in (
            supports_functions,
            supports_containers,
            supports_modules,
            supports_records,
            supports_numeric,
        ):
            self.assertTrue(capability(DEFAULT_RULE_SET), capability.__name__)
            self.assertTrue(capability(PHASE14A_RULE_SET), capability.__name__)

    def test_fact_and_rule_family_contracts_are_closed(self) -> None:
        self.assertEqual(CONDITIONAL_REGION_TABLE_ID, "conditional-region-facts")
        self.assertEqual(CONDITIONAL_REGION_KEY_DOMAIN, "conditional-region-node-id")
        self.assertEqual(
            CONDITIONAL_REGION_LOWERING_SHAPE,
            "flat-guarded-assignment-v1",
        )
        self.assertEqual(len(CONDITIONAL_REGION_OBLIGATIONS), 14)
        self.assertIn("short-circuit-order-preserved", CONDITIONAL_REGION_OBLIGATIONS)
        self.assertIn("structured-c-ir-only", CONDITIONAL_REGION_OBLIGATIONS)
        self.assertIn("allocation-and-cleanup-absent", CONDITIONAL_REGION_OBLIGATIONS)

        manifest = default_registry(
            include_records=True,
            include_numeric=True,
            include_conditional_regions=True,
        ).manifest
        conditional = [
            item for item in manifest if item["rule_id"].startswith("phase14.conditional.")
        ]
        self.assertEqual(
            conditional,
            [
                {
                    "rule_id": "phase14.conditional.boolean_region",
                    "rule_version": "0.14.1",
                    "node_kind": "BoolOp",
                    "specificity": [70],
                },
                {
                    "rule_id": "phase14.conditional.comparison_region",
                    "rule_version": "0.14.1",
                    "node_kind": "Compare",
                    "specificity": [70],
                },
            ],
        )

    def test_explicit_phase14a_configuration_keeps_exact_historical_shape(self) -> None:
        source = "def run() -> int:\n    return 1\n"
        request = ConversionRequest.from_source(
            source,
            rule_set_version=PHASE14A_RULE_SET,
            renderer_version=PHASE14A_RENDERER,
        )
        canonical, diagnostics = canonicalize(request)
        self.assertEqual(diagnostics, ())
        self.assertIsNotNone(canonical)
        assert canonical is not None

        self.assertEqual(PHASE14A_RULE_SET, "phase14-bounded-numeric-v0.14")
        self.assertEqual(PHASE14A_RENDERER, "c-renderer-v0.14")
        self.assertEqual(PHASE14A_CONVERSION_PLAN_SCHEMA, "conversion-plan/0.14")
        self.assertEqual(PHASE14A_C_IR_SCHEMA, "c-ir/0.14")
        self.assertEqual(PHASE14A_GENERATED_C_SCHEMA, "generated-c/0.14")
        self.assertEqual(
            PHASE14A_CONVERSION_SUMMARY_SCHEMA,
            "pycforge.conversion-summary/0.14",
        )
        self.assertEqual(
            PHASE14A_DECISION_TRACE_SCHEMA,
            "pycforge.decision-trace/0.14",
        )
        self.assertEqual(
            canonical.request_fingerprint.value,
            "f3bdc058becb0854692235850037797872afc00a18a132c88b7bb2950a2d4360",
        )
        semantic = canonical.semantic_dict()
        self.assertEqual(semantic["rule_set_version"], PHASE14A_RULE_SET)
        self.assertEqual(semantic["renderer_version"], PHASE14A_RENDERER)
        self.assertEqual(semantic["numeric_policy_version"], PHASE14A_NUMERIC_POLICY)
        self.assertFalse(any("conditional" in key for key in semantic))

    def test_historical_phase14a_keeps_exact_placement_rejections(self) -> None:
        cases = (
            (BOOLEAN_REGION_SOURCE, "PYC2950"),
            (COMPARISON_REGION_SOURCE, "PYC2951"),
        )
        for source, code in cases:
            with self.subTest(code=code):
                result = PythonToCConverter().convert(
                    ConversionRequest.from_source(
                        source,
                        rule_set_version=PHASE14A_RULE_SET,
                        renderer_version=PHASE14A_RENDERER,
                    )
                )
                self.assertEqual(result.status, ResultStatus.REJECTED)
                self.assertEqual([item.code for item in result.diagnostics], [code])
                self.assertIsNone(result.generated_c)
                self.assertIsNone(result.output_fingerprint)
                self.assertEqual(result.stage_artifact.kind, "conversion_plan")
                self.assertEqual(result.stage_artifact.schema_version, "0.14")
                self.assertNotIn(
                    CONDITIONAL_REGION_TABLE_ID,
                    {
                        item["table_id"]
                        for item in result.stage_artifact.payload["fact_tables"]
                    },
                )


if __name__ == "__main__":
    unittest.main()
