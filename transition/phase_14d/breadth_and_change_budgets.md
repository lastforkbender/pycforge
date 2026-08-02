# Phase 14D Breadth and Change Budgets

Status: required-keyword-only opening budget. Crossing a limit pauses
implementation and requires a new reviewed decision. Limits are ceilings, not
implementation targets.

## Breadth budget

| Dimension | Maximum authorized breadth |
| --- | --- |
| New semantic family | One: exact required keyword-only parameters for already-resolved direct source functions |
| Existing Python node kinds consumed | `FunctionDef`, `arguments`, `arg`, `Call`, and `keyword` only |
| New Python or C IR node kinds | Zero |
| New declaration profile | One: otherwise eligible function with one or more required keyword-only formals |
| New call profile | One: exact direct call covering required keyword-only formals by explicit names |
| Target profile | Already-resolved eligible same- or cross-module synchronous top-level source function only |
| Positional declaration profile | Existing required positional-only and positional-or-keyword formals only |
| Keyword-only declaration profile | One or more exactly annotated `kwonlyargs`, every corresponding `kw_defaults` entry null |
| Defaults | Zero positional defaults and zero keyword-only defaults |
| Variadics | No `*args` or `**kwargs` |
| Binding coverage | Every admitted required formal exactly once |
| Positional-only handling | Positional prefix only; never keyword-addressable |
| Keyword-only handling | Explicit named actual only; never positional-addressable |
| Category and representation | Exact existing actual/formal match |
| New statement, expression, or visible binding forms | Zero |
| New fact-table families | Exactly one `keyword-only-call-binding-facts` table under `fact-table/0.14.3` |
| Fact coverage | Complete positive and negative resolved direct-call candidate coverage; call-keyed only |
| New RulePlan families | At most one |
| RulePlan identity | `phase14.keyword_only_call.exact_binding@0.14.3` |
| Existing RulePlan extensions | Affected supported `FunctionDef` plans gain exact keyword-only declaration and C-interface mode-erasure evidence |
| New source diagnostic codes | Zero |
| New helper requirements or assets | Zero |
| New runtime failure channels | Zero |
| New value categories or representations | Zero |
| Allocation, ownership, lifetime, or cleanup changes | Zero |
| New renderer constructs | Zero |
| New public request or approximation policy fields | Zero |
| Other Phase 14 evaluations | Zero |

An eligible declaration contains at least one required keyword-only parameter.
An eligible call necessarily contains at least one explicit named actual because
every required keyword-only formal must be supplied.

The C prototype and definition include all admitted formals in Python formal
order using existing `CParameter` nodes. C's positional syntax is not authority
to weaken the statically enforced source-call mode.

Defaults, omitted formals, defaulted keyword-only parameters, variadics,
`*`/`**` unpacking, `range`, record constructors, methods, dynamic targets,
recursion, and all neighboring profiles are outside this budget. Static
rejection is not authority to model Python `TypeError`.

## Resource breadth

No new parameter-count, argument-count, call-count, or function-count constant
is authorized. Phase 14D continues to rely on sealed source-byte, line, token,
AST-node, maximum-nesting, function/signature, diagnostic, trace, and pipeline
resource ceilings.

For each signature or bounded analysis scope:

- build formal-name, kind, and ordinal indexes once;
- walk declaration formals once;
- walk positional and keyword actual sequences once;
- reconstruct binding from Python IR and predecessor facts once;
- assemble C parameters once in formal order;
- stage each actual and its predecessor-owned prerequisites once; and
- assemble one pure reference per formal once.

Declaration analysis, binding, independent validation, planning, lowering, and
evidence serialization remain linear in affected formals, actuals, and
referenced predecessor facts.

Repeated full-signature searches per keyword, whole-module rescans per call,
permutation enumeration, open-ended refinement, runtime lookup, and
source-controlled discovery are forbidden.

If measurement demonstrates a need for a call-specific resource ceiling,
nonlinear algorithm, or new cancellation model, implementation stops and
records evidence before a separate resource decision.

