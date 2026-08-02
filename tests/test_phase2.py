from __future__ import annotations
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from pycforge import ConversionRequest, PythonToCConverter
from pycforge.converter.core.artifact_io import ArtifactCompatibilityError, artifact_from_dict, artifact_to_dict
from pycforge.converter.core.serialization import result_to_dict
from pycforge.converter.core.stage_artifact import StageArtifact
from pycforge.converter.io.atomic_writer import AtomicWriteError, AtomicWriter
from pycforge.laboratory.audits import audit_architecture, audit_determinism, audit_rules
ROOT=Path(__file__).resolve().parents[1]
ENV={**os.environ,"PYTHONPATH":str(ROOT)}

class Phase2Tests(unittest.TestCase):
    def run_cli(self,*args:str)->subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable,"-m","pycforge",*args],cwd=ROOT,env=ENV,text=True,capture_output=True,check=False)

    def test_convert_operates_headlessly_without_generated_c(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"sample.py"; source.write_text("def add(a: int, b: int) -> int:\n    return a + b\n",encoding="utf-8")
            result=self.run_cli("--format","json","convert",str(source))
            self.assertEqual(result.returncode,0,result.stderr)
            value=json.loads(result.stdout)
            self.assertEqual(value["schema_version"],"0.5")
            self.assertEqual(value["status"],"Converted")
            self.assertIsNotNone(value["generated_c"])
            self.assertNotIn("PyQt",result.stdout)

    def test_text_and_json_expose_same_semantic_facts(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"sample.py"; source.write_text("def add(a: int, b: int) -> int:\n    return a + b\n",encoding="utf-8")
            j=self.run_cli("--format","json","convert",str(source)); t=self.run_cli("convert",str(source))
            value=json.loads(j.stdout)
            self.assertIn(f"status: {value['status']}",t.stdout)
            self.assertIn(f"request_fingerprint: {value['request_fingerprint']['value']}",t.stdout)
            self.assertIn("generated_c: available",t.stdout)
            self.assertIn("diagnostics: 0",t.stdout)

    def test_stage_save_load_and_inspect(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"sample.py"; source.write_text("def add(a: int, b: int) -> int:\n    return a + b\n",encoding="utf-8")
            artifact=Path(td)/"stage.json"
            saved=self.run_cli("--format","json","convert",str(source),"--save-stage",str(artifact))
            self.assertEqual(saved.returncode,0,saved.stderr); self.assertTrue(artifact.exists())
            inspected=self.run_cli("--format","json","inspect",str(artifact))
            self.assertEqual(inspected.returncode,0,inspected.stderr)
            self.assertEqual(json.loads(inspected.stdout)["kind"],"initial")

    def test_incompatible_artifact_rejected_before_use(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"bad.json"; path.write_text('{"envelope_version":"99"}',encoding="utf-8")
            result=self.run_cli("--format","json","inspect",str(path))
            self.assertEqual(result.returncode,65)
            self.assertEqual(json.loads(result.stdout)["error"]["category"],"artifact-incompatible")

    def test_artifact_fingerprint_tamper_is_rejected(self):
        data=artifact_to_dict(StageArtifact.initial("abc")); data["payload"]["stage_order"]=["tampered"]
        with self.assertRaisesRegex(ArtifactCompatibilityError,"PYC3105"):
            artifact_from_dict(data,accepted={("initial","0.1")})

    def test_interrupted_atomic_save_preserves_preceding_file(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"result.json"; path.write_text("last-known-good",encoding="utf-8")
            def fail(_:Path)->None: raise RuntimeError("injected")
            with self.assertRaises(AtomicWriteError): AtomicWriter(before_replace=fail).write_text(path,"candidate")
            self.assertEqual(path.read_text(encoding="utf-8"),"last-known-good")
            self.assertEqual(list(Path(td).glob(".*.tmp")),[])

    def test_command_failures_have_stable_category(self):
        result=self.run_cli("--format","json","convert","missing.py")
        self.assertEqual(result.returncode,74)
        self.assertEqual(json.loads(result.stdout)["error"]["code"],"PYC3001")

    def test_decision_diff_excludes_telemetry(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/"a.json"; b=Path(td)/"b.json"
            base=result_to_dict(PythonToCConverter().convert(ConversionRequest.from_source("")))
            changed=dict(base); changed["telemetry"]={"events":[{"duration":123}]}
            a.write_text(json.dumps(base),encoding="utf-8"); b.write_text(json.dumps(changed),encoding="utf-8")
            result=self.run_cli("--format","json","diff",str(a),str(b)); value=json.loads(result.stdout)
            self.assertTrue(value["equal"]); self.assertFalse(value["telemetry_compared"])

    def test_audits_pass(self):
        self.assertTrue(audit_architecture(ROOT)["passed"])
        self.assertTrue(audit_rules(ROOT)["passed"])
        self.assertTrue(audit_determinism(ROOT)["passed"])

    def test_no_native_toolchain_invocation_tokens(self):
        for path in (ROOT/"pycforge").rglob("*.py"):
            text=path.read_text(encoding="utf-8").lower()
            self.assertNotIn("subprocess.run(['gcc'",text)
            self.assertNotIn('subprocess.run(["gcc"',text)

if __name__ == "__main__": unittest.main()
