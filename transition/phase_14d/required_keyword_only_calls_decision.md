# Phase 14D Required Keyword-Only Calls Decision

Status: feasibility accepted for bounded implementation on 2026-07-26. No
implementation, validation, packaging, promotion, or release is claimed by this
decision.

Authority: Architecture Revision 3.1, Revision 3.2 addendum, the authenticated
and promoted PyCForge 0.14.2 predecessor, and the explicit user direction
“Continue to Phase 14D”.

Revision 3.1 does not assign a particular feature to the letter `14D`. This
decision performs the roadmap-required feasibility classification and selects
the smallest exact continuation of the sealed Phase 14C binder.

## Decision D14D-01 — admit one required keyword-only declaration profile

Phase 14D may accept an otherwise eligible synchronous top-level source function
only when its normalized `arguments` node contains:

- zero or more required positional-only parameters;
- zero or more required positional-or-keyword parameters;
- one or more required keyword-only parameters;
- exact supported annotations on every admitted parameter and return;
- no positional defaults;
- one null `kw_defaults` entry per keyword-only parameter;
- no `*args`;
- no `**kwargs`; and
- no duplicate parameter spelling across admitted kinds.

The admitted formal kinds are exactly `positional-only`,
`positional-or-keyword`, and `keyword-only`. Required status is separate
evidence reconstructed from the corresponding null `kw_defaults` entry; it is
not a new serialized parameter kind. Formal ordinal order is `posonlyargs`,
then `args`, then `kwonlyargs`.

Every formal retains the existing exact binding, category, C representation,
ownership, lifetime, annotation, and provenance contracts. Phase 14D adds no
default evaluation, storage, substitution, coercion, or runtime representation.

The generated C prototype and definition use existing `CParameter` structures
in full formal order. C has no keyword-only syntax; the mode remains a static
source-call obligation recorded in deterministic conversion evidence.

## Decision D14D-02 — retain the closed direct-target profile

A selected `Call` target must already be resolved by sealed lexical, module, and
function facts to one admitted source function. Existing direct same-module and
explicit cross-module `ImportFrom` function resolution is eligible, including
an import spelling alias whose binding still points directly to that function.

Assignment-created aliases, parameters or locals used as callables,
attributes, subscriptions, methods, callable values, nested functions,
lambdas, decorators, reflection, function-pointer models, and unknown or dynamic
targets remain unsupported. `range` and static-record constructors remain
separate call families.

The SourceBundle stays explicit and closed. Phase 14D performs no filesystem,
environment, import-path, installed-package, or network discovery.

## Decision D14D-03 — bind parameter kinds completely and statically

Binding is a deterministic compile-time bijection:

1. ordinary positional actuals bind successive positional-only or
   positional-or-keyword ordinals;
2. no ordinary positional actual may cross into a required keyword-only
   ordinal;
3. an explicit named actual may bind one unbound positional-or-keyword or
   required keyword-only formal with the same exact source name;
4. a positional-only formal is never addressable by keyword;
5. every required keyword-only formal is supplied explicitly by name;
6. every formal receives exactly one actual; and
7. every actual category and C representation exactly match its formal.

Missing required formals, excess positional actuals, unknown names,
positional-only names used as keywords, duplicate binding, unpacking, and
representation mismatch reject before C IR publication. PyCForge does not
synthesize Python's runtime call binder or `TypeError` behavior.

The declaration may remain uncalled inside the supplied bundle. That does not
create a foreign-call promise. Any C call introduced outside PyCForge's
converted SourceBundle is outside the declared source-semantics guarantee.

## Decision D14D-04 — preserve explicit source and formal orders

The source evaluation vector contains ordinary positional values from left to
right followed by explicit keyword values in normalized source order. Each
value's complete predecessor-owned prerequisite sequence is emitted at that
source position, then the value is materialized exactly once in a typed
automatic temporary.

Phase 14A helper prerequisites and Phase 14B conditional-region guards retain
their sealed placement. Phase 14D cannot hoist, duplicate, drop, or reorder a
predecessor-owned prerequisite.

Only after every explicit actual is staged may lowering construct the full
formal vector. It contains one pure temporary reference per formal ordinal,
including required keyword-only ordinals. The existing `CCallExpr` receives
that vector.

The exact lowering shape is:

`source-order-actual-temporaries-formal-order-references-v1`.

No final C argument expression may contain an unstaged source expression, nested
source call, helper call, or other effect whose order C may choose.

## Decision D14D-05 — add one complete call fact table and one call rule

Phase 14D may introduce one immutable `fact-table/0.14.3` table:

`keyword-only-call-binding-facts`.

Its domain is call-keyed and complete over every resolved direct-call candidate
whose target has a required-keyword-only declaration and reaches the Phase 14D
static binder. It contains positive and negative call records only; it is not
keyed by declarations and contains no declaration record.

The table records stable call, function, target-binding, parameter, and actual
identities; formal names, kinds, and ordinals; source-order entries;
actual-to-formal and formal-to-actual vectors; exact required and complete
coverage; categories; support or rejection state; diagnostics; lowering shape;
and provenance. Existing lexical, module, function-signature, category,
call-target, and evaluation-order facts remain referenced rather than copied.

An unsupported call candidate has `supported: false`, one owning diagnostic, a
nonempty reason, a precise rejection node, and no Phase 14D call RulePlan or C
IR.
Every selected Phase 14D call has exactly one supported fact, and every selected
Phase 14D call RulePlan references exactly one supported fact.

