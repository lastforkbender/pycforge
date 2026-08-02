# Phase 15B Gate Evidence

Status: supporting source/headless gate satisfied  
Distribution: PyCForge `0.15.1`  
Workspace contract: `pycforge-workspace/0.4`  
Converter contract: `0.14.3`  
Worker protocol: `pycforge.worker-protocol/0.1`  
Action registry: `pycforge.action-registry/0.1`  
Visual system: `pycforge.visual-system/0.1`  
Presentation settings: schema `1`

## Scope of this gate

Phase 15B is a presentation and application-command milestone. Its supporting
gate checks the declarative action authority, native-backed custom menu
contracts, semantic visual tokens, SVG assets, keyboard/high-DPI/accessibility
foundations, product identity, frozen converter boundary, and preservation of
Phase 15A responsiveness.

PyQt5 is unavailable on the validation host. This record therefore contains
source, static, headless, and contract evidence. It does not convert those
checks into visible platform evidence.

## Predecessor custody

Phase 15B began from the authenticated Phase 15A release:

- source archive: `pycforge_phase_15a_v0_15_0.tar.gz`;
- source archive size: 1,480,105 bytes;
- source archive SHA-256:
  `da33821ef82d948a9204af76baa5495ae2ff5df4500b12f4a67c12663cd95a06`;
- release-tree fingerprint:
  `52014b9bd92912fe25b5d2faf42a388e98e828be66a3b371277d552666cf172a`;
- converter-subtree SHA-256:
  `a45bc2c31b954f9856c8eab36e95f68b086d5fdd682d2cf47ba2186887743124`;
- package: `0.15.0`;
- workspace: `pycforge-workspace/0.3`; and
- worker protocol: `pycforge.worker-protocol/0.1`.

The authenticated predecessor archive remains authoritative for original
pre-migration bytes. Phase 15B receives its own release fingerprint and does
not mutate that archive.

## Identity evidence

Static identity checks establish:

- package `0.15.1`;
- workspace `pycforge-workspace/0.4`;
- action registry `pycforge.action-registry/0.1`;
- visual system `pycforge.visual-system/0.1`;
- unchanged converter `0.14.3`;
- unchanged worker protocol `pycforge.worker-protocol/0.1`; and
- unchanged presentation settings schema `1`.

The current source and distribution use PyCForge identity exclusively. The
legacy presentation-namespace migration and compatibility surface are removed.
A case-insensitive path and byte scan is a mandatory release condition.

## Declarative-action evidence

The action contract is import-safe and independent of PyQt. It provides one
closed declaration for each persistent command and rejects duplicate IDs,
duplicate placements, unknown icons, invalid mnemonics, unsafe shortcuts,
missing accessibility text, and surface drift.

Supporting checks establish that:

- stable IDs own labels, mnemonics, icons, shortcuts, tooltips, status
  explanations, accessible names, checkability, tones, and allowed surfaces;
- the Qt adapter creates each persistent `QAction` once;
- menus, toolbars, context surfaces, and bounded dynamic entries consume the
  registry;
- enablement and checked state project controller state without replacing exact
  revision or Save C authority; and
- persistent actions are not created ad hoc by individual widgets.

## Menu evidence

Source and contract checks cover custom PyCForge File, Edit, View, and
Transpile menus plus context menus for Python source, generated C, Source
Bundle navigation, diagnostics, mappings, Conversion Summary, Decision Trace,
and Telemetry.

The menus retain native `QMenu` and `QAction` interaction mechanics for:

- keyboard traversal;
- mnemonics;
- shortcut columns;
- checked and disabled state;
- focus return;
- Escape and outside-click dismissal;
- submenu behavior;
- assistive exposure; and
- screen-edge placement.

The generated-C context menu is a closed read-only allowlist. Source audits
reject Undo, Cut, Paste, Replace, formatting, refactoring, or another mutation
command on that surface.

## Visual evidence

