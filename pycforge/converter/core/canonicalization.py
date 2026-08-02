from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from pycforge.converter.contracts.configuration import (
    COMPATIBLE_RENDERERS_BY_RULE_SET,
    DEFAULT_TARGET_CONTRACT,
    MAX_SOURCE_DOCUMENTS,
    SUPPORTED_CONTAINER_POLICIES,
    SUPPORTED_HELPER_POLICIES,
    SUPPORTED_MODULE_POLICIES,
    SUPPORTED_NUMERIC_POLICIES,
    SUPPORTED_RECORD_POLICIES,
    SUPPORTED_RENDERERS,
    SUPPORTED_RULE_SETS,
    SUPPORTED_SEMANTIC_POLICIES,
    SUPPORTED_TARGET_CONTRACTS,
    supports_modules,
    supports_numeric,
    supports_records,
)

from .diagnostics import Diagnostic
from .enums import Severity
from .fingerprint import Fingerprint, fingerprint
from .request import ConversionRequest, SourceBundle, SourceDocumentInput
from .resource_policy import ResourcePolicy


_MODULE_SEGMENT = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


@dataclass(frozen=True, slots=True)
class CanonicalRequest:
    request: ConversionRequest
    request_fingerprint: Fingerprint
    resource_fingerprint: Fingerprint

    def semantic_dict(self) -> dict[str, object]:
        request = self.request
        documents = (request.source_bundle.primary,) + request.source_bundle.companions
        return {
            "source_bundle": {
                "schema_version": "source-bundle/0.2" if supports_modules(request.rule_set_version) else "source-bundle/0.1",
                "primary": _document_dict(documents[0]),
                "companions": [_document_dict(item) for item in documents[1:]],
            },
            "python_version": request.python_version,
            "target_contract": request.target_contract,
            "semantic_policy": request.semantic_policy,
            "approximation_allowlist": list(request.approximation_allowlist),
            "rule_set_version": request.rule_set_version,
            "renderer_version": request.renderer_version,
            "helper_policy_version": request.helper_policy_version,
            "container_policy_version": request.container_policy_version,
            "module_policy_version": request.module_policy_version,
            **(
                {"record_policy_version": request.record_policy_version}
                if supports_records(request.rule_set_version)
                else {}
            ),
            **(
                {"numeric_policy_version": request.numeric_policy_version}
                if supports_numeric(request.rule_set_version)
                else {}
            ),
            "resource_policy": request.resource_policy.to_dict(),
        }


def _document_dict(document: SourceDocumentInput) -> dict[str, object]:
    return {
        "logical_name": document.logical_name,
        "module_id": document.module_id,
        "text": document.text,
    }


