from __future__ import annotations
import json
import re
from types import MappingProxyType
from pathlib import Path
from typing import Any
from .fingerprint import Fingerprint, fingerprint
from .stage_artifact import StageArtifact

ARTIFACT_ENVELOPE_VERSION = "0.2"

class ArtifactCompatibilityError(ValueError):
    pass

_FINGERPRINT_FIELDS = {"domain", "schema_version", "canonicalization_version", "algorithm", "value"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

def _fp_from_dict(value: object, *, required: bool, role: str) -> Fingerprint | None:
    if value is None:
        if required:
            raise ArtifactCompatibilityError(f"PYC3103 missing {role} fingerprint")
        return None
    if not isinstance(value, dict) or set(value) != _FINGERPRINT_FIELDS or not all(isinstance(item, str) for item in value.values()):
        raise ArtifactCompatibilityError(f"PYC3103 malformed {role} fingerprint")
    result = Fingerprint(**value)
    if result.domain != "stage-artifact" or result.schema_version != "0.1" or result.canonicalization_version != "canonical-json-v1" or result.algorithm != "sha256" or not _SHA256.fullmatch(result.value):
        raise ArtifactCompatibilityError(f"PYC3103 incompatible {role} fingerprint metadata")
    return result

def artifact_to_dict(artifact: StageArtifact) -> dict[str, Any]:
    payload = {key: list(value) if isinstance(value, tuple) else value for key, value in artifact.payload.items()}
    return {
        "envelope_version": ARTIFACT_ENVELOPE_VERSION,
        "kind": artifact.kind,
        "schema_version": artifact.schema_version,
        "conversion_id": artifact.conversion_id,
        "parent_fingerprint": None if artifact.parent_fingerprint is None else artifact.parent_fingerprint.to_dict(),
        "payload": payload,
        "artifact_fingerprint": artifact.artifact_fingerprint.to_dict(),
    }

def artifact_from_dict(data: dict[str, Any], *, accepted: set[tuple[str, str]] | None = None) -> StageArtifact:
    if data.get("envelope_version") != ARTIFACT_ENVELOPE_VERSION:
        raise ArtifactCompatibilityError("PYC3101 incompatible artifact envelope version")
    required = {"kind", "schema_version", "conversion_id", "parent_fingerprint", "payload", "artifact_fingerprint"}
    if not required.issubset(data):
        raise ArtifactCompatibilityError("PYC3103 incomplete artifact envelope")
    if set(data) != required | {"envelope_version"}:
        raise ArtifactCompatibilityError("PYC3103 artifact envelope contains unknown fields")
    if not all(isinstance(data.get(key), str) and data.get(key) for key in ("kind", "schema_version", "conversion_id")):
        raise ArtifactCompatibilityError("PYC3103 invalid artifact identity")
    pair = (data["kind"], data["schema_version"])
    if accepted is not None and pair not in accepted:
        raise ArtifactCompatibilityError("PYC3102 incompatible artifact kind or schema")
    raw_payload = data["payload"]
    if not isinstance(raw_payload, dict):
        raise ArtifactCompatibilityError("PYC3104 artifact payload must be an object")
    payload = dict(raw_payload)
    if isinstance(payload.get("stage_order"), list):
        payload["stage_order"] = tuple(payload["stage_order"])
    is_initial = data["kind"] == "initial"
    parent = _fp_from_dict(data["parent_fingerprint"], required=not is_initial, role="parent")
    artifact_fingerprint = _fp_from_dict(data["artifact_fingerprint"], required=True, role="artifact")
    if is_initial and parent is not None:
        raise ArtifactCompatibilityError("PYC3103 initial artifact cannot have a parent fingerprint")
    try:
        artifact = StageArtifact(str(data["kind"]), str(data["schema_version"]), str(data["conversion_id"]), parent, MappingProxyType(payload), artifact_fingerprint)
    except (TypeError, ValueError) as exc:
        raise ArtifactCompatibilityError("PYC3105 artifact fingerprint mismatch") from exc
    expected = fingerprint("stage-artifact", {"kind": artifact.kind, "conversion_id": artifact.conversion_id, "parent": None if artifact.parent_fingerprint is None else artifact.parent_fingerprint.value, "payload": {key: list(value) if isinstance(value, tuple) else value for key, value in artifact.payload.items()}})
    if artifact.kind == "initial":
        expected = fingerprint("stage-artifact", {"kind":"initial","conversion_id":artifact.conversion_id,"payload":{"stage_order":list(artifact.payload.get("stage_order",()))}})
    if expected != artifact.artifact_fingerprint:
        raise ArtifactCompatibilityError("PYC3105 artifact fingerprint mismatch")
    return artifact

def save_artifact(path: Path, artifact: StageArtifact, writer: Any) -> None:
    writer.write_text(path, json.dumps(artifact_to_dict(artifact), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n")

def load_artifact(path: Path, *, accepted: set[tuple[str, str]] | None = None) -> StageArtifact:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactCompatibilityError("PYC3100 unreadable artifact") from exc
    if not isinstance(data, dict):
        raise ArtifactCompatibilityError("PYC3103 artifact envelope must be an object")
    return artifact_from_dict(data, accepted=accepted)
