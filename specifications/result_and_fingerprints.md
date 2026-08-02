# Results, Observers, and Fingerprint Domains — v0.14.3

ResultStatus remains `Converted`, `ConvertedWithWarnings`,
`ConvertedWithApproximations`, `Rejected`, `InternalFailure`, or `Canceled`.
A non-publishable result exposes no partial generated-C text, C IR, module
mapping set, or helper output.

Fingerprint domains remain `source-bundle`, `target-contract`,
`semantic-configuration`, `resource-policy`, `rule-set`,
`renderer-configuration`, `helper-manifest`, `helper-registry-manifest`,
`helper-c-ir-asset`, `stage-artifact`, `decision-trace`, and
`generated-output`. Every fingerprint carries domain, schema,
canonicalization version, and algorithm. SHA-256 remains the selected
algorithm.

`source-bundle/0.2` canonicalization includes primary/companion position, exact
logical module/source identities, decoding decisions, and content fingerprints.
The active semantic configuration includes rule set
`phase14-required-keyword-only-calls-v0.14.3`, renderer
`c-renderer-v0.14.3`, the
Phase 13 module and record policies, and the unchanged
`phase14-proved-floor-arithmetic-v0.14` numeric policy. Phase 14D adds no
keyword-only policy field; Phase 14C adds no keyword-binding policy field; Phase
14B adds no conditional-policy field.
Absolute/display paths,
filesystem identity, import search state, environment, network, installed
packages, timings, timestamps, process IDs, locale, telemetry, and observer
state are excluded from semantic and output domains.

The immutable `pycforge.decision-trace/0.14.3` contains all current configuration
identities; input/resource/output fingerprints; stage summaries; selected
RulePlans; diagnostic projections; mappings at `Full`; final artifact metadata;
helper/module manifests; module dependencies and initialization order; record
policy/counts; numeric policy/counts and RulePlans; conditional-region facts,
counts, kinds, plans, and lowering shape; keyword-call fact/plan counts, target,
source/formal ordering, and lowering shape; completeness; compatibility events;
and its self-excluding record fingerprint.
It additionally records required-keyword-only signature eligibility and
FunctionDef obligations, call-fact/plan counts, parameter kinds, exact required
coverage, source/formal orders,
`source-order-actual-temporaries-formal-order-references-v1`, and C-interface
mode-erasure containment. Uncalled admitted declarations remain visible through
their existing FunctionDef RulePlans and signature evidence.
Trace budgets and observer failures remain observation-only under `PYC8001` and
`PYC8002` and cannot affect conversion artifacts.

The active artifact is `generated-c/0.14.3` and declares `c-ir/0.14.3`. It
contains exactly one translation unit for every publishable bundle. The
`pycforge.conversion-summary/0.14.3` projection retains source-free module,
function, container, helper, linkage, dependency, initialization, and mapping
state, record/field/initializer/instance/binding/access counts, and record
policy, numeric fact/plan/helper state plus the numeric policy, and the exact
serialized conditional-region facts. Conditional RulePlans remain visible in
the summary's RulePlan projection and own no helpers.
The summary also retains the exact keyword-call binding facts and their helper-
free RulePlans. Semantic result serialization remains `0.5`.
It additionally retains required-keyword-only declaration/parameter counts,
call-keyed binding facts, supported/rejected call counts, parameter kinds,
source/formal order, lowering shape, and the helper-free 0.14.3 call RulePlan.

An imported alias summary references its target module/function/binding and
never duplicates a signature as a new callable. Source-symbol mappings retain
both importing and target document identity. Output mappings remain
provenance-derived and carry the exact correct source document.

Historical rule sets and inner artifact schemas remain read-compatible. The
Phase 14A artifact, C IR, summary, and trace identities remain exactly 0.14 and
do not acquire conditional-region content. The Phase 14B artifact, C IR,
summary, and trace identities remain exactly 0.14.1 and do not acquire keyword-
call content. The Phase 14C artifact, C IR, summary, and trace identities remain
exactly 0.14.2 and do not acquire required-keyword-only declaration facts, call
facts, or plans. A
Phase 12 singleton/no-import request must have the same generated-output bytes
and generated-output fingerprint as its Phase 11 equivalent. A class-free
Phase 13 request must likewise have the same generated-output bytes and
fingerprint as the matching explicit Phase 12 request, although its enclosing
plan, C IR, artifact, summary, and trace identities are versioned. Historical C
IR serialization and Phase 10 helper asset/registry fingerprints are unchanged.

The separate `pycforge.telemetry/0.9` and transient `ConversionProgress`
surfaces remain observer-only and cannot supply facts or alter diagnostics,
status, artifacts, mappings, traces, generated C, or fingerprints.

The decision trace records those policies and complete record, numeric,
conditional-region, keyword-call, required-keyword-only call, and affected
FunctionDef RulePlans.
Result serialization remains `0.5` because its stable outer envelope does not
change; the active nested artifact, summary, and trace carry their own 0.14.3
identities.

The semantic-configuration fingerprint includes
`phase14-proved-floor-arithmetic-v0.14` for every active numeric-capable Phase
14A, Phase 14B, Phase 14C, or Phase 14D request. The Phase 14B rule-set and renderer
identities select conditional-region semantics without a new policy field; the
Phase 14C identities additionally select exact keyword-call binding without a
new policy field; the Phase 14D identities additionally select exact required-
keyword-only declarations and calls without a new policy field. Explicit
historical Phase 13 requests omit the numeric policy
and retain exact
predecessor generated-C bytes and fingerprints. Numeric facts, divisor proof,
helper requirements, staging, and RulePlans are semantic; workspace state,
platform, C compiler availability, and planned Windows 11 feedback are not.
