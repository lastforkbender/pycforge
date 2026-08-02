# PyCForge 0.15.2

PyCForge 0.15.2 is the first public PyPI and GitHub release of the Phase 15C
IDE-grade Python-to-C transpiler workspace. The converter contract remains
sealed at `0.14.3`.

## Installation

```bash
python -m pip install pycforge
```

The base package now requires `PyQt5>=5.15.11,<6`. A normal installation
therefore installs the desktop application without an extra. Launch it with:

```bash
pycforge-workspace
```

Headless conversion remains available through `pycforge` or
`python -m pycforge`.

## Highlights

- deterministic, independently validated ISO C11 source generation;
- a bounded one-to-64-document source workspace;
- process-isolated conversion with cancellation and stale-result suppression;
- professional PyQt5 authoring, navigation, search, inspection, and telemetry;
- 55 self-contained SVG interface icons;
- immutable generated-C inspection and guarded explicit saves; and
- GPLv3 source distribution compatible with the required PyQt5 runtime.

## Verification

Release gates build both the wheel and source distribution, validate PyPI
metadata, install the wheel into a clean environment, require PyQt5 to be
present without extras, construct the real workspace under Qt's offscreen
backend, exercise the command-line converter, and run the complete repository
test suite.

## Known generated-C note

Generated floor-division or modulo helpers are valid ISO C11 and convert
without diagnostics, but GCC with `-Wall -Wextra` may emit a `-Wparentheses`
warning for the current sign-comparison spelling. Projects that promote all
warnings to errors can temporarily add `-Wno-parentheses`. No generated C is
compiled or executed by PyCForge itself.

The supplemental conversion reference is attached to the GitHub release as
`PyCForge_v0_15_2_Conversion_Examples_Reference_Edition.pdf`.

