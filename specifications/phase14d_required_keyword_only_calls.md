# Phase 14D Required Keyword-Only Calls

Status: promoted and sealed in PyCForge 0.14.3. The historical feasibility,
opening, and rollback records remain preserved in `transition/phase_14d`; this
document states the implemented release contract.

## Purpose

Phase 14D defines one deliberately narrow continuation of the sealed Phase 14C
static call binder: required keyword-only parameters on an already-understood
direct source function.

The feature is exact and source-only. It does not add Python's runtime argument
binder. It proves the callee declaration and every supplied call statically,
stages explicit actual values once in Python source order, and supplies only
pure temporary references to the existing structured C call in full formal
order.

Phase 14D does not authorize defaults. In particular, it does not evaluate,
store, materialize, or substitute a default expression at function-definition
time or call time.

## Exact source boundary

### Function target

An eligible function remains an existing Phase 9/12/14C target:

- a uniquely resolved synchronous top-level source `FunctionDef`;
- declared in a document explicitly present in the closed `SourceBundle`;
- reachable by the sealed same-module binding or existing explicit
  cross-module `ImportFrom` function resolution;
- represented by one stable source-function binding; and
- otherwise eligible under the sealed annotation, return, local-binding,
  call-graph, module, and representation policies.

An existing import spelling alias remains eligible only because its binding
resolves directly to that source function. Assignment-created aliases,
parameters or locals used as callables, attributes, subscriptions, methods,
lambdas, nested functions, decorators, first-class callable values, reflection,
and unknown or dynamic targets remain rejected.

The recognized `range` iterator and Phase 13 static-record constructor remain
separate call families and never select the Phase 14D rule.

### Callee declaration

An eligible `arguments` node has:

- zero or more uniquely named, exactly annotated positional-only parameters;
- zero or more uniquely named, exactly annotated positional-or-keyword
  parameters;
- one or more uniquely named, exactly annotated keyword-only parameters;
- no positional defaults;
- a `kw_defaults` entry corresponding to each keyword-only parameter, with
  every entry null, proving that every keyword-only parameter is required;
- no `*args`;
- no `**kwargs`; and
- no duplicate source parameter name across any admitted parameter kind.

The exact admitted parameter-kind vocabulary is:

- `positional-only`;
- `positional-or-keyword`; and
- `keyword-only`.

Formal ordinals are the deterministic Python declaration order:
`posonlyargs`, then `args`, then `kwonlyargs`. Each admitted formal keeps its
existing exact category, C representation, binding, ownership, lifetime, and
annotation evidence. Required status is separate evidence reconstructed from
the corresponding null `kw_defaults` entry; it is not a new serialized
parameter kind.

A keyword-only parameter has no new runtime representation. Its mode is a
static source-call obligation. The generated C prototype and definition use the
existing `CParameter` structure in full formal order.

### Call occurrence

An eligible call:

- has the already-resolved direct `Name` target described above;
- has zero or more ordinary positional actual values;
- has explicit named keyword actual values with nonempty normalized
  `keyword.arg` spellings;
- contains no `Starred` positional actual;
- contains no null-name keyword entry and therefore no `**` unpacking; and
- binds every required formal exactly once.

Ordinary positional actuals may bind only the leading positional-only or
positional-or-keyword formals. They may never bind a keyword-only formal.

An explicit keyword may bind only:

- an unbound positional-or-keyword formal with the same exact source name; or
- an unbound required keyword-only formal with the same exact source name.

A positional-only formal is never keyword-addressable. Every required
keyword-only formal must therefore be supplied by an explicit named actual.

At least one explicit keyword is necessarily present because the admitted
declaration contains at least one required keyword-only formal.

Every actual category and C representation must exactly match its bound formal.
There is no conversion, coercion, widening, overload choice, or inferred
compatibility.

## Static binding semantics

Binding is a deterministic compile-time bijection:

1. validate the target and declaration profile;
2. index formal names and kinds once in formal order;
3. bind ordinary positional actuals to successive positional-capable ordinals;
4. bind each explicit keyword to one exact unbound named formal;
5. reject a positional attempt to cross into the keyword-only range;
6. reject an unknown name, positional-only name used as keyword, duplicate
   binding, omitted required formal, excess positional, or category mismatch;
7. prove complete exact-once formal coverage; and
8. publish immutable positive or negative binding evidence.

Static rejection occurs before C IR publication. No Python `TypeError`
propagation, runtime parameter table, string-key lookup, hashing, dynamic
dispatch, exception channel, or fallback binding is introduced.

## Evaluation and C call order

Python source evaluation order and C formal order remain separate immutable
vectors.

The source evaluation vector is:

1. ordinary positional actual values from left to right; then
2. explicit keyword actual values in their normalized source order.