## Semantic and schema change budget

- Exactly one immutable table,
  `keyword-only-call-binding-facts` under `fact-table/0.14.3`, may be
  introduced. It is call-keyed and complete over resolved direct-call
  candidates whose targets have required-keyword-only declarations and reach
  the Phase 14D static binder, including negative call candidates. It contains
  no declaration record.
- Required-keyword-only declarations remain in existing
  `function-signature-facts`; the serialized `ParameterFact` shape does not
  change. Parameter kind and required status are reconstructed from normalized
  Python IR.
- Affected existing supported `FunctionDef` RulePlans publish exact
  keyword-only declaration/parameter facts, declaration obligations, and
  C-interface mode-erasure containment, including for an admitted function with
  no call site. This is not a second new rule family.
- Call records publish both source-evaluation and formal-reference orders,
  exact actual/formal associations, complete coverage, categories, support
  state, diagnostic, rejection node, lowering shape, and provenance.
- Every negative call record has `supported: false`, one exact owning diagnostic, a
  nonempty reason, a precise rejection node, and no Phase 14D RulePlan or C IR.
- Every selected Phase 14D call has exactly one supported fact, and every
  selected `phase14.keyword_only_call.exact_binding@0.14.3` RulePlan references
  exactly one supported fact.
- At most one RulePlan family may be introduced:
  `phase14.keyword_only_call.exact_binding@0.14.3`.
- The exact lowering shape is
  `source-order-actual-temporaries-formal-order-references-v1`.
- The prospective active identities are:
  `phase14-required-keyword-only-calls-v0.14.3`,
  `c-renderer-v0.14.3`, `fact-table/0.14.3`,
  `conversion-plan/0.14.3`, `c-ir/0.14.3`,
  `generated-c/0.14.3`, `pycforge.conversion-summary/0.14.3`, and
  `pycforge.decision-trace/0.14.3`.
- Advancing C IR and renderer envelopes does not authorize a new C IR dataclass,
  enum member, statement, expression, type, storage mode, qualifier, linkage
  rule, or renderer syntax.
- SourceBundle 0.2, Python IR 0.4, result serialization 0.5, semantic policy,
  target contract, approximation policy, and helper/container/module/record/
  numeric/conditional/workspace identities are frozen.
- No public keyword-only policy field may be added. The exact fact and RulePlan
  own the source-call obligation.
- Existing Phase 14C fields and facts retain their ordered meanings. Phase 14D
  may reference them but may not silently append a new interpretation to an
  explicit historical 0.14.2 artifact.

## Diagnostic budget

No new source diagnostic code is required or authorized by this opening.

- `PYC2901` and `PYC2902` retain target and module eligibility.
- `PYC2904` retains missing required coverage and excess positional arity,
  including a positional attempt to enter the keyword-only range.
- `PYC2905` retains exact representation mismatch.
- `PYC2910` retains `*`/`**`, null-name unpacking, and excluded call shapes.
- `PYC2911` retains defaults, defaulted keyword-only parameters, variadics, and
  keyword-only declaration profiles outside the exact 14D boundary. Active
  0.14.3 documentation narrows only the rejection of an otherwise valid
  required keyword-only declaration.
- `PYC2912` retains exact static name-binding failures: unknown keyword,
  positional-only keyword, collision, and duplicate binding.
- Existing decorated/generic, nested/closure, recursion, annotation, return,
  module, numeric, conditional, container, and record diagnostics retain
  precedence.

Historical diagnostic meanings and serialized records are immutable. One root
cause produces one primary span-bearing diagnostic; blocked parents retain
causal references instead of cascades.

If implementation requires a new diagnostic meaning, code, severity, or
precedence class, work stops for a separately reviewed diagnostic-budget
decision.

## Compatibility budget

- `phase14-direct-keyword-calls-v0.14.2`,
  `c-renderer-v0.14.2`, and `fact-table/0.14.2` remain explicit historical
  identities.
