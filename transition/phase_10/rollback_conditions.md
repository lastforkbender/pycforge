# Phase 10 Rollback Conditions

Rollback to sealed PyCForge v0.9.0 if any promoted Phase 10 artifact exhibits:

- helper registry identity, asset, target, interface, ownership, lifetime, or
  failure-contract drift without an explicit version transition;
- dependency closure that varies by registration order, emits duplicates,
  omits dependencies, or accepts a cycle;
- raw or user-controlled C text entering through a helper path;
- a helper emitted without an owning exact RulePlan requirement;
- an unused helper appearing in the manifest or generated source;
- partial helper output after rejection, cancellation, or internal failure;
- changed Phase 9 generated C for the unchanged supported subset;
- observer, GUI, or telemetry state affecting helper selection or fingerprints;
- compilation/execution behavior or a source-driven template/include path;
- failure of the 154-test release suite, current validator, package reproduction,
  Qt smoke, or any required audit.

Rollback restores `pycforge_phase_9_v0_9_0.tar.gz` by its recorded SHA-256. The
Phase 9 archive and tree are never edited in place.
