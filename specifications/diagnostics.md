# Diagnostics — v0.14.3

Diagnostics are immutable conversion products. Their public projection contains a deterministic `diagnostic_id`, stable code, severity, stage, message, status effect, source and related spans, causal ID, target contract, semantic policy, rule ID, fact and obligation references, explanation, remediation, approximation metadata, and semantic delta. Fields without applicable evidence are explicitly null or empty.

Stage diagnostics are contextualized by the facade with the canonical target and semantic policy. IDs derive only from semantic diagnostic identity, never timing, host paths, mutable observers, or process state. Cross-document diagnostics are ordered by bundle ordinal, source offset, stage rank, severity rank, code, and decision identity; request-level bundle diagnostics precede source diagnostics. Every source diagnostic identifies logical module, logical source, source-document revision, and span. Internal errors omit implementation exceptions and host details.

Namespaces used by the cumulative implementation:

- `PYC1xxx`: request, configuration, source, cancellation, and grammar boundaries.
- `PYC2xxx`: unsupported semantics, analysis, function/call, and lowering decisions.
- `PYC3xxx`: artifact/CLI compatibility plus helper, container, and explicit-module profile contracts.
- `PYC8xxx`: reserved observation-only conditions.
- `PYC9xxx`: internal stage, C IR, renderer, and facade invariants.

Phase 9 call/local codes include:

| Code | Meaning |
|---|---|
| `PYC2901` | target is unknown, indirect, rebound, or dynamic |
| `PYC2902` | module or target eligibility is outside the closed subset |
| `PYC2904` | required-parameter coverage or positional arity mismatch |
| `PYC2905` | post-binding argument representation mismatch |
| `PYC2910` | `*`/`**`, null keyword name, unpacking, or another excluded keyword-call shape |
| `PYC2911` | duplicate parameter name, positional or keyword-only default, variadic parameter, or keyword-only declaration outside the exact required profile |
| `PYC2912` | unknown keyword name, positional-only name used as keyword, positional/keyword collision, or duplicate keyword binding |
| `PYC2914` | decorated or generic function |
| `PYC2915` | nested function or closure |
| `PYC2920` | direct or mutual recursion |
| `PYC2930` | explicit return representation mismatch |
| `PYC2931` | reachable implicit-`None` fallthrough |
| `PYC2932` | unsupported or missing exact annotation |
| `PYC2940` | use before local binding |
| `PYC2941` | loop-target lifetime escape |
| `PYC2943` | incompatible binding representations |
| `PYC2944` | range-target rebinding |
| `PYC2950` | Boolean short-circuit operand requires conditional placement but lacks an exact Phase 14B region proof |
| `PYC2951` | chained-comparison operand requires conditional placement but lacks an exact Phase 14B region proof |

One root semantic cause is selected before blocked parents. Rejection never publishes partial C.

Phase 14B retains these codes instead of creating a broad new diagnostic
family. An otherwise eligible call, numeric prerequisite, container/record
read, or nested region may now convert when the complete conditional fact and
RulePlan close placement. A more specific unresolved-target, arity, category,
recursion, numeric, container, record, or ownership cause retains precedence;
placement never masks it. Malformed or adversarial published region evidence is
an internal validation failure, not source acceptance. Cancellation during
region analysis, validation, or lowering uses `PYC1901`, returns `Canceled`, and
publishes no partial successor.

Phase 14C narrows only the direct-call keyword boundary. A call selecting the
exact static binding profile may convert after complete target, name, coverage,
category, source-order, and formal-order proof. `PYC2912` owns static name-
binding failures for an otherwise eligible direct source target: an unknown
keyword, a positional-only name used by keyword, a positional/keyword
collision, or a duplicate keyword. `PYC2910` remains the boundary for
`Starred`, `**`/null-name unpacking, and other excluded keyword shapes.
`PYC2904` retains missing/excess coverage, `PYC2905` retains category mismatch,
`PYC2911` retains ineligible declarations, and target, range, record, module,
and recursion diagnostics retain precedence. Malformed or adversarial keyword
facts are internal validation failures. Cancellation uses `PYC1901` and
publishes no partial successor.

Phase 14D narrows only the required-keyword-only declaration and direct-call
boundary under active 0.14.3 identities. An otherwise eligible function may
contain exactly annotated required keyword-only parameters when every
corresponding `kw_defaults` entry is null and no default or variadic exists.
`PYC2911` continues to reject defaults, defaulted keyword-only parameters,
variadics, duplicate names, and keyword-only declaration shapes outside that
exact profile; it no longer rejects an eligible declaration merely because
`kwonlyargs` is nonempty.

At a call site, `PYC2904` owns missing required coverage and positional overflow
into the keyword-only range, `PYC2905` owns representation mismatch, `PYC2910`
owns unpacking/excluded call shapes, and `PYC2912` owns unknown names,
positional-only names used by keyword, collisions, and duplicate binding.
Target, module, annotation, return, recursion, numeric, conditional, container,
and record causes retain precedence. Malformed signature, call-fact, RulePlan,
or C-parameter evidence is an internal validation failure. Cancellation uses
`PYC1901` and publishes no partial successor.

