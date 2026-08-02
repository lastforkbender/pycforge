"""Phase 14D exact required keyword-only direct-call support."""

from .analysis import KeywordOnlyCallAnalyzer
from .model import (
    KEYWORD_ONLY_CALL_FACT_SCHEMA,
    KEYWORD_ONLY_CALL_KEY_DOMAIN,
    KEYWORD_ONLY_CALL_LOWERING_SHAPE,
    KEYWORD_ONLY_CALL_OBLIGATIONS,
    KEYWORD_ONLY_CALL_PROVENANCE_EVIDENCE,
    KEYWORD_ONLY_CALL_RULE_ID,
    KEYWORD_ONLY_CALL_RULE_VERSION,
    KEYWORD_ONLY_CALL_TABLE_DEPENDENCIES,
    KEYWORD_ONLY_CALL_TABLE_ID,
    KeywordOnlyArgumentBindingFact,
    KeywordOnlyCallAnalysis,
    KeywordOnlyCallAnalysisCanceled,
    KeywordOnlyCallAnalysisError,
    KeywordOnlyCallBindingFact,
    KeywordOnlyCallRejection,
    KeywordOnlyCallValidationCanceled,
    keyword_only_call_binding_id,
)
from .validation import validate_keyword_only_call_binding_facts


_LOWERING_EXPORTS = {
    "KeywordOnlyCallCIRLowerer",
    "KeywordOnlyCallLoweringServices",
    "bind_keyword_only_call_lowerer",
}


def __getattr__(name: str):
    """Keep analysis and validation independent of the C IR layer."""

    if name not in _LOWERING_EXPORTS:
        raise AttributeError(name)
    from . import lowering

    value = getattr(lowering, name)
    globals()[name] = value
    return value


__all__ = [
    "KEYWORD_ONLY_CALL_FACT_SCHEMA",
    "KEYWORD_ONLY_CALL_KEY_DOMAIN",
    "KEYWORD_ONLY_CALL_LOWERING_SHAPE",
    "KEYWORD_ONLY_CALL_OBLIGATIONS",
    "KEYWORD_ONLY_CALL_PROVENANCE_EVIDENCE",
    "KEYWORD_ONLY_CALL_RULE_ID",
    "KEYWORD_ONLY_CALL_RULE_VERSION",
    "KEYWORD_ONLY_CALL_TABLE_DEPENDENCIES",
    "KEYWORD_ONLY_CALL_TABLE_ID",
    "KeywordOnlyArgumentBindingFact",
    "KeywordOnlyCallAnalysis",
    "KeywordOnlyCallAnalysisCanceled",
    "KeywordOnlyCallAnalysisError",
    "KeywordOnlyCallAnalyzer",
    "KeywordOnlyCallBindingFact",
    "KeywordOnlyCallCIRLowerer",
    "KeywordOnlyCallLoweringServices",
    "KeywordOnlyCallRejection",
    "KeywordOnlyCallValidationCanceled",
    "bind_keyword_only_call_lowerer",
    "keyword_only_call_binding_id",
    "validate_keyword_only_call_binding_facts",
]
