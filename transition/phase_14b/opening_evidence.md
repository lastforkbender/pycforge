# Phase 14B Opening Evidence

Status: predecessor authentication, feasibility, and entry checkpoint passed.
Implementation and release gates remain open. No manifest, promotion gate, or
release claim is present.

## Authenticated predecessor

- Both available copies of the sealed 1,016,512-byte PyCForge 0.14.0 source
  archive matched SHA-256
  `d4fe065d168241b4371901e19eda346c38835c1d2ac07e3870f27abb5a7b3917`.
- Safe archive inspection independently reproduced canonical release-tree
  SHA-256
  `6eb034b63d4f08b8ea6de08fd38e507d12d4fc2436f0d3a68443624fc4c05d76`
  and converter-subtree SHA-256
  `ccb92a82741202569e4639342e6ae711c246e2122a689f7831715ee182596c2d`.
- Those values match the promoted `transition/phase_14/release_fingerprint.json`.
  The sealed wheel identity and 365-test result also match the Phase 14A
  release evidence.
- Revision 3.1 and the Revision 3.2 addendum match their recorded hashes. No C
  compiler, linker, loader, or generated-code executor participated.

## Authorization and debt

- The user explicitly approved continuing strongly through the deliberately
  bounded Phase 14 mini-phases and reaffirmed that the previously excluded
  dangerous families need not be converted.
- The copied and refreshed debt register retains 14 owned items: 9 High and 5
  Extreme, with no silent approximation. Only
  `DEBT-SHORT-CIRCUIT-CALL-TEMP` is active inside 14B; exception, cleanup,
  suspension, closure, dynamic callable, general object-model, and all other
  neighboring debts remain contained or deferred.
- Phase 14A is treated as sealed predecessor behavior. Its two numeric helpers,
  policies, facts, rules, evidence, and historical files are not reopened.

## Feasibility evidence

- Existing scalar lowering already produces an ordered prerequisite statement
  tuple and one typed result expression. Moving that tuple as a unit into the
  operand's guard solves the placement problem without changing primitive
  expression meaning.
- Existing structured C IR has all required declaration, assignment, Boolean
  expression, `if`, and block nodes. No new C IR kind, helper, runtime,
  allocation, cleanup, ownership transfer, exception channel, or final-text
  escape is required.
- A Boolean accumulator with flat true/false-polarity sibling guards preserves
  `and`/`or` reachability. A Boolean result plus initialized rolling middle
  value and flat `if (result)` sibling guards preserves chained-comparison
  source order and once-only middle reuse.
- The accepted closure is broader than a direct whole-call operand only in
  composition: every primitive must already be accepted by 0.14.0. Complete
  prerequisite closures and exact references to call, numeric, container,
  record, module, and ownership facts prevent placement from becoming a source
  feature back door.
- One complete conditional-region fact family and at most two exact RulePlan
  families are sufficient. Independent reconstruction can verify guard
  polarity, operand order, prerequisite containment, ownership, definite
  initialization strategy, and C IR placement.
- Flat region statements make work and output growth linear and do not create
  operand-count-deep C nesting. Existing aggregate source/AST limits are the
  evidence-based resource boundary; the opening invents no 64-operand limit.
- The cumulative lowerer is already 999 lines. The architecture budget therefore
  requires an isolated conditional-evaluation component and extraction of the
  legacy Boolean/comparison path rather than inline expansion.

## Packet boundary

- `specifications/phase14b_conditional_temporary_regions.md` fixes the exact
  source, fact, plan, lowering, resource, diagnostic, compatibility, and
  non-goal boundary.
- The feasibility decision, entry criteria, budgets, rollback conditions,
  baseline fingerprint, debt register, and entry report are opening artifacts
  only.
- This packet itself changes no converter code, test, helper, GUI/workspace
  file, Phase 14A transition file, manifest, gate evidence, release report, or
  release fingerprint.
- Windows 11 execution remains future user feedback. No widget, compiler,
  linker, loader, native execution, or generated-C execution claim is made.

The opening authorizes bounded Phase 14B implementation. It does not establish
vertical correctness, hardening, packaging, release reproducibility, promotion,
authorization for 14C, or the start of Phase 15.

