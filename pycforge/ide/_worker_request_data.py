"""Strict plain-data mapping for conversion requests and observations."""

from __future__ import annotations

from pycforge.converter.core.fingerprint import fingerprint
from pycforge.converter.core.request import (
    ConversionRequest,
    ObservationOptions,
    SourceBundle,
    SourceDocumentInput,
)
from pycforge.converter.core.resource_policy import ResourcePolicy

from ._worker_protocol_json import (
    _contains_surrogate,
    _exact_fields,
    _list,
    _nonempty_string,
    _nonnegative_integer,
    _object,
    _string,
    _string_list,
)
from ._worker_protocol_types import (
    MAX_SOURCE_BYTES,
    MAX_SOURCE_DOCUMENTS,
    WorkerProtocolError,
)


_REQUEST_FIELDS = frozenset(
    {
        "source_bundle",
        "python_version",
        "target_contract",
        "semantic_policy",
        "approximation_allowlist",
        "rule_set_version",
        "renderer_version",
        "helper_policy_version",
        "container_policy_version",
        "resource_policy",
        "module_policy_version",
        "record_policy_version",
        "numeric_policy_version",
    }
)
_RESOURCE_FIELDS = frozenset(ResourcePolicy.__slots__)


def bundle_fingerprint_for_request(request: ConversionRequest) -> str:
    """Return the workspace bundle identity represented by ``request``."""

    if not isinstance(request, ConversionRequest):
        raise WorkerProtocolError("worker request must contain ConversionRequest")
    bundle = request.source_bundle
    if not isinstance(bundle, SourceBundle):
        raise WorkerProtocolError("worker request source bundle is malformed")
    documents = (bundle.primary,) + tuple(bundle.companions)
    if not documents or any(not isinstance(item, SourceDocumentInput) for item in documents):
        raise WorkerProtocolError("worker request source documents are malformed")
    semantic = [
        {
            "module_id": document.module_id,
            "logical_name": document.logical_name,
            "text": document.text,
            "is_primary": ordinal == 0,
        }
        for ordinal, document in enumerate(documents)
    ]
    return fingerprint("workspace-source-bundle", semantic).value


