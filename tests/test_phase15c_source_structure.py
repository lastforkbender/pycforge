from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
from threading import Event
import unittest
from unittest.mock import patch

from pycforge.ide.source_structure import (
    AsyncSourceStructureService,
    MAX_OUTLINE_SYMBOLS,
    OutlineSymbol,
    SourceStructureDocument,
    breadcrumbs_for_position,
    build_source_structure,
)
import pycforge.ide.source_structure as structure_module
import pycforge.ide.source_structure_async as structure_async


ROOT = Path(__file__).resolve().parents[1]
NESTED_SOURCE = """\
class Vessel:
    def method(self):
        def nested():
            return 1
        return nested()

async def later():
    return 2
"""


def document(
    document_id: str,
    text: str,
    *,
    module_id: str | None = None,
    logical_name: str | None = None,
) -> SourceStructureDocument:
    return SourceStructureDocument(
        document_id,
        module_id or document_id,
        logical_name or f"{document_id}.py",
        text,
    )


class Phase15CSourceStructureTests(unittest.TestCase):
    def test_normalized_outline_is_parent_linked_and_breadcrumb_ready(
        self,
    ) -> None:
        result = build_source_structure(
            (document("main", NESTED_SOURCE),),
            generation=9,
            workspace_key="bundle-fingerprint",
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.generation, 9)
        self.assertEqual(result.workspace_key, "bundle-fingerprint")
        self.assertEqual(result.invalid_document_ids, ())
        self.assertFalse(result.truncated)
        self.assertEqual(result.total_symbol_count, 5)
        self.assertEqual(
            [(item.kind, item.name, item.detail, item.depth) for item in result.symbols],
            [
                ("Module", "main", "module", 0),
                ("ClassDef", "Vessel", "class", 1),
                ("FunctionDef", "method", "function", 2),
                ("FunctionDef", "nested", "function", 3),
                ("AsyncFunctionDef", "later", "async function", 1),
            ],
        )
        by_name = {item.name: item for item in result.symbols}
        self.assertEqual(
            by_name["method"].parent_node_id,
            by_name["Vessel"].node_id,
        )
        self.assertEqual(
            by_name["nested"].parent_node_id,
            by_name["method"].node_id,
        )
        position = NESTED_SOURCE.index("return 1")
        self.assertEqual(
            [
                item.name
                for item in breadcrumbs_for_position(
                    result, "main", position
                )
            ],
            ["main", "Vessel", "method", "nested"],
        )
        eof = breadcrumbs_for_position(
            result, "main", len(NESTED_SOURCE)
        )
        self.assertEqual([item.name for item in eof], ["main"])

    def test_invalid_syntax_is_inert_and_other_open_documents_survive(
        self,
    ) -> None:
        result = build_source_structure(
            (
                document("bad", "def broken(:\n"),
                document("good", "def accepted():\n    return 1\n"),
            )
        )
        assert result is not None
        self.assertEqual(result.invalid_document_ids, ("bad",))
        self.assertEqual(result.observer_failed_document_ids, ())
        self.assertEqual(
            [(item.document_id, item.name) for item in result.symbols],
            [("good", "good"), ("good", "accepted")],
        )
        self.assertFalse(result.truncated)

        with patch.object(
            structure_module,
            "_document_candidates",
            side_effect=RuntimeError("injected observer failure"),
        ):
            failed = build_source_structure(
                (document("observer", "def value():\n    return 1\n"),)
            )
        assert failed is not None
        self.assertEqual(failed.symbols, ())
        self.assertEqual(
            failed.observer_failed_document_ids, ("observer",)
        )

    def test_symbol_depth_name_count_and_text_budgets_are_hard(
        self,
    ) -> None:
        many = "\n".join(
            f"def function_{index}():\n    return {index}"
            for index in range(12)
        )
        capped = build_source_structure(
            (document("main", many),),
            max_symbols=3,
        )
        assert capped is not None
        self.assertEqual(len(capped.symbols), 3)
        self.assertEqual(capped.total_symbol_count, 13)
        self.assertTrue(capped.truncated)

        depth = build_source_structure(
            (document("main", NESTED_SOURCE),),
            max_depth=1,
        )
        assert depth is not None
        self.assertEqual(
            [item.name for item in depth.symbols],
            ["main", "Vessel", "later"],
        )
        self.assertTrue(depth.truncated)

        long_name = "function_" + "x" * 80
        clipped = build_source_structure(
            (
                document(
                    "main",
                    f"def {long_name}():\n    return 1\n",
                ),
            ),
            max_name_chars=12,
        )
        assert clipped is not None
        function = clipped.symbols[1]
        self.assertEqual(len(function.name), 12)
        self.assertTrue(function.name.endswith("…"))
        self.assertTrue(clipped.truncated)

        text_capped = build_source_structure(
            (document("main", "def one():\n    return 1\n"),),
            max_text_chars=1,
        )
        assert text_capped is not None
        self.assertEqual(text_capped.symbols, ())
        self.assertEqual(text_capped.total_symbol_count, 2)
        self.assertTrue(text_capped.truncated)

    def test_cancel_input_validation_and_immutability_fail_closed(
        self,
    ) -> None:
        self.assertIsNone(
            build_source_structure(
                (document("main", "def f():\n    pass\n"),),
                cancelled=lambda: True,
            )
        )
        with self.assertRaisesRegex(ValueError, "between 1 and 64"):
            build_source_structure((), generation=1)
        with self.assertRaisesRegex(ValueError, "document IDs"):
            build_source_structure(
                (
                    document("same", "", module_id="one"),
                    document("same", "", module_id="two"),
                )
            )
        with self.assertRaisesRegex(ValueError, "module IDs"):
            build_source_structure(
                (
                    document("one", "", module_id="same"),
                    document("two", "", module_id="same"),
                )
            )
        with self.assertRaises(TypeError):
            build_source_structure((object(),))  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            build_source_structure(
                (document("main", ""),),
                max_symbols=MAX_OUTLINE_SYMBOLS + 1,
            )

        captured = document("main", "")
        self.assertFalse(hasattr(captured, "path"))
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            captured.text = "changed"  # type: ignore[misc]
        result = build_source_structure((captured,))
        assert result is not None
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            result.symbols = ()  # type: ignore[misc]
        self.assertTrue(
            all(isinstance(item, OutlineSymbol) for item in result.symbols)
        )

    def test_service_keeps_one_active_and_only_latest_key_publishes(
        self,
    ) -> None:
        active_started = Event()
        release_active = Event()
        latest_done = Event()
        observed = []
        real_build = structure_async.build_source_structure

        def blocked(documents, **kwargs):
            if kwargs["workspace_key"] == "first":
                active_started.set()
                self.assertTrue(release_active.wait(2.0))
            return real_build(documents, **kwargs)

        service = AsyncSourceStructureService()
        try:
            with patch.object(
                structure_async, "build_source_structure", blocked
            ):
                first = service.submit(
                    (document("main", "def first():\n    pass\n"),),
                    workspace_key="first",
                    callback=lambda result: observed.append(
                        result.workspace_key
                    ),
                )
                self.assertTrue(active_started.wait(2.0))
                middle = service.submit(
                    (document("main", "def middle():\n    pass\n"),),
                    workspace_key="middle",
                    callback=lambda result: observed.append(
                        result.workspace_key
                    ),
                )
                latest = service.submit(
                    (document("main", "def latest():\n    pass\n"),),
                    workspace_key="latest",
                    callback=lambda result: (
                        observed.append(result.workspace_key),
                        latest_done.set(),
                    ),
                )
                self.assertEqual(service.active_generation, first)
                self.assertEqual(service.pending_generation, latest)
                self.assertNotEqual(middle, latest)
                release_active.set()
                self.assertTrue(latest_done.wait(2.0))
            self.assertEqual(observed, ["latest"])
            self.assertTrue(service.worker_is_daemon)
        finally:
            release_active.set()
            service.close()

    def test_cancel_suppresses_observer_publication(
        self,
    ) -> None:
        active_started = Event()
        release_active = Event()
        observed = []
        real_build = structure_async.build_source_structure

        def blocked(documents, **kwargs):
            active_started.set()
            self.assertTrue(release_active.wait(2.0))
            return real_build(documents, **kwargs)

        service = AsyncSourceStructureService()
        try:
            with patch.object(
                structure_async, "build_source_structure", blocked
            ):
                generation = service.submit(
                    (document("main", "def old():\n    pass\n"),),
                    workspace_key="old",
                    callback=observed.append,
                )
                self.assertTrue(active_started.wait(2.0))
                self.assertGreater(service.cancel(), generation)
                release_active.set()
            self.assertEqual(observed, [])
        finally:
            release_active.set()
            service.close()
        with self.assertRaisesRegex(RuntimeError, "closed"):
            service.submit(
                (document("main", ""),),
                workspace_key="closed",
                callback=observed.append,
            )

    def test_service_survives_observer_and_callback_failures(
        self,
    ) -> None:
        completed = Event()
        fault_started = Event()
        observed = []
        real_build = structure_async.build_source_structure

        def fail_once(documents, **kwargs):
            if kwargs["workspace_key"] == "fault":
                fault_started.set()
                raise RuntimeError("injected observer failure")
            return real_build(documents, **kwargs)

        service = AsyncSourceStructureService()
        try:
            with patch.object(
                structure_async, "build_source_structure", fail_once
            ):
                service.submit(
                    (document("main", "def fault():\n    pass\n"),),
                    workspace_key="fault",
                    callback=observed.append,
                )
                self.assertTrue(fault_started.wait(2.0))
                service.submit(
                    (document("main", "def ready():\n    pass\n"),),
                    workspace_key="ready",
                    callback=lambda result: (
                        observed.append(result.workspace_key),
                        completed.set(),
                        (_ for _ in ()).throw(
                            RuntimeError("callback failure")
                        ),
                    ),
                )
                self.assertTrue(completed.wait(2.0))
            self.assertEqual(observed, ["ready"])
        finally:
            service.close()

    def test_modules_are_headless_bounded_and_parse(
        self,
    ) -> None:
        for relative in (
            "pycforge/ide/source_structure.py",
            "pycforge/ide/source_structure_async.py",
        ):
            path = ROOT / relative
            source = path.read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                ast.parse(source, filename=str(path))
                self.assertLess(len(source.splitlines()), 600)
                self.assertNotIn("from pathlib", source)
                self.assertNotIn("open(", source)


if __name__ == "__main__":
    unittest.main()
