# Phase 12 Gate Evidence

Status: passed and promoted on 2026-07-22.

Phase 12 evidence proves:

- 1-, 2-, and maximum-document SourceBundles with exact canonical identities;
- every approved alias/multiple-name absolute import form end to end;
- exact SourceBundle-only resolution with instrumented proof that source imports
  perform no filesystem, environment, network, import-cache, or installed-package discovery;
- complete immutable module/import/namespace/dependency/initialization/name facts
  and closed module RulePlans;
- dependency-first module-ID-tied order, cycle rejection, and bundle-wide call
  recursion checks;
- external `pycm_` source linkage, unchanged static `pycf_` helper linkage, and
  one validated translation unit with complete prototype/definition order;
- no runtime module initialization/global state and no source-controlled include;
- correct importer/target document diagnostics and mapping relationships;
- one independent negative fixture for every `PYC3501`–`PYC3510` primary code,
  with no partial C IR/helper/mapping/generated output;
- byte-identical singleton/no-import generated C against Phase 11;
- historical schema/helper/container fingerprints and predecessor regressions;
- deterministic fresh-process output across hash seed, locale, timezone,
  temporary path, CPU count, and supported Python patch versions;
- cancellation, observer isolation, stale-output, atomic-save, package/wheel,
  and independent non-executing generated-text conformance gates.

All generated C validation must remain structural and textual. No C or helper
source may be compiled, linked, loaded, or executed.

## Recorded result

- 189 tests passed: 169 predecessor regressions and 20 Phase 12 tests.
- Every `PYC3501` through `PYC3510` primary boundary has an independent
  no-partial-output negative fixture.
- Architecture, rules, helpers, containers, modules, determinism, and
  transition audits passed; all twelve generated evidence reports are fresh.
- Instrumented resolution checks observed no filesystem, environment, import
  hook/cache, installed-package, or network discovery.
- Historical C IR 0.8 through 0.11 fixture bytes, Phase 11 scalar/container
  generated-C bytes, and Phase 10 helper fingerprints match sealed identities.
- Four fresh module-bundle processes were byte-identical while varying hash
  seed, timezone, locale, temporary root, CPU-count observation, and Python
  3.12.3 versus 3.12.13.
- Two `SOURCE_DATE_EPOCH=1735689600` wheel builds were byte-identical. The
  154717-byte wheel has SHA-256
  `ef9db5222c5ce023861ffb558717d00c1d01d5931c558a385b96158863ae47c5`.
- The authenticated wheel installed in an isolated environment and passed the
  module/container vertical slice, schema, mapping, text-conformance, and
  helper-fingerprint checks.
- PyQt5 was unavailable, so no new widget run is claimed. Preserved sealed
  widget evidence and cumulative GUI/controller regressions remain intact.
- Generated C and helper sources were never compiled, linked, loaded, or
  executed.
