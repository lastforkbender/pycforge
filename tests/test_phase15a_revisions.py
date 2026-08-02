from __future__ import annotations

import unittest
from concurrent.futures import CancelledError
from dataclasses import FrozenInstanceError
from threading import Event, get_ident

from pycforge.converter.core.canonicalization import canonicalize
from pycforge.converter.core.fingerprint import fingerprint
from pycforge.ide.model import WorkspaceDocument
from pycforge.ide.revisions import (
    RevisionInput,
    WorkspaceRevisionService,
    build_workspace_revision,
    source_fingerprint,
    workspace_bundle_fingerprint,
)


def document(
    text: str,
    *,
    document_id: str = "doc-main",
    module_id: str = "main",
    logical_name: str = "main.py",
    primary: bool = True,
) -> WorkspaceDocument:
    return WorkspaceDocument(
        document_id=document_id,
        module_id=module_id,
        logical_name=logical_name,
        text=text,
        is_primary=primary,
    )


class Phase15ARevisionIndexTests(unittest.TestCase):
    def test_revision_has_exact_workspace_and_canonical_request_identities(self):
        primary = document("def main() -> int:\n    return 1\n")
        companion = document(
            "VALUE: int = 2\n",
            document_id="doc-helper",
            module_id="helper",
            logical_name="helper.py",
            primary=False,
        )
        documents = (companion, primary)

        revision = build_workspace_revision(
            RevisionInput(41, documents, primary.document_id)
        )

        self.assertEqual(revision.generation, 41)
        self.assertEqual(
            revision.source_fingerprint,
            fingerprint("workspace-source", primary.text).value,
        )
        self.assertEqual(revision.source_fingerprint, source_fingerprint(primary.text))
        self.assertEqual(
            revision.bundle_fingerprint,
            workspace_bundle_fingerprint(documents),
        )
        self.assertEqual(revision.source_bundle.primary.module_id, "main")
        self.assertEqual(
            tuple(item.module_id for item in revision.source_bundle.companions),
            ("helper",),
        )
        canonical, diagnostics = canonicalize(revision.request)
        self.assertEqual(diagnostics, ())
        self.assertIsNotNone(canonical)
        self.assertEqual(
            revision.request_fingerprint,
            canonical.request_fingerprint,
        )
        self.assertEqual(
            revision.resource_fingerprint,
            canonical.resource_fingerprint,
        )
        with self.assertRaises(FrozenInstanceError):
            revision.generation = 42
        with self.assertRaises(FrozenInstanceError):
            revision.active_index.utf8_size = 0

    def test_line_and_utf16_indexes_are_cached_per_document(self):
        text = "A😀\nβ\n"
        revision = build_workspace_revision(
            RevisionInput(1, (document(text),), "doc-main")
        )

        self.assertEqual(revision.line_starts, (0, 3, 5))
        self.assertEqual(revision.utf16_line_starts, (0, 4, 6))
        self.assertEqual(revision.source_utf8_size, len(text.encode("utf-8")))
        self.assertEqual(revision.total_utf8_size, len(text.encode("utf-8")))
        self.assertEqual(revision.active_index.line_count, 3)

    def test_near_maximum_source_is_indexed_off_the_caller_thread(self):
        # 99,999 terminated ten-byte lines plus one nine-byte final line.
        text = "123456789\n" * 99_999 + "123456789"
        self.assertEqual(len(text.encode("utf-8")), 999_999)
        caller_thread = get_ident()
        builder_threads: list[int] = []
        callback_threads: list[int] = []
        published = Event()

        def builder(value: RevisionInput):
            builder_threads.append(get_ident())
            return build_workspace_revision(value)

        def callback(revision):
            callback_threads.append(get_ident())
            published.set()

        service = WorkspaceRevisionService(callback, builder=builder)
        self.addCleanup(service.close)
        revision = service.submit(7, (document(text),), "doc-main").result(timeout=8)

        self.assertTrue(published.wait(timeout=1))
        self.assertEqual(revision.total_utf8_size, 999_999)
        self.assertEqual(revision.active_index.line_count, 100_000)
        self.assertEqual(revision.active_index.line_starts[-1], 999_990)
        self.assertEqual(len(builder_threads), 1)
        self.assertEqual(len(callback_threads), 1)
        self.assertNotEqual(builder_threads[0], caller_thread)
        self.assertEqual(callback_threads[0], builder_threads[0])

    def test_one_active_and_latest_replaceable_pending_are_enforced(self):
        active_started = Event()
        release_active = Event()
        calls: list[int] = []
        published: list[int] = []

        def builder(value: RevisionInput):
            calls.append(value.generation)
            if value.generation == 1:
                active_started.set()
                if not release_active.wait(timeout=5):
                    raise RuntimeError("test revision builder timed out")
            return build_workspace_revision(value)

        service = WorkspaceRevisionService(
            lambda revision: published.append(revision.generation),
            builder=builder,
        )
        self.addCleanup(service.close)
        first = service.submit(1, (document("one\n"),), "doc-main")
        self.assertTrue(active_started.wait(timeout=2))
        self.assertEqual(service.active_generation, 1)

        replaced = service.submit(2, (document("two\n"),), "doc-main")
        latest = service.submit(3, (document("three\n"),), "doc-main")

        self.assertEqual(service.active_generation, 1)
        self.assertEqual(service.pending_generation, 3)
        self.assertTrue(replaced.cancelled())
        with self.assertRaises(CancelledError):
            replaced.result()

        release_active.set()
        self.assertEqual(first.result(timeout=3).generation, 1)
        self.assertEqual(latest.result(timeout=3).generation, 3)
        self.assertTrue(service.wait_idle(timeout=1))
        self.assertEqual(calls, [1, 3])
        self.assertEqual(published, [3])
        self.assertIsNone(service.active_generation)
        self.assertIsNone(service.pending_generation)

    def test_stale_failure_does_not_publish_an_error(self):
        active_started = Event()
        release_active = Event()
        revisions: list[int] = []
        errors: list[int] = []

        def builder(value: RevisionInput):
            if value.generation == 1:
                active_started.set()
                if not release_active.wait(timeout=5):
                    raise RuntimeError("test revision builder timed out")
                raise ValueError("obsolete failure")
            return build_workspace_revision(value)

        service = WorkspaceRevisionService(
            lambda revision: revisions.append(revision.generation),
            on_error=lambda generation, _error: errors.append(generation),
            builder=builder,
        )
        self.addCleanup(service.close)
        stale = service.submit(1, (document("one\n"),), "doc-main")
        self.assertTrue(active_started.wait(timeout=2))
        latest = service.submit(2, (document("two\n"),), "doc-main")
        release_active.set()

        with self.assertRaisesRegex(ValueError, "obsolete failure"):
            stale.result(timeout=3)
        self.assertEqual(latest.result(timeout=3).generation, 2)
        self.assertEqual(revisions, [2])
        self.assertEqual(errors, [])

    def test_close_retires_active_publication_and_cancels_pending(self):
        active_started = Event()
        release_active = Event()
        published: list[int] = []

        def builder(value: RevisionInput):
            active_started.set()
            if not release_active.wait(timeout=5):
                raise RuntimeError("test revision builder timed out")
            return build_workspace_revision(value)

        service = WorkspaceRevisionService(
            lambda revision: published.append(revision.generation),
            builder=builder,
        )
        active = service.submit(1, (document("one\n"),), "doc-main")
        self.assertTrue(active_started.wait(timeout=2))
        pending = service.submit(2, (document("two\n"),), "doc-main")

        service.close(wait=False)
        self.assertTrue(service.is_closed)
        self.assertTrue(pending.cancelled())
        release_active.set()
        self.assertEqual(active.result(timeout=3).generation, 1)
        service.close(wait=True, timeout=2)

        self.assertEqual(published, [])
        self.assertTrue(service.wait_idle(timeout=1))
        with self.assertRaisesRegex(RuntimeError, "closed"):
            service.submit(3, (document("three\n"),), "doc-main")


if __name__ == "__main__":
    unittest.main()
