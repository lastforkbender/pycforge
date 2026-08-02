# Phase 14C Direct Exact Keyword Calls — promoted release contract

Status: promoted and sealed as the PyCForge 0.14.2 release contract. The Phase
14C manifest, gate evidence, release report, and release fingerprint seal
validation, deterministic packaging, authenticated predecessor custody, and
release hashes.

## Purpose

Phase 14C opens one deliberately narrow part of deferred call binding: explicit
named actual values for a direct call to an already-understood source function.
It does not add a runtime argument binder. It uses the callee's existing exact
signature to prove a complete static actual-to-formal bijection.

Python evaluates argument values in source order, while a C call supplies
values by formal position and does not generally specify evaluation order among
argument expressions. Phase 14C therefore records and preserves two different
orders: all source actuals are evaluated and staged once in Python order, then
only pure temporary references are arranged in formal ordinal order for the
existing structured C call.

## Exact source boundary

An eligible source occurrence is a Python `Call` satisfying every condition
below.

### Target

- The call target is a `Name` whose sealed lexical, function, and SourceBundle
  module facts already resolve it directly to one eligible top-level
  synchronous source function.
- The source function may be in the caller's module or another document
  supplied in the same explicit SourceBundle and reached through the existing
  supported direct `ImportFrom` resolution.
- An existing import spelling alias is eligible only because its binding still
  resolves directly to the source function. It is not a Python callable value.
- Assignment-created aliases, parameters or locals used as callables,
  attributes, subscriptions, methods, lambdas, nested functions, decorators,
  function-pointer models, reflection, and unknown or dynamic targets reject.

The recognized `range` iterator and Phase 13 static-record constructor paths
are different call families and never select this rule.

### Callee declaration

The callee retains the exact existing function declaration subset:

- every formal has a unique source parameter name and exact supported
  annotation;
- formals are required positional-only or positional-or-keyword parameters;
- there are no defaults, keyword-only parameters, `*args`, or `**kwargs`; and
- the function remains eligible under the sealed return-path, module, and
  non-recursive call-graph rules.

Phase 14C adds no parameter declaration form and changes no signature, C
prototype, representation, ownership, or lifetime rule.

### Call arguments

The normalized call contains:

1. zero or more ordinary positional value nodes in their existing list order;
   and
2. one or more `keyword` nodes, each with a nonempty normalized Python source
   name and one value node, in normalized source order.

A `Starred` positional actual or a keyword whose `arg` is null is unpacking and
rejects. At least one explicit named keyword is required; a purely positional
call remains predecessor behavior.

Formal matching uses the exact normalized Python IR source name, never a
generated C spelling. Identifier allocation, import target renaming, and C
parameter spelling cannot affect the association.

## Static binding algorithm

For a signature with formal ordinals `0..n-1`, binding is exactly:

1. Reject if the number of ordinary positional actuals exceeds `n`.
2. Bind positional actual ordinal `i` to formal ordinal `i`.
3. Build one deterministic index from each positional-or-keyword formal's exact
   source name to its formal ordinal. Positional-only names are not in this
   keyword-addressable index.
4. Visit explicit keywords once in normalized source order. Each name must
   identify one still-unbound indexed formal; bind its value to that formal.
5. Require every formal ordinal to be bound exactly once.
6. Require each actual's existing value category, C type, passing convention,
   ownership, and lifetime to be exactly compatible with its bound formal.

This produces a total bijection; it is not overload resolution, coercion,
default selection, or dynamic dispatch. Unknown keyword names, positional-only
names used as keywords, duplicate binding through positional-plus-keyword or
keyword-plus-keyword forms, missing required formals, excess positionals, and
category mismatches reject before planning or C IR publication.

The algorithm is linear. Repeated full-signature scans for each keyword,
backtracking, permutation search, hash-order-dependent output, or renderer
participation is forbidden.

## Required binding fact

Every candidate occurrence has exactly one immutable record in a complete
`keyword-call-binding-facts` table under `fact-table/0.14.2`. The candidate
domain is every keyword-bearing `Call` whose direct `Name` target and existing
declaration signature reach the Phase 14C static binder, whether or not that
binder proves an accepted exact association. Thus the table includes complete
negative facts for unknown or duplicate names, positional-only binding,
positional/keyword collision, missing or excess coverage, category mismatch,
and keyword-bearing unpacking or null-name shape. A pure starred-only call never
enters this fact domain. Every record contains exactly the published model
fields:

- deterministic binding ID; call and callee node IDs; target function and
  binding IDs; and the exact target source name;
- positional-only parameter count plus ordered parameter node IDs, source
  names, and value categories;
- ordered positional actual node IDs plus ordered keyword node IDs, exact
  normalized names, and keyword value node IDs;
- one source-order argument-binding entry per actual containing its value node,
  optional keyword node/name, source ordinal, bound parameter node/name/
  ordinal, actual category, and expected category;
- ordered source argument IDs/categories, the source-to-parameter ordinal
  vector, ordered formal argument IDs, and the inverse parameter-to-source
  vector;
