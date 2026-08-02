# Phase 14D Gate Evidence

Scope status: Phase 14D promoted and sealed for PyCForge 0.14.3.  
Evidence status: complete.

## Opening and predecessor authentication

- Phase 14D opened only after authenticating the promoted 0.14.2 predecessor.
  The 1,181,034-byte `pycforge_phase_14c_v0_14_2.tar.gz` archive matched
  SHA-256
  `1eb9666866f38dc80993a6f39175a0d98fdc1634f3aa3ab1eeb3dded2992ffb8`.
  Safe archive inspection, omitting only the exact Phase 14C release-
  fingerprint self-reference, independently reproduced canonical release-tree
  SHA-256
  `be433ef7a46bbb208efe82087b9ef924fad48eba42e42330c7964894a269bcb4`
  and converter-subtree SHA-256
  `ba4457158430bce7fb5094f68e1b07718bd168ca96e22310193efe45bd0d882b`.
- The sealed predecessor wheel is the 309,077-byte
  `pycforge-0.14.2-py3-none-any.whl`, SHA-256
  `6e14d24742e4bfff4017320ebdb04b35117c18fa95d97499560875a764feb4b5`.
- Architecture Revision 3.1, its Revision 3.2 addendum, frozen public
  policies, and the Phase 10 helper registry retained their authenticated
  identities. The helper-registry fingerprint remains
  `fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98`.
- The authenticated Phase 14A, 14B, and 14C transition subtrees retain SHA-256
  values
  `cb92282a063d72c22b6db41cd2c0d2da8b7bdb8cb3c5a3290530744a22d6fe8a`,
  `caddcbe153d005da9d67c14e182ecb6c6bde0e6e7a161dd50807a78aed7cd9e8`,
  and
  `95e5528fc7dca898a7d6883aed101d3a4c5fca5ef53988960307c50f610d04c5`.
- The opening decision, semantic specification, breadth budget, rollback
  conditions, and 14-item debt register admitted only required non-default
  keyword-only parameters on otherwise eligible direct top-level synchronous
  source functions. Defaults, variadics, unpacking, runtime binding, dynamic
  calls, helpers, allocation, new C IR syntax, neighboring Phase 14 families,
  and Phase 15 remained closed.

## Exact vertical-slice evidence

- Phase 14D adds one call-keyed `keyword-only-call-binding-facts` family under
  `fact-table/0.14.3` and exactly one call rule:
  `phase14.keyword_only_call.exact_binding@0.14.3`.
- An admitted declaration is an otherwise eligible top-level synchronous
  source function with one or more exactly annotated required keyword-only
  parameters. Formal order is positional-only, positional-or-keyword, then
  keyword-only. Every `kw_defaults` entry is null, and positional defaults,
  keyword-only defaults, `*args`, and `**kwargs` are absent.
- Required-keyword-only declarations remain in the existing function-signature
  facts without changing the serialized `ParameterFact` shape. Their existing
  `FunctionDef` RulePlans carry exact keyword-only parameter identity,
  parameter-count, and C-interface mode-erasure facts plus the obligations
  `required-keyword-only-parameters-exact`,
  `keyword-only-parameter-kinds-preserved`,
  `c-interface-mode-erasure-after-static-binding`, and
  `defaults-and-variadics-absent`. Independent validation covers admitted
  declarations even if no call site exists.
- An admitted call targets an already-resolved same-module or explicit
  SourceBundle-imported source function. Ordinary positional actuals bind only
  positional-capable formals. Explicit names may bind unbound
  positional-or-keyword or required keyword-only formals. Every required
  formal is supplied exactly once; positional-only formals are never supplied
  by keyword, keyword-only formals are never supplied positionally, and every
  actual has the exact established category and representation required by its
  formal.
- Explicit actuals stage once in Python source order. The existing structured
  `CCallExpr` receives only pure temporary references in complete formal order.
  The exact lowering shape is
  `source-order-actual-temporaries-formal-order-references-v1`. Existing
  `CParameter` nodes express the C declaration in that same formal order; no C
  keyword-only syntax or runtime mechanism is introduced.
- Independent validation reconstructs declaration eligibility, parameter
  kinds and names, target identity, exact binding and coverage, actual
  categories, both order vectors, C parameter order, provenance, RulePlan
  correspondence, cumulative target eligibility, and complete negative
  evidence before lowering. Malformed, duplicate, or inconsistent facts,
  signatures, plans, dependencies, orders, or bindings fail closed without a
  partial generated-C successor.
- Cancellation checks cover discovery, declaration analysis, source-order
  reconstruction, binding, plan lookup, independent validation, actual
  staging, and formal-vector assembly. Cancellation, observer failure,
  rejection, resource exhaustion, or internal validation failure publishes no
  partial successor.
- The central cumulative lowerer is exactly 1,000 lines, at but not above its
  1,000-line architecture ceiling. Phase 14D adds no C IR node kind, renderer
  syntax, support helper, public policy, runtime binder, runtime failure
  channel, allocation, ownership transfer, or cleanup model. The final
  converter-subtree SHA-256 is
  `74b32c25e40af3398dd46288941812ce7ad87f0d4b72fec3d3bd786cc1b8f3a8`.

## Diagnostics, hardening, and compatibility

