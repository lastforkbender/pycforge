# Phase 11 Rollback Conditions

Roll back to the sealed Phase 10 v0.10.0 release if any of these conditions is
found after promotion:

- the predecessor archive/tree identity or authoritative roadmap custody cannot
  be verified;
- a supported container can alias, escape, resize, mutate, allocate, require
  cleanup, or encounter an unproved runtime bounds/hash/key failure;
- dictionary order or key assumptions, negative indexing, or element
  evaluation order diverges from the approved contract;
- unsupported input publishes partial C IR, helper output, or generated C;
- C IR 0.11 arrays bypass structured validation or independent text
  conformance;
- Phase 10 helper fingerprints, scalar generated C bytes, or historical C IR
  serialization change unexpectedly;
- determinism, observer isolation, cancellation, atomic-save, packaging, or
  workspace regression evidence fails;
- generated C is compiled or executed as part of PyCForge validation.

Rollback archive: `pycforge_phase_10_v0_10_0.tar.gz`  
Archive SHA-256: `0f54742d1ae1cef604291d0a38286a475cd048792f986ca95e20b3348cdc5c4b`  
Tree SHA-256: `f3fc12f357ff7c3667f483375d431e087dcfb65302d279194f9ed51466787ea2`
