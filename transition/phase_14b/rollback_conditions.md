# Phase 14B Rollback Conditions

Before promotion, abandon the Phase 14B candidate and restore the authenticated
PyCForge 0.14.0 release if any condition below occurs.

## Candidate-abandon triggers

- The sealed 0.14.0 source archive, canonical release tree, converter subtree,
  wheel, roadmap, addendum, helper registry, or promoted release evidence
  cannot be reproduced at its recorded identity.
- A prerequisite statement, source call, call-argument temporary, helper call,
  arithmetic prerequisite, or nested region is evaluated outside the exact
  guard assigned by its immutable region fact.
- A reached operand is duplicated or reordered, a skipped operand is evaluated,
  a chained middle operand is evaluated more than once, or an operand needed by
  two adjacent comparisons is not reused from one materialization.
- `And` opens a later operand when the accumulator is false, `Or` opens it when
  the accumulator is true, or a chained later operand is evaluated after a
  false preceding comparison.
- A Boolean result or rolling comparison temporary can be read before definite
  initialization, has a mismatched type, escapes its automatic lifetime, or is
  reused across unrelated source regions.
- A region requires operand-count-deep nested guards rather than flat sibling
  statements, or needs a newly invented operand ceiling without a separate
  resource decision.
- An expression primitive that is unsupported under the cumulative predecessor
  obtains a RulePlan or reaches C IR merely because it appears inside a region.
- Non-Boolean operand-returning `and`/`or`, mixed or unsupported comparison
  categories, dynamic calls, keywords, defaults, unpacking, recursion,
  mutation, exceptions, or another deferred family publishes C.
- The implementation introduces raw C text, a C conditional or statement
  expression outside structured C IR, `goto`, a new C IR node kind, a new
  helper or helper version, a runtime state flag, allocation, ownership
  transfer, cleanup, or a new failure channel.
- Region facts fail exact coverage, contain dangling or foreign ownership,
  disagree with Python IR or cumulative call/numeric/container/record facts, or
  cannot be independently reconstructed without consulting lowering output.
- A region RulePlan has an unresolved obligation, an inexact fact/explanation
  set, or a nonempty region-owned helper requirement.
- Lowering re-analyzes source eligibility, rendering infers guard semantics, or
  any final-text path bypasses structured C IR and validation.
- The cumulative lowering hotspot exceeds its 1,000-line architecture ceiling
  or the conditional analysis/lowering separation is crossed.
- A more specific target, arity, representation, recursion, numeric, container,
  record, or module rejection is masked by `PYC2950` or `PYC2951`.
- An explicit 0.14.0 request changes its canonical shape, generated-C bytes,
  output fingerprint, payload, summary, or trace behavior; or a source with no
  selected 14B region changes generated-C bytes under the new active rules.
- Phase 14A helper code, helper fingerprints, registry membership or
  fingerprint, numeric semantics, or generated helper output changes.
- Rejection, cancellation, internal failure, resource exhaustion, or observer
  failure publishes a partial or current successor artifact, or permits stale
  C to be saved as fresh.
- Determinism, provenance, source/output mappings, cancellation responsiveness,
  observer isolation, SourceBundle closure, module behavior, record/container
  ownership, workspace safety, package installation, or any earlier test/audit
  regresses.
- A test, audit, validator, evidence collector, review, or packaging gate
  compiles, links, loads, or executes generated C.
- Promotion is attempted without a later manifest, complete vertical evidence,
  adversarial fact/C IR validation, deterministic artifacts, an owned debt
  register, or an authenticated predecessor.

## Rollback baseline

Rollback source archive: `pycforge_phase_14_v0_14_0.tar.gz`  
Archive size: 1,016,512 bytes  
Archive SHA-256:
`d4fe065d168241b4371901e19eda346c38835c1d2ac07e3870f27abb5a7b3917`  
Canonical tree SHA-256:
`6eb034b63d4f08b8ea6de08fd38e507d12d4fc2436f0d3a68443624fc4c05d76`  
Converter subtree SHA-256:
`ccb92a82741202569e4639342e6ae711c246e2122a689f7831715ee182596c2d`

Rollback preserves every Phase 14A release and custody record. It does not
rewrite `transition/phase_14`, erase failed-candidate evidence, or reclassify an
unmet 14B obligation as passing.

