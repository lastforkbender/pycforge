from __future__ import annotations

import tempfile
import time
import unittest
from concurrent.futures import CancelledError
from dataclasses import FrozenInstanceError
from pathlib import Path

from pycforge.converter.core.request import ConversionRequest
from pycforge.converter.facade import PythonToCConverter
from pycforge.converter.io.atomic_writer import AtomicWriteError, AtomicWriter
from pycforge.ide import WorkspaceController, WorkspaceDocument, WorkspaceState
from pycforge.ide.supervisor import ConversionCancelled


APP = "from lib import increment\n\ndef run(value: int) -> int:\n    return increment(value)\n"
LIB = "def increment(value: int) -> int:\n    return value + 1\n"


class RecordingConverter:
    def __init__(self, *, delay_marker: str | None = None) -> None:
        self.real = PythonToCConverter()
        self.delay_marker = delay_marker
        self.requests = []

    def convert(self, request, **kwargs):
        self.requests.append(request)
        documents = (request.source_bundle.primary,) + request.source_bundle.companions
        if self.delay_marker and any(
            self.delay_marker in document.text for document in documents
        ):
            time.sleep(0.15)
        return self.real.convert(request, **kwargs)


class PyCForgeWorkspaceTests(unittest.TestCase):
    def bundle_controller(self, converter=None, **kwargs) -> tuple[WorkspaceController, str]:
        controller = WorkspaceController(**kwargs)
        self.addCleanup(controller.close)
        controller.set_document_identity(
            "doc-main",
            module_id="app",
            logical_name="app.py",
        )
        controller.set_source(APP)
        companion = controller.add_document(
            "lib",
            "lib.py",
            LIB,
            make_active=False,
        )
        return controller, companion.document_id

    def test_frozen_bundle_converts_primary_and_companion(self):
        controller, companion_id = self.bundle_controller()

        result = controller.convert()

        self.assertEqual(controller.snapshot.state, WorkspaceState.CONVERTED)
        self.assertEqual(result.generated_c, controller.snapshot.generated_c)
        self.assertTrue(controller.snapshot.can_save_c)
        self.assertEqual(dict(controller.snapshot.summary)["modules"], "2")
        request = controller.committed_revision.request
        self.assertEqual(request.source_bundle.primary.module_id, "app")
        self.assertEqual(
            [item.module_id for item in request.source_bundle.companions],
            ["lib"],
        )
        self.assertEqual(controller.snapshot.active_document_id, "doc-main")
        controller.select_document(companion_id)
        self.assertEqual(controller.snapshot.source_text, LIB)
        self.assertEqual(controller.snapshot.active_document.module_id, "lib")
        with self.assertRaises(FrozenInstanceError):
            controller.snapshot.active_document.text = "changed"  # type: ignore[misc]

    def test_identity_duplicate_and_bound_rejections_are_transactional(self):
        controller = WorkspaceController()
        self.addCleanup(controller.close)
        original = controller.snapshot
        for module_id, logical_name in (
            ("main", "other.py"),
            ("other", "main.py"),
            ("Bad.Module", "other.py"),
            ("other", "/absolute.py"),
        ):
            with self.subTest(module_id=module_id, logical_name=logical_name):
                with self.assertRaises(ValueError):
                    controller.add_document(module_id, logical_name)
                self.assertEqual(controller.snapshot, original)

        for index in range(1, 64):
            controller.add_document(
                f"m{index}",
                f"m{index}.py",
                make_active=False,
            )
        self.assertEqual(len(controller.snapshot.documents), 64)
        self.assertFalse(controller.snapshot.can_add_document)
        with self.assertRaises(ValueError):
            controller.add_document("overflow", "overflow.py")

        while len(controller.snapshot.documents) > 1:
            controller.remove_document(controller.snapshot.documents[-1].document_id)
        self.assertFalse(controller.snapshot.can_remove_document)
        with self.assertRaises(ValueError):
            controller.remove_document("doc-main")

    def test_primary_selection_and_reorder_are_explicit_and_safe(self):
        controller, companion_id = self.bundle_controller()
        controller.set_primary_document(companion_id)
        self.assertEqual(controller.snapshot.primary_document.module_id, "lib")
        self.assertFalse(controller.snapshot.documents[0].is_primary)

        controller.reorder_documents((companion_id, "doc-main"))
        self.assertEqual(
            [item.document_id for item in controller.snapshot.documents],
            [companion_id, "doc-main"],
        )
        before = controller.snapshot
        with self.assertRaises(ValueError):
            controller.reorder_documents((companion_id, companion_id))
        self.assertEqual(controller.snapshot, before)

    def test_companion_edit_invalidates_output_and_late_result_is_discarded(self):
        controller = WorkspaceController()
        self.addCleanup(controller.close)
        controller.set_document_identity(
            "doc-main",
            module_id="app",
            logical_name="app.py",
        )
        controller.set_source(
            "from lib import slow_increment\n\n"
            "def run(value: int) -> int:\n"
            "    return slow_increment(value)\n"
        )
        companion = controller.add_document(
            "lib",
            "lib.py",
            "def slow_increment(value: int) -> int:\n    return value + 1\n",
            make_active=False,
        )
        snapshots = []
        controller.subscribe(snapshots.append)
        old = controller.convert_async()

        controller.update_document(companion.document_id, LIB)
        controller.update_document("doc-main", APP)
        new = controller.convert_async()
        new_result = new.result(timeout=5)
        published_count = len(snapshots)
        with self.assertRaises((ConversionCancelled, CancelledError)):
            old.result(timeout=5)

        self.assertEqual(len(snapshots), published_count)
        self.assertEqual(controller.snapshot.generated_c, new_result.generated_c)
        self.assertTrue(controller.snapshot.can_save_c)
        self.assertNotIn("slow_increment", controller.snapshot.generated_c)

        controller.update_document(companion.document_id, LIB + "\n")
        self.assertEqual(controller.snapshot.state, WorkspaceState.STALE)
        self.assertFalse(controller.snapshot.can_save_c)

    def test_document_paths_dirty_state_and_default_c_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "app.py"
            source.write_text(
                "def run(value: int) -> int:\n    return value + 1\n",
                encoding="utf-8",
            )
            controller = WorkspaceController()
            self.addCleanup(controller.close)

            self.assertEqual(controller.open_python(source), source.read_text())
            document = controller.snapshot.primary_document
            self.assertEqual(document.path, str(source))
            self.assertFalse(document.dirty)
            self.assertEqual(controller.snapshot.linked_c_path, str(root / "app.c"))

            controller.set_source(document.text + "\n")
            self.assertTrue(controller.snapshot.active_document.dirty)
            controller.save_document()
            self.assertFalse(controller.snapshot.active_document.dirty)
            self.assertEqual(source.read_text(), controller.snapshot.source_text)

            controller.convert()
            linked = controller.save_generated_c_linked()
            self.assertEqual(linked, str(root / "app.c"))
            self.assertEqual(Path(linked).read_text(), controller.snapshot.generated_c)

            custom = root / "generated" / "module.c"
            self.assertEqual(controller.link_generated_c(custom), str(custom))
            self.assertFalse(controller.snapshot.linked_c_path_is_default)
            controller.save_generated_c_linked()
            self.assertEqual(custom.read_text(), controller.snapshot.generated_c)

    def test_atomic_linked_c_failure_preserves_last_known_good_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "app.py"
            c_path = root / "app.c"
            source.write_text(
                "def run(value: int) -> int:\n    return value + 1\n",
                encoding="utf-8",
            )
            c_path.write_text("last-known-good", encoding="utf-8")

            def fail(_temporary: Path) -> None:
                raise RuntimeError("injected interruption")

            controller = WorkspaceController(
                writer=AtomicWriter(before_replace=fail),
            )
            self.addCleanup(controller.close)
            controller.open_python(source)
            controller.convert()
            with self.assertRaises(AtomicWriteError):
                controller.save_generated_c_linked()
            self.assertEqual(c_path.read_text(encoding="utf-8"), "last-known-good")
            self.assertFalse(any(root.glob(".app.c.*.tmp")))

    def test_legacy_single_source_api_remains_byte_identical(self):
        source = "def identity(value: int) -> int:\n    return value\n"
        controller = WorkspaceController()
        self.addCleanup(controller.close)
        controller.set_source(source)
        workspace_result = controller.convert()
        direct_result = PythonToCConverter().convert(
            ConversionRequest.from_source(source)
        )
        self.assertEqual(workspace_result.generated_c, direct_result.generated_c)
        self.assertEqual(controller.snapshot.source_text, source)
        self.assertEqual(len(controller.snapshot.documents), 1)
        self.assertEqual(controller.snapshot.primary_document.module_id, "main")

    def test_preferences_are_validated_and_plain_serializable_values(self):
        controller = WorkspaceController()
        self.addCleanup(controller.close)
        controller.restore_preferences(
            {"theme": "pycforge", "font_size": 12, "word_wrap": False}
        )
        controller.set_preference("font_size", 13)
        self.assertEqual(
            controller.snapshot.preference_data(),
            {"font_size": 13, "theme": "pycforge", "word_wrap": False},
        )
        with self.assertRaises(TypeError):
            controller.set_preference("bad", object())  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            controller.set_preference("bad", float("nan"))

    def test_semantic_edit_retires_prior_request_observer_artifacts(self):
        controller = WorkspaceController()
        self.addCleanup(controller.close)
        controller.set_source("def invalid(value):\n    return value\n")
        controller.convert()
        self.assertEqual(controller.snapshot.state, WorkspaceState.REJECTED)
        self.assertTrue(controller.snapshot.diagnostics)
        self.assertTrue(controller.snapshot.summary)

        controller.set_source(
            "def valid(value: int) -> int:\n    return value\n"
        )
        self.assertEqual(controller.snapshot.state, WorkspaceState.EMPTY)
        self.assertEqual(controller.snapshot.diagnostics, ())
        self.assertEqual(controller.snapshot.summary, ())
        self.assertIsNone(controller.snapshot.decision_trace)
        self.assertIsNone(controller.snapshot.telemetry)
        self.assertIsNone(controller.snapshot.conversion_summary)

        controller.convert()
        converted_source = controller.snapshot.source_text
        retained_mappings = controller.snapshot.mappings
        controller.set_source(controller.snapshot.source_text + "\n")
        self.assertEqual(controller.snapshot.state, WorkspaceState.STALE)
        self.assertEqual(controller.snapshot.diagnostics, ())
        self.assertEqual(controller.snapshot.summary, ())
        self.assertEqual(controller.snapshot.mappings, retained_mappings)
        self.assertFalse(controller.snapshot.can_save_c)
        controller.set_source(converted_source)
        self.assertEqual(controller.snapshot.state, WorkspaceState.STALE)
        self.assertFalse(controller.snapshot.can_save_c)


if __name__ == "__main__":
    unittest.main()
