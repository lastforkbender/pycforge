# Analysis and Conversion Planning — `conversion-plan/0.14.3`

`analysis.plan` consumes validated bundle-aware `python-ir/0.4` and publishes
one recursively immutable conversion plan. Rejection, cancellation, or internal
validation failure publishes no successor.

The cumulative plan retains lexical scopes/bindings, value categories,
evaluation/effect/truthiness facts, representation/ownership/lifetime requests,
collision-free names, support decisions, frozen rules, closed RulePlans,
function/call/return/local/call-graph facts, Phase 11 container facts, and exact
helper requirements.

Phase 12 adds complete module-source, directly-defined importable-function,
import-item, module-namespace, dependency-edge, SCC, initialization-order, and
module-name/linkage tables. Facts distinguish an owned function binding from an
imported-function alias and store importer/target module and document IDs,
source ordinal, remote/local spelling, exact target binding/signature, resolution
state, diagnostic cause, and provenance. The bundle-wide function call graph
contains same- and cross-module edges and retains the existing recursion policy.

Resolution builds one immutable exact-ID map solely from SourceBundle members.
It performs no path construction, source acquisition, host import, package
fallback, environment lookup, network access, or installed-package inspection.
Dotted IDs are opaque exact identities. Imports do not create module values or
re-exported members.

The dependency graph uses deterministic bounded SCC analysis. Any self-edge or
nontrivial SCC rejects. An acyclic graph publishes dependency-first topological
module order; exact module ID UTF-8 order breaks ready-set ties. Function order
within a module is source order. All supplied documents participate, whether or
not reachable from the primary.

Source spelling is never binding identity. Node, scope, binding, decision,
representation, RulePlan, and generated-name identities include source-document
and module identity where needed. Process state, SourceBundle acquisition order,
hash iteration, timestamps, host paths, observers, telemetry, and registration
order cannot influence semantic decisions.

Every supported decision has one immutable RulePlan with closed obligations.
Phase 12 adds plans for module-document eligibility, absolute import statements,
imported-function bindings, cross-module calls, acyclic compile-time
initialization, and single-translation-unit assembly. Their helper requirement
sets are empty. The published helper requirement union remains exactly the union
owned by all plans.

Multi-document source functions receive centrally allocated `pycm_` qualified
external names under the module policy. Imported aliases reuse target binding
IDs and receive no C name. A singleton document with no import item selects the
legacy name plan. Existing `pycf_` helper reservations, C/target reservations,
normalization/linkage collision checks, and synthetic temporary allocation
remain enforced.

Module analysis is separate from C IR, rendering, the helper registry, and
client/observer state. Lowering consumes only validated published facts and
plans. No explanation, mapping, or renderer pass re-resolves an import.

Phase 13 adds complete static-record definition, field, structural-initializer,
instance, unique-binding, and direct-field-access facts under
`fact-table/0.13`. Record facts prove the exact declaring module/document,
class and field bindings, field order/category, initializer coverage,
construction arity and arguments, function-local owner, permitted occurrences,
and scalar result category of every field read.

Seven record rules plan the class declaration, each field, the structural
initializer, each direct construction, the fresh binding assignment, admitted
record-name occurrences, and each field read. They close exact layout and
initialization; left-to-right once-only construction; unique automatic
ownership; no alias, rebind, escape, mutation, allocation, null, or cleanup;
exact receiver/field identity; module locality; and exclusion of the general
object model. Their helper requirement sets are empty.

Record-class bindings are callable only at statically approved construction
sites. Record-instance bindings receive the distinct `static-record-like`
category, which has no generic scalar representation and therefore cannot flow
through the existing call, assignment, container, return, truthiness, or
comparison paths. A direct field access instead receives its proved scalar
category. Any incomplete or contradictory record evidence rejects before an
active plan is published.

Generated record type, field, and instance names use the same centralized,
collision-checked allocation as other semantic bindings. Multi-document record
names remain internal semantic identities of the defining module; module
analysis refuses imported-record namespace bindings. Lowering consumes the
complete validated record tables and does not rediscover class structure.

Phase 14A adds a separate bounded-numeric analysis pass and one complete
`numeric-operation-facts` publication under `fact-table/0.14`. For every
`FloorDiv` or `Mod` candidate it anchors exact document, module, logical source,
and enclosing-function ownership; operand and operator node identities;
integer categories and `int64_t` representations; direct signed-literal shape
and value; safe-divisor proofs; exact helper identity; left-before-right
evaluation; scalar ownership; and absence of allocation, cleanup, and runtime
failure.

The one `phase14.numeric.floor_arithmetic` RulePlan family closes signed-64
domain, direct-literal eligibility, zero/negative-one/`INT64_MIN` exclusion,
Python floor/modulo meaning, once-only evaluation, target, provenance, and exact
frozen helper selection. The conversion-plan helper requirement set is the
sorted union owned by those RulePlans. Numeric analysis is independent of C IR,
rendering, and helper implementation; lowering consumes only validated numeric
facts and never reconstructs or widens a divisor proof.

Phase 14B adds a separated conditional-placement analysis pass and one complete
`conditional-region-facts` publication under `fact-table/0.14.1`. It does not
add a scalar expression or representation. For an otherwise supported Boolean
`and`/`or` or chained comparison, the pass records the exact function/module/
document owner, ordered operands and operators, unconditional prefix, guard
polarity, per-operand prerequisite closure, once-only evaluation order,
Boolean result, `flat-guarded-assignment-v1` lowering shape, and unchanged
allocation, cleanup, failure, and target contracts.

