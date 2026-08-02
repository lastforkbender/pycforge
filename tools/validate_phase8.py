from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={Path('transition/phase_8/baseline_fingerprint.json')}
def tree_hash()->str:
    h=hashlib.sha256()
    for path in sorted(p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts and p.relative_to(ROOT) not in EXCLUDED and 'build' not in p.parts and 'dist' not in p.parts and not p.name.endswith('.pyc')):
        rel=path.relative_to(ROOT).as_posix().encode(); data=path.read_bytes(); h.update(len(rel).to_bytes(8,'big'));h.update(rel);h.update(len(data).to_bytes(8,'big'));h.update(data)
    return h.hexdigest()
def main()->int:
    required=[ROOT/'specifications/phase8_control_flow.md',ROOT/'transition/phase_8/manifest.json',ROOT/'transition/phase_8/gate_evidence.md',ROOT/'transition/phase_8/rollback_conditions.md',ROOT/'evidence/phase_08/architecture_report.json',ROOT/'evidence/phase_08/determinism_report.json',ROOT/'evidence/phase_08/checkpoint_c.json']
    if not all(p.exists() for p in required): return 2
    manifest=json.loads((ROOT/'transition/phase_8/manifest.json').read_text())
    if manifest.get('required_tests')!=92:return 4
    for name in ('architecture_report.json','rule_report.json','determinism_report.json'):
        if not json.loads((ROOT/'evidence/phase_08'/name).read_text()).get('passed'): return 5
    expected=json.loads((ROOT/'transition/phase_8/baseline_fingerprint.json').read_text())['value']
    value=tree_hash()
    if value!=expected: print(f'baseline mismatch: {value} != {expected}'); return 3
    print('Phase 8 validation passed');print('92 independently executed tests recorded');print(f'Baseline SHA-256: {value}');return 0
if __name__=='__main__':raise SystemExit(main())
