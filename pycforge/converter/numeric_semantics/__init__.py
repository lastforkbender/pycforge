"""Bounded Phase 14A integer floor-arithmetic feature package."""

from .analysis import BoundedNumericAnalyzer
from .lowering import NumericCIRLowerer, NumericLoweringServices, bind_numeric_lowerer
from .model import (
    BoundedNumericAnalysis,
    FloorArithmeticKind,
    NumericAnalysisCanceled,
    NumericAnalysisError,
    NumericOperationFact,
)

__all__ = [
    "BoundedNumericAnalysis",
    "BoundedNumericAnalyzer",
    "FloorArithmeticKind",
    "NumericAnalysisCanceled",
    "NumericAnalysisError",
    "NumericCIRLowerer",
    "NumericLoweringServices",
    "NumericOperationFact",
    "bind_numeric_lowerer",
]