The two active rule families are
`phase14.conditional.boolean_region` and
`phase14.conditional.comparison_region`, both version `0.14.1`. Each selected
region has exactly one helper-free RulePlan that closes the fourteen published
conditional-region obligations. Existing call and Phase 14A numeric plans keep
ownership of their own prerequisites and helpers; the plan-wide helper union is
unchanged by a region rule.

Prerequisite closures are accumulated through persistent ordered evidence and
materialized only where a fact publishes those references. Analysis and the
independent validator are therefore linear in normalized nodes, operand edges,
and emitted prerequisite references rather than rescanning each subtree.
Cooperative cancellation during construction or validation retires the entire
unpublished successor. Lowering consumes only the exact validated region facts
and cannot infer, widen, or repair conditional eligibility.

Phase 14C adds a separated exact keyword-call binding pass and one complete
`keyword-call-binding-facts` publication under `fact-table/0.14.2`. Its complete
candidate domain is keyword-bearing calls whose direct source-function target
and required declaration signature reach the static binder. For every candidate
it records the target, formal names/categories, leading positional actuals,
keyword spellings and values, source-order actual vector, formal-order parameter
vector, forward and inverse association, coverage, once-only evaluation,
support or exact rejection state, and
`source-order-temporaries-formal-order-references-v1` lowering shape.

Rejected candidates retain complete negative facts with `supported: false`, an
exact diagnostic, reason, and rejection node, but have no 14C RulePlan or C IR.
Every selected supported call has exactly one helper-free
`phase14.keyword_call.exact_binding@0.14.2` RulePlan. The plan closes direct
target resolution, explicit-keyword shape, exact parameter coverage and
categories, source-order staging, formal-order pure references, unchanged
ownership/lifetime, absence of runtime binding/allocation/cleanup, structured C
IR, provenance, cancellation, and target obligations. Nested operations retain
their existing facts, plans, prerequisites, and helper ownership.

Independent validation reconstructs the complete candidate set, every binding
and rejection field, and the exact supported-fact-to-RulePlan correspondence
from normalized Python IR plus sealed binding, signature, category, and
call-target facts. It rejects missing, extra, reordered, renamed, colliding,
wrong-category, malformed-provenance, or mismatched RulePlan evidence before
lowering. Binding, reconstruction, and plan publication are linear and
cancellation-safe; lowering never resolves a keyword name or repairs coverage.

Phase 14D extends the active function-signature facts to admit one exact
declaration profile: otherwise eligible functions with one or more exactly
annotated required keyword-only parameters, no positional or keyword-only
defaults, and no variadics. Formal order is `posonlyargs`, `args`, then
`kwonlyargs`. Existing signature and local-binding facts retain declaration
eligibility, ordered parameter identities, bindings, categories,
representations, ownership, lifetime, and exact rejection evidence. Parameter
kind and required status are reconstructed from the normalized `arguments`
node; the serialized `ParameterFact` shape does not change and no parallel
declaration model is introduced.

Phase 14D adds one complete call-keyed
`keyword-only-call-binding-facts` publication under `fact-table/0.14.3`. Its
candidate domain is direct calls whose resolved source-function target has the
required-keyword-only signature profile and reaches the static binder. Each
record retains full formal kinds and order; ordered positional and keyword
actuals; source-to-formal and formal-to-source association; exact required
coverage; categories; support or rejection evidence; source-order actual
staging; formal-order pure references; and
`source-order-actual-temporaries-formal-order-references-v1`.

Ordinary positionals may bind only positional-capable formals. Explicit names
may bind unbound positional-or-keyword or required keyword-only formals.
Positional-only names remain keyword-ineligible and keyword-only formals remain
positional-ineligible. Defaults, omitted required formals, variadics, unpacking,
runtime lookup, and `TypeError` modeling remain rejected.

Every selected call has one helper-free
`phase14.keyword_only_call.exact_binding@0.14.3` RulePlan. Its exact obligation
sequence closes direct target resolution; the required-keyword-only declaration;
absence of defaults, variadics, and unpacking; parameter-kind restrictions;
required keyword-only and complete formal coverage; exact representations;
source-order once-only evaluation; post-evaluation reference permutation; full
formal-order C arguments; ownership, no-runtime-failure, no-allocation/cleanup,
structured-C, provenance, cancellation, and target obligations.

Independent validation reconstructs the required-keyword-only call candidate
set and every call record from Python IR plus existing function-signature,
binding, category, call-target, and evaluation-order facts. It also validates
that admitted uncalled declarations satisfy the exact signature profile before
C parameter construction. Analysis, reconstruction, plan publication, C
parameter assembly, and call lowering remain linear and cancellation-safe.
Lowering cannot classify a formal, bind a source name, repair coverage, or
invent a default.

`conversion-plan/0.14` remains the explicit historical Phase 14A envelope. It
does not acquire conditional-region tables, plans, or active identities.
`conversion-plan/0.14.1` remains the explicit historical Phase 14B envelope. It
does not acquire keyword-call facts or plans and retains its exact keyword
rejection behavior.
`conversion-plan/0.14.2` remains the explicit historical Phase 14C envelope. It
does not acquire required-keyword-only facts or plans and retains its exact
`PYC2911` keyword-only declaration rejection.
