# Phase 14C Breadth and Change Budgets

Status: binding opening budget. Crossing a limit pauses implementation and
requires a new reviewed decision. Limits are not implementation targets.

## Breadth budget

| Dimension | Maximum authorized breadth |
| --- | --- |
| New semantic family | One: exact static binding for direct source-function keyword calls |
| Python root node kinds | Existing `Call` only |
| New accepted argument form | Explicit named keywords after an ordinary positional prefix |
| Target profile | Already-resolved eligible same- or cross-module source function only |
| Declaration profile | Existing required positional-only and positional-or-keyword parameters only |
| Binding coverage | Every existing required formal exactly once |
| Positional-only handling | Positional prefix only; never keyword-addressable |
| Category and representation | Exact existing actual/formal match |
| New statement or visible binding forms | Zero |
| New fact-table families | At most one `keyword-call-binding-facts` family, complete over supported and rejected direct-keyword binder candidates |
| New RulePlan families | At most one |
| RulePlan coverage | Exactly one supported fact per selected 14C call and exactly one supported fact referenced by every selected 14C RulePlan |
| New source diagnostics | One: `PYC2912` for exact static keyword-name binding failures |
| New helper requirements or assets | Zero |
| New runtime failure channels | Zero |
| Allocation, ownership, or cleanup changes | Zero |
| New C IR node kinds or renderer constructs | Zero |
| Other Phase 14 evaluations | Zero |

At least one explicit named keyword is required to select the 14C rule. Purely
positional calls remain predecessor behavior. Existing explicit cross-module
import aliases are eligible only because the sealed resolver already maps the
call target binding directly to one source function; no Python callable value
or alias-by-assignment is admitted.

Defaults, keyword-only parameters, variadics, `*` or `**` unpacking, `range`,
record constructors, methods, dynamic targets, and recursion are outside this
budget. Static binding rejection is not authority to model Python `TypeError`.

## Resource breadth

No new parameter-count or argument-count constant is authorized. Phase 14C
continues to rely on the sealed aggregate source-byte, line, token, AST-node,
and maximum-nesting ceilings and on the predecessor function/signature resource
boundary.

The binder builds one formal-name index and walks the positional, keyword, and
formal sequences once. Fact construction, independent reconstruction,
planning, and lowering must remain linear in the call's actual and formal
counts. Repeated full-signature searches per keyword, whole-module rescans per
call, or permutation enumeration are forbidden.

If measurements demonstrate a need for a new call-specific resource ceiling,
implementation stops and records evidence before a separate resource decision.

## Semantic and schema change budget

- At most one immutable `keyword-call-binding-facts` family under
  `fact-table/0.14.2` may be introduced. Its exact domain is every
  keyword-bearing direct-source-function candidate whose existing declaration
  signature reaches the static binder, including rejected negative facts.
- Every negative fact must publish `supported: false`, its exact diagnostic,
  nonempty reason and rejection node, and no RulePlan or C IR. Every selected
  14C call has exactly one supported fact, and every selected 14C RulePlan
  references exactly one supported fact. No candidate may be omitted and no
  noncandidate may acquire a record.
- At most one RulePlan definition may be introduced:
  `phase14.keyword_call.exact_binding@0.14.2`.
- The active identities may advance to
  `phase14-direct-keyword-calls-v0.14.2`, `c-renderer-v0.14.2`,
  `conversion-plan/0.14.2`, `c-ir/0.14.2`, `generated-c/0.14.2`,
  `pycforge.conversion-summary/0.14.2`, and
  `pycforge.decision-trace/0.14.2`.
- Advancing the C IR envelope does not authorize a new C IR dataclass, enum
  member, statement kind, expression kind, type, storage mode, or renderer
  syntax.
- SourceBundle 0.2, Python IR 0.4, result serialization 0.5, semantic policy,
  target contract, and helper/container/module/record/numeric/conditional/
  workspace policy identities are frozen.
- No public keyword-binding policy field may be added. The rule and exact fact
  own the decision.
