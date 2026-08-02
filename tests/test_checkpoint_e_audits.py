from __future__ import annotations

import ast
from pathlib import Path
import tempfile
import unittest

from pycforge.laboratory.checkpoint_e import (
    EXPECTED_CONTRACT_IDENTITIES,
    SUPPORTED_SUBSET_FAMILIES,
    audit_architecture_branding_product_boundary,
    audit_full_supported_subset,
    current_contract_identities,
    fixed_supported_subset_cases,
    generated_fuzz_cases,
    scan_product_boundary,
)


ROOT = Path(__file__).resolve().parents[1]


class CheckpointEAuditTests(unittest.TestCase):
    def test_semantic_schema_rule_and_renderer_identities_remain_phase14d(self) -> None:
        self.assertEqual(
            current_contract_identities(),
            EXPECTED_CONTRACT_IDENTITIES,
        )

    def test_fixed_corpus_covers_every_promoted_construct_family(self) -> None:
        cases = fixed_supported_subset_cases()
        self.assertEqual(
            {case.family for case in cases},
            SUPPORTED_SUBSET_FAMILIES,
        )
        self.assertEqual(len({case.case_id for case in cases}), len(cases))

    def test_generated_corpus_is_seeded_and_reproducible(self) -> None:
        first = generated_fuzz_cases(seed=1234, count=8)
        repeated = generated_fuzz_cases(seed=1234, count=8)
        different = generated_fuzz_cases(seed=5678, count=8)

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, different)
        self.assertEqual(len(first), 8)
        self.assertEqual(len({case.family for case in first}), 8)
        self.assertTrue(
            {case.family for case in first}.issubset(SUPPORTED_SUBSET_FAMILIES)
        )

    def test_generated_corpus_cycles_across_every_promoted_family(self) -> None:
        cases = generated_fuzz_cases(
            seed=1234,
            count=len(SUPPORTED_SUBSET_FAMILIES),
        )

        self.assertEqual(
            {case.family for case in cases},
            SUPPORTED_SUBSET_FAMILIES,
        )
        by_family = {case.family: case for case in cases}
        self.assertIn(
            " / ",
            by_family["assignments-and-arithmetic"].primary_text,
        )
        self.assertIn(
            "for item in values:",
            by_family["list"].primary_text,
        )

    def test_full_subset_audit_is_source_only_and_passes(self) -> None:
        report = audit_full_supported_subset(seed=321, fuzz_case_count=2)

        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(report["fixed_case_count"], 16)
        self.assertEqual(report["generated_case_count"], 2)
        self.assertEqual(report["missing_supported_families"], [])
        self.assertFalse(report["c_toolchain_invoked"])
        self.assertFalse(report["generated_c_compiled_or_executed"])
        self.assertRegex(str(report["corpus_sha256"]), r"^[0-9a-f]{64}$")
        self.assertRegex(str(report["report_sha256"]), r"^[0-9a-f]{64}$")

    def test_complete_generated_cycle_reports_family_and_feature_counts(self) -> None:
        report = audit_full_supported_subset(
            seed=321,
            fuzz_case_count=len(SUPPORTED_SUBSET_FAMILIES),
        )

        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(
            report["generated_family_counts"],
            {family: 1 for family in sorted(SUPPORTED_SUBSET_FAMILIES)},
        )
        self.assertEqual(report["generated_missing_families"], [])
        self.assertEqual(report["generated_complete_family_cycles"], 1)
        self.assertEqual(
            report["generated_feature_counts"],
            {
                "fixed-container-iteration": 2,
                "floating-division": 1,
            },
        )
        self.assertEqual(
            report["fixed_feature_witnesses"],
            {
                "fixed-container-iteration": "fixed-list",
                "floating-division": "fixed-arithmetic",
            },
        )

    def test_current_architecture_branding_and_product_boundary_pass(self) -> None:
        report = audit_architecture_branding_product_boundary(ROOT)

        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(report["identity_mismatches"], {})
        self.assertEqual(report["boundary_violations"], [])
        self.assertFalse(report["c_toolchain_invoked"])
        self.assertFalse(report["generated_c_compiled_or_executed"])

    def test_boundary_scanner_reports_tooling_actions_and_external_brands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            converter = root / "pycforge" / "converter"
            ide = root / "pycforge" / "ide"
            converter.mkdir(parents=True)
            ide.mkdir(parents=True)
            (converter / "bad.py").write_text(
                "import subprocess\n"
                "def unsafe(source):\n"
                "    return eval(source)\n",
                encoding="utf-8",
            )
            (ide / "bad.py").write_text(
                'ACTION = "Run"\n'
                'BRAND = "OpenAI Codex"\n',
                encoding="utf-8",
            )
            (root / "pyproject.toml").write_text(
                "[project]\n"
                'name = "pycforge"\n'
                "[project.scripts]\n"
                'pycforge = "pycforge.laboratory.cli:main"\n'
                'pycforge-run = "pycforge.ide.qt:run"\n',
                encoding="utf-8",
            )

            violations = scan_product_boundary(root)

        joined = "\n".join(violations)
        self.assertIn("forbidden runtime import subprocess", joined)
        self.assertIn("forbidden runtime call eval", joined)
        self.assertIn("out-of-scope action label 'Run'", joined)
        self.assertIn("external brand 'openai'", joined)
        self.assertIn("external brand 'codex'", joined)
        self.assertIn("out-of-scope project scripts: pycforge-run", joined)

    def test_checkpoint_e_sources_have_no_toolchain_or_dynamic_execution_imports(self) -> None:
        for relative in (
            "pycforge/laboratory/checkpoint_e.py",
            "tools/validate_checkpoint_e.py",
        ):
            path = ROOT / relative
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            imported_roots: set[str] = set()
            direct_calls: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_roots.update(
                        alias.name.split(".", 1)[0] for alias in node.names
                    )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_roots.add(node.module.split(".", 1)[0])
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    direct_calls.add(node.func.id)
            self.assertTrue(
                {"subprocess", "ctypes", "cffi", "pexpect"}.isdisjoint(
                    imported_roots
                ),
                relative,
            )
            self.assertTrue(
                {"compile", "eval", "exec"}.isdisjoint(direct_calls),
                relative,
            )


if __name__ == "__main__":
    unittest.main()
