from __future__ import annotations
import json, subprocess, sys, threading, unittest
from dataclasses import dataclass
from pathlib import Path
from pycforge import PythonToCConverter,ConversionRequest,ResultStatus
from pycforge.converter.core.cancellation import CancellationToken
from pycforge.converter.core.enums import StageTerminal,Severity
from pycforge.converter.core.diagnostics import Diagnostic
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.core.stage_outcome import StageOutcome
ROOT=Path(__file__).resolve().parents[1]
class Phase1Tests(unittest.TestCase):
    def test_identical_requests_are_deterministic(self):
        c=PythonToCConverter(); r=ConversionRequest.from_source("def add(a: int, b: int) -> int:\n    return a + b\n")
        a=c.convert(r); b=c.convert(r)
        self.assertEqual(a.semantic_dict(),b.semantic_dict()); self.assertEqual(a.status,ResultStatus.CONVERTED); self.assertIsNotNone(a.generated_c)
    def test_malformed_request_is_structured_rejection(self):
        out=PythonToCConverter().convert(ConversionRequest.from_source("",logical_name="/absolute.py"))
        self.assertEqual(out.status,ResultStatus.REJECTED); self.assertEqual(out.diagnostics[0].code,"PYC3501"); self.assertIsNone(out.output_fingerprint)
    def test_observers_cannot_change_semantic_result(self):
        r=ConversionRequest.from_source("")
        base=PythonToCConverter().convert(r)
        noisy=PythonToCConverter().convert(r,observation=ObservationOptions("Full",True),inject_trace_failure=True,inject_telemetry_failure=True)
        self.assertEqual(base.semantic_dict(),noisy.semantic_dict()); self.assertTrue(noisy.decision_trace["observer_failed"]); self.assertTrue(noisy.telemetry["observer_failed"])
    def test_cancel_publishes_no_successor(self):
        token=CancellationToken(); token.cancel(); out=PythonToCConverter().convert(ConversionRequest.from_source(""),cancellation=token)
        self.assertEqual(out.status,ResultStatus.CANCELED); self.assertEqual(out.stage_order,()); self.assertIsNone(out.last_completed_stage)
    def test_rejected_stage_publishes_no_successor(self):
        @dataclass(frozen=True)
        class Reject:
            stage_id:str="reject"; input_schema:str="initial/0.1"; output_schema:str="none"
            def run(self,a,s):return StageOutcome(StageTerminal.REJECTED,diagnostics=(Diagnostic("PYC2000",Severity.ERROR,"reject","rejected"),))
            def validate(self,a,s):raise AssertionError
        from pycforge.converter.core.pipeline import Pipeline
        out=PythonToCConverter(Pipeline((Reject(),))).convert(ConversionRequest.from_source(""))
        self.assertEqual(out.status,ResultStatus.REJECTED); self.assertEqual(out.stage_order,())
    def test_concurrent_requests_do_not_share_state(self):
        results=[]
        def work(i):results.append(PythonToCConverter().convert(ConversionRequest.from_source(str(i))))
        ts=[threading.Thread(target=work,args=(i,)) for i in range(20)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(len(results),20); self.assertEqual(len({r.request_fingerprint.value for r in results}),20)
    def test_cross_process_fingerprint(self):
        code='from pycforge import *; import json; r=PythonToCConverter().convert(ConversionRequest.from_source("x=1")); print(json.dumps(r.semantic_dict(),sort_keys=True))'
        env={"PYTHONPATH":str(ROOT)}
        import os; env={**os.environ,**env}
        a=subprocess.check_output([sys.executable,"-c",code],cwd=ROOT,env=env,text=True); b=subprocess.check_output([sys.executable,"-c",code],cwd=ROOT,env=env,text=True)
        self.assertEqual(a,b)
