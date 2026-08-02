# Phase 12 Entry Criteria

Status: contract entry gate satisfied on 2026-07-22; implementation gate open.

- The supplied sealed Phase 11 archive was authenticated at SHA-256
  `8af71e84cb6a1f12fc1206f589233067191f87ce4fc4f550765ff64098038275`.
- The Phase 11 sealed-tree fingerprint remains
  `95fbabf3311a5f7dcb88608ef66c7ef43ed085ae1e3fc99351472da8ca1d4e82`.
- Architecture Revision 3.1 and Revision 3.2 addendum remain packaged at exact
  SHA-256 identities `d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3`
  and `93b228528a10895fdbdce7b6934d422e7eddd1a79b409bdbc15ea6677e5ab8c6`.
- Function, call, helper, container, name, target, source-only, and atomic
  publication contracts are retained as the predecessor baseline.
- `module_bundle_decisions.md` approves exact IDs, imports, namespace/linkage,
  initialization/cycles, diagnostics, mappings, resource ceilings, singleton
  compatibility, and the one-translation-unit representation before code edits.

The gate authorizes only the documented closed-world direct-function import
profile. It does not authorize source-driven discovery, package semantics,
module objects, executable top-level state, Python import equivalence, multiple
C outputs, compilation, linking, loading, or execution.
