# Changelog

## 0.15.2 — Phase 15C IDE-grade authoring and inspection workspace

Status: promoted and sealed; Phase 15D remains unopened.

Prepared the first public PyPI and GitHub distribution without changing the
converter contract. PyQt5 is now a mandatory runtime dependency of the base
package, so an ordinary `pip install pycforge` installs the desktop application
and both `pycforge` and `pycforge-workspace` entry points. Removed the obsolete
`workspace` extra, added PyPI long-description and project metadata, corrected
the command-line examples, and added clean-build, clean-install, offscreen Qt,
GitHub Release, and Trusted Publishing gates.

Established the public source license as `GPL-3.0-only`, compatible with the
GPL PyPI distribution of PyQt5, and included the complete license text in the
source and package metadata.

Advanced the package to `0.15.2`, the workspace contract to
`pycforge-workspace/0.5`, the action registry to
`pycforge.action-registry/0.2`, and the visual system to
`pycforge.visual-system/0.2`. The converter remains sealed at `0.14.3`, the
worker protocol remains `pycforge.worker-protocol/0.1`, and presentation
settings remain schema `1`.

Added identifier-only document-tab and split-pane session state, with at most
two synchronized Python source panes. Added bounded undoable source operations
for line duplication, line movement, indentation, outdentation, and Python
comment toggling, together with go-to-line, whitespace visibility, and source
fold controls.

Added cancellable latest-wins source-structure analysis for already-open Python
text. The normalized outline and breadcrumb projection is parent-linked and
bounded by symbol count, depth, name length, and source-text budgets. Invalid
syntax remains inert and cannot retire valid structure for unrelated open
documents.

Added deterministic literal bundle search across the explicit open
`SourceBundle`, with immutable path-free requests, exact Python and UTF-16
positions, bounded previews, a global 5,000-match cap, and stale-generation
suppression. No host directory or project discovery was introduced.

Added a bounded command palette that projects enabled and visible static
registry actions without retaining handlers or adding a free-form command
execution surface. Added payload-free session transpilation history capped at
64 terminal records.

Expanded the declarative command system to 48 actions, five persistent main
menus, and eleven context surfaces. Added the Navigate menu, source-authoring
commands, document-tab, bundle-search, history, text-input, and read-only-text
contexts while preserving the exact read-only generated-C command allowlist and
single-owner persistent `QAction` construction.

Expanded the vector catalogue from 41 to 55 safe SVG icons and extended the
shared workspace stylesheet for document tabs, split views, breadcrumbs,
outline, bundle-search results, history, and command-palette presentation.

Preserved the Phase 15A spawned-worker model, one-active/one-latest scheduling,
bounded cancellation, immutable revision and fingerprint authentication,
stale-result suppression, off-GUI file and search work, and incremental
generated-C projection. Python remains the only editable code surface.

Recorded current-release real PyQt evidence on the offscreen QPA backend
using Python 3.12.13, PyQt 5.15.11, Qt build 5.15.14, and Qt runtime 5.15.19.
One `QApplication` ran 18 focused workspace cases with zero failures, errors,
or skips. A 250,113-character source constructed the window in 0.054 seconds,
reached the first event turn in 0.0103 seconds, and produced 110 timer ticks at
0.01-second intervals during 1.201 seconds of isolated transpilation. Large-file
mode detached the syntax highlighter while preserving the shared editor buffer;
shutdown left zero new PyCForge threads and zero worker leaks. A small
end-to-end workspace conversion completed in 0.408 seconds as supporting
evidence.

Authenticated, assigned the canonical validation report and release
fingerprint, and built and validated the Phase 15C milestone source archive,
pure-Python wheel, handoff, package report, and checksum records. These
artifacts establish Phase 15C release custody, not the wider Phase 15D
distribution and platform gate.

PyCForge remains a deterministic Python-to-C source transpiler. It does not
compile, assemble, link, load, run, execute, debug, profile, deploy, or invoke
generated C or a C toolchain.

The real offscreen widget evidence is not visible-platform certification.
Visible Windows 11/Linux rendering, physical display scaling, and
assistive-technology validation remain Phase 15D gates.

## 0.15.1 — Phase 15B application shell and visual system

