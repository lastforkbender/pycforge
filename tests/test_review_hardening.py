from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.c_output import validate_c_text
from pycforge.converter.core.artifact_io import (
    ArtifactCompatibilityError,
    artifact_from_dict,
    artifact_to_dict,
)
from pycforge.converter.core.request import SourceBundle, SourceDocumentInput
from pycforge.converter.core.stage_artifact import StageArtifact
from pycforge.converter.ir.c_ir import (
    CBlock,
    CBreakStatement,
    CFunctionDefinition,
    CFunctionPrototype,
    CIdentifier,
    CIntegerLiteral,
    CProvenance,
    CReturnStatement,
    CStorage,
    CTranslationUnitBuilder,
    CType,
    SCHEMA_VERSION,
    validate_translation_unit,
)
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.contracts.configuration import (
    PHASE14A_RENDERER,
    PHASE14A_RULE_SET,
)
from pycforge.ide.controller import WorkspaceController


ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}


def convert(source: str):
    return PythonToCConverter().convert(ConversionRequest.from_source(source))


class ReviewHardeningTests(unittest.TestCase):
    def test_malformed_nested_requests_are_structured_rejections(self):
        requests = (
            ConversionRequest(None),  # type: ignore[arg-type]
            ConversionRequest.from_source("\ud800"),
            ConversionRequest.from_source("", logical_name="\ud800"),
            ConversionRequest.from_source("", logical_name="."),
            ConversionRequest.from_source("", logical_name="bad\nname.py"),
            ConversionRequest(SourceBundle(SourceDocumentInput("main.py", ""), (SourceDocumentInput("other.py", ""),))),
        )
        for request in requests:
            result = PythonToCConverter().convert(request)
            self.assertEqual(result.status, ResultStatus.REJECTED)
            self.assertTrue(result.diagnostics)
            self.assertIsNone(result.generated_c)

    def test_published_artifacts_and_observer_snapshots_are_deeply_immutable(self):
        source = "def f(a: int) -> int:\n    return a\n"
        result = PythonToCConverter().convert(
            ConversionRequest.from_source(source),
            observation=ObservationOptions("Full", True),
        )
        with self.assertRaises(TypeError):
            result.stage_artifact.payload["c_ir"]["target_contract"] = "tampered"
        with self.assertRaises((TypeError, AttributeError)):
            result.decision_trace["events"].append({"kind": "tampered"})
        rejected = convert("def f(a: int) -> int:\n    return missing(a)\n")
        diagnostic = rejected.diagnostics[0].to_dict()
        self.assertRegex(diagnostic["diagnostic_id"], r"^diag-[0-9a-f]{20}$")
        self.assertEqual(diagnostic["target_contract"], "c11-portable-fixed-v1")
        self.assertEqual(diagnostic["semantic_policy"], "strict-source-v1")
        with self.assertRaises(TypeError):
            rejected.diagnostics[0].source_span["start"]["offset"] = 0

    def test_artifact_metadata_and_unknown_envelope_fields_are_rejected(self):
        metadata = artifact_to_dict(StageArtifact.initial("conversion"))
        metadata["artifact_fingerprint"]["algorithm"] = "sha1"
        with self.assertRaisesRegex(ArtifactCompatibilityError, "PYC3103"):
            artifact_from_dict(metadata)
        extra = artifact_to_dict(StageArtifact.initial("conversion"))
        extra["unchecked"] = True
        with self.assertRaisesRegex(ArtifactCompatibilityError, "PYC3103"):
            artifact_from_dict(extra)

    def test_conflicting_binding_categories_reject_without_internal_failure(self):
        result = convert("def f() -> int:\n    x = 1\n    x = True\n    return 0\n")
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertEqual(result.diagnostics[0].code, "PYC2943")
        chain = "def f() -> int:\n" + "".join(
            f"    x{index} = x{index + 1}\n" for index in range(1000)
        ) + "    x1000 = 1\n    return x0\n"
        chained = convert(chain)
        self.assertEqual(chained.status, ResultStatus.REJECTED)
        self.assertEqual(chained.diagnostics[0].code, "PYC2940")

    def test_range_bounds_are_staged_once_before_mutating_loop_body(self):
        result = convert("def f(n: int) -> int:\n    for i in range(n):\n        n = n - 1\n    return n\n")
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertRegex(result.generated_c, r"int64_t pycf_range_[a-f0-9]+ = n;")
        self.assertRegex(result.generated_c, r"for \(int64_t i = 0LL; i < pycf_range_[a-f0-9]+;")

    def test_invalid_range_representations_and_dynamic_step_reject(self):
        cases = (
            ("def f(n: float) -> float:\n    for i in range(n):\n        continue\n    return n\n", "PYC2842"),
            ("def f(n: int, s: int) -> int:\n    for i in range(0, n, s):\n        continue\n    return n\n", "PYC2845"),
        )
        for source, code in cases:
            result = convert(source)
            self.assertEqual(result.status, ResultStatus.REJECTED)
            self.assertEqual(result.diagnostics[0].code, code)

    def test_loop_target_rebind_mutation_and_escape_have_root_diagnostics(self):
        cases = (
            ("def f(n: int) -> int:\n    for n in range(n):\n        continue\n    return n\n", "PYC2944"),
            ("def f(n: int) -> int:\n    for i in range(n):\n        i = i + 1\n    return n\n", "PYC2847"),
            ("def f(n: int) -> int:\n    for i in range(n):\n        continue\n    return i\n", "PYC2941"),
        )
        for source, code in cases:
            result = convert(source)
            self.assertEqual(result.status, ResultStatus.REJECTED)
            self.assertEqual(result.diagnostics[0].code, code)

    def test_shadowed_range_name_is_not_treated_as_the_builtin(self):
        result = convert("def f(range: int) -> int:\n    for i in range(range):\n        continue\n    return range\n")
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertEqual(result.diagnostics[0].code, "PYC2901")

    def test_chained_comparison_in_condition_is_structural_and_single_evaluation(self):
        result = convert("def f(a: int, b: int, c: int) -> int:\n    if a < b < c:\n        return 1\n    return 0\n")
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertEqual(result.generated_c.count(" = b;"), 1)
        self.assertIn(" && ", result.generated_c)

    def test_conditional_regions_are_guarded_while_phase14a_rejections_remain_historical(self):
        cases = (
            (
                "call-in-chain",
                "def identity(x: int) -> int:\n    return x\n\n"
                "def f(a: int, b: int, c: int) -> bool:\n"
                "    return a < b < identity(c)\n",
                "PYC2951",
                "pycf_comparison_region_result_",
            ),
            (
                "arithmetic-in-chain",
                "def f(a: float, b: float, c: float) -> bool:\n"
                "    return a < b < (c / 2.0)\n",
                "PYC2951",
                "pycf_comparison_region_result_",
            ),
            (
                "call-in-boolean",
                "def flag(value: bool) -> bool:\n    return value\n\n"
                "def f(a: bool, b: bool) -> bool:\n"
                "    return a and flag(b)\n",
                "PYC2950",
                "pycf_bool_region_result_",
            ),
        )
        for name, source, historical_code, result_name in cases:
            with self.subTest(name=name, profile="active"):
                active = convert(source)
                self.assertEqual(active.status, ResultStatus.CONVERTED, active.diagnostics)
                self.assertEqual(active.diagnostics, ())
                self.assertIn(f"if ({result_name}", active.generated_c)

            with self.subTest(name=name, profile="phase14a"):
                historical = PythonToCConverter().convert(
                    ConversionRequest.from_source(
                        source,
                        rule_set_version=PHASE14A_RULE_SET,
                        renderer_version=PHASE14A_RENDERER,
                    )
                )
                self.assertEqual(historical.status, ResultStatus.REJECTED)
                self.assertEqual([item.code for item in historical.diagnostics], [historical_code])
                self.assertIsNone(historical.generated_c)

    def test_nested_unary_minus_cannot_lex_as_predecrement(self):
        result = convert("def f(a: int) -> int:\n    return - -a\n")
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertIn("return -(-a);", result.generated_c)
        self.assertNotIn("return --a;", result.generated_c)

    def test_c_and_header_reserved_source_names_are_escaped(self):
        for name in ("_f", "é", "switch", "bool", "int64_t", "pycf_temp", "main", "printf", "malloc", "strlen"):
            result = convert(f"def {name}(a: int) -> int:\n    return a\n")
            self.assertEqual(result.status, ResultStatus.CONVERTED, name)
            self.assertTrue(validate_c_text(result.generated_c).accepted)
            prototype = next(line for line in result.generated_c.splitlines() if line.endswith(";"))
            self.assertNotIn(f" {name}(", prototype)
        macro = convert("def f(INT64_MAX: int) -> int:\n    return INT64_MAX\n")
        self.assertEqual(macro.status, ResultStatus.CONVERTED)
        self.assertNotIn("int64_t INT64_MAX", macro.generated_c)

    def test_utf8_escape_does_not_consume_following_hexadecimal_character(self):
        result = convert("def f() -> str:\n    return \"éA\"\n")
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertIn('"\\xc3\\251A"', result.generated_c)
        trigraph = convert("def f() -> str:\n    return \"??/\"\n")
        self.assertEqual(trigraph.status, ResultStatus.CONVERTED)
        self.assertIn('"\\?\\?/"', trigraph.generated_c)
        self.assertNotIn('"??/"', trigraph.generated_c)

    def test_oversized_integer_and_nonfinite_float_literals_reject(self):
        for source in (
            f"def f() -> int:\n    return {2**63}\n",
            "def f() -> float:\n    return 1e309\n",
        ):
            result = convert(source)
            self.assertEqual(result.status, ResultStatus.REJECTED)
            self.assertEqual(result.diagnostics[0].code, "PYC2822")
            json.dumps(dict(result.stage_artifact.payload), allow_nan=False)
        none_result = convert("def f() -> int:\n    return None\n")
        self.assertEqual(none_result.status, ResultStatus.REJECTED)
        self.assertEqual(none_result.diagnostics[0].code, "PYC2930")
        for literal in ("b'bytes'", "1j", "..."):
            unsupported = convert(f"def f() -> str:\n    return {literal}\n")
            self.assertEqual(unsupported.status, ResultStatus.REJECTED)
            self.assertIsNone(unsupported.generated_c)

    def test_cli_output_preserves_preceding_file_on_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.py"
            output = root / "output.c"
            output.write_text("last-known-good", encoding="utf-8")
            source.write_text("def f(a):\n    return a\n", encoding="utf-8")
            rejected = subprocess.run(
                [sys.executable, "-m", "pycforge", "--format", "json", "convert", str(source), "--output", str(output)],
                cwd=ROOT,
                env=ENV,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "last-known-good")
            self.assertEqual(json.loads(rejected.stdout)["status"], "Rejected")
            source.write_text("def f(a: int) -> int:\n    return a\n", encoding="utf-8")
            accepted = subprocess.run(
                [sys.executable, "-m", "pycforge", "convert", str(source), "--output", str(output)],
                cwd=ROOT,
                env=ENV,
                text=True,
                capture_output=True,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertIn("int64_t f", output.read_text(encoding="utf-8"))

    def test_workspace_cannot_save_retained_output_after_rejection(self):
        controller = WorkspaceController()
        self.addCleanup(controller.close)
        controller.set_source("def f(a: int) -> int:\n    return a\n")
        controller.convert()
        preceding = controller.snapshot.generated_c
        controller.set_source("def f(a):\n    return a\n")
        controller.convert()
        self.assertEqual(controller.snapshot.generated_c, preceding)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                controller.save_generated_c(Path(directory) / "stale.c")

    def test_c_ir_09_requires_prototypes_and_loop_context(self):
        provenance = CProvenance("synthetic")
        identifier = CIdentifier("bind-f", "f", provenance)
        returned = CReturnStatement("ret", CIntegerLiteral("one", 1, "LL", provenance), provenance)
        definition = CFunctionDefinition("fn", identifier, CType("int64_t"), (), CBlock("body", (returned,), provenance), CStorage.NONE, provenance)
        builder = CTranslationUnitBuilder("c11-portable-fixed-v1", schema_version=SCHEMA_VERSION, provenance=provenance)
        builder.add_declaration(definition)
        missing_prototype = validate_translation_unit(builder.build())
        self.assertFalse(missing_prototype.accepted)
        self.assertTrue(any("prototype" in item for item in missing_prototype.errors))

        prototype = CFunctionPrototype("proto", identifier, CType("int64_t"), (), CStorage.NONE, provenance)
        broken_definition = CFunctionDefinition("fn2", identifier, CType("int64_t"), (), CBlock("body2", (CBreakStatement("break", provenance), returned), provenance), CStorage.NONE, provenance)
        builder = CTranslationUnitBuilder("c11-portable-fixed-v1", schema_version=SCHEMA_VERSION, provenance=provenance)
        builder.add_declaration(prototype)
        builder.add_declaration(broken_definition)
        invalid_break = validate_translation_unit(builder.build())
        self.assertFalse(invalid_break.accepted)
        self.assertTrue(any("enclosing loop" in item for item in invalid_break.errors))


if __name__ == "__main__":
    unittest.main()
