from __future__ import annotations

import hashlib
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from pycforge import (
    ConversionProgress,
    ConversionRequest,
    PythonToCConverter,
    ResultStatus,
    __version__,
)
from pycforge.converter.core.serialization import result_to_dict
from pycforge.ide import WorkspaceController, WorkspaceState


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    "def identity(value: int) -> int:\n"
    "    return value\n\n"
    "def use(value: int) -> int:\n"
    "    return identity(value)\n"
)


class Phase10OpeningCheckpointTests(unittest.TestCase):
    def test_authoritative_roadmap_and_addendum_are_packaged(self):
        self.assertIn(
            __version__,
            {
                "0.10.0.dev0",
                "0.10.0",
                "0.11.0.dev0",
                "0.11.0",
                "0.12.0.dev0",
                "0.12.0",
                "0.12.1.dev0",
                "0.12.1",
                "0.12.2.dev0",
                "0.12.2",
                "0.13.0.dev0",
                "0.13.0",
                "0.14.0.dev0",
                "0.14.0",
                "0.14.1",
                "0.14.2",
                "0.14.3",
                "0.14.4",
                "0.15.0",
                "0.15.1",
                "0.15.2",
            },
        )
        roadmap = ROOT / "docs/python_to_c_converter_architecture_revision_3_1.txt"
        addendum = ROOT / "docs/python_to_c_converter_architecture_revision_3_2_addendum.md"
        self.assertEqual(
            hashlib.sha256(roadmap.read_bytes()).hexdigest(),
            "d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3",
        )
        text = addendum.read_text(encoding="utf-8")
        self.assertIn("two concrete", text)
        self.assertIn("Python source editor is the primary workspace", text)
        self.assertIn("observer-only", text)

    def test_progress_events_are_ordered_stage_boundaries(self):
        events: list[ConversionProgress] = []
        result = PythonToCConverter().convert(
            ConversionRequest.from_source(SOURCE), progress=events.append
        )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertEqual(events[0], ConversionProgress("pipeline-ready", None, 0, 6))
        entered = [event for event in events if event.state == "stage-entered"]
        completed = [event for event in events if event.state == "stage-completed"]
        self.assertEqual([event.stage_id for event in entered], list(result.stage_order))
        self.assertEqual([event.stage_id for event in completed], list(result.stage_order))
        self.assertEqual([event.completed_stages for event in completed], [1, 2, 3, 4, 5, 6])
        with self.assertRaises(FrozenInstanceError):
            events[0].state = "tampered"  # type: ignore[misc]

    def test_progress_observer_failure_is_semantically_inert(self):
        converter = PythonToCConverter()
        request = ConversionRequest.from_source(SOURCE)
        baseline = converter.convert(request)

        def fail(_: ConversionProgress) -> None:
            raise RuntimeError("injected progress observer failure")

        observed = converter.convert(request, progress=fail)
        self.assertEqual(result_to_dict(observed), result_to_dict(baseline))
        self.assertEqual(
            observed.stage_artifact.artifact_fingerprint,
            baseline.stage_artifact.artifact_fingerprint,
        )
        invalid = converter.convert(request, progress=object())  # type: ignore[arg-type]
        self.assertEqual(result_to_dict(invalid), result_to_dict(baseline))

    def test_controller_and_workspace_publish_honest_non_modal_progress(self):
        controller = WorkspaceController()
        self.addCleanup(controller.close)
        snapshots = []
        controller.subscribe(snapshots.append)
        controller.set_source(SOURCE)
        controller.convert()
        converting = [
            item for item in snapshots
            if item.state is WorkspaceState.CONVERTING and item.active_stage
        ]
        self.assertTrue(converting)
        self.assertEqual(converting[-1].total_stages, 6)
        self.assertEqual(controller.snapshot.completed_stages, 6)
        self.assertEqual(controller.snapshot.total_stages, 6)
        self.assertIsNone(controller.snapshot.active_stage)

        qt_source = (ROOT / "pycforge/ide/qt.py").read_text(encoding="utf-8")
        self.assertIn("self.output.setVisible(False)", qt_source)
        self.assertIn("self.tabs.setVisible(False)", qt_source)
        self.assertIn('"Show C"', qt_source)
        self.assertIn("QProgressBar", qt_source)
        self.assertIn("180", qt_source)
        self.assertNotIn("QProgressDialog", qt_source)
        self.assertNotIn("QMessageBox", qt_source)


if __name__ == "__main__":
    unittest.main()