Each explicit actual's complete predecessor-owned prerequisite sequence is
emitted at that source position, and the value is materialized exactly once in
a typed automatic temporary. A Phase 14A helper prerequisite remains attached
to its expression. A Phase 14B conditional-region prerequisite remains inside
its exact fact-owned guard. Container reads, record reads, and nested direct
calls retain their sealed predecessor evidence.

Only after every explicit actual has been staged may lowering construct the
formal vector. It contains exactly one pure temporary reference per admitted
formal ordinal. The existing `CCallExpr` receives that vector.

The required lowering-shape identity is:

`source-order-actual-temporaries-formal-order-references-v1`.

No final C argument expression may contain an unstaged source operation, source
call, helper invocation, or other effect whose order C may choose.

## C interface containment

C has no keyword-only parameter syntax. Erasing the source calling mode from the
rendered C prototype is not an approximation inside the declared conversion
contract because:

- every source call in the explicit bundle is statically resolved and checked;
- every generated source call supplies the proved formal vector;
- no Python runtime caller or generated-C foreign interface is promised; and
- calls introduced outside the converted `SourceBundle` are outside PyCForge's
  source-semantics guarantee.

The source calling-mode obligation remains visible in the immutable fact,
RulePlan, conversion summary, decision trace, diagnostics, and source/output
mapping. It is not silently delegated to C.

## Fact contract

Phase 14D may introduce exactly one immutable table under
`fact-table/0.14.3`:

`keyword-only-call-binding-facts`.

The table is call-keyed and complete over every direct-call candidate whose
resolved target has a required-keyword-only declaration and reaches the Phase
14D static binder. It includes supported and rejected call candidates. Recording
negative evidence does not widen acceptance.

Each record identifies at least:

- call, target expression, callee function, and target binding identities;
- caller and callee module/document identities by stable reference;
- ordered positional and keyword source entries;
- exact keyword spellings and value-node identities;
- source-evaluation ordinals;
- formal ordinals, names, and parameter kinds;
- actual-to-formal and formal-to-actual association vectors;
- complete coverage and uniqueness state;
- actual and formal categories;
- lowering-shape identity;
- support state, owning diagnostic, reason, rejection node, and provenance.

Existing authoritative lexical, module, signature, category, call-graph,
conditional-region, representation, ownership, lifetime, target, and
cancellation facts remain referenced rather than silently copied or
reinterpreted.

Required-keyword-only declaration evidence remains in existing
`function-signature-facts` records without changing the serialized
`ParameterFact` shape. Those records retain ordered parameter nodes, bindings,
names, ordinals, categories, representations, ownership/lifetime, annotation
evidence, eligibility, and rejection reason. Parameter kind and required status
are reconstructed from the owning normalized `arguments` node.

Every negative candidate has `supported: false`, one exact owning diagnostic, a
nonempty reason, a precise rejection node, and no Phase 14D RulePlan or C IR.
Every selected Phase 14D call has exactly one supported call fact, and every
selected Phase 14D RulePlan references exactly one supported fact.

Independent validation reconstructs every call candidate, declaration
eligibility, parameter kinds, formal order, source order, name binding, complete
coverage, categories, and the C reference vector directly from Python IR and
existing facts. It also validates required-keyword-only declarations that have
no call site. It does not trust lowering output.

## RulePlan contract

Phase 14D may add exactly one RulePlan family:

`phase14.keyword_only_call.exact_binding@0.14.3`.

The RulePlan is `SupportedDirect`. It owns:

- exact direct-target evidence;
- exact required-keyword-only declaration evidence;
- parameter-kind and complete-coverage obligations;
- distinct source-evaluation and formal-reference orders;
- exact category and representation agreement;
- provenance and mapping obligations;
- deterministic linear-resource and cancellation obligations; and
- the no-runtime-binder and no-approximation boundary.

Its semantic and resolved obligation sequences are exactly:

- `direct-source-target-resolved-once`;
- `required-keyword-only-parameters-proved`;
- `defaults-variadics-and-unpacking-absent`;
- `positional-actuals-limited-to-positional-formals`;
- `keyword-names-bound-to-keyword-addressable-parameters`;
- `required-keyword-only-coverage-exact`;
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

It owns no helper, allocation, cleanup, ownership transfer, semantic
approximation, or runtime failure channel. Existing rules continue to own every
nested actual expression and the body, return, numeric, conditional, container,
record, and module semantics.

Existing supported `FunctionDef` RulePlans for an admitted
required-keyword-only declaration gain:

- `keyword-only-signature:{function_id}`;
- `keyword-only-parameter-count:{n}`;
- one
  `keyword-only-parameter:{ordinal}:{parameter_id}:{name}`
  fact per required keyword-only formal;
