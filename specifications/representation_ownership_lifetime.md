# Representation, Ownership, and Lifetime — v0.14.3

| Value category | C type | Passing | Ownership | Lifetime/cleanup |
|---|---|---|---|---|
| integer-like | `int64_t` | by value | not applicable | activation; no cleanup |
| floating-like | `double` | by value | not applicable | activation; no cleanup |
| boolean-like | `bool` | by value | not applicable | activation; no cleanup |
| string-like | `const char *` | borrowed pointer | borrowed | caller-managed across call; no callee cleanup |
| callable-like | function signature only | direct call only | not applicable | no first-class value |
| fixed-list-like | fixed automatic scalar array | local observation only | automatic owner | function activation; no cleanup |
| fixed-tuple-like | read-only fixed automatic scalar array | local observation only | automatic owner | function activation; no cleanup |
| fixed-dictionary-like | parallel read-only fixed automatic arrays | local observation only | automatic owner | function activation; no cleanup |
| static-record-like | named `const` automatic C aggregate | direct field reads only | unique lexical owner | function activation; no cleanup |

Integer representation is bounded to the declared signed-64 domain. Unsupported overflow/failure behavior is not silently represented as arbitrary-precision Python behavior.

UTF-8 source string literals have static C literal storage. String parameters and returns are borrowed; the caller is responsible for pointer validity for the documented call lifetime. Allocation, transfer, duplication, mutation, nullability, and cleanup helpers remain outside Phase 9.

Every function-signature fact records parameter and return C type, passing, ownership, and lifetime. Every call-target fact records the ordered parameter boundary. Every supported call RulePlan closes the representation, evaluation-order, single-evaluation, ownership, and lifetime obligations. Unknown or conflicting evidence rejects before C IR publication.

Phase 10 helper definitions carry their own immutable ownership, lifetime, and
failure contracts. Phase 14A activates the floor-division and modulo helpers:
they pass and return `int64_t` scalars by value, allocate nothing, retain
nothing, and require no cleanup. Direct safe-literal proof closes their failure
preconditions before lowering. This does not alter the borrowed string boundary
or authorize an allocation helper.

Phase 11 containers never cross a function boundary. They cannot be parameters,
returns, aliases, captured values, or call arguments. Their scalar elements may
use existing by-value or borrowed-literal representations, but the container
retains nothing and owns no heap resource. Dictionary keys and values are
materialized in source pair order before their read-only arrays. The full
capacity/index/key proof means there is no allocation, bounds, hashing, lookup,
or cleanup failure path and no selected helper.

Phase 12 logical modules, imports, and imported aliases have no runtime C value
representation, ownership, storage, allocation, lifetime, or cleanup. An
imported-function binding is a compile-time reference to the target function's
existing signature and external C binding. Calls cross the same by-value or
borrowed scalar boundary already recorded by Phase 9 facts; fixed containers
remain function-local and cannot cross modules through parameters or returns.

The module dependency and initialization plans exist only for deterministic
analysis and declaration ordering. They emit no module object, pointer,
initializer function, global variable, cache, guard, retained alias, or failure
state. Helpers retain their own isolated static linkage and existing ownership
contracts.

Phase 13 record fields are inline `int64_t`, `double`, or `bool` members in a
named C structure. A record instance is fully initialized once as an
object-level `const` automatic aggregate. Its unique local owner cannot be
copied, aliased, rebound, passed, returned, captured, stored, or have its
address exposed. Only exact direct field reads produce ordinary scalar values.

The record is non-null by construction and has no allocation operation,
allocation failure, heap identity, ownership transfer, reference count,
destructor, finalizer, or cleanup edge. The structural `__init__` is declaration
evidence and does not exist as a runtime method. Records never cross a source
function or module boundary and select no helper.

Phase 14A numeric operand and result temporaries are ordinary `int64_t`
automatic scalar values owned by the enclosing function activation. They cannot
escape, alias a resource, require cleanup, or introduce a nullable/failure
state. The registered helper observes only by-value operands and returns a
by-value scalar.

Phase 14B introduces no value category. Its Boolean accumulator is one ordinary
initialized automatic `bool`. Chained-comparison operand temporaries retain the
single exact existing `int64_t`, `double`, or `bool` category proved for the
chain; later storage is defensively type-initialized before any C read, while
the source operand expression and all prerequisites remain inside its guard.
Each reached middle value is assigned once and reused by the adjacent
comparisons.

Region temporaries belong to the enclosing function activation, never escape,
and require no alias, pointer, heap, nullability, reference count, destructor,
or cleanup protocol. A region owns no helper and does not change ownership of a
nested source call or Phase 14A helper operation. Closing a guard skips source
evaluation entirely and creates no new runtime failure or exception channel.

Phase 14C introduces no value category or passing convention. Every keyword-
call actual is materialized once into an ordinary typed automatic temporary at
its Python source position. The final C call observes only pure references to
those temporaries in formal ordinal order. By-value scalars remain by value;
borrowed strings retain the exact existing caller-managed lifetime. Permuting
references does not transfer, extend, duplicate, or reinterpret ownership.

The binding RulePlan owns no helper, allocation, retained runtime name, dynamic
lookup table, failure object, exception channel, destructor, or cleanup edge.
Argument temporaries belong to the enclosing function activation. Nested
operations and Phase 14B guarded prerequisites retain their own ownership and
lifetime contracts; a keyword-call binding cannot hoist or adopt them.

Phase 14D likewise introduces no value category, C type, passing convention,
ownership state, lifetime region, allocation, or cleanup edge. A required
keyword-only formal uses the same existing representation as an equally
annotated positional formal; its keyword-only mode is a static source-call
obligation, not a runtime value or C type property.

Every explicit actual is materialized once into an ordinary typed automatic
temporary at its Python source position. The final C call observes only pure
references in full formal order. By-value scalars and borrowed strings retain
their existing parameter boundaries. Reordering pure references after source
evaluation cannot transfer, retain, duplicate, extend, or reinterpret
ownership.

Existing FunctionDef RulePlans prove the required-keyword-only declaration and
C-interface mode-erasure containment even for uncalled functions. The Phase 14D
call RulePlan owns no helper, default storage, omitted-value sentinel, runtime
name table, failure object, exception channel, destructor, or cleanup edge.
Nested operations retain their predecessor-owned representation and lifetime
contracts.
