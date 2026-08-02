# Phase 11 Bounded-Container Representation Decisions

Status: accepted before Phase 11 implementation on 2026-07-22  
Authority: Architecture Revision 3.1 and Revision 3.2 addendum  
Target: `c11-portable-fixed-v1` under `strict-source-v1`

These decisions admit deliberately bounded local container forms. They do not
add a Python runtime, heap allocation, dynamic resizing, general hashing,
container parameters or returns, arbitrary aliasing, or broad library behavior.

## Shared profile C11-00

- Capacity is fixed by a source literal and must be from 1 through 64 elements.
- Elements must have one homogeneous scalar representation: `int64_t`,
  `double`, `bool`, or borrowed immutable `const char *`.
- Nested containers and comprehensions are rejected.
- A container is created by one function-local, single-name assignment and may
  neither be rebound nor escape through a return, call, alias, or scalar use.
- Storage has automatic function lifetime. No allocation, ownership transfer,
  cleanup, retained reference, or failure channel exists.
- Element expressions are evaluated once in Python source order before the
  container declaration. Any required call staging uses existing typed C IR
  temporaries.
- The converter publishes complete shape, binding, access, and iteration facts.
  Conflicting or incomplete evidence rejects before C IR publication.

## Decision C11-01 — fixed local list

- Source form: a nonempty homogeneous list literal assigned once to a fresh
  local name.
- C form: a fixed-extent automatic array of the selected scalar element type.
- Capacity: the literal length, at most 64.
- Mutation: list element mutation, append, removal, slicing, concatenation,
  resizing, and rebinding are rejected in this Phase 11 profile.
- Aliasing: rejected. The array is never passed, returned, or copied as a Python
  list value.
- Rationale: fixed storage preserves construction, indexing, and iteration for
  programs that do not observe unsupported mutability, without a hidden heap or
  runtime object model.

## Decision C11-02 — fixed local tuple

- Source form: a nonempty homogeneous tuple literal assigned once to a fresh
  local name.
- C form: a fixed-extent `const` automatic array of the selected scalar type.
- Capacity: the literal length, at most 64.
- Immutability: structural and element mutation are rejected. No tuple alias,
  parameter, return, comparison, concatenation, or unpacking contract is
  claimed.
- Rationale: the `const` fixed array makes the admitted immutable observation
  surface explicit and readable.

## Decision C11-03 — insertion-ordered fixed dictionary

- Source form: a nonempty dictionary literal assigned once to a fresh local.
- Keys are homogeneous, distinct literal `int` or `str` values. Boolean, float,
  computed, unpacked, duplicate, and container keys are rejected.
- Values are homogeneous admitted scalar expressions.
- C form: parallel fixed-extent `const` key and value arrays in Python insertion
  order. The arrays use collision-checked project-generated identifiers.
- Lookup: only an exact compile-time literal key known to be present is admitted;
  it resolves to the corresponding value-array offset. No hashing, equality
  helper, sentinel, or runtime lookup failure exists.
- Mutation, insertion, deletion, update, aliasing, and value escape as a
  dictionary are rejected.
- Iteration yields keys in insertion order.

## Decision C11-04 — proven indexing and selected iteration

- List/tuple indexing accepts only a compile-time integer literal, including a
  unary signed literal. Negative indices are normalized against the fixed
  capacity. An out-of-range index rejects conversion.
- Dictionary indexing accepts only a compile-time literal key exactly matching
  a recorded key. A missing or dynamic key rejects conversion.
- Because admissibility proves the access, generated C has no bounds or key
  failure branch and no concealed `IndexError` or `KeyError` behavior.
- `for target in container_name` is admitted for a directly bound supported
  container. Lists and tuples yield elements in source order; dictionaries yield
  keys in insertion order.
- The loop lowers to a bounded index loop. The source target is assigned from
  the selected array once per iteration. Existing `break` and `continue`
  semantics remain structural.
- Loop `else`, target rebinding/mutation, dynamic iterable selection, and
  container mutation during iteration are rejected.

## Stable rejection policy

- `PYC3401`: empty, oversized, nested, or malformed container literal
- `PYC3402`: heterogeneous or unsupported key/element/value representation
- `PYC3403`: container rebinding, aliasing, escape, or unsupported scalar use
- `PYC3404`: index or dictionary key is not statically provable
- `PYC3405`: list/tuple index is out of range or dictionary key is absent
- `PYC3406`: container mutation, resizing, unpacking, or comprehension
- `PYC3407`: unsupported container iteration form

All failures are conversion-time diagnostics. No partial container C IR,
helper manifest, or generated C is published. Generated C remains source-only
and is never compiled or executed by PyCForge.
