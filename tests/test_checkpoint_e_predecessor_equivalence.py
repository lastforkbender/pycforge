from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from pycforge.laboratory.checkpoint_e import FUZZ_SEED
from tools.checkpoint_e_predecessor_equivalence import (
    CORPUS_SCHEMA,
    DEFAULT_PROMOTION_GENERATED_CASE_COUNT,
    SEALED_PREDECESSOR_NAME,
    audit_predecessor_equivalence,
    compare_exact_results,
    promotion_corpus,
)
from tools.validate_checkpoint_e import (
    locate_predecessor_archive,
    validate_checkpoint_e,
)


ROOT = Path(__file__).resolve().parents[1]


class CheckpointEPredecessorEquivalenceTests(unittest.TestCase):
    def _available_predecessor_or_skip(self) -> Path:
        archive = locate_predecessor_archive(ROOT)
        if archive is None:
            self.skipTest(
                "sealed Phase 14D predecessor archive is not beside this tree"
            )
        return archive

    def test_promotion_corpus_is_exactly_sixteen_fixed_plus_sixty_four_generated(
        self,
    ) -> None:
        cases = promotion_corpus()

        self.assertEqual(CORPUS_SCHEMA, "pycforge.checkpoint-e-predecessor-corpus/1")
        self.assertEqual(DEFAULT_PROMOTION_GENERATED_CASE_COUNT, 64)
        self.assertEqual(len(cases), 80)
        self.assertEqual(len({case.case_id for case in cases}), 80)
        self.assertEqual(cases[0].case_id, "fixed-literals")
        self.assertEqual(cases[15].case_id, "fixed-keyword-only-call")
        self.assertEqual(cases[16].case_id, "fuzz-000")
        self.assertEqual(cases[-1].case_id, "fuzz-063")

    def test_historical_equivalence_audit_proves_exact_eighty_of_eighty(
        self,
    ) -> None:
        archive = self._available_predecessor_or_skip()

        equivalence = audit_predecessor_equivalence(
            archive,
            generated_case_count=64,
        )

        self.assertTrue(equivalence["passed"], equivalence["errors"])
        self.assertEqual(equivalence["seed"], FUZZ_SEED)
        self.assertEqual(equivalence["fixed_case_count"], 16)
        self.assertEqual(equivalence["generated_case_count"], 64)
        self.assertEqual(equivalence["case_count"], 80)
        self.assertEqual(
            equivalence["promotion_minimum_generated_case_count"],
            64,
        )
        self.assertEqual(equivalence["promotion_minimum_case_count"], 80)
        self.assertTrue(equivalence["promotion_eligible"])
        self.assertEqual(equivalence["matched_case_count"], 80)
        self.assertEqual(equivalence["mismatched_case_count"], 0)
        self.assertEqual(len(equivalence["case_digests"]), 80)
        self.assertTrue(
            all(item["exact_match"] for item in equivalence["case_digests"])
        )
        self.assertTrue(equivalence["exact_result_json_byte_equivalence"])
        self.assertEqual(
            equivalence["candidate_results_sha256"],
            equivalence["predecessor_results_sha256"],
        )
        self.assertTrue(
            equivalence["archive_authenticated_before_extraction"]
        )
        self.assertTrue(
            equivalence["archive_extracted_to_private_temporary_directory"]
        )
        self.assertTrue(equivalence["temporary_extraction_removed"])
        self.assertTrue(equivalence["python_interpreter_invoked"])
        self.assertTrue(equivalence["python_isolated_mode"])
        self.assertTrue(equivalence["python_no_site_mode"])
        self.assertEqual(equivalence["python_command_flags"], ["-I", "-S"])
        self.assertEqual(equivalence["native_toolchain_commands"], [])
        self.assertFalse(equivalence["untrusted_pickle_loaded"])
        self.assertFalse(equivalence["c_toolchain_invoked"])
        self.assertFalse(equivalence["generated_c_compiled_or_executed"])

    def test_tampered_archive_fails_before_extraction_or_runner_invocation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / SEALED_PREDECESSOR_NAME
            archive.write_bytes(b"not the authenticated Phase 14D release")

            report = audit_predecessor_equivalence(
                archive,
                generated_case_count=0,
            )

        self.assertFalse(report["passed"])
        joined = "\n".join(report["errors"])
        self.assertIn("size mismatch", joined)
        self.assertIn("SHA-256 mismatch", joined)
        self.assertFalse(report["archive_authenticated_before_extraction"])
        self.assertFalse(
            report["archive_extracted_to_private_temporary_directory"]
        )
        self.assertFalse(report["python_interpreter_invoked"])
        self.assertFalse(report["c_toolchain_invoked"])
        self.assertFalse(report["generated_c_compiled_or_executed"])

    def test_focused_skip_is_explicitly_not_promotion_eligible(self) -> None:
        archive = self._available_predecessor_or_skip()

        report = validate_checkpoint_e(
            ROOT,
            predecessor_archive=archive,
            require_predecessor=True,
            run_fuzz=False,
            fuzz_case_count=0,
            run_predecessor_equivalence=False,
        )
        equivalence = report["sealed_predecessor_equivalence"]

        self.assertTrue(equivalence["passed"])
        self.assertTrue(equivalence["skipped"])
        self.assertFalse(equivalence["promotion_eligible"])
        self.assertEqual(
            equivalence["reason"],
            "explicit focused-validator option",
        )

    def test_exact_byte_mismatch_is_reported_with_both_digests(self) -> None:
        candidate = b'{"status":"Converted"}\n'
        predecessor = b'{"status":"Rejected"}\n'
        rows = [
            {
                "case_id": "witness",
                "result_json": predecessor.decode("utf-8"),
                "result_sha256": hashlib.sha256(predecessor).hexdigest(),
                "result_size": len(predecessor),
            }
        ]

        report = compare_exact_results(
            ["witness"],
            {"witness": candidate},
            rows,
        )

        self.assertFalse(report["passed"])
        self.assertFalse(report["exact_result_json_byte_equivalence"])
        self.assertEqual(report["matched_case_count"], 0)
        self.assertEqual(report["mismatched_case_count"], 1)
        mismatch = report["mismatches"][0]
        self.assertEqual(mismatch["case_id"], "witness")
        self.assertEqual(
            mismatch["candidate_sha256"],
            hashlib.sha256(candidate).hexdigest(),
        )
        self.assertEqual(
            mismatch["predecessor_sha256"],
            hashlib.sha256(predecessor).hexdigest(),
        )

    def test_forged_predecessor_result_digest_fails_closed(self) -> None:
        result = b'{"status":"Converted"}\n'
        rows = [
            {
                "case_id": "witness",
                "result_json": result.decode("utf-8"),
                "result_sha256": "0" * 64,
                "result_size": len(result),
            }
        ]

        report = compare_exact_results(
            ["witness"],
            {"witness": result},
            rows,
        )

        self.assertFalse(report["passed"])
        self.assertFalse(report["exact_result_json_byte_equivalence"])
        self.assertIn(
            "witness: predecessor result digest is inconsistent",
            report["errors"],
        )


if __name__ == "__main__":
    unittest.main()
