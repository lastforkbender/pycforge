from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from typing import Any

def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

@dataclass(frozen=True, slots=True)
class Fingerprint:
    domain: str
    schema_version: str
    canonicalization_version: str
    algorithm: str
    value: str

    def to_dict(self) -> dict[str, str]:
        return {"domain": self.domain, "schema_version": self.schema_version, "canonicalization_version": self.canonicalization_version, "algorithm": self.algorithm, "value": self.value}

def fingerprint(domain: str, value: Any) -> Fingerprint:
    digest = hashlib.sha256(canonical_json(value)).hexdigest()
    return Fingerprint(domain, "0.1", "canonical-json-v1", "sha256", digest)