- exact evaluation order, once-only and complete-coverage proofs, and the
  `source-order-temporaries-formal-order-references-v1` lowering shape; and
- allocation, cleanup, runtime-binding-failure, support, diagnostic, reason,
  and rejection-node state.

Record provenance separately publishes exact source node IDs and the fixed
keyword-call evidence tokens. Target/signature/module and other cumulative
evidence remains authoritative in its predecessor fact tables and in the
RulePlan fact set; those fields are not duplicated into the keyword record.

The exact lowering-shape value is
`source-order-temporaries-formal-order-references-v1`.

The new table is additive. Existing call-target and signature facts remain
predecessor evidence and retain their established field meanings. In
particular, an existing argument-node sequence may not be silently redefined
from source order to formal order. A selected 14C RulePlan references the one
complete supported fact for its call; historical rules never observe the table.

Fact coverage is exact at both boundaries: every candidate occurrence has one
record, no record belongs to a noncandidate occurrence, every call selecting
the 14C rule has exactly one supported record, and every selected 14C RulePlan
references exactly one such supported record. A rejected candidate instead has
`supported: false`, an exact diagnostic code, nonempty reason and rejection
node, and `runtime_binding_failure: compile-time-rejected`; it has no 14C
RulePlan and publishes no C IR. Independent validation reconstructs the full
candidate set, target, signature, parameter kinds, names, coverage, uniqueness,
categories, both order vectors, support state, rejection evidence, and
bijection directly from Python IR and predecessor facts. It may not trust a
lowering result. Lowering may not rediscover eligibility, compare keyword names,
widen the profile, or repair a malformed fact.

## RulePlan and exact obligations

Exactly one new RulePlan family is present:

- `phase14.keyword_call.exact_binding@0.14.2`.

The rule owns no helper. Every nested source operation retains its existing
plan and helper ownership. The call plan has the new binding fact and exact
predecessor target/signature/category/call-graph facts necessary to close these
obligations:

- `direct-source-target-resolved-once`;
- `explicit-keywords-only-no-unpacking`;
- `positional-prefix-bound-in-order`;
- `keyword-names-bound-to-positional-or-keyword-parameters`;
- `parameter-coverage-exact`;
- `argument-representations-compatible-after-binding`;
- `source-arguments-evaluated-left-to-right-once`;
- `argument-temporaries-reordered-only-after-evaluation`;
- `c-call-arguments-in-formal-order`;
- `parameter-ownership-boundary-explicit`;
- `runtime-binding-failure-absent`;
- `allocation-and-cleanup-absent`;
- `structured-c-ir-only`;
- `source-provenance-anchored`;
- `cancellation-safe-points-honored`; and
- `target-contract-exact`.

The plan's facts, obligations, explanation tokens, and empty rule-owned helper
set are exact independently validated sets, not descriptive hints. An
unsupported or internally inconsistent call has no RulePlan and publishes no
C IR.

## Evaluation and structured C IR lowering

The source evaluation vector is:

```text
[positional value 0, ..., positional value p-1,
 keyword value 0, ..., keyword value k-1]
```

For each vector entry in order, lowering:

1. emits the value's complete already-planned prerequisite sequence at that
   source position;
2. evaluates the value exactly once; and
3. initializes one typed automatic argument temporary with complete synthetic
   provenance.

Only after all entries have been staged does lowering construct the C argument
vector. For formal ordinals `0..n-1`, it emits the pure identifier reference to
the temporary of the actual bound to that ordinal. The existing `CCallExpr`
receives exactly this vector. Existing result materialization remains unchanged.

For example:

```python
def target(a: int, b: int, c: int) -> int:
    return a + b + c

target(c=first(), a=second(), b=third())
```

has the semantic lowering shape:

```text
c_source = evaluate first() once
a_source = evaluate second() once
b_source = evaluate third() once
result = target(a_source, b_source, c_source)
```

The generated temporary spellings are allocator decisions; the orders and
associations are not.

Only existing C IR declarations, identifier references, and `CCallExpr` nodes
may be used. A direct C call containing unstaged source expressions, named-C
argument invention, raw C text, statement expressions, runtime name tables, a
new C IR node, or renderer inference is forbidden.

## Composition with sealed Phase 14B regions

Composition is bidirectional and independently proved:

- a keyword actual may contain an already-supported Phase 14B conditional
  region, whose complete guarded prelude executes at that actual's source
  position; and
- a Phase 14C call may occur where a predecessor direct source call is eligible
  inside an independently selected Phase 14B operand, in which case the
  call's complete source-order staging and result materialization remain inside
  the region's existing guard.

Neither case changes guard polarity, prerequisite ownership, rolling-middle
reuse, or the 14B lowering shape. If composition cannot be represented through
the sealed region semantics plus the one 14C fact family, the occurrence
rejects; Phase 14C may not revise Phase 14B to admit it.

## Resources, cancellation, and publication

