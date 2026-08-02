# Phase 14C Direct Keyword Calls Decision

Status: feasibility accepted for bounded implementation on 2026-07-22. No
implementation or promotion is claimed by this decision.

Authority: Architecture Revision 3.1, Revision 3.2 addendum, the authenticated
and promoted PyCForge 0.14.1 predecessor, and the explicit user direction
“Continue to Phase 14C”.

## Decision D14C-01 — admit one exact direct-call profile

Phase 14C may accept a `Call` only when the sealed cumulative resolver already
identifies its `Name` target as an eligible synchronous top-level source
function in the supplied SourceBundle. This includes existing direct
same-module resolution and existing explicit cross-module function-import
resolution, including an import spelling alias whose binding still points
directly to that source function. Assignment-created callable aliases,
attributes, subscriptions, parameters used as callables, first-class function
values, and every dynamic target remain unsupported.

The selected call has zero or more ordinary leading positional arguments and
one or more explicit keyword entries whose normalized `keyword.arg` is a
nonempty source name. A `Starred` positional argument or a keyword entry with a
null name is unpacking and remains outside the profile.

The selected callee retains its exact existing declaration profile: uniquely
named, exactly annotated positional-only and positional-or-keyword required
parameters, with no defaults, keyword-only parameters, `*args`, or `**kwargs`.
Phase 14C changes no function declaration form.

## Decision D14C-02 — bind completely and statically

Binding is a deterministic compile-time permutation over the existing formal
signature:

1. ordinary positional actuals bind formal ordinals from zero upward;
2. an explicit keyword may bind only a still-unbound positional-or-keyword
   formal with the same exact Python source name;
3. a positional-only formal is never addressable by keyword;
4. every formal must receive exactly one actual; and
5. each actual category and C representation must exactly match its bound
   formal.

Unknown names, a name aimed at a positional-only formal, absent required
formals, excess positionals, a formal bound twice, or a category mismatch are
compile-time rejections. PyCForge does not synthesize Python's runtime call
binder or `TypeError` behavior.

`PYC2910` remains the primary unsupported-profile boundary for `*`/`**`
unpacking, a null keyword name, or another excluded keyword shape. `PYC2912`
owns exact static name-binding failures for an otherwise eligible direct source
target: an unknown keyword name, a positional-only name used by keyword, a
positional/keyword collision, or a duplicate keyword. Existing `PYC2904`
continues to own missing or excess arity, `PYC2905` representation mismatch,
`PYC2911` ineligible declarations, `PYC2901`/`PYC2902` target eligibility, and
`PYC2920` recursion. No broader new diagnostic family is authorized.

## Decision D14C-03 — preserve two exact orders

Python source evaluation order and C formal order are distinct immutable
vectors.

The source evaluation vector is all ordinary positional value nodes from left
to right followed by all explicit keyword value nodes in their normalized
source order. Each value's complete existing prerequisite sequence is emitted,
then that value is materialized exactly once in a typed automatic argument
temporary. A nested Phase 14B conditional region remains within its own sealed
guards; Phase 14C cannot hoist a guarded prerequisite.

Only after every actual has been staged may lowering construct the formal
vector. It contains one pure temporary reference per formal ordinal. The
`CCallExpr` receives that formal vector, not the source vector. Consequently a
call such as `f(c=first(), a=second(), b=third())` evaluates `first`, `second`,
and `third` once in that source order, then calls C `f(a_tmp, b_tmp, c_tmp)`.

The direct target name has no admitted runtime target-evaluation effect. No
final C argument expression may contain an unstaged source operation, helper
call, nested source call, or side effect whose order C could choose.

## Decision D14C-04 — add one complete fact and one rule

At most one immutable `fact-table/0.14.2` family may be added:
`keyword-call-binding-facts`. It is additive and complete over every
keyword-bearing direct-source-function candidate whose existing declaration
signature reaches the static binder. Its domain includes candidates rejected by
the binder; it must not silently reinterpret the predecessor meaning of an
existing call-target field.

Each candidate record anchors the call, callee, target function and binding;
ordered positional and keyword source entries; exact keyword spellings; source
evaluation ordinals; formal ordinals and names; actual-to-formal association
vectors and exact coverage state; categories; lowering shape; support or
rejection state; and provenance. Caller/callee module identity, C types,
ownership, lifetime, conditional-region evidence, target contract, and
cancellation remain authoritative in their existing predecessor facts and
RulePlan evidence rather than being duplicated into this record.

An unsupported candidate record is complete negative evidence: it has
`supported: false`, the exact owning diagnostic, a nonempty reason and rejection
node, and no RulePlan or C IR. An accepted rule-selected call has exactly one
supported record, and every selected
`phase14.keyword_call.exact_binding@0.14.2` RulePlan references exactly one such
supported record. Candidate coverage and supported RulePlan coverage are both
exact; recording negative evidence does not widen source acceptance.

The exact lowering-shape value is
`source-order-temporaries-formal-order-references-v1`. Independent validation reconstructs
the binding directly from Python IR, signature facts, lexical/module target
facts, value categories, and the sealed call graph. Lowering consumes the
validated two-order fact and may neither resolve names nor repair a binding.

At most one RulePlan family may be added:
`phase14.keyword_call.exact_binding@0.14.2`. It owns no helper. Existing rules
continue to own every nested operation and the target function's semantics.

## Decision D14C-05 — preserve policies, compatibility, and boundaries

No new public call-binding policy field is justified. The active rule set,
fact schema, conversion plan, C IR and generated-C envelopes, summary, trace,
and renderer may advance to 0.14.2. Advancing the C IR and renderer identities
does not authorize a new node, enum, type, storage class, syntax form, or
semantic inference.

`strict-source-v1`, SourceBundle 0.2, Python IR 0.4, result serialization 0.5,
the Phase 14A numeric policy, the Phase 14B conditional fact contract, and all
helper, container, module, record, target, workspace, ownership, and lifetime
policies remain unchanged. Explicit historical 0.14.1 and earlier
configuration requests retain their exact semantic and serialization shapes.
Under the active rules, a source containing no selected keyword call must
retain predecessor generated-C bytes and output fingerprints.

## Explicitly rejected neighboring behavior

This decision does not authorize:

- default values or omission of required parameters;
- keyword-only parameters or any function declaration expansion;
- `*args`, `**kwargs`, `*` or `**` call unpacking;
- keyword calls to `range` or static-record constructors;
- target aliases created as Python values, indirect or dynamic callables,
  methods, closures, decorators, lambdas, or function pointers as Python calls;
- recursion, exceptions, runtime binding failures, mutation, allocation,
  ownership transfer, cleanup, or a Python runtime;
- a new helper, helper version, C IR node, renderer shortcut, compilation,
  linking, loading, or execution;
- destructuring, comprehensions, another Phase 14 mini-phase, Phase 14D, or
  Phase 15.

Decision outcome: feasible and approved for bounded implementation. Promotion
requires a later manifest, complete vertical evidence, adversarial validation,
deterministic artifacts, packaging, and an explicit promoted release record;
none is supplied here.
