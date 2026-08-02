# Bounded Static Records — Phase 13

Status: active unchanged Phase 13 contract in PyCForge 0.14.3
Rule set: `phase13-static-records-v0.13`  
Record policy: `phase13-immutable-automatic-records-v0.13`

Phase 13 admits one class-shaped declaration only when the analyzer can prove
that it is an immutable, uniquely owned, automatic-storage record. This is a
closed source profile, not an approximation of Python classes or objects.

## Declaration grammar

An accepted record is a synchronous, undecorated `ClassDef` directly in one
SourceBundle module. It has no bases, keywords, metaclass, class value,
docstring, or executable class-body statement. Record declarations precede all
top-level functions in their module.

The class name cannot shadow `int`, `float`, `bool`, or `str`, because those
names participate in the closed annotation grammar. Field names cannot be
Python dunder spellings such as `__class__`, `__dict__`, or `__weakref__`;
object-protocol descriptors are never reinterpreted as ordinary data members.

The class body is exactly:

- 1–64 simple, distinct, value-less `AnnAssign` fields in declaration order;
- each field annotated by the exact built-in name `int`, `float`, or `bool`;
- one final, undecorated `def __init__(...) -> None`; and
- no other method or member.

`__init__` has one unannotated parameter spelled `self`, then one required
positional parameter per field. Those parameters have the same names, order,
and exact annotations as the fields. Positional-only parameters, defaults,
keyword-only parameters, variadics, type comments, and decorators reject. Its
body is exactly the ordered direct copies `self.field = field`, one for every
field, with no additional statement or expression.

The initializer is structural declaration evidence. It is not emitted as a C
function and cannot be called as a bound or unbound Python method.

## Construction and observation

Construction is valid only in a directly defined synchronous function in the
record's own module, in this form:

```python
fresh_local = RecordName(arg0, arg1)
```

The target is one fresh local name and the callee is the statically resolved
record declaration. Arguments are positional, have exact field
representations, and match the complete field arity. Conditional, nested,
bare, returned, indirect, keyword, unpacked, or cross-module construction
rejects.

Arguments are evaluated left to right and exactly once before initialization
is observable. The unique local may subsequently appear only as the direct
receiver of a statically resolved field read, for example `fresh_local.field`,
in an otherwise supported scalar expression. The access fact identifies the
exact owner binding, record, field binding, scalar category, function, module,
and source document.

The local cannot be assigned again, copied to another name, passed to a
function, returned, captured, placed in a container or record, compared by
identity or object equality, tested for truth, converted, iterated, hashed, or
represented. Field assignment, augmented assignment, deletion, dynamic
attribute access, and chained attribute access reject.

The constructor assignment itself cannot carry a type comment. Its target must
be the declaration site of one ordinary function-local lexical binding. Scope
directives, exception aliases, pattern captures, context-manager targets,
imports, deletion, nested definitions, or any other rebinding form reject. A
field read must occur in a later owner-body statement than construction; no
read-before-construction proof is inferred from Python's lexical name binding.

## C representation

Every record definition produces one validated `CRecordDefinition` under
`c-ir/0.13`. The renderer emits a deterministic named `typedef struct`; members
retain source declaration order and map as follows:

| Python field | C member type |
|---|---|
| `int` | `int64_t` |
| `float` | `double` |
| `bool` | `bool` |

Each instance produces one fully initialized `const` aggregate in automatic
function storage. Its initializer contains exactly one compatible scalar value
per member in declaration order. When needed, typed scalar temporaries preserve
Python's left-to-right, once-only argument evaluation before the aggregate is
created. Direct field reads render with C `.` member access.

The representation has one lexical owner and lasts for the enclosing function
activation. It is non-null and non-addressable through the source profile.
There is no heap allocation, allocation failure, ownership transfer, copying,
reference count, finalizer, destructor, cleanup edge, hidden header, vtable,
class object, method table, or runtime type test. Record RulePlans request no
helper.

Record definitions precede helper and source prototypes; prototypes precede
function definitions. The output remains one portable ISO C11 translation
unit.

## Module boundary

Record semantics are private to the exact defining logical module. Phase 12
direct-function imports remain supported, but record names are not importable,
re-exportable, or discoverable. A record cannot be constructed or carried
across a module boundary. Resolution still consults only the explicit
SourceBundle; no host import or source discovery channel is opened.

## Stable rejection families

| Code | Boundary |
|---|---|
| `PYC3601` | record declaration placement or class shape |
| `PYC3602` | field count, spelling, value, uniqueness, or scalar type |
| `PYC3603` | exact structural `__init__` signature or ordered assignments |
| `PYC3604` | unsupported class member or ordinary method |
| `PYC3605` | construction position, target, arity, or argument category |
| `PYC3606` | alias, rebind, copy, escape, parameter/return, or object-value use |
| `PYC3607` | mutation, unknown field, or dynamic/chained attribute access |
| `PYC3608` | record use outside its exact defining module/document |
| `PYC3610` | importing a record class through the module import surface |

One deterministic root cause rejects the whole conversion. Rejection,
cancellation, or internal validation failure publishes no partial C IR,
generated C, mappings, conversion summary, or decision trace.

Record analysis and lowering check cooperative cancellation across bounded
class, field, constructor, argument, occurrence, and C IR loops. Serialized
plan validation independently anchors record evidence to lexical bindings,
module/source/function identities, exact argument categories and order, access
context and order, and complete occurrence coverage.

## Deliberate non-goals

Phase 13 does not support general methods, inheritance, `super`, MRO,
metaclasses, descriptors, properties, static/class methods, operator overloads,
protocols, reflection, `__dict__`, dynamic attributes, class variables,
defaulted fields, strings, containers or nested records as fields, nullable
records, record parameters/returns, or cross-module records.

Generated C is checked structurally and textually only. PyCForge does not
compile, link, load, execute, debug, benchmark, or behaviorally validate it.

Phase 14B does not widen this record profile. An already-proved direct scalar
field read may participate in an eligible conditional operand, and its
evaluation remains inside that operand's guard. The region cannot admit a new
record occurrence, construction site, alias, mutation, escape, comparison, or
cross-module use. Record facts, policy, RulePlans, C IR node kinds, ownership,
and helper-free contract remain exactly Phase 13.

Phase 14C does not widen record construction. Record constructors are a
separate call family and remain positional-only under the Phase 13 profile;
keyword constructor arguments still reject with `PYC3605`. A proved scalar
field read may be staged as an actual value in an eligible source-function
keyword call, but the binding rule cannot admit a new record occurrence,
transfer a record value, or change record ownership, lifetime, facts, plans,
policy, C IR, or helper-free behavior.

Phase 14D likewise does not widen the structural record `__init__` or record
constructor profile. Required keyword-only parameters are admitted only on
otherwise eligible ordinary top-level source functions; record structural
initializers retain their exact positional shape, and record-constructor
keywords still reject with `PYC3605`. A proved scalar field read may be staged
as an explicit actual bound to a required keyword-only source-function formal,
but no record value may become a parameter, argument, alias, or transferred
owner. Record facts, RulePlans, C IR, ownership, lifetime, and helper-free
behavior remain unchanged.
