from __future__ import annotations
import ast,json,os,subprocess,sys,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from pycforge import ConversionRequest,PythonToCConverter,ResultStatus
from pycforge.converter.core.resource_policy import ResourcePolicy
from pycforge.converter.frontend.normalizer import PythonNormalizer
from pycforge.converter.frontend.source_document import SourceDocument
from pycforge.converter.frontend.validation import validate_python_ir
from pycforge.converter.analysis.symbols import PythonIRIndex
ROOT=Path(__file__).resolve().parents[1]
ENV={**os.environ,"PYTHONPATH":str(ROOT)}

class Phase3Tests(unittest.TestCase):
    def test_frontend_pipeline_publishes_normalized_ir(self):
        out=PythonToCConverter().convert(ConversionRequest.from_source(
            "x = 1\n",
            rule_set_version="phase3-frontend-v0.3",
            renderer_version="phase3-none-v0.3",
        ))
        self.assertNotEqual(out.status,ResultStatus.INTERNAL_FAILURE)
        self.assertEqual(out.stage_order[:3],("frontend.source_document","frontend.parse","frontend.normalize"))
        self.assertIn(out.stage_artifact.kind,{"python_ir","conversion_plan","generated_c"})
        self.assertEqual(out.stage_artifact.payload["python_ir"]["schema_version"],"python-ir/0.3")
        self.assertIsNone(out.generated_c)

    def test_normalization_is_idempotent_and_deterministic(self):
        text="def add(a: int, b: int) -> int:\n    label = 'value'\n    return a + b\n"
        doc=SourceDocument.create("main.py",text); tree=ast.parse(text,feature_version=(3,11),type_comments=True)
        n=PythonNormalizer(); normalized=n.normalize(tree,doc); a=normalized.to_dict(); b=n.normalize(tree,doc).to_dict()
        self.assertEqual(a,b)
        self.assertNotIn("generated_c",json.dumps(a))
        self.assertNotIn("type_params",json.dumps(a))
        return_node=next(node for node in normalized.nodes if node.kind=="Return")
        broken_return=replace(return_node,fields=tuple((name,"py-missing") if name=="value" else (name,value) for name,value in return_node.fields))
        broken=replace(normalized,nodes=tuple(broken_return if node is return_node else node for node in normalized.nodes))
        self.assertFalse(validate_python_ir(broken)[0])
        normalized_dict=normalized.to_dict(); constant=next(node for node in normalized_dict["nodes"] if node["kind"]=="Constant")
        constant["fields"]["value"]=normalized_dict["root_node_id"]
        self.assertEqual(PythonIRIndex(normalized_dict).child_ids(constant),())

    def test_unicode_tabs_and_mixed_newlines_are_preserved(self):
        text="# å\r\nx = 'β'\n\t# tab\r"
        doc=SourceDocument.create("unicode.py",text)
        self.assertEqual(doc.newline_sequences,("\r\n","\n","\r"))
        self.assertEqual(doc.text,text)
        out=PythonToCConverter().convert(ConversionRequest.from_source(text,logical_name="unicode.py"))
        self.assertNotEqual(out.status,ResultStatus.INTERNAL_FAILURE)

    def test_invalid_syntax_has_stable_span_diagnostic(self):
        for source in ("x = (\n","def f(:\n","å = 1 +\n"):
            out=PythonToCConverter().convert(ConversionRequest.from_source(source))
            self.assertEqual(out.status,ResultStatus.REJECTED)
            diag=next(d for d in out.diagnostics if d.code in {"PYC2001","PYC2002"})
            self.assertIsNotNone(diag.source_span)
            self.assertIn("offset",diag.source_span["start"])
            self.assertIn("offset",diag.source_span["end"])
            self.assertIsNone(out.generated_c)

    def test_token_ceiling_rejects_without_partial_ir(self):
        policy=ResourcePolicy(max_tokens=1)
        out=PythonToCConverter().convert(ConversionRequest.from_source("x=1\n",resource_policy=policy))
        self.assertEqual(out.status,ResultStatus.REJECTED)
        self.assertEqual(out.diagnostics[0].code,"PYC3510")
        self.assertNotEqual(out.stage_artifact.kind,"python_ir")

    def test_ast_node_ceiling_rejects(self):
        policy=ResourcePolicy(max_ast_nodes=2)
        out=PythonToCConverter().convert(ConversionRequest.from_source("x=1\n",resource_policy=policy))
        self.assertEqual(out.status,ResultStatus.REJECTED)
        self.assertIn("PYC3510",{d.code for d in out.diagnostics})
        unsafe=PythonToCConverter().convert(ConversionRequest.from_source("",resource_policy=ResourcePolicy(max_nesting_depth=129)))
        self.assertEqual(unsafe.status,ResultStatus.REJECTED)
        self.assertEqual(unsafe.diagnostics[0].code,"PYC1005")
        deep="def f(x: int) -> int:\n    return "+"- "*200+"x\n"
        bounded=PythonToCConverter().convert(ConversionRequest.from_source(deep))
        self.assertEqual(bounded.status,ResultStatus.REJECTED)
        self.assertEqual(bounded.diagnostics[0].code,"PYC2006")
        near="def f(x: int) -> int:\n    return "+"- "*100+"x\n"
        self.assertEqual(PythonToCConverter().convert(ConversionRequest.from_source(near)).status,ResultStatus.CONVERTED)

    def test_synthetic_provenance_has_distinct_id_domain(self):
        node=PythonNormalizer().synthetic("NormalizedTemporary",("py-deadbeef",),{"purpose":"ordering"})
        self.assertTrue(node.node_id.startswith("syn-"))
        self.assertEqual(node.provenance.origin_kind,"synthetic")
        self.assertEqual(node.provenance.origin_node_ids,("py-deadbeef",))

    def test_final_stage_can_be_saved_and_inspected(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/"a.py"; dst=Path(td)/"ir.json"; src.write_text("def add(a: int, b: int) -> int:\n    return a + b\n",encoding="utf-8")
            saved=subprocess.run([sys.executable,"-m","pycforge","--format","json","convert",str(src),"--save-final-stage",str(dst)],cwd=ROOT,env=ENV,text=True,capture_output=True)
            self.assertEqual(saved.returncode,0,saved.stderr)
            inspected=subprocess.run([sys.executable,"-m","pycforge","--format","json","inspect",str(dst)],cwd=ROOT,env=ENV,text=True,capture_output=True)
            self.assertEqual(inspected.returncode,0,inspected.stderr)
            self.assertIn(json.loads(inspected.stdout)["kind"],{"python_ir","conversion_plan","generated_c"})

    def test_source_is_never_executed(self):
        with tempfile.TemporaryDirectory() as td:
            marker=Path(td)/"executed"
            source=f"open({str(marker)!r}, 'w').write('bad')\n"
            out=PythonToCConverter().convert(ConversionRequest.from_source(source))
            self.assertNotEqual(out.status,ResultStatus.INTERNAL_FAILURE)
            self.assertFalse(marker.exists())

    def test_cross_process_python_ir_determinism(self):
        code=("from pycforge import *;import json;"
              "r=PythonToCConverter().convert(ConversionRequest.from_source('x=1\\n',rule_set_version='phase3-frontend-v0.3',renderer_version='phase3-none-v0.3'));"
              "print(json.dumps(r.stage_artifact.payload['python_ir'],sort_keys=True,separators=(',',':')))" )
        a=subprocess.check_output([sys.executable,"-c",code],cwd=ROOT,env=ENV,text=True)
        b=subprocess.check_output([sys.executable,"-c",code],cwd=ROOT,env=ENV,text=True)
        self.assertEqual(a,b)

if __name__=="__main__": unittest.main()
