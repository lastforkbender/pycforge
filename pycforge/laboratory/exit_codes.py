from __future__ import annotations
from enum import IntEnum
class ExitCode(IntEnum):
    OK = 0
    REJECTED = 2
    CANCELED = 3
    INTERNAL_FAILURE = 4
    USAGE = 64
    ARTIFACT_INCOMPATIBLE = 65
    IO_FAILURE = 74
    AUDIT_FAILURE = 78
