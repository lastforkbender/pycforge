# Phase 10 Gate Evidence

The candidate implements the bounded Support-Template Infrastructure phase.

Evidence covers:

- frozen exact-version registry independent of registration order;
- project-owned structured C IR factories with no raw-text ingestion path;
- two accepted prospective numeric helpers and exact golden C sources;
- complete dependency closure, root/dependency deduplication, and deterministic
  dependency-before-consumer ordering;
- stable malformed, missing, cyclic, target, interface, invalid-asset, and
  duplicate-identity diagnostics;
- target/interface, prototype/definition, static-linkage, reserved-name,
  provenance, ownership/lifetime, and failure-contract validation;
- cancellation without partial helper plan, manifest, C IR, or generated C;
- conditional `c-ir/0.10` assembly with registered include deduplication, all
  prototypes before definitions, and each helper emitted once;
- absent unused helpers and byte-identical Phase 9 generated C for representative
  calls, control flow, and borrowed strings;
- helper policy, registry, exact manifest, semantic obligations, and
  fingerprints in artifacts, summaries, diagnostics, and Full traces;
- explicit Phase 10 public schema identities (`generated-c/0.10`,
  `pycforge.conversion-summary/0.10`, `pycforge.decision-trace/0.10`, and result
  serialization `0.3`) while helper-free C IR remains `c-ir/0.9`;
- architecture, rule, helper, determinism, and transition audits;
- the complete 143-test opening checkpoint regression suite plus 11 Phase 10
  tests;
- an actual PyQt5 5.15.11 / Qt 5.15.14 offscreen widget smoke test covering the
  Python-first view, read-only hidden C, separate details toggle, retained
  output, inline progress, and non-modal conversion;
- reproducible wheel, isolated installation, API/CLI conversion, and source
  archive checks recorded in Phase 10 evidence.

Generated C and helper sources were validated structurally and textually only.
They were not compiled, linked, loaded, or executed.
