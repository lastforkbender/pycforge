from __future__ import annotations

import unittest
from dataclasses import fields, replace
from pathlib import Path

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.c_output import CRenderer, validate_c_text
from pycforge.converter.core.cancellation import CancellationToken
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.ir.c_ir import (
    CProvenance,
    CTranslationUnitBuilder,
    HELPER_SCHEMA_VERSION,
    SCHEMA_VERSION,
    validate_translation_unit,
)
from pycforge.converter.support_templates import (
    FLOOR_DIV_REFERENCE,
    FLOOR_MOD_REFERENCE,
    FrozenHelperRegistry,
    HelperCIRAsset,
    HelperReference,
    HelperRegistryError,
    HelperResolutionCanceled,
    assemble_translation_unit,
    builtin_definitions,
    default_helper_registry,
    floor_mod_asset,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "def identity(value: int) -> int:\n    return value\n"


class Phase10Tests(unittest.TestCase):
    def test_entry_gate_has_two_accepted_non_promoting_decisions(self):
        decision = (ROOT / "transition/phase_10/helper_feasibility_decisions.md").read_text(
            encoding="utf-8"
        )
        specification = (ROOT / "specifications/support_templates.md").read_text(
            encoding="utf-8"
        )
        for reference in (FLOOR_DIV_REFERENCE.canonical, FLOOR_MOD_REFERENCE.canonical):
            self.assertIn(reference, decision)
            self.assertIn(reference, specification)
        self.assertIn("does not promote", decision.replace("\n", " "))
        self.assertIn("caller-proved", specification)

    def test_default_registry_is_frozen_versioned_and_order_independent(self):
        definitions = builtin_definitions()
        forward = FrozenHelperRegistry(definitions)
        reverse = FrozenHelperRegistry(reversed(definitions))
        self.assertEqual(forward.manifest, reverse.manifest)
        self.assertEqual(forward.fingerprint, reverse.fingerprint)
        self.assertEqual(
            [item["reference"] for item in forward.manifest],
            [FLOOR_DIV_REFERENCE.canonical, FLOOR_MOD_REFERENCE.canonical],
        )
        for item in forward.manifest:
            self.assertEqual(item["interface_id"], "pycforge-helper/1")
            self.assertEqual(item["factory_kind"], "structured-c-ir")
            self.assertEqual(item["ownership"]["allocation"], "none")
            self.assertEqual(item["failure"]["strategy"], "caller-proved preconditions")
            self.assertRegex(item["asset_fingerprint"], r"^[0-9a-f]{64}$")

    def test_exact_resolution_deduplicates_and_omits_unused_helpers(self):
        registry = default_helper_registry()
        only_mod = registry.resolve(
            [FLOOR_MOD_REFERENCE, FLOOR_MOD_REFERENCE.canonical],
            target_contract="c11-portable-fixed-v1",
        )
        self.assertEqual(
            [item.reference for item in only_mod.manifest],
            [FLOOR_MOD_REFERENCE],
        )
        both = registry.resolve(
            [FLOOR_MOD_REFERENCE, FLOOR_DIV_REFERENCE, FLOOR_MOD_REFERENCE],
            target_contract="c11-portable-fixed-v1",
        )
        self.assertEqual(
            [item.reference for item in both.manifest],
            [FLOOR_DIV_REFERENCE, FLOOR_MOD_REFERENCE],
        )
        empty = registry.resolve([], target_contract="c11-portable-fixed-v1")
        self.assertFalse(empty.assets)
        self.assertFalse(empty.manifest)
        with self.assertRaises(HelperRegistryError) as unknown_target:
            registry.resolve([], target_contract="unknown-target")
        self.assertEqual(unknown_target.exception.code, "PYC3304")

    def test_dependency_closure_is_exact_and_topological(self):
        floor_div, floor_mod = builtin_definitions()
        dependent_mod = replace(floor_mod, dependencies=(FLOOR_DIV_REFERENCE,))
        first = FrozenHelperRegistry((dependent_mod, floor_div))
        second = FrozenHelperRegistry((floor_div, dependent_mod))
        first_plan = first.resolve(
            [FLOOR_MOD_REFERENCE], target_contract="c11-portable-fixed-v1"
        )
        second_plan = second.resolve(
            [FLOOR_MOD_REFERENCE], target_contract="c11-portable-fixed-v1"
        )
        expected = [FLOOR_DIV_REFERENCE, FLOOR_MOD_REFERENCE]
        self.assertEqual([item.reference for item in first_plan.manifest], expected)
        self.assertEqual(first_plan.manifest_dicts(), second_plan.manifest_dicts())
        self.assertEqual(first_plan.manifest_fingerprint, second_plan.manifest_fingerprint)

    def test_missing_dependency_and_cycle_have_stable_diagnostics(self):
        floor_div, floor_mod = builtin_definitions()
        missing = HelperReference("pycf.i64.missing", "1.0.0")
        incomplete = FrozenHelperRegistry(
            (floor_div, replace(floor_mod, dependencies=(missing,)))
        )
        with self.assertRaises(HelperRegistryError) as missing_error:
            incomplete.resolve(
                [FLOOR_MOD_REFERENCE], target_contract="c11-portable-fixed-v1"
            )
        self.assertEqual(missing_error.exception.code, "PYC3302")
        self.assertIn(missing.canonical, missing_error.exception.message)

        cyclic = FrozenHelperRegistry(
            (
                replace(floor_div, dependencies=(FLOOR_MOD_REFERENCE,)),
                replace(floor_mod, dependencies=(FLOOR_DIV_REFERENCE,)),
            )
        )
        with self.assertRaises(HelperRegistryError) as cycle_error:
            cyclic.resolve(
                [FLOOR_DIV_REFERENCE], target_contract="c11-portable-fixed-v1"
            )
        self.assertEqual(cycle_error.exception.code, "PYC3303")
        self.assertIn(FLOOR_DIV_REFERENCE.canonical, cycle_error.exception.message)
        self.assertIn(FLOOR_MOD_REFERENCE.canonical, cycle_error.exception.message)

    def test_interface_target_duplicate_and_asset_validation_are_closed(self):
        floor_div, floor_mod = builtin_definitions()
        with self.assertRaises(HelperRegistryError) as duplicate:
            FrozenHelperRegistry((floor_div, floor_div))
        self.assertEqual(duplicate.exception.code, "PYC3307")

        with self.assertRaises(HelperRegistryError) as interface:
            FrozenHelperRegistry((replace(floor_div, interface_id="unknown-helper/1"),))
        self.assertEqual(interface.exception.code, "PYC3305")

        other_target = FrozenHelperRegistry(
            (replace(floor_div, target_contracts=("pycforge-c11-int64-v0.1",)),)
        )
        with self.assertRaises(HelperRegistryError) as target:
            other_target.resolve(
                [FLOOR_DIV_REFERENCE], target_contract="c11-portable-fixed-v1"
            )
        self.assertEqual(target.exception.code, "PYC3304")

        with self.assertRaises(HelperRegistryError) as asset:
            FrozenHelperRegistry((replace(floor_div, factory=floor_mod_asset),))
        self.assertEqual(asset.exception.code, "PYC3306")

    def test_resolution_cancellation_publishes_no_partial_plan(self):
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(HelperResolutionCanceled):
            default_helper_registry().resolve(
                [FLOOR_DIV_REFERENCE, FLOOR_MOD_REFERENCE],
                target_contract="c11-portable-fixed-v1",
                cancellation=token,
            )

    def test_helpers_are_structured_c_ir_and_assemble_once(self):
        self.assertEqual(
            {item.name for item in fields(HelperCIRAsset)},
            {"reference", "includes", "prototype", "definition"},
        )
        registry = default_helper_registry()
        plan = registry.resolve(
            [FLOOR_DIV_REFERENCE, FLOOR_MOD_REFERENCE],
            target_contract="c11-portable-fixed-v1",
        )
        source_unit = CTranslationUnitBuilder(
            "c11-portable-fixed-v1",
            schema_version=SCHEMA_VERSION,
            provenance=CProvenance("synthetic"),
        ).build()
        assembled = assemble_translation_unit(source_unit, plan)
        self.assertEqual(assembled.schema_version, HELPER_SCHEMA_VERSION)
        self.assertTrue(validate_translation_unit(assembled).accepted)
        text = CRenderer().render(assembled).text
        self.assertTrue(validate_c_text(text).accepted)
        self.assertEqual(text.count("#include <stdint.h>"), 1)
        self.assertEqual(text.count("pycf_i64_floor_div_v1("), 2)
        self.assertEqual(text.count("pycf_i64_floor_mod_v1("), 2)

    def test_helper_golden_sources_are_exact_and_nonexecuting(self):
        registry = default_helper_registry()
        fixtures = {
            FLOOR_DIV_REFERENCE: "pycf_i64_floor_div_v1.c",
            FLOOR_MOD_REFERENCE: "pycf_i64_floor_mod_v1.c",
        }
        for reference, name in fixtures.items():
            expected = (ROOT / "fixtures/support_templates" / name).read_text(
                encoding="utf-8"
            )
            self.assertEqual(registry.rendered_asset(reference), expected)
            self.assertTrue(validate_c_text(expected).accepted)

    def test_current_rules_emit_no_helpers_but_publish_empty_manifest(self):
        result = PythonToCConverter().convert(
            ConversionRequest.from_source(SOURCE),
            observation=ObservationOptions("Full", False),
        )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        payload = result.stage_artifact.payload
        self.assertEqual(result.stage_artifact.schema_version, "0.14.3")
        self.assertEqual(payload["schema_version"], "generated-c/0.14.3")
        self.assertEqual(payload["c_ir_schema"], "c-ir/0.14.3")
        self.assertEqual(payload["helper_requirements"], [])
        self.assertEqual(payload["helper_manifest"], [])
        self.assertRegex(payload["helper_registry_fingerprint"], r"^[0-9a-f]{64}$")
        self.assertRegex(payload["helper_manifest_fingerprint"], r"^[0-9a-f]{64}$")
        self.assertNotIn("pycf_i64_floor_", result.generated_c)
        self.assertEqual(
            result.conversion_summary["schema_version"],
            "pycforge.conversion-summary/0.14.3",
        )
        self.assertEqual(result.conversion_summary["helpers"], [])
        self.assertEqual(
            result.decision_trace["schema_version"],
            "pycforge.decision-trace/0.14.3",
        )
        self.assertEqual(
            result.decision_trace["helper_policy_version"],
            payload["helper_policy_version"],
        )
        self.assertEqual(result.decision_trace["helper_manifest"], [])
        events = [
            item for item in result.decision_trace["events"]
            if item.get("kind") == "helper_resolution"
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["requirements"], [])
        self.assertEqual(events[0]["helpers"], [])

    def test_undeclared_helper_policy_is_rejected_before_conversion(self):
        result = PythonToCConverter().convert(
            ConversionRequest.from_source(SOURCE, helper_policy_version="unknown")
        )
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertEqual(result.diagnostics[0].code, "PYC1014")
        self.assertIsNone(result.generated_c)


if __name__ == "__main__":
    unittest.main()
