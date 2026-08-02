from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus, __version__
from pycforge.converter.core.serialization import result_to_dict


FINGERPRINT = Path("transition/phase_10/opening_checkpoint_fingerprint.json")
ROADMAP_SHA256 = "d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3"


def included_files() -> list[Path]:
    result: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if relative == FINGERPRINT:
            continue
        if (
            "__pycache__" in path.parts
            or ".pytest_cache" in path.parts
            or "build" in path.parts
            or "dist" in path.parts
            or path.name.endswith(".pyc")
        ):
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
    manifest = json.loads(
        (ROOT / "transition/phase_10/opening_checkpoint_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    fingerprint = json.loads((ROOT / FINGERPRINT).read_text(encoding="utf-8"))
    missing = [
        name for name in manifest.get("required_files", [])
        if not (ROOT / name).is_file()
    ]
    if missing:
        print("Missing opening-checkpoint files: " + ", ".join(sorted(missing)))
        return 2
    if manifest.get("state") != "CompletedEntryCheckpoint":
        print("Opening checkpoint state mismatch")
        return 3
    if manifest.get("promotion_state") != "not-promoted":
        print("Opening checkpoint must not claim Phase 10 promotion")
        return 4
    if manifest.get("checkpoint_package_version") != "0.10.0.dev0" or __version__ != "0.10.0.dev0":
        print("Opening-checkpoint prerelease identity mismatch")
        return 4
    tests = manifest.get("tests", {})
    if tests != {
        "phase_0_to_9_regressions": 139,
        "opening_checkpoint": 4,
        "required": 143,
    }:
        print("Opening-checkpoint test-count contract mismatch")
        return 5
    roadmap = ROOT / "docs/python_to_c_converter_architecture_revision_3_1.txt"
    if hashlib.sha256(roadmap.read_bytes()).hexdigest() != ROADMAP_SHA256:
        print("Packaged Revision 3.1 roadmap hash mismatch")
        return 6
    if 'version = "0.10.0.dev0"' not in (ROOT / "pyproject.toml").read_text(encoding="utf-8"):
        print("The opening checkpoint lacks its prerelease package identity")
        return 7
    for report_name in ("opening_checkpoint_report.json", "package_report.json", "progress_observer_report.json", "test_summary.json"):
        report = json.loads((ROOT / "evidence/phase_10" / report_name).read_text(encoding="utf-8"))
        if not report.get("passed"):
            print(f"Checkpoint evidence did not pass: {report_name}")
            return 8
        if report.get("wheel_sha256") == "PENDING_REBUILD":
            print("Checkpoint package evidence is not finalized")
            return 8

    source = "def identity(value: int) -> int:\n    return value\n"
    request = ConversionRequest.from_source(source)
    converter = PythonToCConverter()
    baseline = converter.convert(request)

    def fail(_event: object) -> None:
        raise RuntimeError("injected progress observer failure")

    observed = converter.convert(request, progress=fail)
    if baseline.status is not ResultStatus.CONVERTED or result_to_dict(observed) != result_to_dict(baseline):
        print("Progress observer changed the semantic conversion result")
        return 9
    if list(observed.stage_artifact.payload.get("helper_requirements", ())) != []:
        print("Opening checkpoint introduced helper requirements before the entry gate")
        return 10

    expected = fingerprint.get("value")
    actual = tree_hash()
    if actual != expected:
        print(f"Opening-checkpoint tree fingerprint mismatch: {actual} != {expected}")
        return 11
    print("Phase 10 opening-checkpoint validation passed")
    print("143 tests recorded: 139 Phase 0-9 regressions + 4 checkpoint tests")
    print(f"Checkpoint SHA-256: {actual}")
    print("Phase 10 remains unpromoted; generated C was not compiled or executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