Status: implemented and validated within the available supporting scope.

Advanced the workspace contract to `pycforge-workspace/0.4` and introduced the
import-safe `pycforge.action-registry/0.1`. Every persistent application command
now has one declarative authority for its stable ID, label, mnemonic, SVG icon,
shortcut, tooltip, status explanation, accessible name, checkability, tone, and
allowed surfaces. The Qt adapter creates each persistent `QAction` once and
shares it across menus, toolbars, context surfaces, and bounded dynamic entries.

Added custom gradient/icon File, Edit, View, and Transpile menus and declared
context menus for Python source, read-only generated C, the Source Bundle
navigator, diagnostics, mappings, conversion summary, decision trace, and
telemetry. The custom presentation remains native-backed by `QMenu` and
`QAction`, preserving keyboard traversal, mnemonics, shortcut columns, checked
state, focus return, Escape dismissal, assistive exposure, submenu behavior,
and screen-edge placement. Generated C uses an explicit read-only command
allowlist.

Introduced `pycforge.visual-system/0.1` with cohesive semantic graphite
surfaces, layered gradients, high-contrast text, blue and violet focus accents,
a restrained warm transpilation accent, and explicit success, warning, error,
and danger treatments. Expanded professional self-contained SVG iconography
uses logical dimensions and excludes raster payloads, embedded data, remote
references, fixed physical sizing, scripts, and font-glyph dependencies.

Added high-DPI and accessibility foundations: high-DPI scaling before
application construction, logical icon sizing, stable menu accessible names,
visible tooltips and accessible names for icon-only controls, visible keyboard
focus, and non-color-only state treatment. The interface has no animation and
is reduced-motion safe by construction.

Removed the legacy presentation-namespace migration and compatibility surface.
Current source, settings, menus, toolbars, tests, evidence, and distribution
use PyCForge identity exclusively. Original pre-migration bytes remain
authoritative in the authenticated Phase 15A archive.

Preserved all Phase 15A responsiveness and isolation guarantees: spawned
conversion, one-active/one-latest scheduling, cooperative and hard
cancellation, immutable revision authentication, stale-result suppression,
off-GUI file I/O and search, bounded editor projections, incremental generated-C
population, and exact Save C authority.

Bounded the structured detail inspectors with an iterative cycle-safe
projection limited to 1,024 nodes, 16 levels, 256 children per container, and
2,048 characters per value. Corrected scroll-area context placement, made
uncommitted identity edits immediately stale and unsavable as C, and suppressed
cancellation-pending diagnostics as non-current.

Hardened release custody around a descriptor-bound, size-bounded source
snapshot and a validation-subject digest that is checked against the exact
packaged bytes. Packaging now pins its production environment, compares
duplicate wheel and normalized-source builds, inspects and smokes the sealed
wheel payload, rejects noncanonical validation JSON, and durably publishes the
seven-artifact directory only after the final vocabulary and checksum graph
passes.

The package is `0.15.1`; the converter remains sealed at `0.14.3`, the worker
protocol remains `pycforge.worker-protocol/0.1`, and presentation settings
remain schema `1`. PyCForge remains a deterministic Python-to-C source
transpiler. No C compiler, linker, loader, runtime execution, debugger,
terminal, toolchain, project explorer, plugin system, or generated-C editor was
added.

PyQt5 is unavailable on the validation host, so Phase 15B evidence is
supporting source, static, headless, registry, icon, and optional-widget
evidence only. Visible Windows 11/Linux rendering, real display scaling, and
assistive-technology validation remain Phase 15D gates. Phase 15C and Phase 15D
remain unopened.

Final discovery runs 750 tests: 734 pass, 16 are expected skips, and none fail.
Eleven skips require unavailable PyQt5 widgets; five require unavailable older
optional custody artifacts.

## 0.15.0 — Phase 15A responsiveness and isolation

Status: promoted and sealed.

Replaced workspace in-process conversion with a spawn-only process supervisor.
The bounded `pycforge.worker-protocol/0.1` uses canonical JSON over byte-only
connections and validates generation, bundle, transport, request, artifact,
mapping, and output identities before publication. Scheduling is exactly one
active plus one replaceable latest pending request.

