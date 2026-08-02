from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINGERPRINT = Path("transition/phase_9/baseline_fingerprint.json")


def included_files() -> list[Path]:
    result: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if relative == FINGERPRINT:
            continue
        if "__pycache__" in path.parts or ".pytest_cache" in path.parts or "build" in path.parts or "dist" in path.parts:
            continue
        if path.name.endswith(".pyc"):
            continue
        result.append(path)
    return sorted(result, key=lambda item: item.relative_to(ROOT).as_posix())


def tree_hash() -> str:
    digest = hashlib.sha256()
    for path in included_files():
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def main() -> int:
    manifest_path = ROOT / "transition/phase_9/manifest.json"
    fingerprint_path = ROOT / FINGERPRINT
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Phase 9 transition metadata is unreadable: {type(exc).__name__}")
        return 2
    missing = [name for name in manifest.get("required_files", []) if not (ROOT / name).is_file()]
    if missing:
        print("Missing required files: " + ", ".join(sorted(missing)))
        return 3
    if manifest.get("phase") != 9 or manifest.get("version") != "0.9.0":
        print("Phase 9 manifest identity mismatch")
        return 4
    if (manifest.get("regression_tests"), manifest.get("review_hardening_tests"), manifest.get("phase_tests"), manifest.get("required_tests")) != (92, 17, 30, 139):
        print("Phase 9 test-count contract mismatch")
        return 5
    if 'version = "0.9.0"' not in (ROOT / "pyproject.toml").read_text(encoding="utf-8"):
        print("Package version mismatch")
        return 6
    for name in (
        "review_report.json",
        "phase9_report.json",
        "test_summary.json",
        "architecture_report.json",
        "rule_report.json",
        "determinism_report.json",
        "transition_report.json",
        "mapping_report.json",
        "observer_cancellation_resource_report.json",
        "semantic_gate_report.json",
        "python_package_report.json",
    ):
        report = json.loads((ROOT / "evidence/phase_09" / name).read_text(encoding="utf-8"))
        if not report.get("passed"):
            print(f"Evidence report did not pass: {name}")
            return 7
    expected = fingerprint.get("value")
    actual = tree_hash()
    if expected != actual:
        print(f"Phase 9 tree fingerprint mismatch: {actual} != {expected}")
        return 8
    print("Phase 9 validation passed")
    print("139 tests recorded: 92 regressions + 17 review hardening + 30 Phase 9")
    print(f"Baseline SHA-256: {actual}")
    print("Generated C was not compiled or executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
