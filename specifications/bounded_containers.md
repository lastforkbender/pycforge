# Bounded Containers — Phase 11 StableInternal Contract

Policy identity: `phase11-fixed-local-containers-v0.11`  
Rule set: `phase11-bounded-containers-v0.11`  
Target: `c11-portable-fixed-v1` under `strict-source-v1`

## Shared admission contract

A container literal is admitted only when it is assigned once to one fresh
name directly in a function body. Capacity is the literal length and must be
from 1 through 64. Elements or values have one homogeneous scalar category:
`integer-like`, `floating-like`, `boolean-like`, or `string-like`. Nested
containers, comprehensions, unpacking, aliasing, escape, rebinding, parameters,
returns, comparison, slicing, and all mutation or resizing are rejected.

Element expressions are evaluated once in Python source order. Existing call
lowering stages arguments and results before an element temporary; array
initializers therefore contain only already materialized scalar references.
Storage is automatic for the enclosing function. There is no heap allocation,
retained reference, ownership transfer, cleanup action, allocation failure, or
runtime container failure channel.

The planner publishes complete `container-shape-facts`,
`container-binding-facts`, `container-access-facts`, and
`container-iteration-facts`. Each supported RulePlan cites those facts and
closes capacity, representation, order, alias, lifetime, and failure
obligations. Conflicting or incomplete evidence rejects before C IR.

## Representations

| Python form | Required shape | C representation | Observable order |
|---|---|---|---|
| list literal | homogeneous scalar elements | fixed-extent automatic array | literal/source order |
| tuple literal | homogeneous scalar elements | fixed-extent read-only automatic array | literal/source order |
| dictionary literal | distinct homogeneous literal `int` or `str` keys; homogeneous scalar values | parallel fixed-extent read-only key/value arrays | insertion order |

Dictionary Boolean, float, computed, unpacked, duplicate, and container keys
are rejected. Because keys are literal, distinct, and homogeneous, Python key
equality is resolved during analysis; no hash function, equality helper,
sentinel, collision policy, or runtime lookup is present. Dictionary iteration
yields keys in insertion order.

Read-only pointer arrays render with the correct declarator qualification, for
example `const char * const values[2]`. Generated component names such as
`mapping_keys` and `mapping_values` pass the same collision policy as other C
names. List storage is writable at the C type level, but no admitted RulePlan
can emit a write; Python list mutation is outside this fixed observational
profile.

## Indexing and iteration

List and tuple indexing accepts only a compile-time signed integer literal.
Negative indices are normalized as `capacity + index`; conversion rejects any
result outside `[0, capacity)`. Boolean indices, dynamic expressions, and
slices are rejected.

Dictionary indexing accepts only a compile-time literal key of the recorded key
category. The key must be present. Analysis resolves the exact insertion-order
offset, so generated C is one array subscript with no `IndexError`, `KeyError`,
bounds branch, or hidden approximation.

`for target in container_name` accepts a direct fixed binding, a single fresh
name target, and no loop `else`. It lowers to an `int64_t` index from zero to the
fixed capacity. Lists and tuples select the element array; dictionaries select
the key array. The source target is initialized once per iteration. Existing
structured `break` and `continue` remain valid. Target mutation, rebinding, or
escape uses the cumulative loop-lifetime diagnostics.

## Helpers, ownership, and failure

All Phase 11 container RulePlans have an empty helper requirement set. The
Phase 10 registry remains available and fingerprint-identical, but no container
conversion selects it. Successful output has an empty helper manifest. A
container rejection stops before helper resolution and publishes no generated
C or partial helper output.

The stable primary codes are:

| Code | Boundary |
|---|---|
| `PYC3401` | empty, oversized, nested, or malformed literal |
| `PYC3402` | heterogeneous or unsupported element/key/value representation |
| `PYC3403` | rebinding, aliasing, escape, or scalar use |
| `PYC3404` | dynamic or representation-mismatched index/key |
| `PYC3405` | out-of-range index or absent key |
| `PYC3406` | mutation, resizing, unpacking, method use, or comprehension |
| `PYC3407` | unsupported container iteration form |

PyCForge validates generated C structurally and textually only. It never
compiles or executes the result.