- No new source diagnostic code was introduced. `PYC2904` retains missing
  required coverage and excess positional arity, including entry into the
  keyword-only range; `PYC2905` retains exact representation mismatch;
  `PYC2910` retains `*`/`**`, null keyword names, and excluded call shapes;
  `PYC2912` retains unknown names, positional-only names used by keyword,
  collisions, and duplicates; and `PYC2911` retains defaults, defaulted
  keyword-only parameters, variadics, and declarations outside the exact
  required profile.
- Under active 0.14.3 identities, `PYC2911` no longer rejects an otherwise
  eligible declaration solely because it has required keyword-only
  parameters. Explicit 0.14.2 requests preserve the historical rejection and
  exact Phase 14C contracts, diagnostics, facts, plans, generated C, and
  fingerprints.
- The keyword-only audit proved same-module and explicit cross-module binding,
  source/formal order separation, declaration evidence, complete negative
  facts, no helper selection, observer isolation, cancellation custody, and
  fresh-process determinism. Its accepted witness contains one keyword-only
  fact and one call RulePlan. Its generated-C SHA-256 is
  `4d3603d82dbb61ea54e0406807f6f2c4913ea835e4e74435d0c8f4e200e2ae01`;
  its serialized-result SHA-256 is
  `d772a4c5cfd5bc2fe84c12f9685cf1193b83f732a3b7b94d575f03d4030e4f83`.
  The standalone audit closes nine negative cases; the authenticated
  validator independently closes a 16-case rejection matrix.
- The sealed Phase 14C keyword audit still passes. Its generated-C SHA-256 is
  `3d99653c0f0e1ee86a8508fdd618d19f9bb4f1de93012325f1bc3552f8a3e671`,
  and its serialized result under the current compatible envelope has SHA-256
  `ebe91b4eec14220f2df452d38afbae7931e8886ebf5fe647de54e5e1918b0070`.
- Active sources selecting no Phase 14D declaration or call behavior retain
  Phase 14C generated-C bytes and output fingerprints. Cumulative function
  eligibility, same-module and cross-module targeting, recursion rejection,
  diagnostic precedence, cancellation, malformed-evidence hardening, and
  source-output mapping regressions passed.
- Independent-review reconciliation proved that validation reconstructs
  annotation categories from normalized Python IR instead of trusting mutable
  dependency facts; verifies the complete call-target support, resolution,
  diagnostic, and reason state; and admits only exact rule-set/renderer
  profile pairs. Mid-wide-signature cancellation checkpoints were injected
  across declaration analysis, independent reconstruction, C parameter
  assembly, and formal-reference assembly.
- Release-validator hardening requires the source archive's embedded Phase 14D
  fingerprint to match the exact root fingerprint bytes before self-exclusion,
  admits exactly one normalized gzip member, and requires the manifest itself
  to declare every canonical promotion file.

## Promotion and packaging evidence

- The promoted release suite discovered 539 tests: 524 passed, 15 skipped, and none
  failed. Ten skips were the expected PyQt5-unavailable GUI cases; five were
  tests requiring unavailable older sealed-predecessor custody artifacts.
  All 65 Phase 14D tests passed.
- Architecture, rules, helpers, containers, modules, records, numeric,
  conditional, keyword, keyword-only, determinism, sealed Phase 14C
  transition, and Phase 14D transition audits passed. The cumulative
  determinism SHA-256 is
  `6d132fa7544ea5d8b609689907c014b14c663cdd4999b47d921836182c38a35a`.
- The authenticated Phase 14D validator passed active and historical
  contracts, accepted same-module and cross-module witnesses, the closed
  rejection matrix, malformed-evidence hardening, cancellation, determinism,
  predecessor archive and wheel authentication, and package checks.
- Two fixed-epoch wheel builds were byte-identical. The final wheel is
  `pycforge-0.14.3-py3-none-any.whl`, size 340,054 bytes, SHA-256
  `c0dd0c0ed79131daa5af815a8a9bb096b9f955c9c617ec0b8eb6a10c69d27b7f`.
  Its 132 RECORD members include 17 SVG assets and no native binary.
- A clean isolated wheel installation passed installed same-module and
  explicit SourceBundle keyword-only conversion, the installed keyword-only
  audit, workspace linked-C atomic save, stale-output save blocking, and an
  injected atomic-write failure.
- The normalized source artifact is
  `pycforge_phase_14d_v0_14_3.tar.gz`. Two fixed-epoch normalized builds were
  byte-identical. Its size and SHA-256 are recorded externally to avoid
  embedding an archive identity inside itself. The canonical release-tree
  SHA-256 is authenticated by
  `transition/phase_14d/release_fingerprint.json`; that file alone carries the
  value and is excluded from its own hash domain.

## Toolchain and platform custody

Phase 14D validation uses Python IR, immutable facts and RulePlans, structured C
IR, independent conformance checks, deterministic rendering, and isolated
package-install evidence. No C compiler, linker, loader, foreign-function
bridge, or generated-C execution path was invoked. Generated C was never
compiled, linked, loaded, or executed. PyCForge still exposes no compilation,
linking, loading, execution, debugging, terminal, package-discovery, or host
import-resolution surface.

PyQt5 was unavailable in the release environment, so the 10 GUI tests retained
their expected skips and sealed offscreen-widget evidence remains in custody.
Five additional skips were limited to older sealed-predecessor custody
artifacts unavailable in this environment. Windows 11 laptop testing remains
downstream user feedback; no Windows 11 execution or validation claim is made
for 0.14.3.

Phase 14D is promoted and sealed as PyCForge 0.14.3. No neighboring phase or
excluded family opens automatically. Phase 15 has not started.