Phase 10 helper codes are `PYC3301` malformed exact reference, `PYC3302`
missing dependency, `PYC3303` dependency cycle, `PYC3304` target mismatch,
`PYC3305` interface/policy mismatch, `PYC3306` invalid contract or structured C
IR asset, and `PYC3307` duplicate identity. Resolver cancellation uses the
existing canceled result and publishes no helper diagnostic cascade.

Phase 11 container codes are `PYC3401` malformed/capacity/nesting,
`PYC3402` heterogeneous or unsupported scalar representation, `PYC3403`
alias/rebind/escape/scalar use, `PYC3404` dynamic or mismatched index/key,
`PYC3405` out-of-range index or absent key, `PYC3406` mutation/resizing/
unpacking/comprehension, and `PYC3407` unsupported iteration. These are primary
source diagnostics with container fact and obligation references. They stop
before C IR, helper assembly, or generated-C publication.

Phase 12 module-bundle primary codes are:

| Code | Meaning |
|---|---|
| `PYC3501` | malformed or noncanonical bundle document, logical module ID, or logical source identity |
| `PYC3502` | duplicate logical module ID or logical source name, producing ambiguous bundle identity |
| `PYC3503` | exact imported module is absent from the supplied SourceBundle |
| `PYC3504` | unsupported plain, relative, star, late/local/conditional, or dynamic import form |
| `PYC3505` | imported member is absent or is not a directly defined eligible top-level function |
| `PYC3506` | import alias or namespace collision, duplicate/rebound binding, unimported foreign reference, module-as-value use, or re-export |
| `PYC3507` | self-edge or multi-module import dependency cycle |
| `PYC3508` | requested package/import-system behavior, implicit parent, prefix match, or discovery fallback |
| `PYC3509` | executable module initialization, general global state, or another unsupported top-level statement |
| `PYC3510` | module-document, import-item, or aggregate resource ceiling exceeded |

Existing `PYC2904`, `PYC2905`, and `PYC2920` continue to own call arity,
representation mismatch, and direct/mutual function recursion, including across
modules. Every PYC35xx primary rejection stops before C IR, helper assembly,
source-mapping publication, or generated C. Blocked bundle decisions carry one
causal reference rather than duplicate the root module diagnostic.

Phase 13 record primary codes are:

| Code | Meaning |
|---|---|
| `PYC3601` | record declaration is misplaced, decorated, inherited, keyworded, shadows a closed annotation builtin, or otherwise is not the exact top-level shape |
| `PYC3602` | field count, spelling (including dunder exclusion), uniqueness, value-less form, or exact `int`/`float`/`bool` annotation is invalid |
| `PYC3603` | structural `__init__` signature, return, parameter order/type, or complete ordered assignments are invalid |
| `PYC3604` | class body contains an unsupported member, executable statement, or ordinary method |
| `PYC3605` | record construction is not one direct same-module fresh-local positional construction without a type comment and with exact arity/categories |
| `PYC3606` | record value is read before construction, aliased, rebound, copied, passed, returned, escaped, stored, compared, truth-tested, or otherwise used as an object value |
| `PYC3607` | record field is mutated, unknown, dynamic, chained, or not a statically proved direct read |
| `PYC3608` | record construction or use crosses its exact defining module/document boundary |
| `PYC3610` | an `ImportFrom` item attempts to import a record class |

`PYC1017` is the request-level rejection for an unknown record-policy identity.
Record diagnostics identify the exact module, logical source, document, node,
and span where available. Every PYC36xx rejection stops before C IR, helper
assembly, mapping, summary, trace, or generated-C publication; unsupported
class behavior never falls back to a generic structure approximation.

Phase 14A numeric primary codes are:

| Code | Meaning |
|---|---|
| `PYC3701` | a floor-arithmetic operand is not exact integer-like, the occurrence is outside an understood scalar context, or its source/function ownership evidence is incomplete |
| `PYC3702` | the divisor is not a directly admitted signed integer literal, is zero, negative one, `INT64_MIN`, out of range, dynamic/calculated, or lacks a complete safe-divisor proof |

`PYC1018` rejects an unknown numeric-policy identity. Every PYC37xx rejection
selects no helper and stops before C IR, mapping, summary, trace, or generated-C
publication. Attribution identifies the operator or divisor in the exact
logical document without exposing a host path or unstable AST representation.

Explicit historical Phase 14A requests retain the original `PYC2950` and
`PYC2951` rejection behavior because their `conversion-plan/0.14` artifacts do
not contain conditional-region evidence.
Explicit historical Phase 14B requests retain `PYC2910` for explicit keyword
calls because their `conversion-plan/0.14.1` artifacts contain no Phase 14C
binding facts or RulePlans.
Explicit historical Phase 14C requests retain the 0.14.2 `PYC2911`
keyword-only declaration rejection because their `conversion-plan/0.14.2`
artifacts contain no required-keyword-only call facts or FunctionDef
obligations. Historical diagnostics are not rewritten to the active 0.14.3
boundary.
