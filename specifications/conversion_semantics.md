# Conversion Semantics — `strict-source-v1`

The policy supports only forms whose declared representation, evaluation order, control flow, ownership, lifetime, and failure obligations close under the selected bounded contract. Unsupported or unknown behavior rejects; the empty approximation allowlist authorizes no silent semantic delta.

`int` is a signed-64 representation-domain contract, not arbitrary-precision equivalence. `float`, `bool`, and borrowed immutable UTF-8 string boundaries follow their documented target mappings. Operations outside the selected value/failure domain remain unsupported even when Python syntax parses.

Python evaluation order is made explicit wherever ordinary C could obscure it.
Call arguments are staged left to right and once. Range bounds are staged once
before the loop. Chained operands use deterministic temporaries. Phase 14B may
place an already-supported prerequisite sequence inside the exact Boolean or
chained-comparison guard; an operand without a complete region proof still
rejects rather than being evaluated eagerly.

Phase 14C direct keyword calls preserve two explicit orders. Every leading
positional and explicit keyword value is staged left to right and once in
Python source order. After complete static name/category/coverage proof, only
pure temporary references are permuted into formal ordinal order for the C
call. There is no runtime binder, default selection, unpacking, or `TypeError`
model.

Every supported source decision has one RulePlan. Lowering consumes the published bindings, facts, representation/name plans, and RulePlans; it constructs typed C IR only. Generated C is published only after C IR and independent text validation. The converter never compiles or executes the result.

Phase 12 module imports are closed-world compile-time binding declarations.
Only absolute `from exact.module import direct_function` items in a module
preamble are supported. Resolution uses the explicitly supplied SourceBundle
map and exact logical IDs; no Python import hook, path, package, filesystem,
environment, network, or installed distribution participates. Imported aliases
reuse one target function identity and signature. They do not create module or
function objects and cannot be rebound or re-exported.

Module initialization has no executable observation in the selected subset.
The import graph must be acyclic and publishes dependency-first, module-ID-tied
order. Namespace construction occurs entirely during planning. The generated C
has no import cache, module initializer, global guard, or runtime import failure.
Every supplied module is lowered into the same translation unit. Any source
form that could observe broader Python module/package behavior rejects instead
of being approximated.

Phase 13 record classes are closed structural declarations, not runtime Python
class objects. Every accepted field, structural initializer, fresh
construction, owner binding, and field read is statically exact. Construction
arguments are evaluated left to right and once before a fully initialized
automatic aggregate becomes observable. The unique owner is immutable and
cannot be copied, aliased, rebound, escaped, passed, returned, or stored.

The C structure preserves field declaration order and exact scalar types; a
direct field read observes the corresponding initialized scalar for the
enclosing function activation. There is no accepted source observation of
object identity, truth, equality, mutation, allocation, nullability,
destruction, dynamic dispatch, methods, or cross-module record identity. Any
such form rejects instead of being approximated.

Phase 14A integer floor arithmetic is a statically proved helper-backed scalar
operation, not C operator equivalence. Both operands use the existing signed-64
integer representation. The divisor must be a direct signed literal in
`[-9223372036854775807, -2]` or `[1, 9223372036854775807]`; zero, negative one,
`INT64_MIN`, dynamic values, mixed categories, and constant-folded expressions
reject before planning.

The proof makes C11 division and remainder defined for every represented left
operand. Floor division selects the frozen `pycf.i64.floor_div@1.0.0` helper;
modulo selects `pycf.i64.floor_mod@1.0.0`. Signed-64 left, right, and result
temporaries preserve left-to-right exactly-once evaluation, while the helper
corrects C truncation semantics to Python floor quotient and divisor-sign
remainder. No exception, allocation, cleanup, arbitrary-precision, or dynamic
failure behavior is admitted.

Phase 14B conditional regions are placement proofs, not new expression
semantics. An exact Boolean `and`/`or` accumulator uses true or false gates as
Python requires. A chained comparison evaluates its first two operands, then
materializes each later compatible operand only while the accumulated result is
true and reuses the middle value once. Nested prerequisites remain lexically
inside the parent guard. No skipped source operand evaluates, and no helper,
allocation, cleanup, or failure behavior is introduced by the region itself.

When a RulePlan has an exact helper requirement, the helper may close only the
obligations declared by its registered semantic, ownership, lifetime, target,
and failure contract. Phase 14A promotes only the two numeric helpers under the
proof above; Phase 14B region, Phase 14C keyword binding, Phase 13 record, and
all other current RulePlans require no helper of their own.