def _request_to_data(request: ConversionRequest) -> dict[str, object]:
    if not isinstance(request, ConversionRequest):
        raise WorkerProtocolError("worker request must contain ConversionRequest")
    bundle = request.source_bundle
    if not isinstance(bundle, SourceBundle):
        raise WorkerProtocolError("worker request source bundle is malformed")
    documents = (bundle.primary,) + tuple(bundle.companions)
    if (
        not documents
        or len(documents) > MAX_SOURCE_DOCUMENTS
        or any(not isinstance(item, SourceDocumentInput) for item in documents)
    ):
        raise WorkerProtocolError("worker request document count is outside bounds")
    total_bytes = 0

    def document_data(document: SourceDocumentInput) -> dict[str, object]:
        nonlocal total_bytes
        if (
            not isinstance(document.logical_name, str)
            or not document.logical_name
            or _contains_surrogate(document.logical_name)
            or not isinstance(document.text, str)
            or _contains_surrogate(document.text)
            or (
                document.module_id is not None
                and (
                    not isinstance(document.module_id, str)
                    or _contains_surrogate(document.module_id)
                )
            )
        ):
            raise WorkerProtocolError("worker request source document is malformed")
        try:
            total_bytes += len(document.text.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise WorkerProtocolError(
                "worker request source text is not valid UTF-8"
            ) from exc
        return {
            "logical_name": document.logical_name,
            "text": document.text,
            "module_id": document.module_id,
        }

    primary = document_data(documents[0])
    companions = [document_data(item) for item in documents[1:]]
    if total_bytes > MAX_SOURCE_BYTES:
        raise WorkerProtocolError("worker request source bytes exceed protocol bounds")
    if not isinstance(request.approximation_allowlist, tuple) or any(
        not isinstance(item, str) or _contains_surrogate(item)
        for item in request.approximation_allowlist
    ):
        raise WorkerProtocolError("worker request approximation allowlist is malformed")
    string_fields = (
        request.python_version,
        request.target_contract,
        request.semantic_policy,
        request.rule_set_version,
        request.renderer_version,
        request.helper_policy_version,
        request.container_policy_version,
        request.module_policy_version,
        request.record_policy_version,
        request.numeric_policy_version,
    )
    if any(
        not isinstance(item, str) or not item or _contains_surrogate(item)
        for item in string_fields
    ):
        raise WorkerProtocolError("worker request configuration is malformed")
    if not isinstance(request.resource_policy, ResourcePolicy):
        raise WorkerProtocolError("worker request resource policy is malformed")
    resource = request.resource_policy.to_dict()
    if set(resource) != _RESOURCE_FIELDS or any(
        not isinstance(item, int) or isinstance(item, bool) or item < 0
        for item in resource.values()
    ):
        raise WorkerProtocolError("worker request resource policy is malformed")
    return {
        "source_bundle": {
            "primary": primary,
            "companions": companions,
        },
        "python_version": request.python_version,
        "target_contract": request.target_contract,
        "semantic_policy": request.semantic_policy,
        "approximation_allowlist": list(request.approximation_allowlist),
        "rule_set_version": request.rule_set_version,
        "renderer_version": request.renderer_version,
        "helper_policy_version": request.helper_policy_version,
        "container_policy_version": request.container_policy_version,
        "resource_policy": resource,
        "module_policy_version": request.module_policy_version,
        "record_policy_version": request.record_policy_version,
        "numeric_policy_version": request.numeric_policy_version,
    }


def _request_from_data(value: object) -> ConversionRequest:
    data = _object(value, "conversion request")
    _exact_fields(data, _REQUEST_FIELDS, "conversion request")
    source_bundle_data = _object(data["source_bundle"], "source bundle")
    _exact_fields(source_bundle_data, {"primary", "companions"}, "source bundle")
    primary = _document_from_data(source_bundle_data["primary"])
    raw_companions = _list(source_bundle_data["companions"], "source companions")
    if len(raw_companions) + 1 > MAX_SOURCE_DOCUMENTS:
        raise WorkerProtocolError("worker request document count is outside bounds")
    companions = tuple(_document_from_data(item) for item in raw_companions)
    allowlist = _string_list(
        data["approximation_allowlist"], "approximation allowlist"
    )
    resource_data = _object(data["resource_policy"], "resource policy")
    _exact_fields(resource_data, _RESOURCE_FIELDS, "resource policy")
    resource_values = {
        key: _nonnegative_integer(value, f"resource policy {key}")
        for key, value in resource_data.items()
    }
    string_values = {}
    for key in (
        "python_version",
        "target_contract",
        "semantic_policy",
        "rule_set_version",
        "renderer_version",
        "helper_policy_version",
        "container_policy_version",
        "module_policy_version",
        "record_policy_version",
        "numeric_policy_version",
    ):
        string_values[key] = _nonempty_string(data[key], key)
    request = ConversionRequest(
        SourceBundle(primary, companions),
        python_version=string_values["python_version"],
        target_contract=string_values["target_contract"],
        semantic_policy=string_values["semantic_policy"],
        approximation_allowlist=allowlist,
        rule_set_version=string_values["rule_set_version"],
        renderer_version=string_values["renderer_version"],
        helper_policy_version=string_values["helper_policy_version"],
        container_policy_version=string_values["container_policy_version"],
        resource_policy=ResourcePolicy(**resource_values),
        module_policy_version=string_values["module_policy_version"],
        record_policy_version=string_values["record_policy_version"],
        numeric_policy_version=string_values["numeric_policy_version"],
    )
    # Reuse the encoder's aggregate byte and structural bounds.
    _request_to_data(request)
    return request


def _document_from_data(value: object) -> SourceDocumentInput:
    data = _object(value, "source document")
    _exact_fields(data, {"logical_name", "text", "module_id"}, "source document")
    logical_name = _nonempty_string(data["logical_name"], "source logical name")
    text = _string(data["text"], "source text")
    module_id = data["module_id"]
    if module_id is not None:
        module_id = _string(module_id, "source module ID")
    return SourceDocumentInput(logical_name, text, module_id)


def _observation_to_data(observation: ObservationOptions) -> dict[str, object]:
    if (
        not isinstance(observation, ObservationOptions)
        or observation.trace_level not in {"None", "Summary", "Decisions", "Full"}
        or not isinstance(observation.telemetry_enabled, bool)
    ):
        raise WorkerProtocolError("worker observation options are malformed")
    return {
        "trace_level": observation.trace_level,
        "telemetry_enabled": observation.telemetry_enabled,
    }


def _observation_from_data(value: object) -> ObservationOptions:
    data = _object(value, "observation options")
    _exact_fields(
        data, {"trace_level", "telemetry_enabled"}, "observation options"
    )
    trace_level = data["trace_level"]
    telemetry_enabled = data["telemetry_enabled"]
    if trace_level not in {"None", "Summary", "Decisions", "Full"} or not isinstance(
        telemetry_enabled, bool
    ):
        raise WorkerProtocolError("worker observation options are malformed")
    return ObservationOptions(trace_level, telemetry_enabled)
