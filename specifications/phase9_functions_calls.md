# Phase 9 Functions and Calls — v0.9.0

Phase 9 extends the cumulative converter with a bounded, closed-world function-call slice. Generated C remains the final product boundary and is never compiled or executed.

## Selected source forms

- One or more top-level synchronous `def` statements; other module statements reject.
- Exact built-in-spelling annotations `int`, `float`, `bool`, and `str` on every positional parameter and function return.
- Uniquely named positional and positional-only parameters without defaults.
- Single-name local declarations and compatible reassignments outside first-definition control-flow regions.
- Direct calls through a `Name` occurrence that resolves to one eligible top-level source function binding.
- Explicit returns whose representations match the declared return on every reachable path.
- Calls in ordinary expressions, assignments, returns, expression statements, direct branch/loop conditions, supported range bounds, and supported branch/loop bodies.

## Target resolution

Resolution consumes lexical binding facts; source spelling alone is insufficient. The target binding must be a promoted top-level function, must never be rebound, and must have an eligible exact signature. Aliases, parameters used as callables, local callable values, attributes, subscriptions, lambdas, reflection, imports, and unknown names reject with a stable diagnostic.

The name `range` is recognized only for a `for` iterator when its occurrence resolves to the unshadowed implicit built-in binding. A parameter or function named `range` is never silently treated as the built-in.

## Signatures and prototypes

Each eligible function receives one binding-backed C identifier, one `CFunctionPrototype`, and one `CFunctionDefinition`. All prototypes precede all definitions, so forward calls are valid in rendered C without order-dependent inference. The C IR validator requires prototype/definition return type, parameter type, parameter binding, spelling, and arity consistency.

Representation mapping:

| Python evidence | C representation | Passing | Ownership/lifetime |
|---|---|---|---|
| exact `int` | `int64_t` | by value | activation value |
| exact `float` | `double` | by value | activation value |
| exact `bool` | `bool` | by value | activation value |
| exact `str` | `const char *` | borrowed pointer | caller-managed and valid across the call |

This is a representation contract, not a claim that arbitrary Python values fit the bounded C representation. Integer arithmetic remains subject to the documented signed-64 domain precondition.

## Argument order and single evaluation

Python evaluates positional arguments from left to right. C does not generally specify function-argument evaluation order. PyCForge therefore lowers every supported call as:

1. lower argument 0 and its nested prerequisites;
2. store it once in a binding-backed `pycf_arg_...` temporary;
3. repeat in ascending argument order;
4. emit a structured `CCallExpr` whose arguments are only those pure temporary references;
5. materialize the result once in a `pycf_call_...` temporary when the value is consumed.

Nested calls follow the same recursive ordering. Temporaries use a deterministic collision-checked allocator and synthetic provenance. An expression that would require eager evaluation across a Python short-circuit boundary rejects until a conditional-temporary rule exists; later chained-comparison operands are currently limited to effect-free names and literals.

## Returns and fallthrough

Return-path facts list all explicit return nodes, expected and actual categories, fallthrough reachability, and cleanup policy. Every explicit return must match the signature. A path that could reach implicit Python `None` rejects with `PYC2931`; it is never emitted as accidental C fallthrough. Bare returns and incompatible returns reject. Phase 9 requires no call cleanup because supported scalars are by value and strings are borrowed.

## Local declarations

Python function scope is predeclared before load resolution. The local-declaration analysis rejects:

- use before first binding (`PYC2940`);
- a binding assigned incompatible C representations (`PYC2943`);
- first definition inside selected branch/loop control (`PYC2870`);
- a loop-local target used or stored outside its selected C lifetime (`PYC2941`);
- reuse of a parameter, local, or earlier loop target as a range target (`PYC2944`);
- mutation of the active range target, which would alter C loop progression but not Python range iteration (`PYC2847`).

Source and generated identifiers are separated by stable binding IDs. The allocator escapes C keywords, standard header/type/macro names, all ISO C11 identifiers reserved for external linkage (including hosted `main`), leading underscores, the `pycf_` namespace, normalization collisions, and linkage collisions.

## Recursion and nested functions

The call graph is analyzed with a deterministic, bounded strongly-connected-component pass. Direct and mutual recursion reject with `PYC2920` in Phase 9. Nested functions and closures reject with `PYC2915`. These are explicit subset boundaries, not inference failures.

## Facts, plans, schemas, and mappings

Phase 9 publishes complete immutable tables for function signatures, call targets, return paths, local declarations, and the call graph. The call RulePlan exposes annotation node evidence, argument categories, evaluation order, ownership boundaries, target identity, and closed semantic obligations.

API, JSON CLI, and workspace results also expose an immutable source-free conversion summary containing each signature’s annotation spelling/node evidence, C representation, passing/ownership/lifetime boundary, generated name, and each call’s target, categories, source order, annotation evidence, ownership boundary, and single-evaluation state.

- conversion plan: `conversion-plan/0.9`
- C IR: `c-ir/0.9`
- generated artifact: `generated-c/0.9`
- artifact envelope: `0.2`
- rule set: `phase9-functions-calls-v0.9`
- renderer: `c-renderer-v0.9`

Mappings are derived from C IR provenance and cover definitions, prototypes, parameters, returns, call occurrences, callee references, arguments, argument/result temporaries, control-flow regions, and synthetic range/comparison structure.

## Explicit exclusions

Defaults, keyword-only parameters, keyword calls, variadics, unpacking, target aliases, first-class functions, function pointers as a Python-call model, decorators, generators, imports, reflection, `eval`, `exec`, async functions, helpers, runtime support, containers, exceptions, classes, compilation, linking, and execution remain unsupported.
