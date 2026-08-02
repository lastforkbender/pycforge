# Generated-C Text Conformance — v0.14.3 compatibility contract

After C IR validation, the deterministic renderer emits one bounded ISO C11
translation unit. A separate lexer and recursive parser checks the rendered
text without importing the C IR model, renderer, Python source, or module facts.

The independent grammar retains the complete Phase 11 subset: registered
includes, scalar/fixed-array declarations, prototypes, definitions, structured
statements/calls/expressions, helper `static` declarations, fixed-array
declarators, nonempty brace initializers, pointer-object `const`, and postfix
subscripts. It enforces registered headers, include-prefix placement,
`stdint.h`/`stdbool.h` requirements, balanced and complete structure, explicit
`void` empty parameter lists, legal ASCII identifiers including validated
`pycm_` spellings, and final LF.

Phase 12 adds no C grammar construct. Text conformance additionally proves that
there is one translation unit, every prototype precedes every definition, no
source-controlled include or unresolved import token appears, and no module
initializer/global import state is rendered. Module ownership and topological
order remain C IR validation duties; the independent parser validates the
resulting source structure without consulting those facts.

The renderer retains deterministic UTF-8 escaping, octal termination,
trigraph-safe `\?`, unary-token separation, precedence, and mappings. The check
invokes no compiler, linker, executable, runtime, native toolchain, Python
import machinery, or behavioral comparison.

Phase 13 extends the independent grammar with named `typedef struct`
definitions, ordered scalar members, named record types, aggregate
initializers, object-level `const`, and postfix `.`/`->` member selection. It
checks complete braces/declarators, legal identifiers, known record/member
spelling, scalar initializer grammar, definition-before-use order, and required
standard headers without consulting record facts or the C IR model.

The accepted source profile renders direct `.` access only, but the closed C IR
grammar validates both explicit member modes. No allocation call, pointer
ownership protocol, null check, constructor function, method table, cleanup
function, compiler directive, or second translation unit is admitted. A
class-free Phase 13 result remains byte-identical to its Phase 12 generated C.

Phase 14A adds no independent grammar kind. Existing scalar declarations,
direct calls, helper prototypes/definitions, and structured conditional
statements represent the numeric staging and frozen helper bodies. The parser
checks exact registered helper spelling/linkage/signature, declaration before
use, complete two-argument calls, balanced helper structure, and the ordered
signed-64 temporary declarations without consulting numeric facts or Python
source. It cannot validate divisor safety; that remains an independently
anchored analysis/C IR obligation.

Phase 14B likewise adds no grammar kind. Existing automatic scalar
declarations, assignment statements, `if` blocks, logical negation, calls, and
binary comparisons render the complete guarded region. The independent parser
checks initialized declarations, declaration-before-use, balanced sibling
guards, branch-contained statement syntax, valid assignments, and the closed
C11 expression grammar. Exact Python gate polarity, prerequisite provenance,
and rolling-middle identity remain independently validated C IR obligations,
not renderer inference.

Phase 14C also adds no grammar kind. Existing typed automatic declarations,
identifier references, and direct calls represent the complete lowering. The
independent parser checks declaration-before-use, one compatible argument per
formal, pure identifier-reference call arguments, and the closed direct-call
grammar. Exact keyword spelling, static binding, source-order staging, formal-
order permutation, and provenance remain independently validated fact/C IR
obligations, not renderer or text-parser inference.

For an explicit historical 0.14.2 request that selects no Phase 14C keyword call, generated-C
bytes remain identical to the matching explicit Phase 14B request. Historical
`generated-c/0.14.1` remains unchanged and cannot contain a 0.14.2 keyword-call
plan. Historical `generated-c/0.14` remains unchanged and cannot contain a
0.14.1 conditional-region plan.

Explicit historical Phase 13 output remains byte-identical to the sealed
predecessor. Historical Phase 14C conformance invokes no compiler, linker,
loader, executable, or generated-code runtime.

Phase 14D adds no independent grammar kind. Required keyword-only formals render
as existing C parameters in full validated formal order; explicit actuals remain
typed automatic declarations followed by direct calls containing pure
identifier references. The parser checks prototype/definition agreement,
declaration-before-use, exact compatible arity, pure-reference arguments, and
the closed direct-call grammar. It does not infer parameter kind, source
calling mode, omitted values, or keyword binding.

Exact required status, absence of defaults/variadics/unpacking, source-order
staging, full formal-order references, mode-erasure containment, and provenance
remain independently validated signature/RulePlan/fact/C IR obligations.

For an active 0.14.3 request that selects no Phase 14D declaration or call
behavior, generated-C bytes remain identical to the matching explicit Phase
14C request. Historical `generated-c/0.14.2` remains unchanged and cannot
contain a 0.14.3 required-keyword-only fact or plan. Active Phase 14D
conformance invokes no compiler, linker, loader, executable, or generated-code
runtime.
