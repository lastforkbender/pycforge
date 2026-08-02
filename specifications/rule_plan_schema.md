# RulePlan Schema — cumulative through 0.14.3

A RulePlan is a frozen serializable decision containing `plan_id`,
`decision_key`, versioned rule identity, source document/node, terminal support
state, facts used, semantic obligations, resolved/unresolved obligations, exact
helper requirements, and explanation tokens. A supported decision has exactly
one plan; unsupported decisions have none. Published plans have no unresolved
obligation and their resolutions exactly equal their declared obligations.

Phase 9 function/call and Phase 11 container obligations remain unchanged.
Phase 10 exact helper requirements remain unique and sorted; the conversion-plan
requirement set equals their exact RulePlan-owned union.

Phase 12 plans cite exact module, import, namespace, dependency, initialization,
linkage/name, and cross-module call facts. They close:

- canonical explicit bundle membership and source identity;
- SourceBundle-only exact import resolution and direct target eligibility;
- isolated namespace and immutable imported-function alias identity;
- exact signature, arity, representation, and once-only call ordering;
- no module value, re-export, package fallback, or source-driven discovery;
- complete acyclic dependency proof and deterministic initialization order;
- compile-time-only namespace construction with no runtime initialization state;
- external source-function linkage, collision-free `pycm_` naming, and singleton
  legacy-name compatibility;
- one translation unit, complete prototype/definition order, and correct
  per-document mapping relationships.

New module plans have empty helper requirements and introduce no ownership,
allocation, cleanup, or runtime failure channel. Lowering, diagnostics, mappings,
summaries, and traces reference the same plan identity; no later pass reselects
a module rule or re-resolves an import.

Phase 13 adds seven record rule families: class, field, structural initializer,
construction, owner binding, record name, and direct attribute read. Together
they resolve exact record/field/binding identities; field layout and scalar
types; initializer coverage; source-order once-only argument evaluation; fresh
automatic ownership; immutable/noalias/noescape lifetime; exact direct receiver
and field selection; module locality; and exclusion of heap, null, cleanup,
ordinary methods, and the general Python object model.

Record RulePlans cite the corresponding complete `fact-table/0.13` records and
have empty helper requirement sets. The structural `__init__` plan authorizes
aggregate initialization only, not a callable C function. Any dangling record
fact, unresolved obligation, unsupported use occurrence, or later attempt to
infer a new field/receiver causes validation failure before lowering.

Phase 14A adds one `phase14.numeric.floor_arithmetic` rule family. Each
accepted `//` or `%` occurrence receives one plan citing its complete
`numeric-operation-facts` record. Its resolved obligations cover exact
integer-like categories and signed-64 representation, direct safe literal
divisor proof, Python floor-quotient or divisor-sign-remainder meaning,
left-to-right once-only evaluation, scalar ownership, absence of runtime
failure/allocation/cleanup, target and provenance, and the exact frozen helper.

Floor division requires only `pycf.i64.floor_div@1.0.0`; modulo requires only
`pycf.i64.floor_mod@1.0.0`. Repeated references are deduplicated only when the
plan-owned union is resolved. Unsupported numeric candidates receive no
RulePlan and select no helper. Lowering cannot infer a divisor, repair missing
proof, or substitute a helper.

Phase 14B adds two helper-free version `0.14.1` rule families:
`phase14.conditional.boolean_region` for `BoolOp` and
`phase14.conditional.comparison_region` for `Compare`. Each selected region
extends its existing Boolean-supported plan with exactly these fact forms:
`conditional-region:<node-id>`, `conditional-region-kind:<kind>`,
`conditional-unconditional-prefix:<count>`,
`conditional-guarded-operand-count:<count>`,
`conditional-lowering-shape:flat-guarded-assignment-v1`, and
`conditional-target:c11-portable-fixed-v1`; the retained base fact is
`value-category:boolean-like`.

The appended explanation is exactly `conditional-region`, region kind,
`unconditional-prefix`, count, `guarded-operands`, count, `lowered-as`, and
`flat-guarded-assignment-v1`, following the existing selected-rule prefix. The
semantic and resolved obligation sequences are exactly:

- `scalar-operand-representations-proved`;
- `unconditional-prefix-proved`;
- `guard-polarity-proved`;
- `short-circuit-order-preserved`;
- `operands-evaluated-left-to-right-once`;
- `prerequisite-statements-branch-contained`;
- `intermediate-values-reused-without-reevaluation`;
- `structured-c-ir-only`;
- `result-materialized-once`;
- `allocation-and-cleanup-absent`;
- `runtime-failure-channel-unchanged`;
- `source-provenance-anchored`;
- `cancellation-safe-points-honored`; and
- `target-contract-exact`.

