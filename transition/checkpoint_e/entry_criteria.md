# Checkpoint E Entry Criteria

Status: satisfied for documentation-only opening on 2026-07-26; implementation,
promotion, packaging, and release are not claimed

## Authenticated predecessor

- PyCForge 0.14.3 / Phase 14D is the sealed predecessor.
- Its release report records 539 discovered tests: 524 passed, 15 expected
  skips, and zero failures. The focused Phase 14D gate passed 65 of 65 tests.
- Its promoted wheel is `pycforge-0.14.3-py3-none-any.whl`, 340,054 bytes,
  SHA-256
  `c0dd0c0ed79131daa5af815a8a9bb096b9f955c9c617ec0b8eb6a10c69d27b7f`.
- Its promoted converter-subtree SHA-256 is
  `74b32c25e40af3398dd46288941812ce7ad87f0d4b72fec3d3bd786cc1b8f3a8`.
- Phase 14D’s source archive, transition records, contracts, generated-C
  identities, and historical predecessor custody remain sealed.

## Authority

The user requested an extreme-high-quality, next-generation PyCForge
application with professional IDE features, custom gradient/icon main and
context menus, and no hangs or freezes during large-file conversion.

Checkpoint E is the hardening boundary in which that requirement is specified
and measured before Phase 15. It does not silently open another Phase 14
semantic family and does not turn PyCForge into a compiler.

## Naming and product boundary

- The application-facing name is `PyCForge`.
- No alternate theme-derived active product or component name is allowed.
- Original pre-migration bytes remain authoritative in the authenticated Phase
  15A archive.
- Generated C remains immutable.
- The application has no run, build, compile, link, load, debug, terminal,
  toolchain, plugin, project-explorer, host-discovery, or generated-C editing
  surface.

## Architecture readiness

- The current headless controller already captures a frozen source bundle,
  advances a request generation, cooperatively cancels older work, and guards
  result publication with generation and bundle fingerprint.
- The current PyQt bridge uses queued signals to return worker snapshots to the
  GUI thread and retains stale-output and atomic-save custody.
- These are correctness foundations, not sufficient responsiveness evidence.
  The current single in-process thread worker cannot hard-stop a
  non-cooperative conversion, and eager GUI projection contains main-thread
  work proportional to full source, output, mappings, and observer trees.
- The accepted future architecture therefore uses a process-isolated
  conversion worker, bounded latest-wins scheduling, and lazy/virtualized
  presentation.

## Resource-envelope readiness

The existing `ResourcePolicy` declares the stress ceilings used by Checkpoint E:

| Resource | Gate ceiling |
|---|---:|
| aggregate UTF-8 source | 1,000,000 bytes |
| aggregate source lines | 100,000 |
| aggregate tokens | 250,000 |
| aggregate AST nodes | 100,000 |

The gate uses independent near-ceiling fixtures, a valid combined-envelope
fixture, and over-limit rejection fixtures. A tiny demonstration file is not
performance evidence.

## Opening completion

Checkpoint E validation may begin only after all of the following opening
records exist:

- `docs/pycforge_workspace_quality_addendum.md`;
- architecture/workspace, performance, feature-boundary, change-budget, and
  rollback decisions under `transition/checkpoint_e/`;
- an opening evidence record; and
- owned initial workspace debt and entry reports under
  `evidence/checkpoint_e/`.

This opening changes no Python source, version, active converter contract,
historical transition, release report, manifest, or release fingerprint. Phase
15 implementation still requires separate authorization after Checkpoint E is
sealed.
