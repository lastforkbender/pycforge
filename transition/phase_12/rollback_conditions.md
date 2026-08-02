# Phase 12 Rollback Conditions

After promotion, roll back to sealed Phase 11 v0.11.0 if:

- the predecessor archive/tree or authoritative roadmap identities fail;
- a source import consults any host path, filesystem, environment, network,
  import hook/cache, installed package, or implicit companion;
- module IDs resolve by anything other than approved exact SourceBundle identity;
- an unsupported import/package/init form is accepted or lacks its stable
  PYC35xx primary diagnostic;
- a cycle, namespace conflict, missing target/member, or unproved cross-module
  call reaches C IR;
- module order, external source linkage, `pycm_` naming, helper linkage, or
  prototype/definition order diverges from the approved contract;
- more than one translation unit, a module initializer/global import state,
  source-controlled include, build/link instruction, or partial output appears;
- mappings or diagnostics identify the wrong source document;
- singleton/no-import generated C differs from Phase 11;
- predecessor tests, historical serializers/fingerprints, determinism, observer
  isolation, cancellation, atomic save, packaging, or text conformance fail;
- generated C is compiled or executed by PyCForge validation.

Rollback archive: `pycforge_phase_11_v0_11_0.tar.gz`  
Archive SHA-256: `8af71e84cb6a1f12fc1206f589233067191f87ce4fc4f550765ff64098038275`  
Tree SHA-256: `95fbabf3311a5f7dcb88608ef66c7ef43ed085ae1e3fc99351472da8ca1d4e82`
