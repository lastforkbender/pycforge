# Phase 6 First Complete Conversion Slice

Schema: `generated-c/0.6`

## Supported boundary

One annotated top-level function with positional annotated parameters, a required annotated return, basic single-name local declarations, return statements, simple names, integer/float/Boolean/string literals, and selected `+`, `-`, `*`, `/` numeric expressions.

Integer representation is `int64_t`; floating representation is `double`; Boolean representation is C `bool`; strings are immutable UTF-8 C string literals with lexical/static literal lifetime. String mutation, concatenation, calls, control flow, defaults, decorators, nested functions, dynamic annotations, and unsupported arithmetic reject with stable diagnostics.

Lowering consumes the immutable Phase 5 facts, generated-name plans, representations, and RulePlans. It constructs structured C IR only. The existing independent C IR validator, deterministic renderer, text-conformance validator, and provenance-based mapping assembler publish the final source result.

Generated C is never compiled or executed.
