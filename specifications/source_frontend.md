# Source Frontend Contract — cumulative through Phase 14C

The frontend accepts only decoded source documents explicitly present in a
validated `source-bundle/0.2`. It never imports, evaluates, executes, opens, or
discovers a document in response to source text.

The publication chain is:

1. `source-bundle/0.2` — one primary and zero or more explicit companions with
   canonical module/source identities and exact UTF-8 content fingerprints.
2. `source_document/0.3` — one immutable per-document text identity, line
   index, exact newline sequence, and bounded token sequence.
3. `python-ast/0.3` — per-document parser summaries; host AST objects remain
   request-local scratch state.
4. `python-ir/0.4` — a bundle envelope containing deterministically ordered
   module units using the established 0.3 normalized node vocabulary and
   globally unambiguous document/node provenance.

Python 3.11 is the only accepted grammar. Each parser invocation uses explicit
`feature_version=(3, 11)`. Documents are acquired, decoded, tokenized, parsed,
and normalized in SourceBundle order; published bundle IR uses the approved
module order where specified. Failure in any member rejects the whole stage and
publishes no partial bundle IR.

Source byte, line, token, and AST-node ceilings apply to aggregate bundle
totals; nesting depth applies independently to each document. The fixed policy
also admits at most 64 documents and 4,096 normalized import items. Diagnostic,
trace, telemetry, and cancellation policies remain bounded and observer-inert.

The frontend's import nodes are syntax and provenance only. Exact SourceBundle
resolution occurs in module analysis and cannot consult a path, filesystem,
environment, network, installed package, import hook, or Python module cache.

Phase 13 changes no parser grammar or source-acquisition channel. Ordinary
Python 3.11 class, annotated-field, initializer, construction, and attribute
nodes are retained with exact provenance; the later record analyzer alone
decides whether they satisfy the closed static-record profile. A class parse is
therefore not a support claim, and no frontend pass infers layout or executes a
class body.

Phase 14A likewise adds no parser grammar, normalizer field, source-acquisition
channel, or constant-folding pass. Ordinary Python 3.11 `FloorDiv`, `Mod`, and
unary/literal nodes retain their exact normalized shape and provenance. The
separate numeric analyzer alone decides whether an occurrence satisfies the
direct safe signed-literal boundary.

Phase 14B also leaves parsing, normalization, acquisition, and `python-ir/0.4`
unchanged. Ordinary `BoolOp`, `Compare`, call, arithmetic, container-read, and
record-read nodes retain their source structure. Conditional-region meaning and
prerequisite placement are published only by the later analysis pass; the
frontend neither hoists nor executes an operand.

Phase 14C likewise leaves the frontend unchanged. Normalized `Call.args` and
`keyword` nodes retain source order, exact keyword spellings, and value
references. Static actual-to-formal binding and formal-order permutation are
published only by the later analysis pass; the frontend performs no call
binding or runtime lookup.
