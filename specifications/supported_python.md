# Supported Python — PyCForge 0.14.3

## Grammar and source contract

The frontend parses from 1 through 64 explicitly supplied decoded
UTF-8-compatible documents with the declared Python 3.11 grammar. It never
imports, evaluates, executes, or discovers source. Each document has one exact
logical module ID and one unique logical source name under `source-bundle/0.2`.

## Cumulative scalar, function, control, and container subset

- Module with optional approved absolute `from` imports, then any accepted
  module-local record declarations, then one or more top-level synchronous
  function definitions.
- `from exact.module.id import direct_function` with optional aliases and
  multiple ordered names, resolving only inside the explicit SourceBundle.
- Exact `int`, `float`, `bool`, or `str` annotations on every admitted
  source-function positional-only, positional-or-keyword, or required
  keyword-only parameter and return.
- No positional defaults, keyword-only defaults, `*args`, or `**kwargs`.
- Simple name loads; single-name local declarations and
  representation-compatible scalar assignments.
- Integer, finite floating, Boolean, and UTF-8 string literals without embedded
  NUL.
- Selected numeric `+`, `-`, `*`, and floating `/`; Phase 14A bounded integer
  `//` and `%`; unary `+`, unary `-`, and representation-supported `not`.
- Numeric/Boolean `==`, `!=`, `<`, `<=`, `>`, `>=`; selected chained
  comparisons with once-only operands and Phase 14B guarded prerequisites.
- Boolean-represented `and` and `or` with C short-circuit structure and Phase
  14B guarded prerequisites.
- `if`/`elif`/`else`, `while` without `else`, and `for` over unshadowed
  `range(stop)`, `range(start, stop)`, and
  `range(start, stop, nonzero-literal-step)`.
- `break` and `continue` inside supported loops.
- Direct same-module or explicitly imported calls to eligible source-defined
  functions, with either exact positional arity or the Phase 14C leading-
  positional-plus-explicit-keyword profile, extended by Phase 14D to exact
  explicit coverage of required keyword-only formals, with exact representation
  match.
- Explicit compatible returns from every reachable source-function path.
- Nonempty homogeneous list and tuple literals of at most 64 scalar elements,
  assigned once to a fresh direct function-local name.
- Nonempty dictionaries of at most 64 entries with distinct homogeneous
  literal `int` or `str` keys and homogeneous scalar values.
- Compile-time proved list/tuple indices, compile-time present dictionary keys,
  and bounded direct iteration over fixed container names.

## Phase 13 record subset

An accepted record is an undecorated, base-free top-level class in its defining
module, before all functions. Its body contains 1–64 distinct value-less
fields, each annotated exactly `int`, `float`, or `bool`, followed by exactly
one `__init__` and no other member.

The initializer is an unannotated `self`, followed by one required positional
parameter per field with the same name, order, and exact annotation, and
returns `None`. Its body is exactly one ordered `self.field = field` assignment
per field. It is structural initialization evidence, not a general method.

Construction is one direct assignment `fresh_local = RecordName(args...)`
inside a directly defined function in the same module. Arguments are positional
and exactly match all fields. They evaluate left to right and once. The fresh
record binding is immutable and may be observed only through statically proved
direct field reads such as `fresh_local.field`.

Records cannot be methods' receivers, aliases, copies, parameters, returns,
call arguments, container elements, captured values, truth values, identity or
equality operands, or cross-module values. Fields cannot be assigned, deleted,
or accessed dynamically after construction. See
`specifications/static_records.md`.

## Phase 14A bounded integer floor arithmetic

Integer `left // right` and `left % right` are supported only when `left` is an
otherwise supported exact integer-like scalar expression and `right` is a
direct signed integer literal. After Python AST normalization, the divisor must
be `Constant(n)`, `+Constant(n)`, or `-Constant(n)` and have mathematical value
in `[-9223372036854775807, -2]` or
`[1, 9223372036854775807]`.

The profile does not constant-fold the divisor. It rejects zero, negative one,
`INT64_MIN`, Boolean, floating, dynamic, called, named, indexed, attributed,
calculated, nested-sign, and out-of-range divisors. The minimum signed divisor
is not reconstructed through unsigned C or a special IR form.

Each occurrence selects one exact frozen helper: `//` selects
`pycf.i64.floor_div@1.0.0` and `%` selects
`pycf.i64.floor_mod@1.0.0`. Operands and result are staged through signed-64
temporaries, preserving left-to-right, once-only evaluation. Static divisor
proof excludes division by zero and `INT64_MIN / -1`, so no runtime failure or
exception channel is required. The result matches Python floor quotient and
divisor-sign remainder within the declared signed-64 domain.

## Phase 14B conditional temporary regions

Phase 14B removes only the unsafe eager-placement boundary for an expression
already inside the cumulative scalar subset. In a Boolean-represented `and` or
`or` with at least two exact Boolean operands, the first operand is evaluated
unconditionally; every later operand and all its prerequisite statements run
only while the accumulated result keeps that Python short-circuit gate open.
`And` uses a true gate and `Or` a false gate.

In a chained comparison with at least two operators, all operands must share
one exact supported `int`, `float`, or `bool` representation. The first two
operands and first comparison are unconditional. Each later operand—including
a pure expression that still requires delayed materialization—is evaluated
once only after the preceding comparison succeeds. The middle value is reused
for its adjacent comparisons.

