# Configuration — v0.14.3

Default canonical identities:

- target contract: `c11-portable-fixed-v1`
- semantic policy: `strict-source-v1`
- rule set: `phase14-required-keyword-only-calls-v0.14.3`
- renderer: `c-renderer-v0.14.3`
- helper policy: `phase10-support-templates-v0.10`
- container policy: `phase11-fixed-local-containers-v0.11`
- module policy: `phase13-explicit-record-modules-v0.13`
- record policy: `phase13-immutable-automatic-records-v0.13`
- numeric policy: `phase14-proved-floor-arithmetic-v0.14`
- approximation allowlist: empty

Phase 14D introduces no request policy field. Exact required-keyword-only
declaration and direct-call eligibility are selected only by the active rule-set
and renderer identities; the target, semantic, helper, container, module,
record, and numeric policies remain frozen. Phase 14B conditional and Phase 14C
direct-keyword fact schemas are unchanged historical contracts.

The request accepts `source-bundle/0.2`, Python grammar `3.11`, these exact
registered identities, and a validated `ResourcePolicy`. Each document carries
an explicit canonical logical module ID, canonical logical source name, and
decoded Unicode source encodable as UTF-8. User-supplied resolvers, registries,
templates, record layouts, module, numeric, conditional, invented keyword-
binding or keyword-only policies, import roots, search paths, and package
indexes are forbidden.

Canonicalization rejects malformed nested objects; malformed, duplicate, or
ambiguous logical identities; absolute or parent-traversing logical source
names; invalid Unicode; more than 64 documents; more than 4,096 normalized
import items; duplicate approximation codes; unknown identities; and invalid
resource limits. It preserves primary/companion order, normalizes only the
approximation allowlist, and fingerprints the active rule set, renderer,
module, record, and numeric policies. Direct-keyword and required-keyword-only
selection are parts of versioned rule-set identities, not separately
configurable fields.
Existing source byte/line/token/AST limits are bundle-aggregate and nesting is
per document.

Historical identities remain read-compatible for regression validation. An
explicit Phase 14C rule set `phase14-direct-keyword-calls-v0.14.2` and renderer
`c-renderer-v0.14.2` select exact `conversion-plan/0.14.2`, `c-ir/0.14.2`, and
`generated-c/0.14.2` identities, publish no required-keyword-only facts or
plans, and retain the historical `PYC2911` keyword-only declaration rejection.
An explicit Phase 14B rule set `phase14-conditional-regions-v0.14.1` and renderer
`c-renderer-v0.14.1` select exact `conversion-plan/0.14.1`, `c-ir/0.14.1`, and
`generated-c/0.14.1` identities, publish no keyword-call facts or plans, and
retain the historical `PYC2910` keyword rejection. An
explicit Phase 14A rule set `phase14-bounded-numeric-v0.14` and renderer
`c-renderer-v0.14` select exact `conversion-plan/0.14`, `c-ir/0.14`, and
`generated-c/0.14` identities and publish no conditional-region facts or plans.
An explicit Phase 13 rule set and renderer selects exact `conversion-plan/0.13`,
`c-ir/0.13`, and `generated-c/0.13` identities and omits the numeric policy
from its semantic payload and fingerprint. Phase 12 historical selection
remains unchanged. New requests default to Phase 14D. Unknown values never fall
back. `PYC1015` owns an unknown container policy; `PYC1017` owns an unknown
record policy; `PYC1018` owns an unknown numeric policy; an unknown module
policy is a stable configuration rejection and cannot select an earlier
profile.
