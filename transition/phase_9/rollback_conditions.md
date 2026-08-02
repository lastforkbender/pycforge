# Phase 9 Rollback Conditions

Reject this candidate and retain v0.8.0 if any of the following is observed:

- a call target is accepted without one deterministic eligible binding;
- a positional argument can be evaluated out of order or more than once;
- a call prerequisite crosses a Python short-circuit boundary eagerly;
- a prototype, definition, call, return, declaration, or reference bypasses C IR validation;
- reachable implicit `None`, incompatible return, use-before-binding, representation conflict, loop lifetime, recursion, or ownership remains unresolved;
- unsupported defaults, keywords, unpacking, variadics, aliases, dynamic callables, nested functions, or recursion publish C;
- rule/explanation/mapping state diverges from the immutable plan;
- observers, GUI state, host paths, timing, or registration order change semantic artifacts;
- cancellation, resource exhaustion, rejection, internal failure, or stale workspace state publishes/saves new C;
- any prior phase test, architecture/rule/determinism/transition audit, or Phase 9 validator fails;
- a compiler, linker, executable, runtime comparison, or native toolchain enters the product path;
- the promoted Phase 8 archive changes from SHA-256 `c30bb745aa0c471683c8056ca017aa501366ecdb4e3c4c4c16d905658015cbc6`.
