"""Phase 13 bounded immutable static-record analysis."""

from .analysis import StaticRecordAnalyzer
from .lowering import RecordCIRLowerer, RecordLoweringServices
from .model import (
    MAX_RECORD_FIELDS,
    RecordAnalysisCanceled,
    RecordAnalysisError,
    RecordDefinitionFact,
    RecordFieldAccessFact,
    RecordFieldFact,
    RecordInitializerFact,
    RecordInstanceBindingFact,
    RecordInstanceFact,
    RecordValueCategory,
    StaticRecordAnalysis,
)

__all__ = [
    "MAX_RECORD_FIELDS",
    "RecordAnalysisCanceled",
    "RecordAnalysisError",
    "RecordDefinitionFact",
    "RecordFieldAccessFact",
    "RecordFieldFact",
    "RecordInitializerFact",
    "RecordInstanceBindingFact",
    "RecordInstanceFact",
    "RecordCIRLowerer",
    "RecordLoweringServices",
    "RecordValueCategory",
    "StaticRecordAnalysis",
    "StaticRecordAnalyzer",
]
