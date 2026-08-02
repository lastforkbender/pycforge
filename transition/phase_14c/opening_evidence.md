# Phase 14C Opening Evidence

Status: predecessor authentication, feasibility, and entry checkpoint passed.
Implementation and release gates remain open. No manifest, promotion gate, or
release claim is present.

## Authenticated predecessor

- The sealed 1,088,259-byte PyCForge 0.14.1 source archive matched SHA-256
  `30737e3a49dc3ed163be071742736f8310c2636a1dc8ac9b9b297aa8c030d2a1`.
- Safe archive inspection independently reproduced canonical release-tree
  SHA-256
  `895329a2723301de66adcb118a32308648a7993068e3ef7b5c9764914b9e2f4f`
  and converter-subtree SHA-256
  `5d261abb5f7dbc480050472cac40a6b4a9539945a3d2e3211af552e094f9780d`.
- Those values match the promoted
  `transition/phase_14b/release_fingerprint.json`. The sealed wheel identity and
  413-test result also match the Phase 14B release evidence.
- Revision 3.1 and the Revision 3.2 addendum match their recorded hashes. No C
  compiler, linker, loader, or generated-code executor participated.

## Authorization and debt

- The user explicitly directed: “Continue to Phase 14C”.
- The refreshed debt register retains 14 owned items: 9 High and 5 Extreme,
  with no silent approximation. Only the exact direct-keyword slice of
  `DEBT-EXPANDED-CALL-BINDING` is active inside 14C. Defaults, keyword-only
  parameters, variadics, unpacking, runtime failures, and every neighboring
  debt remain contained or deferred.
- Phase 14A numeric behavior and Phase 14B conditional behavior are sealed
  predecessor contracts. Their helpers, policies, facts, rules, evidence, and
  historical files are not reopened.

## Feasibility evidence

- Existing signature facts already publish exact source formal names,
  ordinals, categories, C representations, ownership, and lifetime. Existing
  lexical and SourceBundle module facts already identify eligible same- and
  cross-module direct function targets.
- Normalized Python IR preserves ordinary positional order and explicit keyword
  entry order, including each keyword spelling and value node. The selected
  profile can therefore be bound without runtime lookup or approximation.
- Existing positional-call lowering already materializes each actual into a
  typed automatic temporary so C cannot choose the order of source evaluation.
  Phase 14C needs only to retain source-order staging while permuting pure
  temporary references into formal order for the existing `CCallExpr`.
- Existing C IR contains every required declaration, reference, and call node.
  No new C IR kind, helper, runtime, allocation, cleanup, ownership transfer,
  exception channel, renderer construct, or toolchain surface is required.
- One complete binding fact family is sufficient to publish both immutable
  orders and the actual-to-formal bijection. One RulePlan family can close the
  binding, ordering, category, ownership, provenance, resource, cancellation,
  and target obligations.
- Independent reconstruction can validate target eligibility, parameter kind,
  names, coverage, uniqueness, categories, source order, formal order, and C IR
  argument references without trusting lowering.
- Same-module and explicit cross-module calls share the sealed resolved target
  identity; Phase 14C performs no filesystem, environment, installed-package,
  or host import discovery.
- Binding, validation, and lowering are linear. The opening adds no arbitrary
  parameter/argument count and relies on sealed aggregate resource ceilings.
- The central lowerer is 957 lines. The architecture budget requires an
  isolated call-binding component rather than inline feature growth.

## Packet boundary

- `specifications/phase14c_direct_keyword_calls.md` fixes the exact source,
  fact, plan, lowering, resource, diagnostic, compatibility, and non-goal
  boundary.
- The feasibility decision, entry criteria, budgets, rollback conditions,
  baseline fingerprint, debt register, and entry report are opening artifacts
  only.
- This packet itself changes no converter code, tests, helpers, GUI/workspace
  files, sealed Phase 14A or 14B transition files, manifest, gate evidence,
  release report, or release fingerprint.
- Windows 11 execution remains future user feedback. No widget, compiler,
  linker, loader, native execution, or generated-C execution claim is made.

The opening authorizes bounded Phase 14C implementation. It does not establish
vertical correctness, hardening, packaging, release reproducibility,
promotion, authorization for Phase 14D, or the start of Phase 15.
