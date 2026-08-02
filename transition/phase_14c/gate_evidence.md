# Phase 14C Gate Evidence

Scope status: Phase 14C promoted and sealed for PyCForge 0.14.2.  
Evidence status: complete.

## Opening and predecessor authentication

- Phase 14C opened only after authenticating the promoted 0.14.1 predecessor.
  The 1,088,259-byte `pycforge_phase_14b_v0_14_1.tar.gz` archive matched
  SHA-256
  `30737e3a49dc3ed163be071742736f8310c2636a1dc8ac9b9b297aa8c030d2a1`.
  Safe archive inspection, with the exact Phase 14B release-fingerprint
  self-reference omitted, independently reproduced canonical release-tree
  SHA-256
  `895329a2723301de66adcb118a32308648a7993068e3ef7b5c9764914b9e2f4f`
  and converter-subtree SHA-256
  `5d261abb5f7dbc480050472cac40a6b4a9539945a3d2e3211af552e094f9780d`.
- The sealed predecessor wheel is the 278,494-byte
  `pycforge-0.14.1-py3-none-any.whl`, SHA-256
  `255cba6d45b6f7f2c8347f4764d37ad9858d9616f84cc93b65b07e205785a70d`.
- Architecture Revision 3.1, its Revision 3.2 addendum, the frozen policies,
  the Phase 10 helper registry, and the sealed Phase 14A and 14B transition
  evidence retained their authenticated identities. The helper-registry
  fingerprint remains
  `fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98`.
- The opening decision, specification, breadth budget, rollback conditions,
  and conversion-debt register admitted only exact static binding of explicit
  keywords for already-resolved direct source functions. Phase 14D, Phase 15,
  and neighboring dangerous families remained closed.

## Exact vertical-slice evidence

- Phase 14C adds one isolated `keyword-call-binding-facts` family under
  `fact-table/0.14.2` and exactly one rule:
  `phase14.keyword_call.exact_binding@0.14.2`.
- An eligible call targets an already-resolved same-module or explicit
  SourceBundle-imported top-level source function. Its declaration has only
  required, exactly annotated positional-only and positional-or-keyword
  parameters, with no defaults, keyword-only parameters, or variadics.
- Calls contain zero or more ordinary positional actuals and one or more
  explicit named keyword actuals. Binding proves that every formal is supplied
  exactly once, positional-only formals are supplied only positionally, and
  every actual has the exact established category and representation expected
  by its formal.
- Analysis records two immutable vectors. Actual values are evaluated and
  staged exactly once in Python source order. The existing structured
  `CCallExpr` then receives only pure temporary references in formal ordinal
  order. The exact lowering shape is
  `source-order-temporaries-formal-order-references-v1`.
- Source-order reconstruction is linear. It uses a two-pointer merge over the
  normalized positional and keyword lists by source offset, so even an
  excluded interleaving such as a keyword before a later starred argument has
  truthful negative evaluation evidence. Formal-name indexing, binding,
  independent reconstruction, permutation validation, RulePlan lookup, and
  lowering are also linear. Keyword RulePlans are indexed once by source node;
  duplicate plans reject.
- Final cumulative function eligibility is authoritative. If an otherwise
  exact binding targets a function later proved ineligible by sealed
  return-path, local-binding, nested-call, module, or call-graph rules, the
  candidate becomes complete negative `PYC2911` evidence with reason
  `Keyword-call target is outside the eligible direct source-function profile`,
  no Phase 14C RulePlan, and no C IR. The intrinsic owning diagnostic remains
  primary; keyword handling cannot mask a more specific root cause.
- Independent validation reconstructs candidate coverage, target identity,
  signatures, parameter kinds and names, actual categories, both order
  vectors, the bijection, provenance, cumulative eligibility, exact negative
  evidence, and supported-plan coverage. Null, wrong-type, duplicate, or
  malformed tables, dependencies, bindings, signatures, plans, facts, and
  permutations fail closed as a clean internal validation failure or bounded
  `PYC2912` rejection; they never escape as raw `TypeError`, `AttributeError`,
  or partial output.
- Cancellation checks cover candidate discovery, the linear source merge,
  binding, independent reconstruction, plan indexing, permutation validation,
  source-actual staging, and formal-vector assembly. Cancellation, rejection,
  resource exhaustion, observer failure, or internal validation failure
  publishes no partial generated-C successor.
- The central cumulative lowerer remains 991 lines, below its 1,000-line
  architecture ceiling. Phase 14C adds no helper, policy, C IR node kind,
  renderer syntax, runtime binder, runtime failure channel, allocation,
  ownership transfer, or cleanup model.

## Diagnostic and compatibility evidence

