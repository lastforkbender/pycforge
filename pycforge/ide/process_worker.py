"""Spawn-safe child-process entry point for one PyCForge conversion request."""

from __future__ import annotations

from threading import Thread

from pycforge.converter.core.cancellation import CancellationToken
from pycforge.converter.core.progress import ConversionProgress
from pycforge.converter.facade import PythonToCConverter

from .worker_protocol import (
    ByteConnection,
    WorkerProtocolError,
    WorkerRequest,
    encode_failure,
    encode_progress,
    encode_terminal,
    receive_control,
    receive_request,
    send_event,
)


def worker_main(
    request_connection: ByteConnection,
    event_connection: ByteConnection,
    control_connection: ByteConnection,
) -> None:
    """Receive, convert, publish one terminal event, and exit.

    Conversion runs only in this child process.  The small daemon listener
    translates the sole control command into the converter's existing local
    ``CancellationToken``; the converter facade itself remains unchanged.
    """

    request: WorkerRequest | None = None
    token = CancellationToken()
    try:
        request = receive_request(request_connection)
        _close_quietly(request_connection)
        Thread(
            target=_listen_for_cancel,
            args=(control_connection, request, token),
            name=f"pycforge-cancel-{request.generation}",
            daemon=True,
        ).start()

        def report(progress: ConversionProgress) -> None:
            send_event(event_connection, encode_progress(request, progress))

        result = PythonToCConverter().convert(
            request.request,
            observation=request.observation,
            cancellation=token,
            progress=report,
        )
        send_event(event_connection, encode_terminal(request, result))
    except WorkerProtocolError as exc:
        _send_failure_quietly(
            event_connection,
            request,
            "protocol-error",
            str(exc),
        )
    except MemoryError:
        _send_failure_quietly(
            event_connection,
            request,
            "worker-resource-exhaustion",
            "converter worker exhausted its bounded process resources",
        )
    except (EOFError, BrokenPipeError, OSError):
        _send_failure_quietly(
            event_connection,
            request,
            "request-transport-error",
            "converter worker transport closed before terminal publication",
        )
    except Exception:
        _send_failure_quietly(
            event_connection,
            request,
            "worker-internal-error",
            "converter worker failed before terminal publication",
        )
    finally:
        _close_quietly(request_connection)
        _close_quietly(control_connection)
        _close_quietly(event_connection)


def _listen_for_cancel(
    connection: ByteConnection,
    request: WorkerRequest,
    token: CancellationToken,
) -> None:
    try:
        control = receive_control(connection)
        if (
            control.generation == request.generation
            and control.bundle_fingerprint == request.bundle_fingerprint
            and control.transport_fingerprint == request.transport_fingerprint
        ):
            token.cancel()
    except (WorkerProtocolError, EOFError, BrokenPipeError, OSError):
        return
    finally:
        _close_quietly(connection)


def _send_failure_quietly(
    connection: ByteConnection,
    request: WorkerRequest | None,
    classification: str,
    message: str,
) -> None:
    try:
        send_event(
            connection,
            encode_failure(request, classification, message),
        )
    except (WorkerProtocolError, EOFError, BrokenPipeError, OSError):
        pass


def _close_quietly(connection: ByteConnection) -> None:
    try:
        connection.close()
    except (BrokenPipeError, OSError):
        pass
