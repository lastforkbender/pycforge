from __future__ import annotations
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.core.cancellation import CancellationToken
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.c_output import validate_c_text

ROOT=Path(__file__).resolve().parents[1]
ENV={**os.environ,"PYTHONPATH":str(ROOT)}
ADD="def add(a: int, b: int) -> int:\n    return a + b\n"

def convert(source=ADD, **kwargs):
    req=ConversionRequest.from_source(source,rule_set_version="phase6-first-slice-v0.6",renderer_version="c-renderer-v0.6")
    return PythonToCConverter().convert(req,**kwargs)

class Phase6Tests(unittest.TestCase):
    def test_first_complete_slice_matches_golden(self):
        r=convert(); self.assertEqual(r.status,ResultStatus.CONVERTED)
        self.assertEqual(r.generated_c,(ROOT/'fixtures/first_milestone/expected.c').read_text())
        self.assertEqual(r.last_completed_stage,'lowering.first_slice')

    def test_generated_c_has_independent_conformance(self):
        r=convert(); self.assertTrue(validate_c_text(r.generated_c).accepted)
        self.assertEqual(r.stage_artifact.payload['c_ir_schema'],'c-ir/0.8')

    def test_assignment_and_integer_literal(self):
        r=convert('def f(a: int) -> int:\n    x = 2\n    return a + x\n')
        self.assertEqual(r.status,ResultStatus.CONVERTED); self.assertIn('int64_t x = 2LL;',r.generated_c)

    def test_float_boolean_and_utf8_string_literals(self):
        cases=(
            ('def f(a: float) -> float:\n    return a * 2.0\n','double f(double a)','a * 2.0'),
            ('def f() -> bool:\n    return True\n','bool f(void)','return true;'),
            ('def f() -> str:\n    return "β"\n','char * f(void)','"\\xce\\xb2"'),
            ('def f() -> str:\n    return "py-value"\n','char * f(void)','"py-value"'),
            ('def f() -> str:\n    return "syn-value"\n','char * f(void)','"syn-value"'),
        )
        for source,*needles in cases:
            r=convert(source); self.assertEqual(r.status,ResultStatus.CONVERTED)
            for needle in needles:self.assertIn(needle,r.generated_c)

    def test_selected_arithmetic_is_bounded(self):
        for op in ('+','-','*','/'):
            r=convert(f'def f(a: float, b: float) -> float:\n    return a {op} b\n')
            self.assertEqual(r.status,ResultStatus.CONVERTED)
        r=convert('def f(a: int, b: int) -> int:\n    return a ** b\n')
        self.assertEqual(r.status,ResultStatus.REJECTED); self.assertEqual(r.diagnostics[0].code,'PYC2622')

    def test_neighboring_constructs_reject_cleanly(self):
        sources=(
            'def f(a):\n    return a\n',
            'def f(a: int = 1) -> int:\n    return a\n',
            'def f() -> str:\n    return "a" + "b"\n',
            'def f(a: int) -> int:\n    return g(a)\n',
        )
        for source in sources:
            r=convert(source); self.assertEqual(r.status,ResultStatus.REJECTED); self.assertIsNone(r.generated_c); self.assertTrue(r.diagnostics)

    def test_mappings_cover_function_return_expression_and_names(self):
        maps=convert().stage_artifact.payload['source_output_mappings']
        kinds={m['c_node_id'].split('-')[1] for m in maps}
        self.assertTrue({'fn','ret','bin','ref'}.issubset(kinds))
        for m in maps:
            self.assertLessEqual(m['start_byte'],m['end_byte'])
            self.assertGreaterEqual(m['start_line'],1)

    def test_ruleplans_are_retained_in_published_result(self):
        payload=convert().stage_artifact.payload
        ids={p['rule_id'] for p in payload['rule_plans']}
        self.assertIn('phase6.function.annotated',ids); self.assertIn('phase6.numeric.arithmetic',ids)
        self.assertTrue(all(not p['unresolved_obligations'] for p in payload['rule_plans']))

    def test_observers_cannot_change_conversion_artifacts(self):
        plain=convert(); noisy=convert(observation=ObservationOptions('Full',True),inject_trace_failure=True,inject_telemetry_failure=True)
        self.assertEqual(plain.semantic_dict(),noisy.semantic_dict())
        self.assertEqual(plain.stage_artifact.artifact_fingerprint,noisy.stage_artifact.artifact_fingerprint)

    def test_cross_process_output_is_byte_identical(self):
        code=("from pycforge import *;r=PythonToCConverter().convert(ConversionRequest.from_source("+repr(ADD)+",rule_set_version='phase6-first-slice-v0.6',renderer_version='c-renderer-v0.6'));print(r.generated_c,end='')")
        a=subprocess.check_output([sys.executable,'-c',code],cwd=ROOT,env=ENV)
        b=subprocess.check_output([sys.executable,'-c',code],cwd=ROOT,env=ENV)
        self.assertEqual(a,b)

    def test_cancellation_publishes_no_generated_c(self):
        token=CancellationToken();token.cancel();r=convert(cancellation=token)
        self.assertEqual(r.status,ResultStatus.CANCELED);self.assertIsNone(r.generated_c)

    def test_cli_convert_inspect_and_validate(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'add.py';art=Path(td)/'result.json';src.write_text(ADD)
            convert_p=subprocess.run([sys.executable,'-m','pycforge','--format','json','convert',str(src),'--save-final-stage',str(art)],cwd=ROOT,env=ENV,text=True,capture_output=True)
            self.assertEqual(convert_p.returncode,0,convert_p.stderr);self.assertIn('int64_t add',json.loads(convert_p.stdout)['generated_c'])
            inspect_p=subprocess.run([sys.executable,'-m','pycforge','--format','json','inspect',str(art)],cwd=ROOT,env=ENV,text=True,capture_output=True)
            self.assertEqual(json.loads(inspect_p.stdout)['kind'],'generated_c')
            valid_p=subprocess.run([sys.executable,'-m','pycforge','--format','json','validate','--source',str(src)],cwd=ROOT,env=ENV,text=True,capture_output=True)
            self.assertTrue(json.loads(valid_p.stdout)['valid'])

if __name__=='__main__':unittest.main()