- The closed rejection matrix is exact: `PYC2910` owns `*`/`**` unpacking;
  `PYC2912` owns unknown names, positional-only names used by keyword,
  positional/keyword collisions, and duplicate keywords; `PYC2904` owns
  missing or excess arity; `PYC2905` owns actual/formal category mismatch; and
  `PYC2911` owns ineligible declarations and cumulative target eligibility.
  Existing `PYC2842`, `PYC3605`, `PYC2901`, and `PYC2920` remain primary for
  range keywords, record-constructor keywords, dynamic targets, and recursion.
- Same-module, positional-prefix, reordered heterogeneous, positional-only,
  nested-call, numeric-helper, container/record-read, Phase 14B guarded, and
  explicit cross-module SourceBundle witnesses passed. The keyword audit
  reconstructed two exact facts and RulePlans, both lowering permutations,
  the cross-module target and module order, 16 rejection cases, summaries,
  traces, mappings, observer evidence, and fresh-process determinism.
- The keyword-audit witness generated-C SHA-256 is
  `3d99653c0f0e1ee86a8508fdd618d19f9bb4f1de93012325f1bc3552f8a3e671`;
  its serialized-result SHA-256 is
  `c85327ffe11244ab5f8f8c8ce972102425f76b8fc930004d95ce6a14891a28aa`.
- The authenticated validator's nested reordered witness retains generated-C
  SHA-256
  `114938d6ce3737421059f65839d1985592fb7c12d692b6c1d17e305a2b089738`,
  request fingerprint
  `61bbf8ac300f9416edcdb5bed2d8fc365342a7cb89b1b95ac9d43a6e32efdf92`,
  output fingerprint
  `cef64ddeffdc0512c3af745e02a901187d85c44e02602e15fc862cf62165b9ea`,
  and artifact fingerprint
  `e4608658de0c206f9f6dad2386bc2634bff230d57c8dba508b24fed8a1577203`.
- Active sources selecting no keyword-call rule remain byte-compatible with
  explicit Phase 14B output. The positional compatibility generated-C
  SHA-256 is
  `36528709609e8b53a06fff4739dfa1ae5f1568d27daa0838a03315ecf701fb7e`
  and its output fingerprint is
  `a30db4341270842057a722c41d5a88e9599aff0a6992cf058aad642f7a724300`.
  Explicit 0.14.1 requests retain their exact `PYC2910` keyword rejection,
  request, plan, summary, trace, artifact, generated-C, and diagnostic
  envelopes.

## Promotion and packaging evidence

- The final suite discovered 474 tests: 464 passed, 10 had the expected
  PyQt5-unavailable skip, and none failed.
- Architecture, rules, helpers, containers, modules, records, numeric,
  conditional, keyword, determinism, and all applicable sealed Phase 14A,
  Phase 14B, and Phase 14C transition audits passed. The cumulative
  determinism SHA-256 is
  `337ec6f2fc04912c924981e66ff9ae6a25126b6868319d46916d681bec15c243`.
- The authenticated Phase 14C validator passed its active and historical
  contracts, accepted witnesses, exact rejection matrix, malformed-evidence
  hardening, tamper rejection, cancellation, determinism, predecessor archive
  and wheel authentication, release-tree, wheel, and source-archive checks.
- Two fixed-epoch wheel builds were byte-identical. The final wheel is
  `pycforge-0.14.2-py3-none-any.whl`, size 309,077 bytes, SHA-256
  `6e14d24742e4bfff4017320ebdb04b35117c18fa95d97499560875a764feb4b5`.
  Its 126 RECORD members include 17 SVG assets and no native binary.
- A clean isolated wheel installation passed installed same-module and
  explicit SourceBundle keyword conversion, the installed keyword audit, and
  workspace linked-C atomic save.
- Two normalized source-archive builds were byte-identical. The final archive
  is `pycforge_phase_14c_v0_14_2.tar.gz`; its size and SHA-256 are recorded
  externally to avoid embedding an archive identity inside itself.
- The canonical release-tree SHA-256 is recorded externally and authenticated
  by `transition/phase_14c/release_fingerprint.json`. That file alone carries
  the value and is excluded from its own hash domain.

## Toolchain and platform custody

Phase 14C validation uses Python IR, immutable facts and plans, structured C
IR, independent conformance checks, and deterministic rendering evidence. No C
compiler, linker, loader, foreign-function bridge, or execution path was
invoked. Generated C was never compiled, linked, loaded, or executed. PyCForge
exposes no compilation, linking, loading, execution, debugging, terminal,
package-discovery, or host import-resolution surface.

PyQt5 was unavailable in the release environment, so the 10 existing GUI tests
retain their expected skips and the sealed offscreen-widget evidence remains
in custody. Windows 11 laptop testing remains downstream user feedback; no
Windows 11 execution or validation claim is made for 0.14.2.

Phase 14C is the sealed mini-phase boundary. Phase 14D has not opened and must
not open automatically. Phase 15 has not started.