- Existing call-target fields may be consumed as predecessor target evidence,
  but their established ordered meanings may not be silently repurposed. The
  new fact must name source evaluation order and formal call order separately.
- `PYC2910` remains the `*`/`**`, null-name, unpacking, and excluded-shape
  boundary. `PYC2912` is limited to exact static name-binding failures on an
  otherwise eligible direct target: unknown keyword names, positional-only
  names used by keyword, positional/keyword collisions, and duplicate
  keywords. Existing target, signature, arity, category, and recursion
  diagnostics retain precedence.

## Compatibility budget

- `phase14-conditional-regions-v0.14.1` and `c-renderer-v0.14.1` remain explicit
  historical configuration identities.
- An explicit historical 0.14.1 request must preserve its exact canonical
  request shape, facts, plans, generated-C bytes, output fingerprint, payload,
  summary, trace, diagnostics, and rejection of keyword calls. No 14C field may
  leak into that shape.
- All earlier explicit historical configurations retain their sealed behavior.
- Under the new active configuration, a source with no selected 14C call must
  preserve predecessor generated-C bytes and output fingerprints. Versioned
  envelopes may differ only where this opening explicitly permits.
- Phase 14A helper sources, interfaces, versions, registry membership, registry
  fingerprint, and generated helper bytes remain exact.
- Phase 14B region facts, guards, prerequisite containment, generated C for
  predecessor sources, and historical audits remain exact. A keyword actual
  containing a region composes with that sealed fact; it cannot change it.
- Existing SourceBundle closure, module initialization, record/container
  ownership, workspace staleness, read-only generated C, and linked-save
  behavior may not change.

## Implementation-location budget

One isolated direct-call-binding component may own keyword discovery, static
binding facts, independent binding reconstruction, and formal-order adaptation.
Integration edits are limited to active contract identities and capability
checks, analysis publication, effective call eligibility, call-graph inputs,
planning, fact validation, lowering delegation, summaries, traces,
diagnostics/feature metadata, audits, tests, and later release evidence.

The cumulative `pycforge/converter/lowering.py` file is 957 lines against the
1,000-line architecture ceiling. Phase 14C must not implement binding inline or
cross that ceiling. General call lowering may delegate source-order staging and
formal-order reference assembly through a narrow service boundary. Binding
analysis cannot depend on C IR or rendering, and lowering cannot resolve source
names, decide support, or emit final C text.

GUI widgets, workspace state/control, saving, source acquisition, host import
discovery, module-resolution policy, function declaration eligibility,
container/record ownership, numeric or conditional semantics, helper registry,
and renderer syntax invention are outside the implementation-location budget.

## Complexity, cancellation, and publication budget

- Build formal-name and ordinal indexes once per signature or bounded analysis
  scope. Analysis and validation remain linear in actuals, formals, and
  referenced predecessor facts.
- Lowering stages actual values in their fact-recorded source order, then
  assembles one pure reference per formal ordinal. It may not evaluate an
  expression while iterating formal order.
- Cancellation checks are required during keyword binding, fact
  reconstruction, RulePlan publication, per-actual staging, and formal-vector
  assembly.
- Rejection, cancellation, internal validation failure, or interrupted
  replacement publishes no partial successor fact table, plan, C IR, mapping,
  helper manifest, summary, decision trace, semantic telemetry, or generated C.
- Observers remain bounded and semantically inert. Their configuration and
  failure cannot influence bindings, order vectors, temporary names, mappings,
  or output fingerprints.

## Budget reopening triggers

Stop Phase 14C rather than stretching this budget if implementation appears to
need a runtime binder, default storage/evaluation, keyword-only declarations,
variadic state, unpacking, dynamic lookup, `TypeError` propagation, a helper,
allocation, cleanup, ownership transfer, a new failure channel, a new C IR node
or renderer construct, more than one fact or rule family, a call-specific
resource ceiling, or any neighboring Phase 14 mini-phase.
