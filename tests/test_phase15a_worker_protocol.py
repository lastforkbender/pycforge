from __future__ import annotations

import json
import multiprocessing
import unittest

from pycforge.converter.core.fingerprint import canonical_json
from pycforge.converter.core.artifact_io import artifact_to_dict
from pycforge.converter.core.progress import ConversionProgress
from pycforge.converter.core.request import (
    ConversionRequest,
    ObservationOptions,
    SourceBundle,
    SourceDocumentInput,
)
from pycforge.converter.core.serialization import result_to_json
from pycforge.converter.facade import PythonToCConverter
from pycforge.ide.process_worker import worker_main
from pycforge.ide.worker_protocol import (
    MAX_REQUEST_BYTES,
    PROTOCOL_SCHEMA,
    WorkerProtocolError,
    WorkerRequest,
    bundle_fingerprint_for_request,
    decode_control,
    decode_event,
    decode_request,
    encode_cancel,
    encode_failure,
    encode_progress,
    encode_request,
    encode_terminal,
    receive_event,
    send_request,
)


APP = (
    "from lib import increment\n\n"
    "def run(value: int) -> int:\n"
    "    return increment(value)\n"
)
LIB = "def increment(value: int) -> int:\n    return value + 1\n"
ADD = "def add(a: int, b: int) -> int:\n    return a + b\n"


def bundled_request() -> ConversionRequest:
    return ConversionRequest(
        SourceBundle(
            SourceDocumentInput("app.py", APP, "app"),
            (SourceDocumentInput("lib.py", LIB, "lib"),),
        )
    )


def worker_request(
    request: ConversionRequest | None = None,
    *,
    generation: int = 7,
) -> WorkerRequest:
    request = request or bundled_request()
    return WorkerRequest.create(
        generation,
        bundle_fingerprint_for_request(request),
        request,
        ObservationOptions("Full", True),
    )


class BytesOnlyConnection:
    def __init__(self) -> None:
        self.frame: bytes | None = None
        self.maximum: int | None = None

    def send_bytes(self, frame: bytes) -> None:
        self.frame = frame

    def recv_bytes(self, maxlength: int | None = None) -> bytes:
        self.maximum = maxlength
        if self.frame is None:
            raise EOFError
        return self.frame

    def close(self) -> None:
        pass


