"""Current public and StableInternal contract identities.

Keeping active identities in one data-only module prevents the pipeline,
serialization, CLI, and observers from silently publishing different phases.
Historical identities remain beside their historical readers.
"""

SOURCE_BUNDLE_SCHEMA = "source-bundle/0.2"
PYTHON_IR_BUNDLE_SCHEMA = "python-ir/0.4"

# The install/package version may advance for hardening or distribution work
# without changing deterministic conversion records.  This identity advances
# only when the active converter semantics or serialized contracts advance.
CONVERTER_CONTRACT_VERSION = "0.14.3"

# Phase 12 readers and explicit historical requests keep exact identities.
PHASE12_CONVERSION_PLAN_SCHEMA = "conversion-plan/0.12"
PHASE12_C_IR_SCHEMA = "c-ir/0.12"
PHASE12_GENERATED_C_SCHEMA = "generated-c/0.12"
PHASE12_CONVERSION_SUMMARY_SCHEMA = "pycforge.conversion-summary/0.12"
PHASE12_DECISION_TRACE_SCHEMA = "pycforge.decision-trace/0.12"

PHASE13_CONVERSION_PLAN_SCHEMA = "conversion-plan/0.13"
PHASE13_C_IR_SCHEMA = "c-ir/0.13"
PHASE13_GENERATED_C_SCHEMA = "generated-c/0.13"
PHASE13_CONVERSION_SUMMARY_SCHEMA = "pycforge.conversion-summary/0.13"
PHASE13_DECISION_TRACE_SCHEMA = "pycforge.decision-trace/0.13"

# Phase 14A readers and explicit historical requests keep exact identities.
PHASE14A_CONVERSION_PLAN_SCHEMA = "conversion-plan/0.14"
PHASE14A_C_IR_SCHEMA = "c-ir/0.14"
PHASE14A_GENERATED_C_SCHEMA = "generated-c/0.14"
PHASE14A_CONVERSION_SUMMARY_SCHEMA = "pycforge.conversion-summary/0.14"
PHASE14A_DECISION_TRACE_SCHEMA = "pycforge.decision-trace/0.14"
PHASE14_CONVERSION_PLAN_SCHEMA = PHASE14A_CONVERSION_PLAN_SCHEMA
PHASE14_C_IR_SCHEMA = PHASE14A_C_IR_SCHEMA
PHASE14_GENERATED_C_SCHEMA = PHASE14A_GENERATED_C_SCHEMA
PHASE14_CONVERSION_SUMMARY_SCHEMA = PHASE14A_CONVERSION_SUMMARY_SCHEMA
PHASE14_DECISION_TRACE_SCHEMA = PHASE14A_DECISION_TRACE_SCHEMA

PHASE14B_CONVERSION_PLAN_SCHEMA = "conversion-plan/0.14.1"
PHASE14B_C_IR_SCHEMA = "c-ir/0.14.1"
PHASE14B_GENERATED_C_SCHEMA = "generated-c/0.14.1"
PHASE14B_CONVERSION_SUMMARY_SCHEMA = "pycforge.conversion-summary/0.14.1"
PHASE14B_DECISION_TRACE_SCHEMA = "pycforge.decision-trace/0.14.1"

# Phase 14C readers and explicit historical requests keep exact identities.
PHASE14C_CONVERSION_PLAN_SCHEMA = "conversion-plan/0.14.2"
PHASE14C_C_IR_SCHEMA = "c-ir/0.14.2"
PHASE14C_GENERATED_C_SCHEMA = "generated-c/0.14.2"
PHASE14C_CONVERSION_SUMMARY_SCHEMA = "pycforge.conversion-summary/0.14.2"
PHASE14C_DECISION_TRACE_SCHEMA = "pycforge.decision-trace/0.14.2"

CONVERSION_PLAN_SCHEMA = "conversion-plan/0.14.3"
C_IR_SCHEMA = "c-ir/0.14.3"
GENERATED_C_SCHEMA = "generated-c/0.14.3"
CONVERSION_SUMMARY_SCHEMA = "pycforge.conversion-summary/0.14.3"
DECISION_TRACE_SCHEMA = "pycforge.decision-trace/0.14.3"

# The result envelope shape is unchanged. Its nested summary and trace carry
# their own bumped schema identities, so result serialization remains 0.5.
RESULT_SCHEMA_VERSION = "0.5"
CONTAINER_FACT_SCHEMA = "fact-table/0.11"
MODULE_FACT_SCHEMA = "fact-table/0.12"
RECORD_FACT_SCHEMA = "fact-table/0.13"
NUMERIC_FACT_SCHEMA = "fact-table/0.14"
CONDITIONAL_FACT_SCHEMA = "fact-table/0.14.1"
CONDITIONAL_REGION_FACT_SCHEMA = CONDITIONAL_FACT_SCHEMA
PHASE14B_CONDITIONAL_FACT_SCHEMA = CONDITIONAL_FACT_SCHEMA
KEYWORD_CALL_FACT_SCHEMA = "fact-table/0.14.2"
KEYWORD_ONLY_CALL_FACT_SCHEMA = "fact-table/0.14.3"
