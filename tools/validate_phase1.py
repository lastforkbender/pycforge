from __future__ import annotations
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REQUIRED=["pycforge/converter/facade.py","pycforge/converter/core/request.py","pycforge/converter/core/result.py","pycforge/converter/core/stage_artifact.py","pycforge/converter/core/stage_outcome.py","pycforge/converter/decision_trace/recorder.py","pycforge/converter/telemetry/sink.py","tests/test_phase1.py","transition/phase_1/manifest.json"]
def main()->int:
    missing=[p for p in REQUIRED if not (ROOT/p).is_file()]
    if missing:raise SystemExit(f"missing: {missing}")
    subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-v"],cwd=ROOT,check=True)
    payload={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(REQUIRED)}
    fp=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    out=ROOT/"transition/phase_1/baseline_fingerprint.json"; out.write_text(json.dumps({"domain":"phase-baseline","schema_version":"0.1","canonicalization_version":"canonical-json-v1","algorithm":"sha256","value":fp},indent=2)+"\n")
    print(f"Phase 1 validation passed: {fp}"); return 0
if __name__=="__main__":raise SystemExit(main())
