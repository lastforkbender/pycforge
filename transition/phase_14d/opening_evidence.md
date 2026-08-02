# Phase 14D Opening Evidence

Status: predecessor source authentication, feasibility, and entry checkpoint
passed. Implementation and release gates remain open. No manifest, promotion
gate, release report, or release fingerprint is present.

## Authenticated predecessor

- The sealed 1,181,034-byte PyCForge 0.14.2 source archive matched SHA-256
  `1eb9666866f38dc80993a6f39175a0d98fdc1634f3aa3ab1eeb3dded2992ffb8`.
- Safe archive inspection independently reproduced canonical release-tree
  SHA-256
  `be433ef7a46bbb208efe82087b9ef924fad48eba42e42330c7964894a269bcb4`
  and converter-subtree SHA-256
  `ba4457158430bce7fb5094f68e1b07718bd168ca96e22310193efe45bd0d882b`.
- Those values match the promoted Phase 14C custody records. The sealed wheel
  identity is `pycforge-0.14.2-py3-none-any.whl`, 309,077 bytes, SHA-256
  `6e14d24742e4bfff4017320ebdb04b35117c18fa95d97499560875a764feb4b5`.
  Candidate promotion must authenticate the preserved wheel bytes with the
  predecessor archive and current candidate.
- The sealed Phase 14C release records 474 discovered tests: 464 passing, 10
  expected PyQt5-unavailable skips, and zero failures. Its cumulative audits,
  deterministic packaging, isolated installation, atomic save, and no-toolchain
  evidence remain predecessor custody.
- Revision 3.1 and the Revision 3.2 addendum match their recorded hashes. No C
  compiler, linker, loader, generated-code executor, or widget execution claim
  participated in this opening.

## Authorization and phase selection

- The user explicitly directed: “Continue to Phase 14D”.
- The roadmap does not preassign a feature to the letter `14D`; it requires each
  Phase 14 feature to pass separate feasibility, semantic, breadth, and atomic
  promotion decisions.
- This opening selects only exact required keyword-only parameters for
  already-resolved direct source functions. It is the smallest static
  continuation of the sealed Phase 14C binder and does not authorize any
  default, variadic, unpacking, runtime binding, or neighboring feature.
- The refreshed debt register retains 14 owned items: 9 High and 5 Extreme,
  with no unowned item, missing containment, or silent approximation. Only the
  exact required-keyword-only slice of `DEBT-EXPANDED-CALL-BINDING` is active.
- Phase 14A numeric behavior, Phase 14B conditional-region behavior, and Phase
  14C direct-keyword behavior remain sealed predecessor contracts. Their
  helpers, policies, facts, rules, evidence, historical configurations, and
  generated outputs are not reopened.

## Feasibility evidence

- Normalized Python IR 0.4 already retains ordered `posonlyargs`, `args`,
  `kwonlyargs`, `defaults`, `kw_defaults`, `vararg`, and `kwarg`. A null
  `kw_defaults` entry is exact evidence that its keyword-only formal is
  required.
- Existing symbol discovery already creates stable parameter bindings for
  keyword-only `arg` nodes. Existing signature analysis and lowering reject
  keyword-only declarations explicitly, providing a contained eligibility
  boundary rather than an accidental partial implementation.
- Existing C IR has function parameters, prototypes, definitions, typed
  automatic temporaries, pure identifier references, and calls. Required
  keyword-only formals can use the same C parameter representation in full
  formal order without a new C IR or renderer construct.
- Phase 14C already proves direct same-module and explicit cross-module source
  targets, stages explicit actuals once in Python source order, and supplies
  pure references in formal order. Phase 14D needs explicit preservation of the
  existing `keyword-only` kind, separate required-status evidence, and exact
  coverage obligations, not a runtime binder.
- C has no keyword-only call syntax, but this creates no admitted approximation:
  all converted SourceBundle calls are statically checked, the source mode stays
  in deterministic facts and traces, and foreign C calls are outside the
  source-semantics guarantee.
- One complete call-keyed `keyword-only-call-binding-facts` table is sufficient
  to publish ordered formal kinds, positive and negative call bindings, two
  exact order vectors, coverage, categories, diagnostics, and provenance. It
  contains no declaration record.
- Required-keyword-only declarations can remain in existing
  `function-signature-facts` without changing the serialized `ParameterFact`
  shape. Exact keyword-only parameter and C-interface mode-erasure evidence can
  be appended to affected existing `FunctionDef` RulePlans.
- One `phase14.keyword_only_call.exact_binding@0.14.3` RulePlan family can close
  target, declaration, binding, ordering, category, representation, provenance,
  resource, cancellation, and no-runtime obligations without a helper.
  Extending existing `FunctionDef` plans does not add a second new rule family.
- Independent reconstruction can validate declaration shape, parameter kinds,
  name binding, exact coverage, categories, source order, formal order,
  prototype/definition parameter order, and `CCallExpr` references without
  trusting lowering. It can also validate an admitted uncalled function through
  Python IR, existing signature facts, and its existing `FunctionDef` RulePlan.
- Declaration analysis, binding, validation, C-parameter assembly, staging, and
  formal-reference assembly are linear. The opening adds no new arbitrary count
  and relies on sealed aggregate resource ceilings.
- The cumulative central lowerer is 991 lines. The architecture budget forbids
  inline keyword-only classification or crossing the 1,000-line ceiling.
- Existing codes can preserve diagnostic specificity: `PYC2904` owns missing
  coverage and positional overflow, `PYC2905` representation mismatch,
  `PYC2910` unpacking, `PYC2911` excluded declaration shapes, and `PYC2912`
  exact name-binding failures. No new source diagnostic code is required.

## Resource, observer, and publication evidence

- The opening requires one-pass formal indexes and linear declaration, binding,
  reconstruction, planning, C-parameter, staging, and reference-vector work.
- Cancellation safe points are required at every newly touched boundary.
  Rejection, cancellation, resource exhaustion, or internal validation failure
  publishes no partial successor.
- Decision trace, telemetry, and progress remain bounded observers over
  immutable evidence. Their configuration, truncation, delay, absence, or
  failure cannot influence conversion facts, diagnostics, C IR, generated C,
  mappings, summaries, or fingerprints.
- Stale, rejected, canceled, failed, resource-limited, or
  observation-incomplete work cannot replace the last successful result or
  make stale C eligible for atomic Save C.

## Packet boundary

- `specifications/phase14d_required_keyword_only_calls.md` fixes the exact
  source, declaration, fact, plan, lowering, diagnostic, resource,
  compatibility, rollback, and non-goal boundary.
- The feasibility decision, entry criteria, budgets, rollback conditions,
  baseline fingerprint, debt register, and entry report are opening artifacts
  only.
- This packet changes no converter runtime, test, validator, helper,
  GUI/workspace, existing Phase 14A/14B/14C file, README, changelog,
  `CURRENT_STATE.md`, release manifest, gate evidence, release report, or release
  fingerprint.
- Windows 11 execution remains future external feedback. No compiler, linker,
  loader, native runtime, generated-C execution, or new actual widget execution
  is claimed.

The opening authorizes bounded Phase 14D implementation targeting 0.14.3. It
does not establish vertical correctness, hardening, packaging, reproducibility,
promotion, another Phase 14 feature, or Phase 15.
