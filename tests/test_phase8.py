from __future__ import annotations
import json, os, subprocess, sys, unittest
from pathlib import Path
from pycforge import PythonToCConverter, ConversionRequest, ResultStatus

ROOT=Path(__file__).resolve().parents[1]
ENV={**os.environ,'PYTHONPATH':str(ROOT)}

def convert(source:str): return PythonToCConverter().convert(ConversionRequest.from_source(source))

class Phase8Tests(unittest.TestCase):
    def test_if_elif_else(self):
        r=convert('def f(a: int) -> int:\n    if a < 0:\n        return -1\n    elif a > 0:\n        return 1\n    else:\n        return 0\n')
        self.assertEqual(r.status,ResultStatus.CONVERTED); self.assertIn('if (a < 0LL)',r.generated_c); self.assertIn('else',r.generated_c)
    def test_boolean_short_circuit(self):
        r=convert('def f(a: bool, b: bool, c: bool) -> bool:\n    return a and b or c\n')
        self.assertEqual(r.status,ResultStatus.CONVERTED); self.assertIn('a && b || c',r.generated_c)
    def test_chained_comparison_uses_temporaries(self):
        r=convert('def f(a: int, b: int, c: int) -> bool:\n    return a < b < c\n')
        self.assertEqual(r.status,ResultStatus.CONVERTED); self.assertEqual(r.generated_c.count(' = b;'),1); self.assertIn('&&',r.generated_c)
    def test_while_break_continue(self):
        r=convert('def f(a: int) -> int:\n    while a:\n        if a < 0:\n            break\n        a = a - 1\n        continue\n    return a\n')
        self.assertEqual(r.status,ResultStatus.CONVERTED); self.assertIn('while (a != 0LL)',r.generated_c); self.assertIn('break;',r.generated_c); self.assertIn('continue;',r.generated_c)
    def test_for_range_forms(self):
        for header in ('range(n)','range(1, n)','range(n, 0, -1)'):
            r=convert(f'def f(n: int) -> int:\n    for i in {header}:\n        continue\n    return n\n')
            self.assertEqual(r.status,ResultStatus.CONVERTED,header); self.assertIn('for (int64_t i =',r.generated_c)
    def test_loop_else_rejected(self):
        r=convert('def f(a: int) -> int:\n    while a:\n        break\n    else:\n        return 1\n    return 0\n')
        self.assertEqual(r.status,ResultStatus.REJECTED); self.assertEqual(r.diagnostics[0].code,'PYC2830')
    def test_non_range_for_rejected(self):
        r=convert('def f(a: str) -> int:\n    for x in a:\n        continue\n    return 0\n')
        self.assertEqual(r.status,ResultStatus.REJECTED); self.assertEqual(r.diagnostics[0].code,'PYC2841')
    def test_branch_defined_binding_rejected(self):
        r=convert('def f(a: int) -> int:\n    if a:\n        x = 1\n    return a\n')
        self.assertEqual(r.status,ResultStatus.REJECTED); self.assertEqual(r.diagnostics[0].code,'PYC2870')
    def test_mapping_contains_control_flow_and_temps(self):
        r=convert('def f(a: int, b: int, c: int) -> bool:\n    if a:\n        return a < b < c\n    return False\n')
        self.assertEqual(r.status,ResultStatus.CONVERTED); kinds={m['origin_kind'] for m in r.stage_artifact.payload['source_output_mappings']}; self.assertIn('synthetic',kinds)
    def test_decision_trace_contains_phase8_rules(self):
        r=convert('def f(a: bool, b: bool) -> bool:\n    return a and b\n')
        rules={p['rule_id'] for p in r.stage_artifact.payload['rule_plans']}; self.assertIn('phase8.boolean.short_circuit',rules)
    def test_cross_process_determinism(self):
        code="from pycforge import *;r=PythonToCConverter().convert(ConversionRequest.from_source('def f(a: int)->int:\\n    while a:\\n        a = a - 1\\n    return a\\n'));print(r.output_fingerprint.value)"
        vals=[subprocess.check_output([sys.executable,'-c',code],cwd=ROOT,env=ENV,text=True).strip() for _ in range(2)]
        self.assertEqual(vals[0],vals[1])
    def test_gui_facade_equivalence_remains(self):
        from pycforge.ide.controller import WorkspaceController
        src='def f(a: int) -> int:\n    if a:\n        return 1\n    return 0\n'; direct=convert(src); c=WorkspaceController(); self.addCleanup(c.close); c.set_source(src); gui=c.convert(); self.assertEqual(direct.generated_c,gui.generated_c); self.assertEqual(direct.stage_artifact.payload["rule_plans"],gui.stage_artifact.payload["rule_plans"])

if __name__=='__main__': unittest.main()
