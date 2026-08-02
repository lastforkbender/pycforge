# Phase 1 Empty-Pipeline Invariants

1. The facade is the sole public conversion entry point.
2. A request is canonicalized before any stage runs.
3. Every completed stage publishes exactly one new immutable artifact.
4. Rejected, failed, and canceled outcomes publish no successor artifact.
5. Observer failures and truncation cannot alter semantic results or fingerprints.
6. Phase 1 publishes no generated C text.
7. The empty stage order is explicit, deterministic, and inspectable.
8. All mutable lifecycle state is request-local.
9. User source is treated only as inert text.
10. No native toolchain or GUI dependency exists.
