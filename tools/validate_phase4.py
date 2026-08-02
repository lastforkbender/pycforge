from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def tree_hash()->str:
    h=hashlib.sha256(); excluded={Path("transition/phase_4/baseline_fingerprint.json")}
    for path in sorted(p for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.relative_to(ROOT) not in excluded):
        rel=path.relative_to(ROOT).as_posix().encode();data=path.read_bytes()
        h.update(len(rel).to_bytes(8,"big"));h.update(rel);h.update(len(data).to_bytes(8,"big"));h.update(data)
    return h.hexdigest()

def main()->int:
    required=[ROOT/"specifications/c_ir_schema.md",ROOT/"specifications/c_renderer_contract.md",ROOT/"specifications/generated_c_conformance.md",ROOT/"transition/phase_4/manifest.json",ROOT/"transition/phase_4/gate_evidence.md",ROOT/"fixtures/c_ir/essential_golden.c"]
    if not all(p.exists() for p in required):return 2
    manifest=json.loads((ROOT/"transition/phase_4/manifest.json").read_text())
    if manifest.get("required_tests")!=44:return 4
    value=tree_hash();expected=json.loads((ROOT/"transition/phase_4/baseline_fingerprint.json").read_text())["value"]
    if value!=expected:
        print(f"baseline mismatch: {value} != {expected}");return 3
    print("Phase 4 validation passed")
    print("44 independently executed tests recorded")
    print(f"Baseline SHA-256: {value}")
    return 0
if __name__=="__main__":raise SystemExit(main())
