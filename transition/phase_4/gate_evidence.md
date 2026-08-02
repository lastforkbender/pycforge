# Phase 4 Gate Evidence

- Target C Source Contract remains Candidate.
- Source identity and normalized provenance remain StableInternal.
- C IR validates without consulting Python IR or conversion rules.
- Renderer output is byte deterministic and total over accepted C IR.
- Precedence, declarator, C keyword, reserved-name, and parentheses fixtures pass.
- Direct-source and synthetic provenance survive rendering into exact mapping ranges.
- The independent text-conformance validator accepts every positive renderer golden.
- Architecture audit enforces that rules and helpers cannot own final rendering.
- The production pipeline still stops at normalized Python IR.