def _valid_logical_name(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    path = PurePosixPath(value)
    return bool(
        path.parts
        and path.as_posix() == value
        and not value.startswith("/")
        and "\\" not in value
        and ".." not in path.parts
        and not any(ord(character) < 32 for character in value)
    )


def _valid_module_id(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    parts = value.split(".")
    return bool(
        len(encoded) <= 255
        and 1 <= len(parts) <= 16
        and all(_MODULE_SEGMENT.fullmatch(part) for part in parts)
    )


def canonicalize(request: ConversionRequest) -> tuple[CanonicalRequest | None, tuple[Diagnostic, ...]]:
    errors: list[Diagnostic] = []
    if not isinstance(request, ConversionRequest):
        return None, (Diagnostic("PYC1000", Severity.ERROR, "request", "Request must be ConversionRequest"),)
    if not isinstance(request.source_bundle, SourceBundle) or not isinstance(request.source_bundle.primary, SourceDocumentInput):
        return None, (Diagnostic("PYC1000", Severity.ERROR, "request", "Request must contain a SourceBundle with one primary SourceDocumentInput"),)
    if not isinstance(request.resource_policy, ResourcePolicy):
        return None, (Diagnostic("PYC1005", Severity.ERROR, "request", "resource_policy must be ResourcePolicy"),)

    policy_errors = request.resource_policy.validate()
    errors.extend(Diagnostic("PYC1005", Severity.ERROR, "request", message) for message in policy_errors)

    companions = request.source_bundle.companions
    if not isinstance(companions, (tuple, list)) or any(not isinstance(item, SourceDocumentInput) for item in companions):
        errors.append(Diagnostic("PYC1007", Severity.ERROR, "request", "Companion source documents must be SourceDocumentInput values"))
        documents: tuple[SourceDocumentInput, ...] = (request.source_bundle.primary,)
    else:
        documents = (request.source_bundle.primary,) + tuple(companions)

    modules_enabled = isinstance(request.rule_set_version, str) and supports_modules(request.rule_set_version)
    if not modules_enabled and len(documents) > 1:
        errors.append(Diagnostic("PYC1007", Severity.ERROR, "request", "Companion source documents require a module-bundle rule set"))
    configured_document_limit = request.resource_policy.max_source_documents
    valid_document_limit = isinstance(configured_document_limit, int) and not isinstance(configured_document_limit, bool) and configured_document_limit > 0
    document_limit = min(configured_document_limit, MAX_SOURCE_DOCUMENTS) if valid_document_limit else None
    if modules_enabled and document_limit is not None and len(documents) > document_limit:
        errors.append(Diagnostic("PYC3510", Severity.ERROR, "request", "SourceBundle exceeds the closed 64-document or configured document ceiling"))

    total_bytes = 0
    normalized_documents: list[SourceDocumentInput] = []
    for ordinal, document in enumerate(documents):
        role = "Primary" if ordinal == 0 else "Companion"
        if not _valid_logical_name(document.logical_name):
            errors.append(Diagnostic("PYC3501" if modules_enabled else "PYC1001", Severity.ERROR, "request", f"{role} logical name must be a canonical non-empty relative logical path"))
        if modules_enabled and not _valid_module_id(document.module_id):
            errors.append(Diagnostic("PYC3501", Severity.ERROR, "request", f"{role} module ID must be an exact canonical lowercase dotted logical identifier"))
        if not isinstance(document.text, str):
            errors.append(Diagnostic("PYC1002", Severity.ERROR, "request", f"{role} source must be decoded text"))
            continue
        try:
            encoded = document.text.encode("utf-8")
        except UnicodeEncodeError:
            errors.append(Diagnostic("PYC1002", Severity.ERROR, "request", f"{role} source must be valid Unicode encodable as UTF-8"))
            continue
        total_bytes += len(encoded)
        normalized_documents.append(SourceDocumentInput(document.logical_name, document.text, document.module_id))

    if modules_enabled:
        module_ids = [item.module_id for item in documents if isinstance(item.module_id, str)]
        logical_names = [item.logical_name for item in documents if isinstance(item.logical_name, str)]
        if len(module_ids) != len(set(module_ids)) or len(logical_names) != len(set(logical_names)):
            errors.append(Diagnostic("PYC3502", Severity.ERROR, "request", "SourceBundle logical module IDs and logical source names must each be unique"))
    source_byte_limit = request.resource_policy.max_source_bytes
    valid_source_byte_limit = isinstance(source_byte_limit, int) and not isinstance(source_byte_limit, bool) and source_byte_limit >= 0
    if valid_source_byte_limit and total_bytes > source_byte_limit:
        code = "PYC3510" if modules_enabled else "PYC1003"
        errors.append(Diagnostic(code, Severity.ERROR, "request", "SourceBundle exceeds max_source_bytes" if modules_enabled else "Primary source exceeds max_source_bytes"))

    if request.python_version != "3.11":
        errors.append(Diagnostic("PYC1004", Severity.ERROR, "request", "Unsupported Python grammar version"))

    allowlist = request.approximation_allowlist
    if not isinstance(allowlist, (tuple, list)) or any(not isinstance(item, str) for item in allowlist):
        errors.append(Diagnostic("PYC1006", Severity.ERROR, "request", "Approximation allowlist must be an ordered collection of string codes"))
        normalized_allowlist: tuple[str, ...] = ()
    else:
        normalized_allowlist = tuple(sorted(allowlist))
        if len(set(allowlist)) != len(allowlist):
            errors.append(Diagnostic("PYC1006", Severity.ERROR, "request", "Approximation allowlist contains duplicates"))

    checks = (
        (request.target_contract, SUPPORTED_TARGET_CONTRACTS, "PYC1008", "Unsupported Target C Source Contract"),
        (request.semantic_policy, SUPPORTED_SEMANTIC_POLICIES, "PYC1009", "Unsupported conversion semantic policy"),
        (request.rule_set_version, SUPPORTED_RULE_SETS, "PYC1010", "Unsupported conversion rule-set version"),
        (request.renderer_version, SUPPORTED_RENDERERS, "PYC1011", "Unsupported C renderer version"),
        (request.helper_policy_version, SUPPORTED_HELPER_POLICIES, "PYC1014", "Unsupported helper policy version"),
        (request.container_policy_version, SUPPORTED_CONTAINER_POLICIES, "PYC1015", "Unsupported container policy version"),
        (request.module_policy_version, SUPPORTED_MODULE_POLICIES, "PYC1016", "Unsupported module policy version"),
        (request.record_policy_version, SUPPORTED_RECORD_POLICIES, "PYC1017", "Unsupported record policy version"),
        (request.numeric_policy_version, SUPPORTED_NUMERIC_POLICIES, "PYC1018", "Unsupported numeric policy version"),
    )
    for value, supported, code, message in checks:
        if not isinstance(value, str) or value not in supported:
            errors.append(Diagnostic(code, Severity.ERROR, "request", message))
    if (
        request.rule_set_version in SUPPORTED_RULE_SETS
        and request.renderer_version in SUPPORTED_RENDERERS
        and request.renderer_version
        not in COMPATIBLE_RENDERERS_BY_RULE_SET.get(
            request.rule_set_version,
            frozenset(),
        )
    ):
        errors.append(Diagnostic(
            "PYC1011",
            Severity.ERROR,
            "request",
            "C renderer version is incompatible with selected rule-set version",
        ))
    if (
        isinstance(request.rule_set_version, str)
        and supports_numeric(request.rule_set_version)
        and request.target_contract in SUPPORTED_TARGET_CONTRACTS
        and request.target_contract != DEFAULT_TARGET_CONTRACT
    ):
        errors.append(Diagnostic(
            "PYC1008",
            Severity.ERROR,
            "request",
            "Phase 14 bounded numeric rules require the exact c11-portable-fixed-v1 target contract",
        ))

    if errors:
        return None, tuple(errors)
    if len(normalized_documents) != len(documents):
        return None, (Diagnostic("PYC1000", Severity.ERROR, "request", "SourceBundle could not be canonicalized"),)

    bundle = SourceBundle(normalized_documents[0], tuple(normalized_documents[1:]))
    normalized = ConversionRequest(
        source_bundle=bundle,
        python_version=request.python_version,
        target_contract=request.target_contract,
        semantic_policy=request.semantic_policy,
        approximation_allowlist=normalized_allowlist,
        rule_set_version=request.rule_set_version,
        renderer_version=request.renderer_version,
        helper_policy_version=request.helper_policy_version,
        container_policy_version=request.container_policy_version,
        resource_policy=request.resource_policy,
        module_policy_version=request.module_policy_version,
        record_policy_version=request.record_policy_version,
        numeric_policy_version=request.numeric_policy_version,
    )
    placeholder = fingerprint("canonicalization-placeholder", {})
    temporary = CanonicalRequest(normalized, placeholder, placeholder)
    semantic = temporary.semantic_dict()
    return CanonicalRequest(
        normalized,
        fingerprint("conversion-request", semantic),
        fingerprint("resource-policy", normalized.resource_policy.to_dict()),
    ), ()
