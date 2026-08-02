# Phase 9 Gate Evidence

The candidate implements the bounded function/call slice through immutable facts, one-time RulePlan selection, structured C IR 0.9, deterministic rendering, independent non-executing text conformance, provenance mappings, and complete-result publication.

Evidence covers:

- deterministic lexical target resolution and rejection of unknown/rebound/indirect targets;
- exact signatures and prototype/definition consistency;
- left-to-right, once-only positional argument staging, including nested calls;
- forward calls through prototypes;
- compatible reachable returns and explicit fallthrough rejection;
- local use-before-binding, representation conflict, declaration placement, name collision, and loop-target policies;
- explicit borrowed string parameter/return boundary;
- iterative direct/mutual recursion detection and nested-function rejection;
- function, prototype, parameter, argument, call, result-temporary, return, and control-flow mappings;
- annotation evidence and ownership obligations in the call RulePlan and decision trace;
- negative C IR validation for missing prototypes, invalid loop control, and call arity;
- malformed-request containment, recursive artifact immutability, artifact tamper detection, CLI atomic output, and stale workspace save prevention;
- field-aware Python IR references and bounded dependency-worklist analysis, including a 1,000-binding adversarial chain and a 150-function recursive cycle;
- centralized C11 keyword, header-token, reserved-external-name, and trigraph-safe output policy;
- runtime/schema-aligned immutable decision trace and telemetry records, deterministic trace levels and truncation, observer failure isolation, cancellation, resource rejection, API/CLI/workspace equivalence, and fresh-process determinism;
- two byte-identical fixed-epoch wheel builds followed by an isolated install and conversion smoke test;
- preservation of every earlier phase test and the no-compilation/no-execution boundary.

The final gate record is 139 independently discoverable tests: 92 Phase 0–8 regressions, 17 cross-phase review-hardening tests, and 30 Phase 9 tests. Generated C was structurally and textually validated only. It was not compiled or executed.
