# Target C Source Contract — `c11-portable-fixed-v1`

- Language: portable ISO C11 source; no extensions.
- Encoding and layout: ASCII spelling for generated identifiers and syntax, escaped UTF-8 bytes in string literals, `\?` protection against C11 translation-phase trigraphs, LF line endings, final newline.
- Headers: registered system includes only. `<stdint.h>` is emitted when fixed-width integers occur; `<stdbool.h>` is emitted when Boolean types or literals occur.
- Integer mapping: bounded Python `int` evidence maps to signed `int64_t`. Operations are valid only within the declared representable domain; arbitrary-precision overflow equivalence is not claimed.
- Float mapping: finite source literals and annotated values map to `double` within the selected failure-policy boundary.
- Boolean mapping: C `bool`, `true`, and `false` from `<stdbool.h>`.
- String mapping: immutable UTF-8 literals and borrowed `const char *`; embedded NUL rejects.
- Functions: source functions use external linkage. Multi-document source functions use deterministic reserved `pycm_` module-qualified spellings; singleton/no-import requests retain legacy source spellings. Registered helper functions use reserved `pycf_` spellings and internal `static` linkage. Every function has one deterministic prototype, all prototypes precede definitions, and ordered signatures match exactly.
- Calls: binding-backed direct calls only. Positional and admitted Phase 14C
  keyword actuals are evaluated once, staged left to right in Python source
  order, and passed as pure temporary references in formal order.
- Identifiers: centralized deterministic allocation; no C keyword, leading underscore, standard fixed-width/type/macro name, ISO C11 library external-linkage identifier, hosted `main` collision, unauthorized `pycf_`/`pycm_` collision, normalized collision, or duplicate linkage spelling.
- Declarations: C11-compatible structured declarations with validator-proved scope and type consistency.
- Conditional regions: initialized automatic scalar temporaries and flat
  structured `if` blocks only; branch-local prerequisites, exact Boolean guard
  polarity, once-only middle-value reuse, and declaration-before-read are
  validator-proved. No conditional expression, statement expression, raw C, or
  `goto` is introduced.
- Records: validated named `typedef struct` definitions with 1–64 ordered
  scalar members, followed by fully initialized object-level `const` automatic
  aggregates. Source record reads use direct member access. There is no heap,
  nullable record, constructor function, method table, runtime tag, or cleanup.
- Preprocessor: registered includes only; no source-controlled directives.
- Helpers: interface identity `pycforge-helper/1`; exact registered versions only, structured C IR factories only, target/ownership/failure validation required, and each resolved helper emitted once. Phase 14A floor arithmetic may select only the frozen signed-64 floor-division and modulo helpers after static safe-divisor proof. Phase 12 module, Phase 13 record, Phase 14B conditional-region, and Phase 14C keyword-call RulePlans select no helpers; helper emission remains the exact union required by all cumulative RulePlans.
- Output boundary: source only. The application never compiles, links, loads, executes, or behaviorally validates this C.
- Translation unit: exactly one generated C translation unit per publishable SourceBundle; no module header, source-controlled include, module initializer, second source file, object, or link instruction.

The contract deliberately excludes assumptions about plain `char` signedness, native `int` width, locale, signed-overflow wrapping, unspecified operand evaluation order, a Python object runtime, or a native toolchain.
