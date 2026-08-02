# Product Boundary — PublicStable 1.0

PyCForge is a Python-to-C **source converter**.

Canonical flow:

> explicit Python source bundle → conversion pipeline → complete generated C source → inspect or save → stop

## Included

PyCForge accepts explicitly supplied Python source, analyzes only what conversion requires, produces readable deterministic C source, emits structured diagnostics and decision evidence, and permits completed source artifacts to be viewed or atomically saved.

## Permanently excluded

PyCForge shall not compile, link, execute, benchmark, debug, sanitize, or runtime-verify generated C. It shall not discover or invoke GCC, Clang, MSVC, a linker, debugger, terminal, executable, or native build system. It shall not import, evaluate, or execute user Python source.

A successful conversion means only that a complete source artifact satisfies PyCForge's declared contracts and structural validation.
