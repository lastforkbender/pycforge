# Phase 8 Control Flow — v0.8.0

Phase 8 extends the promoted source-conversion subset with structured control flow only. Generated C remains the final boundary and is never compiled or executed.

## Supported forms

- `if` / `elif` / `else` over boolean, integer, or floating conditions with representation-specific truthiness.
- `and` / `or` lowered to C short-circuit operators while preserving left-to-right evaluation.
- Numeric and Boolean comparisons: `==`, `!=`, `<`, `<=`, `>`, `>=`.
- Chained comparisons lowered through deterministic synthetic temporaries so every source operand is evaluated once in source order.
- `while` without `else`.
- `for` over positional `range(stop)`, `range(start, stop)`, and `range(start, stop, step)` forms. Bounds and step are rendered from the planned source expressions; a literal zero step is rejected.
- `break` and `continue` only inside a supported loop.

## Explicit policies

- Branch and loop bodies form C blocks.
- A binding must be declared before entering control flow. First definition inside a branch or loop is rejected in this phase, preventing Python function-scope bindings from being silently narrowed to C block scope.
- Zero-iteration loops are represented directly by C loop conditions.
- The `range` loop target has loop-local C lifetime.
- Loop `else`, mutation-sensitive general iteration, strings and containers as iterables, calls other than the recognized `range` loop form, and dynamic truthiness are rejected.
- Chained-comparison temporaries have deterministic synthetic provenance and source/output mappings.

## Schema changes

- C IR advances to `c-ir/0.8` with assignment, branch, loop, break, and continue statements.
- Generated artifact identity advances to `generated-c/0.8`.
- Rule-set identity is `phase8-control-flow-v0.8`.
