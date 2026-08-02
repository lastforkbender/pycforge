"""Phase 14C exact direct keyword-call analysis and lowering."""

from .analysis import KeywordCallAnalyzer
from .model import (
    KEYWORD_CALL_FACT_SCHEMA,
    KEYWORD_CALL_KEY_DOMAIN,
    KEYWORD_CALL_LOWERING_SHAPE,
    KEYWORD_CALL_OBLIGATIONS,
    KEYWORD_CALL_PROVENANCE_EVIDENCE,
    KEYWORD_CALL_RULE_ID,
    KEYWORD_CALL_RULE_VERSION,
    KEYWORD_CALL_TABLE_DEPENDENCIES,
    KEYWORD_CALL_TABLE_ID,
    KeywordArgumentBindingFact,
    KeywordCallAnalysis,
    KeywordCallAnalysisCanceled,
    KeywordCallAnalysisError,
    KeywordCallBindingFact,
    KeywordCallRejection,
    KeywordCallValidationCanceled,
    keyword_call_binding_id,
)
from .validation import validate_keyword_call_binding_facts


_LOWERING_EXPORTS = {
    "KeywordCallCIRLowerer",
    "KeywordCallLoweringServices",
    "bind_keyword_call_lowerer",
}


def __getattr__(name: str):
    """Keep analysis/validation imports independent of the C IR layer."""

    if name not in _LOWERING_EXPORTS:
        raise AttributeError(name)
    from . import lowering

    value = getattr(lowering, name)
    globals()[name] = value
    return value


__all__ = [
    "KEYWORD_CALL_FACT_SCHEMA",
    "KEYWORD_CALL_KEY_DOMAIN",
    "KEYWORD_CALL_LOWERING_SHAPE",
    "KEYWORD_CALL_OBLIGATIONS",
    "KEYWORD_CALL_PROVENANCE_EVIDENCE",
    "KEYWORD_CALL_RULE_ID",
    "KEYWORD_CALL_RULE_VERSION",
    "KEYWORD_CALL_TABLE_DEPENDENCIES",
    "KEYWORD_CALL_TABLE_ID",
    "KeywordArgumentBindingFact",
    "KeywordCallAnalysis",
    "KeywordCallAnalysisCanceled",
    "KeywordCallAnalysisError",
    "KeywordCallAnalyzer",
    "KeywordCallBindingFact",
    "KeywordCallCIRLowerer",
    "KeywordCallLoweringServices",
    "KeywordCallRejection",
    "KeywordCallValidationCanceled",
    "bind_keyword_call_lowerer",
    "keyword_call_binding_id",
    "validate_keyword_call_binding_facts",
]