- `keyword-only-c-interface:mode-erased-after-static-binding`; and
- exact resolved obligations
  `required-keyword-only-parameters-exact`,
  `keyword-only-parameter-kinds-preserved`,
  `c-interface-mode-erasure-after-static-binding`, and
  `defaults-and-variadics-absent`.

The appended explanation tokens are
`required-keyword-only-signature`, count, `c-interface-mode-erasure`, and
`after-static-binding`. This is not a second new rule family. The existing
function plan proves the declaration directly from Python IR and
`function-signature-facts`, including when the function is uncalled. Its helper
set remains empty.

Lowering consumes only the validated fact and RulePlan. It may not resolve
source names, classify parameter kinds, infer missing coverage, repair a
rejected binding, or emit final C text.

## Diagnostics and precedence

No new source diagnostic family is required by this contract.

- `PYC2901` and `PYC2902` retain target and module eligibility.
- `PYC2904` retains missing required-formal coverage and excess positional
  arity, including a positional attempt to enter the keyword-only range.
- `PYC2905` retains exact post-binding representation mismatch.
- `PYC2910` retains `*`/`**`, null keyword names, unpacking, and other excluded
  call shapes.
- `PYC2911` remains the ineligible declaration boundary for defaults,
  defaulted keyword-only parameters, variadics, and keyword-only declaration
  shapes outside this exact profile. Under the 0.14.3 contract it no longer
  rejects an otherwise eligible required keyword-only declaration merely
  because `kwonlyargs` is nonempty.
- `PYC2912` retains exact static name-binding failures: unknown keyword,
  positional-only name used as keyword, positional/keyword collision, or
  duplicate keyword binding.
- `PYC2914`, `PYC2915`, `PYC2920`, `PYC2930`, `PYC2931`, and `PYC2932` retain
  decorated/generic, nested/closure, recursion, return, fallthrough, and exact
  annotation precedence.

The most specific predecessor diagnostic wins before a Phase 14D binding
diagnostic. One root cause produces one primary diagnostic with an exact source
span and deterministic ordering. Blocked parents retain causal references and
do not produce cascades.

Historical 0.14.2 and earlier configurations retain their exact diagnostic
meanings and rejection envelopes. The active 0.14.3 documentation must version
the narrowed `PYC2911` keyword-only boundary explicitly rather than rewriting
historical evidence.

## Resource and cancellation contract

Phase 14D adds no parameter-count or argument-count constant. It continues to
use the sealed source-byte, line, token, AST-node, maximum-nesting, function,
signature, diagnostic, and trace ceilings.

For each signature or bounded analysis scope, implementation builds formal-name,
formal-kind, and ordinal indexes once. Declaration analysis, call binding,
independent reconstruction, planning, C-parameter assembly, actual staging, and
formal-reference assembly remain linear in the affected formal, actual, and
referenced predecessor-fact counts.

Repeated full-signature searches per keyword, whole-module rescans per call,
permutation enumeration, open-ended refinement, and runtime name lookup are
forbidden.

Cancellation checks are required during:

- declaration and parameter-kind analysis;
- fact construction and independent reconstruction;
- RulePlan publication;
- per-actual prerequisite emission and staging;
- C parameter/prototype assembly; and
- formal-reference vector assembly.

Cancellation, rejection, resource exhaustion, or internal validation failure
publishes no partial current fact table, plan, C IR, mapping, helper manifest,
summary, decision trace, telemetry snapshot, or generated C.

If measurement demonstrates a need for a new call-specific ceiling or
nonlinear algorithm, implementation stops for a separate resource decision.

## Observer and publication isolation

Decision-trace, telemetry, and progress observers consume immutable completed
facts or events. Their enablement, truncation, latency, absence, or failure
cannot influence:

- parameter eligibility or kind;
- binding or coverage;
- either order vector;
- temporary names or C parameter order;
- diagnostics or ResultStatus;
- C IR, mappings, summaries, or generated bytes; or
- semantic and output fingerprints.

Bounded observer failure emits only observation evidence. It cannot publish a
partial successor or prevent an otherwise valid conversion result.

Rejected, canceled, resource-limited, internally failed, stale, or
observation-incomplete work cannot overwrite the last successful result or
make stale generated C eligible for Save C. Existing atomic linked-save and
read-only generated-C protections remain mandatory.

## Contract identities and compatibility

The active promoted identities are:

- release: `0.14.3`;
- rule set: `phase14-required-keyword-only-calls-v0.14.3`;
- renderer: `c-renderer-v0.14.3`;
- facts: `fact-table/0.14.3`;
- conversion plan: `conversion-plan/0.14.3`;
- C IR envelope: `c-ir/0.14.3`;
- generated artifact: `generated-c/0.14.3`;
- conversion summary: `pycforge.conversion-summary/0.14.3`;
- decision trace: `pycforge.decision-trace/0.14.3`; and
- RulePlan: `phase14.keyword_only_call.exact_binding@0.14.3`.

