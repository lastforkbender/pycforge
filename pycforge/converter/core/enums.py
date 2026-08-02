from __future__ import annotations
from enum import Enum

class ResultStatus(str, Enum):
    CONVERTED = "Converted"
    CONVERTED_WITH_WARNINGS = "ConvertedWithWarnings"
    CONVERTED_WITH_APPROXIMATIONS = "ConvertedWithApproximations"
    REJECTED = "Rejected"
    INTERNAL_FAILURE = "InternalFailure"
    CANCELED = "Canceled"

class StageTerminal(str, Enum):
    COMPLETED = "Completed"
    REJECTED = "Rejected"
    INTERNAL_FAILURE = "InternalFailure"
    CANCELED = "Canceled"

class Severity(str, Enum):
    INFORMATION = "Information"
    WARNING = "Warning"
    APPROXIMATION = "Approximation"
    ERROR = "Error"
    INTERNAL_ERROR = "InternalError"
