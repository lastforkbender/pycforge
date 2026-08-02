# Phase 2 Headless Laboratory Contract

The laboratory is a client of the StableInternal converter facade. It may submit requests, serialize completed results, inspect compatible immutable artifacts, run audits, and atomically save evidence. It may not parse Python independently, select conversion rules, build C IR, render generated C, invoke a native toolchain, or depend on PyQt.

Commands expose stable exit categories: success (0), conversion rejection (2), cancellation (3), internal failure (4), usage (64), incompatible artifact (65), I/O failure (74), and audit failure (78). JSON and text views are projections of the same `ConversionResult` facts. Operational telemetry is excluded from semantic diffing.
