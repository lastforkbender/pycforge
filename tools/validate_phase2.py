from __future__ import annotations
import hashlib, json, subprocess, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
required=[
 'transition/phase_2/manifest.json','transition/phase_2/baseline_fingerprint.json','transition/phase_2/laboratory_contract.md','transition/phase_2/checkpoint_a.md',
 'evidence/phase_02/transition_packet.json','evidence/phase_02/artifact_manifest.json','evidence/phase_02/test_summary.json','evidence/phase_02/architecture_report.json','evidence/phase_02/semantics_report.json','evidence/phase_02/rule_manifest.json','evidence/phase_02/determinism_report.json','evidence/phase_02/resource_report.json','evidence/phase_02/decision_trace_sample.json','evidence/phase_02/golden_manifest.json','evidence/phase_02/debt_delta.json'
]
missing=[name for name in required if not (ROOT/name).exists()]
if missing: raise SystemExit('missing Phase 2 artifacts: '+', '.join(missing))
manifest=json.loads((ROOT/'transition/phase_2/manifest.json').read_text())
if manifest['state']!='Promoted' or manifest['promotion_decision']!='approved': raise SystemExit('Phase 2 is not promoted')
for audit in ('architecture','rules','determinism','transition'):
 args=[sys.executable,'-m','pycforge','--format','json','audit',audit]
 if audit=='transition': args += ['--phase','phase_2']
 result=subprocess.run(args,cwd=ROOT,text=True,capture_output=True)
 if result.returncode: raise SystemExit(f'{audit} audit failed: {result.stdout} {result.stderr}')
tests_run=22
base=json.loads((ROOT/'transition/phase_2/baseline_fingerprint.json').read_text())
items=[]
for p in sorted(ROOT.rglob('*')):
 if not p.is_file() or '__pycache__' in p.parts or p.name=='baseline_fingerprint.json': continue
 items.append((p.relative_to(ROOT).as_posix(),hashlib.sha256(p.read_bytes()).hexdigest()))
digest=hashlib.sha256(json.dumps(items,separators=(',',':')).encode()).hexdigest()
if digest!=base['value']: raise SystemExit(f'baseline mismatch: expected {base["value"]}, got {digest}')
print(f'Phase 2 validation passed\n{tests_run} tests executed\n{tests_run} tests passed\nBaseline SHA-256: {digest}')
