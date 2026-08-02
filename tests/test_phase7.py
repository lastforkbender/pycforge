from __future__ import annotations
import json, tempfile, unittest
from concurrent.futures import CancelledError
from pathlib import Path
from pycforge.converter.core.request import ConversionRequest
from pycforge.converter.facade import PythonToCConverter
from pycforge.converter.io.atomic_writer import AtomicWriter, AtomicWriteError
from pycforge.ide import QT_AVAILABLE, WorkspaceController, WorkspaceState
from pycforge.ide.supervisor import ConversionCancelled

ADD='def add(a: int, b: int) -> int:\n    return a + b\n'
BAD='def f(a):\n    return a\n'

class Phase7Tests(unittest.TestCase):
    def test_controller_uses_facade_and_publishes_complete_result(self):
        c=WorkspaceController(); self.addCleanup(c.close); c.set_source(ADD); r=c.convert()
        self.assertEqual(c.snapshot.state,WorkspaceState.CONVERTED); self.assertEqual(c.snapshot.generated_c,r.generated_c)
        self.assertTrue(c.snapshot.summary); self.assertTrue(c.snapshot.decision_trace is not None); self.assertTrue(c.snapshot.telemetry is not None)

    def test_source_edit_marks_output_stale_and_prevents_save(self):
        c=WorkspaceController(); self.addCleanup(c.close); c.set_source(ADD); c.convert(); c.set_source(ADD+'\n')
        self.assertEqual(c.snapshot.state,WorkspaceState.STALE)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError): c.save_generated_c(Path(td)/'out.c')

    def test_late_result_cannot_replace_newer_source(self):
        c=WorkspaceController(); self.addCleanup(c.close)
        snapshots=[]; c.subscribe(snapshots.append)
        c.set_source(ADD.replace('add','slow')); old=c.convert_async(); c.set_source(ADD); new=c.convert_async(); new.result(); published=len(snapshots)
        with self.assertRaises((ConversionCancelled, CancelledError)): old.result()
        self.assertEqual(len(snapshots),published)
        self.assertIn('int64_t add',c.snapshot.generated_c); self.assertNotIn('slow',c.snapshot.generated_c)

    def test_rejected_request_does_not_replace_last_complete_c(self):
        c=WorkspaceController(); self.addCleanup(c.close); c.set_source(ADD); c.convert(); previous=c.snapshot.generated_c
        c.set_source(BAD); c.convert(); self.assertEqual(c.snapshot.state,WorkspaceState.REJECTED); self.assertEqual(c.snapshot.generated_c,previous)

    def test_atomic_open_and_save(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/'in.py'; out=root/'out.py'; cfile=root/'out.c'; src.write_text(ADD,encoding='utf-8')
            c=WorkspaceController(); self.addCleanup(c.close); self.assertEqual(c.open_python(src),ADD); c.save_python(out); c.convert(); c.save_generated_c(cfile)
            self.assertEqual(out.read_text(),ADD); self.assertEqual(cfile.read_text(),c.snapshot.generated_c)

    def test_atomic_save_interruption_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'source.py'; p.write_text('old')
            def fail(_): raise RuntimeError('injected')
            c=WorkspaceController(writer=AtomicWriter(before_replace=fail)); self.addCleanup(c.close); c.set_source(ADD)
            with self.assertRaises(AtomicWriteError): c.save_python(p)
            self.assertEqual(p.read_text(),'old')

    def test_mapping_navigation_is_provenance_based(self):
        c=WorkspaceController(); self.addCleanup(c.close); c.set_source(ADD); c.convert(); node=next(m['source_node_ids'][0] for m in c.snapshot.mappings if m.get('source_node_ids'))
        self.assertTrue(c.navigate_source_to_output(node))

    def test_qt_is_optional_for_headless_engine(self):
        self.assertIsInstance(QT_AVAILABLE,bool)
        c=WorkspaceController(); self.addCleanup(c.close); c.set_source(ADD); self.assertEqual(c.convert().generated_c,c.snapshot.generated_c)

    def test_workspace_has_no_execution_controls(self):
        qt=Path('pycforge/ide/qt.py').read_text()
        forbidden=('Run','Build','Debug','Terminal','compiler','toolchain')
        for word in forbidden: self.assertNotIn("'"+word+"'",qt)

    def test_svg_iconography_is_custom_and_non_ascii(self):
        icons=Path('pycforge/ide/resources/icons')
        names={p.name for p in icons.glob('*.svg')}
        self.assertTrue({'open.svg','save.svg','convert.svg','export.svg','cancel.svg'} <= names)
        self.assertTrue(all('<svg' in p.read_text() for p in icons.glob('*.svg')))
        self.assertFalse(any(icons.glob('*.png')))

if __name__=='__main__': unittest.main()
