# Phase 13 Rollback Conditions

Before promotion, abandon the candidate and return to sealed PyCForge 0.12.2
if any of these conditions occurs:

- the predecessor archive, tree, or converter-subtree identity cannot be
  reproduced exactly;
- a class outside the approved static-record grammar reaches planning or C IR;
- a field type, initializer binding, construction target, receiver, field ID,
  module owner, argument order, or scalar representation is inferred without
  complete evidence;
- a record can be mutated, rebound, copied, aliased, passed, returned, nested,
  imported, made nullable, heap allocated, or made to require cleanup;
- inheritance, descriptors, dynamic attributes, reflection, class values,
  general methods, or other Python object-model behavior is approximated;
- rejected/cancelled conversion publishes partial record C IR, mappings,
  observer artifacts, or generated output;
- accepted predecessor source changes generated C bytes or historical Phase 12
  rule, renderer, policy, schema, serialization, fingerprint, or diagnostics
  are silently relabeled;
- deterministic ordering, source mappings, helper identity, module isolation,
  no-host-discovery, atomic publication, workspace stale-output protection, or
  package installation regresses;
- validation compiles, links, loads, or executes generated C.

Rollback archive: `pycforge_phase_12_2_v0_12_2.tar.gz`  
Archive SHA-256: `6a603684001f2cb2e9365d7e9b318f1a95dbe95b2cb36cf8821c30403c1754d0`  
Tree SHA-256: `434981decfd2b2fc2b344f5b9a3b37377396376c2e0a8c8ed00bb9fa9077d765`  
Converter subtree SHA-256: `4d7676a46105652efd13efb699d00e7a39a4b1bfd7ae7daad32c22702fd41b51`
