# Phase 11 Gate Evidence

Phase 11 exits with a complete vertical slice for the approved profile:

- immutable shape, binding, access, and iteration facts with source provenance;
- seven reachable Phase 11 rules and closed semantic obligations;
- fixed-array, initializer-list, and subscript C IR 0.11 nodes and validation;
- deterministic array declarators, read-only tuple/dictionary arrays, and
  independent generated-text conformance;
- list, tuple, dictionary, positive/negative indexing, and selected iteration
  fixtures, including call staging and `break`/`continue`;
- primary `PYC3401`–`PYC3407` rejection fixtures with no generated C or partial
  helper output;
- explicit automatic lifetime, no allocation, no transfer, no cleanup, and no
  runtime bounds/hash/key-failure channel;
- empty helper requirements/manifests for every container RulePlan;
- exact preservation of the Phase 10 helper registry and asset fingerprints;
- centralized active schema/configuration identities, separate container
  analysis/lowering modules, a current-contract index, and generated evidence;
- 169 passing cumulative tests plus architecture, rule, helper, container,
  determinism, transition, package, installed-wheel, and workspace checks.

All C validation was structural and textual. No generated C or helper source
was compiled, linked, loaded, or executed.
