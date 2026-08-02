from __future__ import annotations

import unittest

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus, __version__
from pycforge.converter.contracts.configuration import (
    DEFAULT_NUMERIC_POLICY,
    DEFAULT_RENDERER,
    DEFAULT_RULE_SET,
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
    PHASE13_C_IR_SCHEMA,
    PHASE13_CONVERSION_PLAN_SCHEMA,
    PHASE13_CONVERSION_SUMMARY_SCHEMA,
    PHASE13_DECISION_TRACE_SCHEMA,
    PHASE13_GENERATED_C_SCHEMA,
    RESULT_SCHEMA_VERSION,
)
from pycforge.converter.core.canonicalization import canonicalize
from pycforge.converter.support_templates import (
    FLOOR_DIV_REFERENCE,
    FLOOR_MOD_REFERENCE,
    HELPER_REGISTRY_VERSION,
    default_helper_registry,
)


class Phase14NumericContractTests(unittest.TestCase):
    def test_active_phase14_identities_are_explicit_and_additive(self) -> None:
        request = ConversionRequest.from_source("def run() -> int:\n    return 1\n")

        self.assertEqual(__version__, "0.15.2")
        self.assertEqual(
            request.rule_set_version,
            "phase14-required-keyword-only-calls-v0.14.3",
        )
        self.assertEqual(request.renderer_version, "c-renderer-v0.14.3")
        self.assertEqual(
            request.numeric_policy_version,
            "phase14-proved-floor-arithmetic-v0.14",
        )
        self.assertEqual(request.rule_set_version, DEFAULT_RULE_SET)
        self.assertEqual(request.renderer_version, DEFAULT_RENDERER)
        self.assertEqual(request.numeric_policy_version, DEFAULT_NUMERIC_POLICY)
        self.assertEqual(CONVERSION_PLAN_SCHEMA, "conversion-plan/0.14.3")
        self.assertEqual(C_IR_SCHEMA, "c-ir/0.14.3")
        self.assertEqual(GENERATED_C_SCHEMA, "generated-c/0.14.3")
        self.assertEqual(CONVERSION_SUMMARY_SCHEMA, "pycforge.conversion-summary/0.14.3")
        self.assertEqual(DECISION_TRACE_SCHEMA, "pycforge.decision-trace/0.14.3")
        self.assertEqual(NUMERIC_FACT_SCHEMA, "fact-table/0.14")
        self.assertEqual(RESULT_SCHEMA_VERSION, "0.5")

        self.assertTrue(supports_functions(DEFAULT_RULE_SET))
        self.assertTrue(supports_containers(DEFAULT_RULE_SET))
        self.assertTrue(supports_modules(DEFAULT_RULE_SET))
        self.assertTrue(supports_records(DEFAULT_RULE_SET))
        self.assertTrue(supports_numeric(DEFAULT_RULE_SET))
        self.assertTrue(supports_functions(PHASE13_RULE_SET))
        self.assertTrue(supports_containers(PHASE13_RULE_SET))
        self.assertTrue(supports_modules(PHASE13_RULE_SET))
        self.assertTrue(supports_records(PHASE13_RULE_SET))
        self.assertFalse(supports_numeric(PHASE13_RULE_SET))

    def test_phase13_contract_identities_remain_named_without_relabeling(self) -> None:
        self.assertEqual(PHASE13_RULE_SET, "phase13-static-records-v0.13")
        self.assertEqual(PHASE13_RENDERER, "c-renderer-v0.13")
        self.assertEqual(PHASE13_CONVERSION_PLAN_SCHEMA, "conversion-plan/0.13")
        self.assertEqual(PHASE13_C_IR_SCHEMA, "c-ir/0.13")
        self.assertEqual(PHASE13_GENERATED_C_SCHEMA, "generated-c/0.13")
        self.assertEqual(
            PHASE13_CONVERSION_SUMMARY_SCHEMA,
            "pycforge.conversion-summary/0.13",
        )
        self.assertEqual(
            PHASE13_DECISION_TRACE_SCHEMA,
            "pycforge.decision-trace/0.13",
        )

        request = ConversionRequest.from_source(
            "def run() -> int:\n    return 1\n",
            rule_set_version=PHASE13_RULE_SET,
            renderer_version=PHASE13_RENDERER,
        )
        canonical, diagnostics = canonicalize(request)
        self.assertEqual(diagnostics, ())
        self.assertIsNotNone(canonical)
        assert canonical is not None
        self.assertEqual(canonical.request.rule_set_version, PHASE13_RULE_SET)
        self.assertEqual(canonical.request.renderer_version, PHASE13_RENDERER)
        self.assertNotIn("numeric_policy_version", canonical.semantic_dict())

    def test_numeric_policy_is_an_active_request_identity(self) -> None:
        request = ConversionRequest.from_source("def run() -> int:\n    return 1\n")
        canonical, diagnostics = canonicalize(request)
        self.assertEqual(diagnostics, ())
        self.assertIsNotNone(canonical)
        assert canonical is not None
        self.assertEqual(
            canonical.semantic_dict()["numeric_policy_version"],
            DEFAULT_NUMERIC_POLICY,
        )

        rejected = PythonToCConverter().convert(
            ConversionRequest.from_source(
                "def run() -> int:\n    return 1\n",
                numeric_policy_version="numeric-policy/unknown",
            )
        )
        self.assertEqual(rejected.status, ResultStatus.REJECTED)
        self.assertEqual([item.code for item in rejected.diagnostics], ["PYC1018"])
        self.assertIsNone(rejected.generated_c)

    def test_phase10_helper_registry_and_assets_remain_frozen(self) -> None:
        registry = default_helper_registry()
        entries = {item["reference"]: item for item in registry.manifest}

        self.assertEqual(HELPER_REGISTRY_VERSION, "phase10-support-templates-v0.10")
        self.assertEqual(
            registry.fingerprint,
            "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98",
        )
        self.assertEqual(
            sorted(entries),
            [FLOOR_DIV_REFERENCE.canonical, FLOOR_MOD_REFERENCE.canonical],
        )
        self.assertEqual(
            entries[FLOOR_DIV_REFERENCE.canonical]["asset_fingerprint"],
            "23fa88ff57ffe15bc20845c6a7359f6d35648ecffd3a30ea23fe43f24e1dd869",
        )
        self.assertEqual(
            entries[FLOOR_MOD_REFERENCE.canonical]["asset_fingerprint"],
            "cc2e29f5823a119009df78ed20dc410c6eef4d72c57ada115790bd1120dc663e",
        )
        self.assertTrue(
            all(item["factory_kind"] == "structured-c-ir" for item in entries.values())
        )
        self.assertTrue(
            all(
                item["failure"]["runtime_failure_channel"] == "none"
                for item in entries.values()
            )
        )


if __name__ == "__main__":
    unittest.main()