Added cooperative cancellation with a 750 ms grace, hard termination and
two-second reclamation, latest-pending start bounds, non-blocking close, and
recoverable startup, crash, malformed/oversized IPC, broken-pipe, and worker
resource-exhaustion handling. Canceled, failed, stale, superseded, partial, or
mismatched work cannot publish C or replace last-known-good C.

Added immutable off-GUI revision/index services with cached UTF-8 and UTF-16
position facts. Convert and Save C remain disabled until the latest revision
authenticates. Moved linked-file reads, hashes, observations, and guarded atomic
writes to bounded daemon workers; an in-flight stale Save C fails before atomic
replacement.

Added debounced latest-wins literal search with an exact total and a 5,000-range
projection cap. Added automatic large-file editor mode, bounded syntax/bracket
work, marker and overview caps, viewport-focused selections, incremental 32 KiB
generated-C projection, and deferred hidden output/detail work. Source edits
are coalesced before proportional controller synchronization.

Validated direct-versus-isolated serialized-result equality, hard-cancel and
failure containment, maximum-envelope revision/search/index behavior, injected
slow file I/O, and 100 edit/convert/cancel cycles without stale publication,
deadlock, crash, obsolete pending work, or orphan processes.

Advanced the package to `0.15.0` and workspace contract to
`pycforge-workspace/0.3`. The complete converter subtree and every converter
contract remain sealed at `0.14.3`.

PyCForge remains a Python-to-C source transpiler. No compiler, linker, loader,
generated-C executor, runner, debugger, terminal, toolchain, plugin,
project-explorer, host-discovery, or generated-C editor was added. Phase 15B,
15C, and 15D remain unopened; visible Windows 11/Linux PyQt and accessibility
claims are reserved for Phase 15D.

## 0.14.4 — Hardening Checkpoint E

Status: promoted and sealed.

Completed the roadmap's post-Phase-14 full-subset architecture review,
deterministic full-supported-subset fuzz and metamorphic gate, and documentation
and 69-entry feature-matrix reconciliation. No Python construct, C IR shape,
helper, diagnostic, conversion policy, public converter schema, or generated-C
style was added or changed.

Separated the package identity (`0.14.4`) from the sealed deterministic
converter contract identity (`0.14.3`). Golden output, serialized results,
facts, RulePlans, summaries, traces, telemetry, diagnostics, mappings, and
fingerprints remain Phase 14D values.

Corrected the active desktop identity to PyCForge across front-facing titles,
accessibility names, theme exports, and the settings namespace. Added a bounded,
non-destructive migration for allow-listed predecessor presentation settings
and retained non-exported compatibility aliases only for sealed historical
validators.

Established `pycforge-workspace/0.2` and a binding workspace-quality addendum.
The addendum assigns the requested process-isolated conversion supervisor,
maximum-input responsiveness, professional IDE-grade authoring and inspection,
custom gradient/icon main and context menus, accessibility, high-DPI, and real
Windows 11/Linux PyQt gates to Phase 15. Checkpoint E does not claim those
future gates or open Phase 15.

PyCForge remains a Python-to-C source transpiler. It does not compile, link,
load, run, execute, debug, benchmark, or otherwise invoke generated C or a C
toolchain.

Promotion executes all 69 frozen feature-matrix entries plus the unlisted
default, with 37 supported witnesses converted and 33 boundary witnesses
rejected without mismatch. The seeded hardening corpus contains 16 fixed and
64 generated cases, four per promoted family, and all 80 match the
authenticated Phase 14D predecessor byte-for-byte.

Final validation discovers 589 tests: 572 pass, 17 are expected skips, and
zero fail. The focused Checkpoint E set passes 46 of 46, and every cumulative
source-only audit passes. Reproducible wheel and normalized source-archive
builds are byte-identical; isolated wheel and extracted-source smokes pass.
The wheel contains both PyCForge entry points, exactly 17 SVG assets, and no
native binaries.

## 0.14.3 — Phase 14D exact required keyword-only calls

Status: promoted and sealed.

Added one exact source-only declaration and call profile for required
keyword-only parameters on already-resolved direct source functions. An admitted
function may have existing required positional-only and positional-or-keyword
parameters followed by one or more exactly annotated required keyword-only
parameters. Every `kw_defaults` entry is null; positional defaults,
keyword-only defaults, `*args`, and `**kwargs` remain rejected.

