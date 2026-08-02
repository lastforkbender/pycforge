# Support-Template Infrastructure — Phase 10

## Contract

The support-template system is a frozen registry of trusted project assets. It
is not a Python runtime and is not a user extension mechanism. A RulePlan may
request only an exact reference of the form `helper-id@major.minor.patch`.
Ranges, implicit latest versions, source-controlled paths, arbitrary includes,
and raw C text are rejected.

The registry identity is `phase10-support-templates-v0.10`; every helper uses
interface `pycforge-helper/1`. Definitions record target compatibility,
dependencies, prospective consumer, earliest eligibility phase, semantic
obligations, ownership/lifetime, failure behavior, cancellation policy, and a
structured C IR factory.

## Resolution and assembly

Resolution performs these deterministic steps:

1. parse, exact-version, sort, and deduplicate RulePlan requirements;
2. compute the complete registered dependency closure;
3. validate interface and Target C Source Contract compatibility;
4. diagnose missing dependencies or cycles without a partial plan;
5. topologically order dependencies before consumers with canonical identity as
   the tie-break key;
6. instantiate each prevalidated asset once and publish a manifest fingerprint.

An empty requirement set produces an empty manifest and leaves the source C IR
unchanged. A nonempty plan assembles `c-ir/0.10` for historical source IR or
retains the source unit's `c-ir/0.14.3` schema for an active Phase 14D bundle
(`c-ir/0.14.2` for historical Phase 14C, `c-ir/0.14.1` for Phase 14B,
`c-ir/0.14` for Phase 14A, `c-ir/0.13` for Phase 13, `c-ir/0.12` for Phase 12,
and `c-ir/0.11` for Phase 11): registered includes are
deduplicated, all helper and source prototypes precede definitions, helper
definitions use reserved `pycf_` names and internal `static` linkage, and the
complete translation unit is validated before rendering. Factories return C IR
nodes only. They cannot return or append final C source text.

The conversion artifact and summary expose helper policy, registry fingerprint,
exact requirements, included-helper manifest, and manifest fingerprint. Full
decision traces record the same resolution result. Observer failure cannot alter
any of these semantic fields.

## Accepted assets

| Exact reference | Prospective consumer | Ownership | Failure policy | Dependencies |
|---|---|---|---|---|
| `pycf.i64.floor_div@1.0.0` | Phase 14A bounded integer `//` RulePlan | scalar by value; no allocation or cleanup | caller-proved nonzero divisor and `INT64_MIN / -1` exclusion | none |
| `pycf.i64.floor_mod@1.0.0` | Phase 14A bounded integer `%` RulePlan | scalar by value; no allocation or cleanup | caller-proved nonzero divisor and `INT64_MIN / -1` exclusion | none |

Phase 14A RulePlans activate exactly one of these assets per accepted numeric
occurrence. The helper manifest remains the deterministic deduplicated union, so
each selected helper is emitted once. All other current RulePlans, including
Phase 11 container, Phase 12 module, Phase 13 record, and Phase 14B conditional-
region rules, the Phase 14C keyword-call rule, and the Phase 14D
required-keyword-only call rule and affected FunctionDef plans remain
helper-free. A conditional region or keyword actual may contain a numeric
operation, but the nested numeric RulePlan alone owns its helper requirement.
Phase 14D preserves the exact Phase 10 asset and registry fingerprints;
explicit Phase 14A and Phase 13 conversions preserve historical C IR and
generated-C bytes.

## Stable diagnostics

- `PYC3301`: malformed or non-exact helper reference
- `PYC3302`: missing helper or dependency
- `PYC3303`: dependency cycle
- `PYC3304`: target-contract incompatibility
- `PYC3305`: helper-interface or registry-policy mismatch
- `PYC3306`: invalid contract, C IR factory, asset, or assembly
- `PYC3307`: duplicate helper identity

Cancellation uses the existing conversion cancellation result and publishes no
partial helper plan. Registry or asset corruption is an internal conversion
failure with no generated C.

## Product boundary

Helpers are rendered source assets only. PyCForge does not compile, link, load,
execute, benchmark, or behaviorally test them. User-supplied templates and
broad runtime libraries remain outside the product boundary. Phase 14A proves
its static failure preconditions before requesting a helper; Phase 14B may only
place that already-proved operation inside a guard, and Phase 14C may only stage
it at an already-proved argument source position. Phase 14D may bind that
already-proved staged scalar to a required keyword-only formal but cannot adopt
or change helper ownership. Phase 11 bounded containers,
Phase 12 module bindings, Phase 13 static records, Phase 14B regions, and Phase
14C keyword binding plus Phase 14D required-keyword-only binding remain direct
structured C IR/planning forms and do not own helpers.
