"""Phase 14B conditional temporary-region analysis and lowering."""

from .analysis import ConditionalRegionAnalyzer
from .model import (
    CONDITIONAL_REGION_KEY_DOMAIN,
    CONDITIONAL_REGION_LOWERING_SHAPE,
    CONDITIONAL_REGION_OBLIGATIONS,
    CONDITIONAL_REGION_PROVENANCE_EVIDENCE,
    CONDITIONAL_REGION_TABLE_DEPENDENCIES,
    CONDITIONAL_REGION_TABLE_ID,
    ConditionalEvaluationMode,
    ConditionalGuardPolarity,
    ConditionalOperandPlacementFact,
    ConditionalRegionAnalysis,
    ConditionalRegionAnalysisCanceled,
    ConditionalRegionAnalysisError,
    ConditionalRegionFact,
    ConditionalRegionKind,
    ConditionalRegionValidationCanceled,
    conditional_region_id,
)

# validation is imported last so its independent reconstruction cannot become
# an accidental dependency of the producer or lowerer.
from .validation import validate_conditional_region_facts

_LOWERING_EXPORTS = {
    "ConditionalRegionCIRLowerer",
    "ConditionalRegionLoweringServices",
    "bind_conditional_region_lowerer",
}


def __getattr__(name: str):
    """Load the C-IR-facing half only when a lowering symbol is requested.

    Importing conditional analysis or validation must not acquire C IR through
    package initialization.
    """

    if name not in _LOWERING_EXPORTS:
        raise AttributeError(name)
    from . import lowering

    value = getattr(lowering, name)
    globals()[name] = value
    return value

__all__ = [
    "CONDITIONAL_REGION_KEY_DOMAIN",
    "CONDITIONAL_REGION_LOWERING_SHAPE",
    "CONDITIONAL_REGION_OBLIGATIONS",
    "CONDITIONAL_REGION_PROVENANCE_EVIDENCE",
    "CONDITIONAL_REGION_TABLE_DEPENDENCIES",
    "CONDITIONAL_REGION_TABLE_ID",
    "ConditionalEvaluationMode",
    "ConditionalGuardPolarity",
    "ConditionalOperandPlacementFact",
    "ConditionalRegionAnalysis",
    "ConditionalRegionAnalysisCanceled",
    "ConditionalRegionAnalysisError",
    "ConditionalRegionValidationCanceled",
    "ConditionalRegionCIRLowerer",
    "ConditionalRegionFact",
    "ConditionalRegionKind",
    "ConditionalRegionLoweringServices",
    "ConditionalRegionAnalyzer",
    "bind_conditional_region_lowerer",
    "conditional_region_id",
    "validate_conditional_region_facts",
]