Ordinary positional actuals bind only positional-capable formals. Explicit named
actuals may bind unbound positional-or-keyword or required keyword-only formals.
Every required formal is covered exactly once with an exact category and
representation match. Explicit values stage once in Python source order; only
pure temporary references are arranged in full formal order for the existing
structured `CCallExpr`. No runtime binder, `TypeError` channel, default
evaluation, coercion, allocation, ownership transfer, or cleanup model was
added.

Added complete positive and negative `keyword-only-call-binding-facts` under
`fact-table/0.14.3` and the helper-free
`phase14.keyword_only_call.exact_binding@0.14.3` RulePlan. The lowering shape is
`source-order-actual-temporaries-formal-order-references-v1`. Independent
validation reconstructs declaration kind, target, name binding, coverage,
categories, source/formal orders, C parameter order, and exact plan
correspondence before lowering.
Required-keyword-only declarations remain in the existing function-signature
facts without changing the serialized `ParameterFact` shape. Affected existing
`FunctionDef` RulePlans gain explicit keyword-only parameter and
C-interface-mode-erasure facts and obligations, and independent validation
covers admitted declarations even when they have no call site.

No new source diagnostic code is required. `PYC2904` retains missing coverage
and excess positional arity, `PYC2905` exact representation mismatch, `PYC2910`
unpacking and excluded call shapes, and `PYC2912` exact name-binding failures.
Under active 0.14.3 identities `PYC2911` continues to reject defaults,
defaulted keyword-only parameters, variadics, and keyword-only declarations
outside the exact required profile; it no longer rejects an otherwise eligible
required keyword-only declaration solely because `kwonlyargs` is nonempty.
Historical 0.14.2 diagnostics remain unchanged.

Advanced the active rule set to
`phase14-required-keyword-only-calls-v0.14.3`, renderer to
`c-renderer-v0.14.3`, and conversion-plan, C IR, generated-C, summary, and
decision-trace envelopes to 0.14.3. SourceBundle 0.2, Python IR 0.4, result
serialization 0.5, target and semantic policies, the helper registry, and all
container/module/record/numeric/conditional policies remain frozen.

Explicit 0.14.2 and earlier requests retain their exact facts, plans,
diagnostics, generated-C bytes, and fingerprints. Under active 0.14.3
identities, sources selecting no Phase 14D declaration or call behavior retain
Phase 14C generated-C bytes and output fingerprints. Required keyword-only
support adds no C IR syntax kind, renderer grammar, helper, host discovery, or
toolchain surface. Generated C remains source-validated only and is not
compiled, linked, loaded, or executed. Defaults, variadics, unpacking, dynamic
targets, methods, recursion, exceptions, closures, generators, async behavior,
and every neighboring Phase 14 family remain excluded. Phase 15 has not
started.

Promotion passed 539 discovered tests: 524 passed, 15 skipped, and zero failed.
The skips are exactly 10 for unavailable PyQt5 and five for unavailable older
custody artifacts. The focused Phase 14D gate passed 65 of 65 tests. Every
active cumulative audit passed, including the required-keyword-only and
Phase 14D transition audits.

Two fixed-epoch builds produced the same 340,054-byte
`pycforge-0.14.3-py3-none-any.whl`, SHA-256
`c0dd0c0ed79131daa5af815a8a9bb096b9f955c9c617ec0b8eb6a10c69d27b7f`.
The wheel archive and `RECORD` each account for 132 members: 17 SVG assets and
zero native-code members. Two normalized source-archive builds were likewise
byte-identical. The promoted converter subtree SHA-256 is
`74b32c25e40af3398dd46288941812ce7ad87f0d4b72fec3d3bd786cc1b8f3a8`.

Release validation remained source-only: no gate compiled, linked, loaded, or
executed generated C. No new actual PyQt5 widget or Windows 11 execution is
claimed. Historical opening records remain preserved, and Phase 15 has not
started.

## 0.14.2 — Phase 14C direct exact keyword calls

Status: promoted and sealed.