Phase 14C adds no arbitrary argument or formal count. Sealed aggregate
source-byte, line, token, AST-node, and nesting ceilings and predecessor
signature limits bound the input. Binding, reconstruction, planning, and
lowering are linear in actual/formal entries and referenced facts.

Cancellation checks are required while visiting actuals, constructing and
validating the bijection, publishing the RulePlan, staging each source actual,
and assembling the formal reference vector. Cancellation, rejection, resource
exhaustion, or internal validation failure publishes no partial successor fact
table, plan, C IR, mapping, summary, trace, telemetry semantics, or generated C.
Observers remain bounded and semantically inert.

## Stable diagnostics and precedence

`PYC2910` remains the primary boundary for `*`/`**` unpacking, a null keyword
name, or another excluded keyword call shape. `PYC2912` owns exact static name-
binding failures for an otherwise eligible direct source target: an unknown
keyword name, a positional-only name used by keyword, a positional/keyword
collision, or a duplicate keyword. Existing diagnostics retain ownership:

- `PYC2901`/`PYC2902` for target or eligibility failures;
- `PYC2904` for excess positional or missing required arity;
- `PYC2905` for actual/formal representation mismatch;
- `PYC2911` for an ineligible declaration profile; and
- `PYC2920` for direct or mutual recursion.

No general Python call exception family is opened.

A more specific root cause must not be masked by a generic keyword diagnostic.
Malformed or adversarial facts are internal validation failures, not broader
source acceptance. Unsupported calls publish diagnostics and no generated C.

## Promoted release contract identities

- rule set: `phase14-direct-keyword-calls-v0.14.2`;
- renderer: `c-renderer-v0.14.2`;
- keyword binding facts: `fact-table/0.14.2`;
- conversion plan: `conversion-plan/0.14.2`;
- C IR envelope: `c-ir/0.14.2` with no new node kind;
- generated C: `generated-c/0.14.2`;
- conversion summary: `pycforge.conversion-summary/0.14.2`;
- decision trace: `pycforge.decision-trace/0.14.2`; and
- result serialization: unchanged at `0.5`.

No new public policy field is introduced. SourceBundle 0.2, Python IR 0.4,
`strict-source-v1`, `c11-portable-fixed-v1`, the Phase 14A numeric policy,
Phase 14B conditional-region semantics, and sealed helper, container, module,
record, ownership, lifetime, workspace, and product-boundary contracts remain
unchanged. Advancing the renderer identity records the active release; it does
not authorize new renderer syntax or semantics.

## Release validation and promotion boundary

Run from the promoted release root:

```text
python -m unittest discover -s tests
python tools/validate_phase14c.py --run-tests
python tools/validate_phase14c.py --run-tests --predecessor-archive pycforge_phase_14b_v0_14_1.tar.gz --require-predecessor --predecessor-wheel pycforge-0.14.1-py3-none-any.whl --require-predecessor-wheel --wheel pycforge-0.14.2-py3-none-any.whl --require-wheel --source-archive pycforge_phase_14c_v0_14_2.tar.gz --require-source-archive
python -m pycforge audit architecture
python -m pycforge audit rules
python -m pycforge audit helpers
python -m pycforge audit containers
python -m pycforge audit modules
python -m pycforge audit records
python -m pycforge audit numeric
python -m pycforge audit conditional
python -m pycforge audit keyword
python -m pycforge audit determinism
python -m pycforge audit transition --phase phase_14
python -m pycforge audit transition --phase phase_14b
python -m pycforge audit transition --phase phase_14c
```

The authenticated invocation verifies the sealed Phase 14B source archive and
wheel together with the promoted 0.14.2 wheel and source archive. Tests, audits,
independent fact/C IR validation, packaging, and generated-C text conformance
invoked no compiler, linker, loader, or generated-C execution path. PyQt5 was
unavailable in the release environment, so no new actual widget execution is
claimed; sealed offscreen-widget evidence remains preserved. Windows 11 laptop
execution remains future user feedback and is not claimed by this release.
Phase 14D and Phase 15 have not started.

## Historical compatibility

An explicit 0.14.1 request must retain its exact canonical request shape,
facts, plans, `PYC2910` keyword rejection, generated-C bytes, output
fingerprint, payload, summary, and trace behavior. Earlier historical
configurations retain their own sealed exact behavior. No 14C field may leak
into a historical artifact.

Under the active 0.14.2 configuration, sources with no call selecting the 14C
rule retain predecessor generated-C bytes and output fingerprints. Versioned
envelopes may change only where the active identity contract requires it.
Phase 14A helpers and Phase 14B region output for predecessor sources remain
byte-exact.

## Explicit non-goals

Phase 14C does not open defaults, omitted parameters, keyword-only parameters,
variadics, unpacking, `range` keywords, record-constructor keywords, methods,
target values or aliases, indirect calls, recursion, closures, lambdas,
decorators, generators, async calls, exceptions, runtime `TypeError`, mutation,
allocation, cleanup, advanced strings, new containers, destructuring,
comprehensions, general objects, host import discovery, compilation, linking,
loading, or execution. It does not authorize Phase 14D or begin Phase 15.