- An explicit 0.14.2 request retains its exact canonical request shape, facts,
  plans, generated-C bytes, output fingerprint, payload, summary, trace,
  diagnostics, and rejection of keyword-only declarations. No 14D field may
  leak into that shape.
- All earlier explicit historical configurations retain their sealed behavior.
- Under active 0.14.3 identities, a source with no Phase 14D declaration or
  selected call behavior retains predecessor generated-C bytes and output
  fingerprints. Versioned envelopes may differ only where this opening permits.
- Phase 14A helper source, interface, version, registry membership,
  fingerprints, and generated helper bytes remain exact.
- Phase 14B conditional facts, guards, prerequisite containment, and
  predecessor generated C remain exact.
- Phase 14C direct-keyword facts, exact two-order binding, diagnostic
  precedence, RulePlan, lowering shape, generated C for predecessor sources,
  historical audits, and release evidence remain exact.
- Existing SourceBundle closure, module initialization, record/container
  ownership, workspace staleness, read-only generated C, and atomic linked-save
  behavior may not change.

## Implementation-location budget

Required-keyword-only declaration analysis, existing-signature and
`FunctionDef`-plan evidence, call-fact construction, independent
reconstruction, and formal-kind validation belong behind an isolated component
boundary or a narrowly extended existing static-binding boundary.

Integration edits may later touch only active contract identities and
capability checks, signature analysis, local parameter initialization,
declaration/prototype construction, call eligibility, call-graph inputs,
planning, fact publication and validation, lowering delegation, summaries,
traces, diagnostics/feature metadata, audits, tests, and release evidence.

The cumulative `pycforge/converter/lowering.py` file opens at 991 lines against
the 1,000-line architecture ceiling. Phase 14D may not implement signature
classification or keyword-only binding inline there and may not cross the
ceiling. If an affected module would cross its architecture limit, split an
owned component rather than stretching the limit.

Analysis cannot depend on C IR or rendering. Lowering cannot resolve source
names, classify formal kinds, decide support, repair coverage, or emit final C
text. Rendering cannot infer keyword-only semantics.

GUI widgets, workspace state, saving, source acquisition, host discovery,
module-resolution policy, container/record ownership, numeric or conditional
semantics, helper registry, C IR syntax invention, and renderer formatting
policy are outside the implementation-location budget.

## Complexity, cancellation, observer, and publication budget

- Declaration analysis, existing-plan extension, call-fact construction,
  independent validation, planning, C-parameter assembly, actual staging, and
  formal-vector assembly remain linear.
- Cancellation checks are required during declaration/parameter analysis, fact
  construction, independent reconstruction, RulePlan publication, C parameter
  assembly, per-actual prerequisite/staging, and formal-vector assembly.
- Rejection, cancellation, resource exhaustion, internal validation failure,
  observer failure, or interrupted replacement publishes no partial current
  fact table, plan, C IR, mapping, helper manifest, summary, decision trace,
  telemetry snapshot, or generated C.
- Observers remain bounded and semantically inert. Their configuration,
  truncation, delay, absence, or failure cannot influence formal kinds,
  bindings, order vectors, temporary names, diagnostics, mappings, generated
  bytes, or fingerprints.
- Failed, canceled, rejected, stale, or observation-incomplete results cannot
  replace the last successful result or make stale C savable as current.

## Budget reopening triggers

Stop Phase 14D rather than stretching this budget if implementation appears to
need:

- positional or keyword-only default evaluation, storage, or substitution;
- omission of a required formal;
- variadic state or `*`/`**` unpacking;
- runtime lookup, a Python argument binder, or `TypeError` propagation;
- a new value category, representation, helper, helper version, allocation,
  ownership transfer, cleanup, or failure channel;
- a new Python IR or C IR node, renderer construct, or public policy field;
- more than one new fact table or new RulePlan family;
- a new source diagnostic code or changed historical diagnostic meaning;
- superlinear analysis, a call-specific resource ceiling, or open-world
  discovery;
- an unapproved StableInternal schema break;
- loss of exact 0.14.2 compatibility; or
- any neighboring Phase 14 mini-phase or Phase 15 work.