Added one closed compile-time binding profile for explicit keyword arguments on
already-resolved direct source-function calls. Calls may use a leading ordinary
positional prefix followed by one or more explicit named keywords. Every
required formal is bound exactly once, positional-only formals remain
positional-only, and actual/formal categories must match exactly. Same-module
and existing explicit cross-module source-function bindings are eligible;
dynamic targets, callable values, methods, defaults, keyword-only parameters,
variadics, `*`/`**` unpacking, recursion, `range` keywords, and record-
constructor keywords remain excluded.

Added independent keyword-call analysis and reconstruction,
`keyword-call-binding-facts` under `fact-table/0.14.2`, and the helper-free
`phase14.keyword_call.exact_binding@0.14.2` RulePlan. Argument values are staged
left to right and once in Python source order, then pure temporary references
are arranged in formal ordinal order for the existing structured `CCallExpr`.
No C IR node kind, renderer grammar, helper, runtime binder, failure channel,
allocation, ownership transfer, or cleanup model was added.

Added `PYC2912` for exact static name-binding failures: unknown keyword names,
positional-only names used as keywords, positional/keyword collisions, and
duplicate keywords. `PYC2910` remains the boundary for `*`/`**`, null keyword
names, unpacking, and other excluded keyword shapes. Existing target,
declaration, arity, category, record, `range`, and recursion diagnostics retain
precedence.

Advanced the active rule set, renderer, conversion plan, C IR, generated-C,
summary, and trace envelopes to 0.14.2. SourceBundle 0.2, Python IR 0.4, result
serialization 0.5, all public policies, the helper registry, Phase 14A numeric
facts/helpers, and Phase 14B `fact-table/0.14.1` conditional facts and RulePlans
remain unchanged. Explicit 0.14.1 requests retain their historical keyword
rejection and artifact behavior; active sources selecting no 14C call retain
predecessor generated-C bytes and output fingerprints.

Promotion authenticated the sealed Phase 14B source archive and wheel, passed
the cumulative suite and audits including the keyword and Phase 14/14B/14C
transition audits, sealed deterministic wheel and source-archive builds, and
passed isolated package validation. All release validation remained source-only;
generated C was not compiled, linked, loaded, or executed. PyQt5 was unavailable
in the release environment, so no new widget execution is claimed and sealed
offscreen-widget evidence remains preserved. Windows 11 execution is not
claimed. Phase 14D and Phase 15 have not started.

## 0.14.1 — Phase 14B conditional temporary regions

Status: Phase 14B promoted and sealed.

Added exact conditional placement for statement-producing temporaries belonging
to expressions already supported by the cumulative scalar subset. Boolean
`and`/`or` expressions now use an initialized Boolean result and flat guarded
assignments. Later operands of chained comparisons use guarded materialization
and rolling middle values, preserving left-to-right, exactly-once evaluation
without eagerly evaluating skipped operands.

Added independent conditional-region analysis and validation,
`fact-table/0.14.1` conditional facts, two 0.14.1 RulePlan families, and active
`conversion-plan/0.14.1`, `c-ir/0.14.1`, `generated-c/0.14.1`, summary, trace,
rule-set, and renderer identities. No Python syntax, primitive operation,
public policy, helper, runtime failure channel, allocation, ownership, cleanup,
or C IR node kind was added.

Preserved the sealed Phase 14A numeric policy and helper registry exactly.
Explicit 0.14.0 configuration retains its historical artifacts and placement
rejections; active sources that select no conditional region retain predecessor
generated-C bytes and output fingerprints. General exceptions, heap objects,
dynamic dispatch, closures, generators, async behavior, context cleanup, and
the broader class model remain excluded.

## 0.14.0 — Phase 14A bounded integer floor arithmetic

Status: Phase 14A sealed.

Added exact integer `//` and `%` for existing integer-like expressions when
the divisor is a direct signed integer literal in
`[-9223372036854775807, -2]` or `[1, 9223372036854775807]`. Zero, negative one,
`INT64_MIN`, Boolean, floating, dynamic, folded, calculated, and out-of-range
divisors reject deterministically.

Added separate numeric analysis and lowering, `fact-table/0.14` numeric
operation facts, the `phase14.numeric.floor_arithmetic` RulePlan family,
`conversion-plan/0.14`, `c-ir/0.14`, `generated-c/0.14`, and 0.14 summary and
decision-trace identities. The active numeric policy is
`phase14-proved-floor-arithmetic-v0.14`.

