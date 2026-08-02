# Phase 14C Entry Criteria

Status: satisfied for the Phase 14C feasibility and opening checkpoint on
2026-07-22. Implementation, vertical validation, promotion, and release are not
claimed by this packet.

## Predecessor authentication

- The sealed `pycforge_phase_14b_v0_14_1.tar.gz` archive is 1,088,259 bytes and
  has SHA-256
  `30737e3a49dc3ed163be071742736f8310c2636a1dc8ac9b9b297aa8c030d2a1`.
- Independent safe archive inspection reproduced the promoted canonical
  release-tree SHA-256
  `895329a2723301de66adcb118a32308648a7993068e3ef7b5c9764914b9e2f4f`
  recorded by `transition/phase_14b/release_fingerprint.json`.
- The archived `pycforge/converter` subtree independently hashes to
  `5d261abb5f7dbc480050472cac40a6b4a9539945a3d2e3211af552e094f9780d`.
- The sealed wheel is `pycforge-0.14.1-py3-none-any.whl`, 278,494 bytes, with
  SHA-256
  `255cba6d45b6f7f2c8347f4764d37ad9858d9616f84cc93b65b07e205785a70d`.
- The promoted predecessor records 413 discovered tests: 403 passing, 10
  expected PyQt5-unavailable skips, and zero failures. Architecture, rules,
  helpers, containers, modules, records, numeric, conditional, determinism,
  and cumulative transition audits passed.
- No compiler, linker, loader, or generated-C executor was invoked while
  authenticating or opening Phase 14C.

## Authority

- The exact user direction is: “Continue to Phase 14C”.
- Architecture Revision 3.1 and the Revision 3.2 addendum match SHA-256
  `d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3`
  and
  `93b228528a10895fdbdce7b6934d422e7eddd1a79b409bdbc15ea6677e5ab8c6`.
- Phase 14B is sealed and promoted. Phase 14C is one separate bounded
  evaluation; it does not reopen conditional-region mechanics, authorize
  another Phase 14 family, begin Phase 14D, or begin Phase 15.
- The Phase 14C debt register retains an owner and containment boundary for all
  14 High or Extreme items. Only `DEBT-EXPANDED-CALL-BINDING` becomes active,
  and only its exact direct-keyword slice.
- `direct_keyword_calls_decision.md` and
  `breadth_and_change_budgets.md` close the semantic and change boundary before
  implementation is eligible.

## Architecture readiness

- Existing signature facts already record every formal parameter's source
  name, ordinal, category, representation, ownership, and lifetime.
- Existing lexical and module facts already resolve same-module and explicit
  cross-module source-function targets without host discovery. Existing call
  lowering already stages positional actual values once before constructing a
  `CCallExpr`.
- Exact direct keyword calls therefore require a static binding permutation,
  not a Python runtime binder: values are staged in source evaluation order,
  and the resulting pure temporary references are supplied in formal order.
- Existing C IR already represents every required temporary declaration,
  identifier reference, and positional C call. No new C IR node, renderer
  syntax, helper, runtime, allocation, ownership, cleanup, exception channel,
  or toolchain surface is necessary.
- A new immutable fact must keep source evaluation order distinct from formal
  call order. Reusing one ordered field for both meanings or asking lowering to
  infer the permutation is forbidden.
- The cumulative central lowerer is 957 lines against its 1,000-line ceiling.
  Keyword binding analysis, validation, and ordering belong behind an isolated
  component boundary; inline growth beyond the ceiling is not authorized.

## Authorized opening

Implementation may begin only for a direct `Call` whose target already resolves
to an eligible top-level source function in the same SourceBundle, including an
existing explicit cross-module direct import resolution. The call may contain:

1. zero or more leading ordinary positional actual values; and
2. one or more explicit named keyword actual values.

Every existing required formal must be bound exactly once. Positional-only
formals may be bound only by the leading positional prefix. Named actuals may
bind only existing positional-or-keyword formals. Every actual category must
exactly match its bound formal under the sealed representation policy.

Defaults, keyword-only declarations, variadics, starred positional unpacking,
double-star keyword unpacking, unknown or indirect targets, call-target values,
`range`, record constructors, recursion, and every other call profile remain
rejected. Phase 14C adds no dynamic `TypeError` model; statically invalid
bindings reject before C IR publication.

Windows 11 testing remains future user feedback and is not claimed by this
opening. Workspace stale-output protection, generated-C immutability, atomic
save, closed SourceBundle resolution, cancellation, observer isolation, exact
historical configuration behavior, and the no-toolchain boundary remain
mandatory.
