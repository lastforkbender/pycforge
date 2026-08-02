# Phase 13 Static-Record Representation Decisions

Status: accepted before Phase 13 implementation on 2026-07-22  
Authority: Architecture Revision 3.1 and explicit Phase 13 approval  
Target: `c11-portable-fixed-v1` under `strict-source-v1`

Phase 13 treats one deliberately closed Python `class` spelling as a static
record declaration. It does not claim general Python class semantics. Every
accepted class, construction, field binding, type, lifetime, and use is proved
before C IR publication.

## R13-01 — closed class declaration

- A record is a top-level, undecorated `class Name:` with no bases, keywords,
  metaclass, docstring, class values, or executable class-body statement.
- The body declares 1–64 fields first, each exactly once as a value-less
  annotation `field: int`, `field: float`, or `field: bool`.
- Class names cannot shadow `int`, `float`, `bool`, or `str`; field names cannot
  be Python dunder spellings or object-protocol descriptors.
- One final `def __init__(self, ...) -> None:` is required. It is structural
  initialization syntax, not a generally callable instance method.
- `self` is the first, unannotated parameter. Each remaining required
  positional parameter corresponds one-for-one, in field declaration order,
  with exactly the same scalar annotation. Defaults, positional-only syntax,
  keyword-only parameters, variadics, and duplicate parameter/field names
  reject.
- The initializer body contains exactly the ordered direct assignments
  `self.field = parameter`, one for every field. No expression, branch, loop,
  call, return statement, read-before-write, or additional statement is
  admitted.
- Record declarations precede top-level functions in their defining module.
  Nested/local classes, nested records, async declarations, other dunder
  members, properties, static/class methods, and all general methods reject.

## R13-02 — construction and admitted observations

- Construction appears only as a direct function-local assignment
  `fresh_name = ClassName(arguments)` to a fresh, single owner binding.
- The class callee and fresh owner are proved by lexical binding identity. The
  constructor assignment has no type comment; scope directives, exception or
  pattern aliases, imports, deletion, nested definitions, context-manager
  targets, and every other rebinding form reject.
- Positional arguments match initializer arity and exact scalar types. Keyword,
  unpacked, indirect, conditional, nested, returned, or bare construction
  rejects.
- Arguments are evaluated exactly once in Python source order before any record
  field becomes observable. Lowering stages side-effecting scalar expressions
  through typed temporaries where C does not guarantee that order.
- A constructed local may be observed only by direct `fresh_name.field` reads
  in already-supported scalar expression positions. The receiver and field ID
  are statically exact; no dynamic attribute spelling or bound attribute value
  exists.
- Every read occurs after the direct construction statement. Analysis and
  lowering use cooperative cancellation safe points and publish no partial
  successor on cancellation.
- Every field is immutable after initialization. Attribute assignment,
  deletion, augmentation, rebinding, or mutation rejects.

## R13-03 — representation, ownership, and lifetime

- Each accepted record declaration maps to one deterministic collision-checked
  C structure type whose members preserve source field order and map to
  `int64_t`, `double`, or `bool`.
- Each instance uses automatic storage in the owning function activation. No
  allocation operation or allocation-failure path exists.
- The local binding is the unique owner. Copying or aliasing the record, passing
  it as an argument, returning it, placing it in a container or another record,
  capturing it, or exposing its address rejects.
- Records are never nullable. There is no null value, sentinel, reference
  count, destructor, finalizer, ownership transfer, or cleanup action.
- Python identity, object equality, truth testing, representation, hashing,
  iteration, membership, and conversion of a record value are outside the
  admitted surface.

## R13-04 — module boundary

- A record type is private to its defining SourceBundle module. Its declaration,
  construction, and field reads must all belong to that exact module identity.
- Phase 12 direct-function imports remain available, but a record class cannot
  be imported, aliased across modules, re-exported, passed through an imported
  call, or discovered by implicit namespace search.
- The closed SourceBundle remains the only source of module information. Phase
  13 adds no filesystem, path, environment, import-hook, package, installed
  distribution, or network lookup.

## R13-05 — exclusions remain hard rejections

Inheritance, multiple inheritance, `super`, MRO, metaclasses, descriptors,
properties, general methods, dynamic attributes, `__dict__`, reflection,
operator overloading, protocols, class variables, default field values,
string/object/container fields, record parameters or returns, aliases, heap
allocation, nullability, and cleanup are not approximated. An unproved record
operation rejects the conversion and publishes no partial C IR, mappings,
summary, trace, or generated C.

Generated C validation remains structural and textual. PyCForge does not
compile, link, load, or execute generated C.