Eligible operands may compose existing direct positional source-function
calls, their supported arguments, supported scalar arithmetic and unary forms,
simple comparisons, proved container or record scalar reads, and promoted
Phase 14A floor arithmetic. Nested conditional regions are admitted only when
each child has its own complete fact and RulePlan, so the child's entire
prerequisite sequence stays within the parent guard. Phase 14B adds no call
shape, representation, helper, allocation, cleanup, exception, or runtime
failure channel.

## Phase 14C direct exact keyword calls

An eligible direct source-function call may contain zero or more leading
ordinary positional values and one or more explicit named keyword values. The
target must already resolve to an eligible same-module or explicit SourceBundle
function binding, and its declaration remains limited to required positional-
only and positional-or-keyword parameters with exact annotations and no
defaults, keyword-only parameters, or variadics.

Positional values bind by ordinal. Each keyword must name one still-unbound
positional-or-keyword formal, every formal must be bound exactly once, and each
actual category must exactly match its formal. All actual values and their
prerequisites stage left to right and once in source order; only pure temporary
references are then arranged in formal order for the C call. Unknown names,
positional-only names used as keywords, collisions, and duplicates reject with
`PYC2912`. `*`/`**`, null keyword names, unpacking, and other excluded keyword
shapes reject with `PYC2910`.

The profile does not admit `range` keywords, record-constructor keywords,
methods, callable aliases or values, indirect/dynamic targets, recursion,
defaults, keyword-only declarations, variadics, runtime lookup, or Python
`TypeError` behavior.

## Phase 14D exact required keyword-only calls

An otherwise eligible top-level synchronous source function may contain one or
more exactly annotated required keyword-only parameters. Existing required
positional-only and positional-or-keyword parameters may precede them. Formal
order is `posonlyargs`, `args`, then `kwonlyargs`; every corresponding
`kw_defaults` entry is null. Positional defaults, keyword-only defaults,
`*args`, and `**kwargs` remain unsupported.

Ordinary positional actuals bind only positional-capable formals. Explicit named
actuals may bind one unbound positional-or-keyword or required keyword-only
formal with the same exact source name. Positional-only formals remain
keyword-ineligible, keyword-only formals remain positional-ineligible, and
every required formal must be covered exactly once with an exact category and
representation match.

Every explicit actual and its predecessor-owned prerequisites stage once in
Python source order. Only pure temporary references are then assembled in full
formal order for the existing C call. The C prototype and definition contain
ordinary existing parameters in that same formal order; the erased C
keyword-only mode is contained by static bundle-wide binding proof and explicit
FunctionDef RulePlan evidence, including for an uncalled admitted function.

The active call-keyed `keyword-only-call-binding-facts` table is
`fact-table/0.14.3`; each supported call selects
`phase14.keyword_only_call.exact_binding@0.14.3`. Defaults, omission,
variadics, unpacking, runtime binding or `TypeError`, `range` and record
constructor keywords, methods, indirect targets, and recursion remain rejected.

## Module semantics

Every module namespace is isolated. Imported aliases are immutable direct
function bindings, not first-class values or new C functions. Record classes
are module-local semantic declarations and cannot be imported or re-exported.
Imports form an acyclic graph and cause only compile-time namespace
construction. All supplied documents belong to one conversion unit and one
generated C translation unit. No module initialization code or global import
state is emitted.

## Representation and evaluation

Annotations remain conversion evidence under
`annotation-policy/strict-builtins-v1`. Only direct `Name` nodes spelled `int`,
`float`, `bool`, or `str` qualify for source functions; record fields accept
only the first three.

`int` maps to signed `int64_t` within the declared domain, `float` to `double`,
`bool` to `bool`, and `str` to borrowed immutable `const char *`. Record
definitions map to named C structures and each record owner to a fully
initialized `const` automatic aggregate. Function calls and record construction
arguments preserve left-to-right once-only evaluation. Phase 14C keyword-call
actuals stage in source order before pure references are permuted into formal
order. Phase 14D preserves the same staging while extending the formal vector
to required keyword-only parameters. `PYC2950` and `PYC2951`
remain the primary placement diagnostics when a conditional expression cannot
satisfy the exact Phase 14B proof; explicit historical Phase 14A requests retain
their original rejection boundary.

## Default unsupported boundary

Anything not listed is unsupported by default. This includes plain, relative,
star, late, local, conditional, and dynamic imports; module objects,
attributes, re-export, package behavior, implicit module discovery, executable
module initialization, general globals, target aliases, dynamic callables,
recursion, nested functions, closures, decorators, generators,
comprehensions, nested or heterogeneous containers, dynamic subscripting,
slicing, container aliasing or mutation, general classes or methods,
inheritance, MRO, metaclasses, descriptors, properties, class variables,
dynamic attributes, reflection, record mutation/alias/escape/cross-module use,
exceptions, pattern matching, dynamic or floating floor arithmetic, `divmod`,
power and bit operators, async syntax, `eval`, `exec`, a Python runtime,
compilation, linking, loading, and execution.

No other Phase 14 construct family is opened by Phase 14D. In particular,
defaults, omitted required formals, variadics, unpacking,
assignment expressions, exceptions, recursion, dynamic calls, mutation, and
general objects remain outside conversion territory. Rejection publishes
diagnostics and no generated C; no unsupported form is silently approximated.