class Phase15AWorkerProtocolTests(unittest.TestCase):
    def test_request_round_trip_preserves_exact_conversion_request(self) -> None:
        request = worker_request()

        frame = encode_request(request)
        decoded = decode_request(frame)

        self.assertEqual(decoded, request)
        self.assertEqual(decoded.request, request.request)
        self.assertEqual(decoded.observation, ObservationOptions("Full", True))
        self.assertLess(len(frame), MAX_REQUEST_BYTES)
        self.assertEqual(json.loads(frame)["schema"], PROTOCOL_SCHEMA)
        self.assertEqual(frame, canonical_json(json.loads(frame)))

    def test_bytes_only_connection_helpers_apply_receive_bound(self) -> None:
        request = worker_request()
        connection = BytesOnlyConnection()

        send_request(connection, request)
        decoded = decode_request(connection.recv_bytes(MAX_REQUEST_BYTES))

        self.assertEqual(decoded, request)
        self.assertEqual(connection.maximum, MAX_REQUEST_BYTES)

    def test_cancel_round_trip_is_bound_to_full_request_identity(self) -> None:
        request = worker_request()

        control = decode_control(encode_cancel(request))

        self.assertEqual(control.generation, request.generation)
        self.assertEqual(control.bundle_fingerprint, request.bundle_fingerprint)
        self.assertEqual(
            control.transport_fingerprint, request.transport_fingerprint
        )

    def test_request_decoder_rejects_noncanonical_unknown_and_duplicate_json(
        self,
    ) -> None:
        frame = encode_request(worker_request())
        with self.assertRaises(WorkerProtocolError):
            decode_request(b" " + frame)

        data = json.loads(frame)
        data["unknown"] = True
        with self.assertRaises(WorkerProtocolError):
            decode_request(canonical_json(data))

        duplicate = (
            b'{"schema":"'
            + PROTOCOL_SCHEMA.encode("ascii")
            + b'","schema":"'
            + PROTOCOL_SCHEMA.encode("ascii")
            + b'"}'
        )
        with self.assertRaises(WorkerProtocolError):
            decode_request(duplicate)

    def test_request_decoder_rejects_tampering_and_bundle_mismatch(self) -> None:
        request = worker_request()
        data = json.loads(encode_request(request))
        data["request"]["source_bundle"]["primary"]["text"] += "\n"
        with self.assertRaises(WorkerProtocolError):
            decode_request(canonical_json(data))

        wrong_bundle = WorkerRequest.create(
            request.generation,
            "0" * 64,
            request.request,
            request.observation,
        )
        with self.assertRaises(WorkerProtocolError):
            encode_request(wrong_bundle)

    def test_request_encoder_enforces_maximum_source_envelope(self) -> None:
        request = ConversionRequest.from_source("x" * 1_000_001)
        with self.assertRaises(WorkerProtocolError):
            worker_request(request)

    def test_progress_event_round_trip_and_identity_guards(self) -> None:
        request = worker_request()
        progress = ConversionProgress("stage-entered", "frontend", 0, 7)
        frame = encode_progress(request, progress)

        event = decode_event(frame, expected=request)

        self.assertEqual(event.kind, "progress")
        self.assertEqual(event.progress, progress)
        self.assertIsNone(event.result)
        with self.assertRaises(WorkerProtocolError):
            decode_event(frame, expected_generation=request.generation + 1)

    def test_terminal_round_trip_rehydrates_complete_immutable_result(self) -> None:
        conversion_request = bundled_request()
        request = worker_request(conversion_request)
        result = PythonToCConverter().convert(
            conversion_request,
            observation=request.observation,
        )
        self.assertIsNotNone(result.generated_c)

        event = decode_event(encode_terminal(request, result), expected=request)

        self.assertEqual(event.kind, "terminal")
        self.assertIsNotNone(event.result)
        assert event.result is not None
        self.assertEqual(result_to_json(event.result), result_to_json(result))
        self.assertEqual(
            canonical_json(artifact_to_dict(event.result.stage_artifact)),
            canonical_json(artifact_to_dict(result.stage_artifact)),
        )
        self.assertEqual(
            event.result.output_fingerprint, result.output_fingerprint
        )
        self.assertEqual(
            canonical_json(list(event.mappings)),
            canonical_json(
                list(result.stage_artifact.payload["source_output_mappings"])
            ),
        )
        with self.assertRaises(TypeError):
            event.mappings[0]["origin_kind"] = "tampered"

    def test_terminal_decoder_rejects_output_and_identity_tampering(self) -> None:
        conversion_request = ConversionRequest.from_source(ADD)
        request = worker_request(conversion_request)
        result = PythonToCConverter().convert(
            conversion_request,
            observation=request.observation,
        )
        data = json.loads(encode_terminal(request, result))
        data["result"]["generated_c"] += "\n/* tampered */"
        with self.assertRaisesRegex(
            WorkerProtocolError, "output fingerprint mismatch"
        ):
            decode_event(canonical_json(data), expected=request)

        data = json.loads(encode_terminal(request, result))
        data["generation"] += 1
        with self.assertRaisesRegex(WorkerProtocolError, "generation mismatch"):
            decode_event(canonical_json(data), expected=request)

    def test_terminal_decoder_rejects_mapping_tampering(self) -> None:
        conversion_request = ConversionRequest.from_source(ADD)
        request = worker_request(conversion_request)
        result = PythonToCConverter().convert(
            conversion_request,
            observation=request.observation,
        )
        data = json.loads(encode_terminal(request, result))
        data["mappings"] = []
        with self.assertRaisesRegex(WorkerProtocolError, "mappings mismatch"):
            decode_event(canonical_json(data), expected=request)

    def test_failure_event_has_no_publishable_payload(self) -> None:
        request = worker_request()

        event = decode_event(
            encode_failure(
                request,
                "worker-internal-error",
                "converter worker failed before terminal publication",
            ),
            expected=request,
        )

        self.assertEqual(event.kind, "failure")
        self.assertEqual(event.failure_classification, "worker-internal-error")
        self.assertIsNone(event.result)
        self.assertEqual(event.mappings, ())

    def test_spawned_worker_uses_protocol_and_publishes_one_terminal_result(
        self,
    ) -> None:
        context = multiprocessing.get_context("spawn")
        request_receive, request_send = context.Pipe(duplex=False)
        event_receive, event_send = context.Pipe(duplex=False)
        control_receive, control_send = context.Pipe(duplex=False)
        process = context.Process(
            target=worker_main,
            args=(request_receive, event_send, control_receive),
        )
        process.start()
        request_receive.close()
        event_send.close()
        control_receive.close()
        request = worker_request(ConversionRequest.from_source(ADD))
        send_request(request_send, request)
        request_send.close()
        events = []
        try:
            while True:
                self.assertTrue(event_receive.poll(15), "worker event timed out")
                event = receive_event(event_receive, expected=request)
                events.append(event)
                if event.kind in {"terminal", "failure"}:
                    break
        finally:
            control_send.close()
            event_receive.close()
            process.join(15)
            if process.is_alive():
                process.terminate()
                process.join(5)

        self.assertEqual(process.exitcode, 0)
        self.assertEqual(events[-1].kind, "terminal")
        self.assertTrue(any(item.kind == "progress" for item in events))
        self.assertIsNotNone(events[-1].result)
        assert events[-1].result is not None
        self.assertIsNotNone(events[-1].result.generated_c)


if __name__ == "__main__":
    unittest.main()
