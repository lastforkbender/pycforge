# SourceBundle and Logical Identity Contract — `source-bundle/0.2`

A `SourceBundle` is an explicit ordered collection containing one primary
`SourceDocumentInput` and zero or more companion inputs. Phase 12 introduced,
and Phases 13 and 14A retain, the range of
1 through 64 documents. Every accepted document is parsed, validated, planned,
and included in the conversion unit; an unreferenced companion is not silently
discarded.

Each public `SourceDocumentInput` contains exactly:

- `module_id`: canonical semantic logical-module identity;
- `logical_name`: canonical relative POSIX logical-source identity;
- decoded Unicode `text`, encodable as UTF-8.

The primary is identified by its position, not by a reserved module spelling.
Companion order remains part of canonical SourceBundle serialization, while
module initialization and generated declaration order follow the separate
dependency-order contract.

## Canonical logical module IDs

A logical module ID has 1 through 16 dot-separated segments. Each segment
matches `[a-z][a-z0-9_]{0,62}` and the complete UTF-8 spelling is at most 255
bytes. Validation uses exact byte equality. The converter performs no case
folding, Unicode normalization, path conversion, extension removal, parent
inference, prefix matching, or package fallback. Module IDs must be unique.
`a`, `a.b`, and `a_b` are three unrelated exact IDs.

Logical source names retain the canonical relative POSIX-path contract: they
are nonempty valid UTF-8, contain no control character or backslash, are not
absolute, contain no `..` component, and equal their `PurePosixPath` spelling.
They must also be unique within the bundle. A logical source name never
participates in import resolution.

## Canonicalization and fingerprints

The `source-bundle` fingerprint covers schema identity, primary/companion
position, exact logical module and source names, declared decoding decision,
and exact UTF-8 content fingerprints. Absolute host paths, display paths,
timestamps, filesystem identities, environment state, and acquisition details
are not fields of `SourceDocumentInput` and never enter semantic or output
fingerprints.

The converter consumes the supplied text and an immutable exact-ID map only.
An import never triggers filesystem, environment, network, installed-package,
`sys.path`, working-directory, or host-path inspection. Malformed identities,
duplicate module/source identities, more than 64 documents, or more than 4,096
normalized import items reject the entire request without a successor artifact.

Historical `source-bundle/0.1` remains scoped to one primary document and no
companions. It is not silently interpreted as a Phase 12 or Phase 13 bundle.