The unresolved and region-owned helper sets are empty. Nested calls and Phase
14A numeric operations retain their own plans and helper ownership. Independent
validation requires exact fact/plan coverage; historical 0.14 plans do not
acquire either conditional rule.

Phase 14C adds one helper-free version `0.14.2` rule family:
`phase14.keyword_call.exact_binding` for an eligible direct source-function
`Call` containing at least one explicit named keyword. Its fact forms include
the deterministic binding identity, call node, target binding, source-argument
count, parameter count, and
`source-order-temporaries-formal-order-references-v1` lowering shape, alongside
the retained annotation, category, and direct call-target evidence.

Its semantic and resolved obligation sequences are exactly:

- `direct-source-target-resolved-once`;
- `explicit-keywords-only-no-unpacking`;
- `positional-prefix-bound-in-order`;
- `keyword-names-bound-to-positional-or-keyword-parameters`;
- `parameter-coverage-exact`;
- `argument-representations-compatible-after-binding`;
- `source-arguments-evaluated-left-to-right-once`;
- `argument-temporaries-reordered-only-after-evaluation`;
- `c-call-arguments-in-formal-order`;
- `parameter-ownership-boundary-explicit`;
- `runtime-binding-failure-absent`;
- `allocation-and-cleanup-absent`;
- `structured-c-ir-only`;
- `source-provenance-anchored`;
- `cancellation-safe-points-honored`; and
- `target-contract-exact`.

The rule-owned helper set is empty. Nested calls, numeric operations,
containers, records, and conditional regions retain their own plans and helper
ownership. Independent validation requires exact binding-fact, call-target,
fact-set, obligation, rule-version, and plan coverage. Historical 0.14.1 plans
do not acquire this rule or observe the keyword-call table.

Phase 14D adds one helper-free version `0.14.3` call rule family:
`phase14.keyword_only_call.exact_binding`. It selects an eligible direct
source-function `Call` whose target declaration has one or more required
keyword-only parameters. Its facts identify the call-keyed
`keyword-only-call-binding-facts` record, direct target, required-keyword-only
signature, formal kinds/count, source-actual count, exact required coverage,
and `source-order-actual-temporaries-formal-order-references-v1`, alongside
retained annotation, category, ownership, and target evidence.

Its semantic and resolved obligation sequences are exactly:

- `direct-source-target-resolved-once`;
- `required-keyword-only-parameters-proved`;
- `defaults-variadics-and-unpacking-absent`;
- `positional-actuals-limited-to-positional-formals`;
- `keyword-names-bound-to-keyword-addressable-parameters`;
- `required-keyword-only-coverage-exact`;
- `parameter-coverage-exact`;
- `argument-representations-compatible-after-binding`;
- `source-arguments-evaluated-left-to-right-once`;
- `argument-temporaries-reordered-only-after-evaluation`;
- `c-call-arguments-in-formal-order`;
- `parameter-ownership-boundary-explicit`;
- `runtime-binding-failure-absent`;
- `allocation-and-cleanup-absent`;
- `structured-c-ir-only`;
- `source-provenance-anchored`;
- `cancellation-safe-points-honored`; and
- `target-contract-exact`.

Affected existing supported `FunctionDef` RulePlans gain these exact facts:

- `keyword-only-signature:{function_id}`;
- `keyword-only-parameter-count:{n}`;
- one
  `keyword-only-parameter:{ordinal}:{parameter_id}:{name}`
  per required keyword-only formal; and
- `keyword-only-c-interface:mode-erased-after-static-binding`.

Their appended semantic and resolved obligations are exactly:

- `required-keyword-only-parameters-exact`;
- `keyword-only-parameter-kinds-preserved`;
- `c-interface-mode-erasure-after-static-binding`; and
- `defaults-and-variadics-absent`.

Their appended explanation tokens are
`required-keyword-only-signature`, count, `c-interface-mode-erasure`, and
`after-static-binding`. These plans consume existing `function-signature-facts`;
they do not create a second new rule family or a declaration record in the
call-keyed table. Independent validation covers them even when the admitted
function has no call site.

The Phase 14D call rule and affected FunctionDef plans own no helper. Nested
calls, numeric operations, containers, records, and conditional regions retain
their own plans and helper ownership. Independent validation requires exact
signature, call-fact, target, parameter-kind, coverage, fact-set, obligation,
rule-version, and C-interface evidence. Historical 0.14.2 plans do not acquire
the new rule, required-keyword-only obligations, or call-fact table.
