from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "transition" / "phase_0" / "manifest.json"


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    missing = [name for name in manifest["required_files"] if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit("Missing Phase 0 artifacts:\n" + "\n".join(missing))

    for path in ROOT.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))

    product = (ROOT / "specifications" / "product_boundary.md").read_text(encoding="utf-8").lower()
    required_boundary_terms = ["shall not compile", "execute", "shall not import"]
    absent = [term for term in required_boundary_terms if term not in product]
    if absent:
        raise SystemExit(f"Product boundary is missing required prohibitions: {absent}")

    first_c = (ROOT / "fixtures" / "first_milestone" / "expected.c").read_bytes()
    if not first_c.endswith(b"\n") or b"\r\n" in first_c:
        raise SystemExit("Milestone C fixture must use LF and end in a newline")

    payload = {
        "manifest": manifest,
        "artifact_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in sorted(manifest["required_files"])
        },
    }
    baseline_fingerprint = hashlib.sha256(canonical_json(payload)).hexdigest()
    out = ROOT / "transition" / "phase_0" / "baseline_fingerprint.json"
    out.write_text(json.dumps({
        "domain": "phase-baseline",
        "schema_version": "0.1",
        "canonicalization_version": "canonical-json-v1",
        "algorithm": "sha256",
        "value": baseline_fingerprint,
    }, indent=2) + "\n", encoding="utf-8")

    print(f"Phase 0 validation passed: {baseline_fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