Static visual-token checks cover semantic surfaces, text roles, borders,
separators, focus and selection accents, transpilation accent, and
success/warning/error/danger states.

SVG audits require:

- a logical `0 0 24 24` view box;
- no raster elements or embedded raster payload;
- no remote, file, or data references;
- no script or foreign object;
- no font-glyph dependency;
- no fixed physical width or height; and
- a closed logical icon catalogue.

Supporting source checks cover gradient menu surfaces, visible labels and
icons, shortcut columns, selection rails, submenu indicators, disabled and
danger treatment, logical icon dimensions, icon-only tooltips and accessible
names, and stable menu accessible names.

The interface has no animation and is reduced-motion safe by construction.

## Responsiveness evidence

The Phase 15A asynchronous architecture remains binding. Phase 15B source
changes do not move conversion, revision/index construction, file I/O, hashing,
literal search, or atomic writes back onto the GUI thread.

Supporting checks preserve:

- spawned child-process conversion;
- one active plus one replaceable latest pending request;
- cooperative cancellation with bounded hard termination and reaping;
- exact generation, revision, bundle, request, and transport publication
  guards;
- stale, failed, canceled, malformed, oversized, partial, and superseded
  result suppression;
- bounded large-file editor projections; and
- incremental generated-C installation with deferred hidden work.

Action enablement and menu refresh remain bounded presentation projections.
They neither invoke the transpiler nor scan complete source bundles or the host
environment.

Structured Summary, Decision Trace, and Telemetry data is projected
iteratively with cycle detection and absolute limits of 1,024 nodes, 16
levels, 256 children per container, and 2,048 characters per displayed value.
Pending identity edits immediately disable Save C and mark output stale.
Cancellation-pending diagnostics are treated as non-current.

## Release-custody evidence

Promotion hashes one descriptor-bound and size-bounded source snapshot.
Snapshotted project configuration and converter bytes are validated directly;
no live-tree reread can substitute another candidate. The validation-subject
digest excludes only the validation report and release fingerprint, and the
final release fingerprint then includes the report.

Packaging requires the pinned Python, compression library, and Python package
tool versions. It compares two fixed-epoch wheel builds and two normalized
source builds, inspects and smokes a sealed copy of the exact wheel bytes to be
published, rejects duplicate-key, non-finite, or noncanonical validation JSON,
and verifies the final vocabulary and checksum graph.

All seven deliverables are written to a private sibling staging directory,
synchronized, and published as one directory under an exclusive publication
lock. Any failure before the atomic directory rename leaves the requested
output absent.

## Transpiler safety evidence

PyCForge remains a deterministic Python-to-C source transpiler. Generated C is
read-only and explicit-save-only. Phase 15B adds no compilation, assembly,
linking, loading, execution, debugging, terminal, toolchain, project discovery,
plugin, or generated-code runtime surface.

The supporting validation commands are:

```text
python -m unittest tests.test_phase15b_action_foundation
python -m unittest tests.test_phase15b_visual_foundation
python -m unittest tests.test_phase15b_visual_integration
python -m unittest tests.test_phase15b_release_contract
python -m unittest tests.test_validate_phase15b
python -m unittest tests.test_phase15b_release_packaging
python tools/validate_phase15b.py --mode promotion
python -m unittest discover -s tests
```

No Phase 15B validation step invokes a C toolchain or executes generated C.

Final discovery runs 750 tests: 734 pass, 16 are expected skips, and zero fail.
Eleven skips require unavailable PyQt5 widgets; five require unavailable older
optional custody artifacts.

## Platform evidence boundary

Because PyQt5 is unavailable on the validation host, Phase 15B does not claim:

- visible Windows 11 behavior;
- visible Linux desktop behavior;
- real display-scaling coverage;
- assistive-technology integration;
- visible focus, menu placement, or dismissal behavior; or
- visible rendering quality.

Those real platform gates remain mandatory in Phase 15D. Phase 15C and Phase
15D remain unopened.