Activated the frozen `pycf.i64.floor_div@1.0.0` and
`pycf.i64.floor_mod@1.0.0` Phase 10 assets without changing their registry or
asset fingerprints. Each occurrence selects exactly one helper, and the
registry emits each selected helper once. Deterministic signed-64 temporaries
preserve left-to-right, exactly-once operand evaluation.

The admitted divisor proof excludes C11 division by zero and
`INT64_MIN / -1`; no runtime failure channel, exception emulation,
arbitrary-precision runtime, allocation, or cleanup was added. Mathematical
fixtures close Python floor quotient, divisor-sign remainder, and the division
identity across the supported sign and boundary cases.

Preserved exact explicit Phase 13 conversion behavior and the unchanged module,
record, container, workspace, no-host-discovery, and source-only product
boundaries. Generated C was not compiled, linked, loaded, or executed.

Phase 14A is sealed independently. Broader Phase 14 remains closed pending a
new decision and explicit approval. Phase 15 has not started.

## 0.13.0 — Phase 13 static records

Status: promoted.

Added a deliberately narrow immutable-record subset expressed with one exact
top-level Python class shape. Accepted records contain 1–64 ordered `int`,
`float`, or `bool` fields, an exact structural `__init__`, direct fresh
function-local positional construction, and direct statically resolved field
reads.

Added `fact-table/0.13` record definitions, fields, initializers, instances,
bindings, and accesses; seven record RulePlans; `conversion-plan/0.13`; record
nodes in `c-ir/0.13`; `generated-c/0.13`; and 0.13 summary and decision-trace
identities. The active record policy is
`phase13-immutable-automatic-records-v0.13`.

Record lowering emits deterministic named C `typedef struct` declarations and
fully initialized `const` aggregates in automatic function storage. Arguments
are evaluated left to right and once before construction; field reads use
direct member access. No record helper or runtime is selected.

General methods, inheritance and the broader Python object model remain
unsupported. Records cannot be mutated, aliased, rebound, copied, escaped,
passed, returned, stored in containers, imported, or used across modules.
There is no heap allocation, null state, ownership transfer, or cleanup.

Adversarial hardening added binding-identity constructor resolution,
read-after-construction and complete fresh-local proofs, dunder-field and
annotation-builtin collision rejection, correct companion-module diagnostics,
cooperative record cancellation, exact const/member and field-type C IR
validation, manifest-bound provenance, and independent serialized record-fact
cross-validation. Historical `fact-table/0.12` module records retain their
exact shape; record linkage remains in Phase 13 evidence.

An initial working candidate was abandoned when an external compile-only
review triggered the declared no-toolchain rollback rule. The release candidate
was reseeded from a newly authenticated 0.12.2 extraction; the incident remains
recorded and is not rewritten as passing evidence.

Preserved the Phase 12 function-import profile, Phase 11 containers, Phase 10
helper registry, source-only product boundary, and PyCForge workspace safety
model. Explicit historical Phase 12 requests retain their 0.12 identities, and
class-free Phase 13 conversions preserve predecessor generated-C bytes.

The sealed 0.12.2 predecessor was authenticated before Phase 13 edits. Windows
11 laptop testing remains planned user feedback after all phases; this release
does not claim Windows execution. Phase 14 has not started.

## 0.12.2 — PyCForge workspace hardening

Corrected conversion-generation retirement, Save As destination validation,
unexpected worker failure recovery, visible module identity commits,
document-reorder controls, Unicode replacement navigation, keyboard access,
and failure-tolerant versioned presentation settings without changing the
sealed Phase 12 converter.

## 0.12.1 — PyCForge workspace

Introduced the optional professional PyQt5 workspace over the sealed Phase 12
converter, including explicit bundle navigation, Python and immutable C
editors, diagnostics and mappings, stale-output protection, and atomic linked-C
saving.

## 0.12.0 — Phase 12 explicit module bundles

Introduced the bounded 1–64-document SourceBundle profile, exact compile-time
direct-function imports, deterministic dependency ordering, and one generated
C translation unit without host module discovery or runtime initialization.
