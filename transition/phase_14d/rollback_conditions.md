# Phase 14D Rollback Conditions

Before promotion, abandon the Phase 14D candidate and restore the authenticated
PyCForge 0.14.2 release if any condition below occurs.

## Candidate-abandon triggers

- The sealed 0.14.2 source archive, canonical release tree, converter subtree,
  wheel identity, roadmap, addendum, helper registry, or promoted release
  evidence cannot be reproduced at its recorded identity.
- A declaration with a positional default, non-null keyword-only default,
  `*args`, `**kwargs`, missing exact annotation, duplicate formal name, or an
  otherwise excluded signature publishes C through the Phase 14D profile.
- A keyword-only formal is bound positionally, a positional-only formal is
  bound by keyword, a required formal is unbound, a formal is bound twice, an
  unknown keyword is accepted, or actual/formal category compatibility is
  inferred rather than proved.
- An omitted required keyword-only formal is supplied with a synthesized value,
  zero initializer, null sentinel, retained prior value, or default expression.
- Any default expression is evaluated, stored, moved to call time, copied into a
  call, or otherwise admitted without a separately approved default-semantics
  phase.
- A call using `*` or `**` unpacking, a null keyword name, runtime lookup,
  `range` keywords, record-constructor keywords, a method, callable value,
  assignment-created target alias, indirect or dynamic target, or recursion
  publishes C.
- Python runtime argument binding, `TypeError` behavior, an exception channel,
  runtime parameter table, source-name hashing/comparison at runtime, overload
  resolution, coercion, or dynamic dispatch is introduced.
- A required keyword-only formal is missing from the C prototype or definition,
  is duplicated, has a different representation, or appears outside full Python
  formal order.
- An explicit actual, nested call, helper-backed operation, or complete
  prerequisite sequence evaluates in formal order rather than Python source
  order; evaluates more than once; is hoisted before its source position; or is
  omitted.
- The emitted C call receives temporary references in any order other than full
  formal ordinal order, or a reference does not identify the one actual
  statically bound to that formal.
- A final `CCallExpr` argument contains an unstaged source expression, source
  call, helper call, or other effect whose evaluation order C may choose.
- A Phase 14A numeric prerequisite or Phase 14B conditional-region prerequisite
  is moved outside its sealed fact-owned placement, or Phase 14D changes either
  predecessor semantic contract.
- `keyword-only-call-binding-facts` omit an eligible resolved direct-call
  candidate, contain a declaration record, contain dangling or foreign
  ownership, disagree with Python IR or
  predecessor lexical/module/signature/category/call-graph/conditional facts,
  or cannot be reconstructed independently without lowering output.
- A call fact fails to record exact formal kinds, source and formal orders,
  complete actual/formal bijection, support or rejection state, diagnostic
  ownership, or provenance.
- Existing `function-signature-facts` change the serialized `ParameterFact`
  shape, or required status is encoded as a new parameter kind instead of
  reconstructed from the corresponding null `kw_defaults` entry.
- An admitted required-keyword-only declaration lacks exact keyword-only
  parameter and C-interface mode-erasure evidence on its existing
  `FunctionDef` RulePlan, including when the function is uncalled.
- A supported Phase 14D call RulePlan lacks exactly one supported call fact, has an
  unresolved semantic, target, representation, ownership, lifetime, ordering,
  failure, resource, cancellation, or provenance obligation, or owns a helper.
- Lowering resolves source names, classifies formal kinds, repairs unsupported
  coverage, or chooses support; rendering infers call semantics; or final text
  bypasses structured C IR and validation.
- `PYC2910` ceases to own unpacking and excluded call shapes; `PYC2912` is used
  outside exact static name-binding failures; or `PYC2911` ceases to reject
  defaults, defaulted keyword-only parameters, variadics, and keyword-only
  declarations outside the exact admitted profile.
