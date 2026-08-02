# Phase 14D Entry Criteria

Status: satisfied for the Phase 14D feasibility and opening checkpoint on
2026-07-26. Implementation, vertical validation, packaging, promotion, and
release are not claimed by this packet.

## Predecessor authentication

- The sealed `pycforge_phase_14c_v0_14_2.tar.gz` archive is 1,181,034 bytes and
  has SHA-256
  `1eb9666866f38dc80993a6f39175a0d98fdc1634f3aa3ab1eeb3dded2992ffb8`.
- Independent safe archive inspection reproduced the promoted canonical
  release-tree SHA-256
  `be433ef7a46bbb208efe82087b9ef924fad48eba42e42330c7964894a269bcb4`
  recorded by `transition/phase_14c/release_fingerprint.json`.
- The archived `pycforge/converter` subtree independently hashes to
  `ba4457158430bce7fb5094f68e1b07718bd168ca96e22310193efe45bd0d882b`.
- The promoted wheel identity is
  `pycforge-0.14.2-py3-none-any.whl`, 309,077 bytes, with SHA-256
  `6e14d24742e4bfff4017320ebdb04b35117c18fa95d97499560875a764feb4b5`.
  Candidate promotion must revalidate the preserved wheel bytes together with
  the predecessor archive and current candidate artifacts.
- The promoted predecessor records 474 discovered tests: 464 passing, 10
  expected PyQt5-unavailable skips, and zero failures. Architecture, rules,
  helpers, containers, modules, records, numeric, conditional, keyword,
  determinism, packaging, installation, and cumulative transition evidence are
  sealed by Phase 14C.
- No compiler, linker, loader, or generated-C executor was invoked while
  authenticating or opening Phase 14D.

## Authority and bounded phase selection

- The exact user direction is: “Continue to Phase 14D”.
- Architecture Revision 3.1 and the Revision 3.2 addendum match SHA-256
  `d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3`
  and
  `93b228528a10895fdbdce7b6934d422e7eddd1a79b409bdbc15ea6677e5ab8c6`.
- The authoritative roadmap assigns no preselected feature to the letter
  “14D”. It requires every advanced feature to pass an independent feasibility
  classification, semantic specification, breadth budget, and atomic
  promotion.
- This opening resolves that ambiguity narrowly: Phase 14D evaluates exact
  required keyword-only parameters for already-resolved direct source-function
  calls. It does not authorize defaults, variadics, unpacking, another Phase 14
  family, or Phase 15.
- Phase 14C is sealed and promoted. Its static direct-keyword binding,
  two-order staging, diagnostics, facts, RulePlans, generated C, and historical
  identities are predecessor evidence, not records to rewrite.
- The Phase 14D debt register retains an owner and containment boundary for all
  14 High or Extreme items. Only `DEBT-EXPANDED-CALL-BINDING` is active, and
  only its exact required-keyword-only slice.
- `required_keyword_only_calls_decision.md` and
  `breadth_and_change_budgets.md` close the semantic and change boundary before
  implementation is eligible.

## Architecture readiness

- Normalized Python IR 0.4 already preserves `posonlyargs`, `args`,
  `kwonlyargs`, `defaults`, `kw_defaults`, `vararg`, and `kwarg` in declared
  Python order. Required keyword-only status is therefore observable as a
  keyword-only formal whose corresponding `kw_defaults` entry is null; no new
  Python IR kind is necessary.
- Existing symbol discovery already assigns stable parameter bindings to
  keyword-only `arg` nodes. Existing signature analysis deliberately rejects
  `kwonlyargs`, so Phase 14D can open one explicit declaration profile instead
  of inventing a competing signature model.
- Existing Phase 14C target facts identify eligible same-module and explicit
  cross-module direct source functions without host discovery. Existing binding
  machinery already keeps source evaluation order distinct from C formal order.
- Existing C IR already represents function parameters, prototypes,
  definitions, typed automatic temporaries, pure identifier references, and
  positional C calls. C does not encode the keyword-only marker; the source
  obligation remains in normalized Python IR, existing function-signature
  facts, affected existing `FunctionDef` RulePlans, call facts, summaries,
  traces, diagnostics, and mappings.
- No new C IR node, renderer syntax, helper, runtime, allocation, ownership,
  cleanup, exception channel, representation, public policy, or toolchain
  surface is necessary.
- A new immutable `keyword-only-call-binding-facts` table must record formal
  kinds and distinguish source evaluation order from full formal order. Its
  domain is call-keyed only; required-keyword-only declarations remain in
  existing function-signature facts without changing the serialized
  `ParameterFact` shape. Affected existing `FunctionDef` RulePlans carry exact
  declaration and C-interface mode-erasure evidence, including for uncalled
  admitted functions. Reusing one ordered field for both meanings or asking
  lowering to infer parameter kinds is forbidden.
- The cumulative central lowerer is 991 lines against its 1,000-line
  architecture ceiling. Phase 14D may not implement declaration classification
  or binding inline there or cross the ceiling.

## Authorized opening

Implementation may begin only for an otherwise eligible synchronous top-level
source function whose declaration contains:

1. zero or more exactly annotated required positional-only parameters;
2. zero or more exactly annotated required positional-or-keyword parameters;
3. one or more exactly annotated required keyword-only parameters;
4. no positional or keyword-only defaults; and
5. no `*args` or `**kwargs`.

An eligible call target must already resolve directly to that function in the
same closed SourceBundle. Ordinary positional actuals bind only
positional-capable formals. Explicit named actuals may bind unbound
positional-or-keyword or required keyword-only formals. Positional-only formals
remain keyword-ineligible, keyword-only formals remain positional-ineligible,
and every required formal must be bound exactly once with an exact category and
representation match.

Explicit actuals stage once in Python source order. Only pure staged references
enter the existing `CCallExpr` in full formal order. The required lowering shape
is
`source-order-actual-temporaries-formal-order-references-v1`.

Defaults, defaulted keyword-only parameters, variadics, starred or double-star
unpacking, runtime binding, `range`, record constructors, methods, unknown or
indirect targets, recursion, and every neighboring call or Phase 14 profile
remain rejected before C IR publication.

Windows 11 testing remains future user feedback and is not claimed by this
opening. Workspace stale-output protection, generated-C immutability, atomic
save, closed SourceBundle resolution, cancellation, observer isolation, exact
historical configuration behavior, and the no-toolchain boundary remain
mandatory.
