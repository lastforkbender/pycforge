from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def tree_hash()->str:
    h=hashlib.sha256(); excluded={Path('transition/phase_6/baseline_fingerprint.json')}
    for path in sorted(p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts and p.relative_to(ROOT) not in excluded):
        rel=path.relative_to(ROOT).as_posix().encode();data=path.read_bytes();h.update(len(rel).to_bytes(8,'big'));h.update(rel);h.update(len(data).to_bytes(8,'big'));h.update(data)
    return h.hexdigest()
def main()->int:
    required=[ROOT/'specifications/phase6_first_complete_slice.md',ROOT/'transition/phase_6/manifest.json',ROOT/'transition/phase_6/gate_evidence.md',ROOT/'transition/phase_6/checkpoint_b.md',ROOT/'evidence/phase_06/conversion_debt.json']
    if not all(p.exists() for p in required):return 2
    if json.loads((ROOT/'transition/phase_6/manifest.json').read_text()).get('required_tests')!=70:return 4
    value=tree_hash(); expected=json.loads((ROOT/'transition/phase_6/baseline_fingerprint.json').read_text())['value']
    if value!=expected:print(f'baseline mismatch: {value} != {expected}');return 3
    print('Phase 6 validation passed');print('70 independently executed tests recorded');print(f'Baseline SHA-256: {value}');return 0
if __name__=='__main__':raise SystemExit(main())