Required-keyword-only declarations remain in the existing
`function-signature-facts` records without changing the serialized
`ParameterFact` shape. Parameter kind and required status are reconstructed
from the normalized `arguments` node. Affected existing supported `FunctionDef`
RulePlans gain these exact facts:

- `keyword-only-signature:{function_id}`;
- `keyword-only-parameter-count:{n}`;
- one `keyword-only-parameter:{ordinal}:{parameter_id}:{name}` fact per
  required keyword-only formal; and
- `keyword-only-c-interface:mode-erased-after-static-binding`.

Those existing plans append the exact obligations
`required-keyword-only-parameters-exact`,
`keyword-only-parameter-kinds-preserved`,
`c-interface-mode-erasure-after-static-binding`, and
`defaults-and-variadics-absent`. Their appended explanation tokens are
`required-keyword-only-signature`, the count,
`c-interface-mode-erasure`, and `after-static-binding`.

Independent validation reconstructs declaration eligibility, formal kinds,
source order, formal order, binding, coverage, categories, and C reference order
from Python IR and predecessor facts. It separately validates admitted
declarations and their affected existing `FunctionDef` RulePlans even when the
function has no call site. It does not trust lowering.

Phase 14D may add exactly one RulePlan family:

`phase14.keyword_only_call.exact_binding@0.14.3`.

The plan is `SupportedDirect` and uses no helper. Existing rules continue to own
all nested actual expressions and predecessor language semantics. Extending the
existing `FunctionDef` plans does not create a second new rule family.

## Decision D14D-06 — retain diagnostic ownership and precedence

No new source diagnostic family is authorized by this opening.

- `PYC2901`/`PYC2902` retain target and module eligibility.
- `PYC2904` retains missing required coverage and excess positional arity,
  including positional entry into the keyword-only range.
- `PYC2905` retains exact representation mismatch.
- `PYC2910` retains `*`/`**`, null-name unpacking, and excluded call shapes.
- `PYC2911` retains defaults, defaulted keyword-only parameters, variadics, and
  keyword-only declaration shapes outside this exact profile. Under active
  0.14.3 identities it no longer rejects a valid required keyword-only
  declaration solely because `kwonlyargs` is nonempty.
- `PYC2912` retains unknown keyword, positional-only keyword, positional/keyword
  collision, and duplicate keyword binding.
- Existing decorator, closure, recursion, annotation, return, module, numeric,
  conditional, container, and record diagnostics retain precedence.

The 0.14.3 specification narrows the active `PYC2911` rejection boundary
explicitly. Historical 0.14.2 and earlier diagnostic records and meanings are
never rewritten.

One root cause produces one primary deterministic diagnostic with an exact span.
Blocked parents refer causally rather than emitting a cascade.

## Decision D14D-07 — preserve policies, compatibility, and atomicity

The prospective active identities are:

- `phase14-required-keyword-only-calls-v0.14.3`;
- `c-renderer-v0.14.3`;
- `fact-table/0.14.3`;
- `conversion-plan/0.14.3`;
- `c-ir/0.14.3`;
- `generated-c/0.14.3`;
- `pycforge.conversion-summary/0.14.3`; and
- `pycforge.decision-trace/0.14.3`.

SourceBundle 0.2, Python IR 0.4, result serialization 0.5,
`strict-source-v1`, `c11-portable-fixed-v1`, and all helper, container, module,
record, numeric, conditional, workspace, ownership, lifetime, and public-policy
identities remain frozen.

An explicit 0.14.2 or earlier request must retain its exact canonical shape,
facts, plans, diagnostics, payload, summary, trace, generated-C bytes, and
fingerprints. Under active 0.14.3 identities, a source selecting no Phase 14D
declaration or call behavior retains predecessor generated-C bytes and output
fingerprints.

Analysis, validation, planning, C-parameter assembly, actual staging, and
formal-vector assembly remain linear. Existing aggregate resource ceilings
remain in force, cancellation is checked at declared new boundaries, and no
partial successor is published.

Observer enablement, truncation, delay, absence, or failure remains semantically
inert. Rejection, cancellation, resource exhaustion, internal failure, observer
failure, stale results, and interrupted saves cannot overwrite the promoted
0.14.2 baseline or the last successful linked generated-C output.

## Explicitly rejected neighboring behavior

This decision does not authorize:

- positional or keyword-only defaults;
- omission of any required formal;
- definition-time or call-time default evaluation or storage;
- `*args`, `**kwargs`, `*` or `**` unpacking;
- runtime binding, `TypeError`, coercion, overloads, or dynamic dispatch;
- keyword calls to `range` or static-record constructors;
- methods, callable values, indirect targets, assignment-created target aliases,
  closures, decorators, lambdas, or function pointers as Python calls;
- recursion, exceptions, unwinding, mutation, allocation, ownership transfer,
  cleanup, generators, async behavior, or a Python runtime;
- a new helper, helper version, representation, category, C IR node, renderer
  shortcut, or public policy;
- host discovery, compilation, linking, loading, execution, debugging, or a
  terminal;
- another Phase 14 mini-phase; or
- Phase 15.

Decision outcome: feasible and approved for bounded implementation. Promotion
requires a later manifest, complete vertical evidence, adversarial
fact/C-IR validation, deterministic artifacts, resource and observer audits,
failure injection, reproducible packaging, and an explicit promoted release
record. None is supplied here.