Advancing an envelope does not authorize a new Python IR node, C IR dataclass,
enum member, expression or statement kind, type, storage mode, helper, renderer
syntax, public request policy, or result-serialization shape.

The following remain frozen:

- SourceBundle `source-bundle/0.2`;
- normalized Python IR `python-ir/0.4`;
- result serialization `0.5`;
- semantic policy `strict-source-v1`;
- target contract `c11-portable-fixed-v1`;
- Phase 14A numeric policy and helpers;
- Phase 14B conditional-region facts and placement;
- Phase 14C direct-keyword facts, rule, historical configuration, and generated
  output;
- helper, container, module, record, workspace, ownership, and lifetime
  policies; and
- closed SourceBundle resolution with no host discovery.

An explicit 0.14.2 or earlier request retains its exact canonical request,
facts, plans, diagnostics, payload, summary, trace, generated-C bytes, and
fingerprints. Under the active 0.14.3 identities, a source that selects no Phase
14D declaration or call behavior retains predecessor generated-C bytes and
output fingerprints.

## Explicit non-goals

Phase 14D does not authorize:

- positional defaults or omission of positional formals;
- keyword-only defaults or omission of keyword-only formals;
- arbitrary default expressions or definition-time default evaluation;
- `*args`, `**kwargs`, `*` or `**` call unpacking;
- runtime binding, Python `TypeError`, coercion, overloads, or dynamic dispatch;
- keyword calls to `range` or static-record constructors;
- methods, callable values, indirect targets, target aliases created by
  assignment, lambdas, nested functions, decorators, or closures;
- recursion, exceptions, unwinding, mutation, allocation, ownership transfer,
  cleanup, generators, async behavior, or context managers;
- a new helper, helper version, representation, value category, C IR node, or
  renderer construct;
- host import, filesystem, environment, installed-package, or network
  discovery;
- compilation, linking, loading, execution, debugging, benchmarking, or a
  terminal;
- another Phase 14 mini-phase; or
- Phase 15.

## Release validation and promotion

The historical opening packet authorized only bounded implementation.
Promotion subsequently closed the manifest, complete vertical-slice and
adversarial evidence, exact historical compatibility, deterministic
fresh-process artifacts, resource and observer audits, failure injection,
packaging reproducibility, authenticated predecessor custody, and explicit
release records.

Final validation discovered 539 tests: 524 passed, 15 skipped, and zero failed.
The skips are exactly 10 for unavailable PyQt5 and five for unavailable older
custody artifacts. The focused Phase 14D gate passed 65 of 65 tests.

Two fixed-epoch wheel builds were byte-identical. The sealed
`pycforge-0.14.3-py3-none-any.whl` is 340,054 bytes with SHA-256
`c0dd0c0ed79131daa5af815a8a9bb096b9f955c9c617ec0b8eb6a10c69d27b7f`.
Its archive and `RECORD` each account for 132 members; 17 are SVG assets and
zero are native-code members. Two normalized source-archive builds were also
byte-identical. The promoted converter subtree SHA-256 is
`74b32c25e40af3398dd46288941812ce7ad87f0d4b72fec3d3bd786cc1b8f3a8`.

The release can be revalidated with:

```text
python -m unittest discover -s tests
python -m unittest tests.test_phase14d_cumulative_eligibility tests.test_phase14d_keyword_only_analysis tests.test_phase14d_keyword_only_contracts tests.test_phase14d_keyword_only_hardening tests.test_phase14d_keyword_only_lowering tests.test_validate_phase14d
python tools/validate_phase14d.py --run-tests --predecessor-archive pycforge_phase_14c_v0_14_2.tar.gz --require-predecessor --predecessor-wheel pycforge-0.14.2-py3-none-any.whl --require-predecessor-wheel --wheel pycforge-0.14.3-py3-none-any.whl --require-wheel --source-archive pycforge_phase_14d_v0_14_3.tar.gz --require-source-archive
python -m pycforge audit architecture
python -m pycforge audit rules
python -m pycforge audit helpers
python -m pycforge audit containers
python -m pycforge audit modules
python -m pycforge audit records
python -m pycforge audit numeric
python -m pycforge audit conditional
python -m pycforge audit keyword
python -m pycforge audit keyword-only
python -m pycforge audit determinism
python -m pycforge audit transition --phase phase_14
python -m pycforge audit transition --phase phase_14b
python -m pycforge audit transition --phase phase_14c
python -m pycforge audit transition --phase phase_14d
```

Validation remains source-only. No gate compiled, linked, loaded, or executed
generated C. No new actual PyQt5 widget execution or Windows 11 execution is
claimed. Phase 15 has not started.