- `PYC2904` no longer owns missing required coverage or positional overflow into
  keyword-only formals, `PYC2905` no longer owns exact representation mismatch,
  or a generic 14D diagnostic masks a more specific predecessor rejection.
- A historical 0.14.2 or earlier diagnostic record is rewritten to reflect the
  active narrowed 0.14.3 `PYC2911` boundary.
- The implementation introduces raw C text, a new Python or C IR node kind,
  renderer syntax, helper or helper version, representation, value category,
  runtime state, allocation, ownership transfer, cleanup, or failure channel.
- The cumulative lowerer exceeds its 1,000-line architecture ceiling, or
  signature analysis, fact construction, independent validation, lowering, and
  rendering responsibilities are not separated.
- Declaration analysis, binding, reconstruction, C-parameter assembly, staging,
  or formal-vector assembly becomes superlinear through repeated signature
  scans, module rescans per call, or permutation enumeration.
- An explicit 0.14.2 or earlier request changes its canonical shape, facts,
  plans, generated-C bytes, output fingerprint, payload, summary, trace,
  diagnostics, or historical keyword-only rejection.
- Under active 0.14.3 identities, a source selecting no Phase 14D declaration or
  call behavior changes predecessor generated-C bytes or output fingerprint.
- Phase 14A helper sources, interfaces, versions, registry membership,
  fingerprints, numeric semantics, or generated helper output change.
- Phase 14B conditional facts, guard placement, lowering shapes, predecessor
  generated C, or sealed transition evidence change.
- Phase 14C keyword-call facts, two-order binding, RulePlan, lowering shape,
  diagnostic precedence, predecessor generated C, or sealed transition/release
  evidence change.
- Rejection, cancellation, internal failure, resource exhaustion, observer
  failure, stale result handling, or interrupted replacement publishes a
  partial/current successor artifact, overwrites the last successful result, or
  permits stale C to be saved as fresh.
- Observer configuration, truncation, delay, absence, or failure changes
  signature eligibility, binding, formal order, diagnostics, C IR, mappings,
  summaries, traces, generated bytes, or semantic/output fingerprints.
- Determinism, provenance, source/output mappings, cancellation responsiveness,
  SourceBundle closure, module behavior, record/container ownership, workspace
  safety, atomic save, package installation, or an earlier test/audit regresses.
- A test, audit, validator, evidence collector, review, or packaging gate
  compiles, links, loads, or executes generated C.
- Promotion is attempted without a later manifest, complete vertical and
  adversarial evidence, deterministic fresh-process artifacts, resource and
  observer reports, failure injection, an owned debt register, reproducible
  packaging, and authenticated predecessor archive/wheel custody.
- Work crosses into defaults, variadics, unpacking, another Phase 14 mini-phase,
  Phase 15, or any other excluded family without a separate approved opening.

## Rollback baseline

- Rollback release: PyCForge `0.14.2` / Phase 14C
- Source archive: `pycforge_phase_14c_v0_14_2.tar.gz`
- Archive size: 1,181,034 bytes
- Archive SHA-256:
  `1eb9666866f38dc80993a6f39175a0d98fdc1634f3aa3ab1eeb3dded2992ffb8`
- Canonical tree SHA-256:
  `be433ef7a46bbb208efe82087b9ef924fad48eba42e42330c7964894a269bcb4`
- Converter subtree SHA-256:
  `ba4457158430bce7fb5094f68e1b07718bd168ca96e22310193efe45bd0d882b`
- Rollback wheel: `pycforge-0.14.2-py3-none-any.whl`
- Wheel size: 309,077 bytes
- Wheel SHA-256:
  `6e14d24742e4bfff4017320ebdb04b35117c18fa95d97499560875a764feb4b5`

Rollback preserves every Phase 14A, Phase 14B, and Phase 14C release and custody
record. It does not rewrite `transition/phase_14`, `transition/phase_14b`, or
`transition/phase_14c`, erase failed-candidate evidence, or reclassify an unmet
Phase 14D obligation as passing.
