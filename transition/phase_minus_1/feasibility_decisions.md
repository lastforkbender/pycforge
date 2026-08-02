# Phase -1 Feasibility Decisions

| Risk area | Initial classification | Decision |
|---|---|---|
| evaluation order | supported directly | explicit sequencing facts and temporaries where C order is not guaranteed |
| unknown/contradictory evidence | unsupported boundary | distinct fact states; neither may silently select a rule |
| numeric overflow/division/modulo | deferred beyond milestone | fixed-width milestone is bounded; checked semantics require later rules |
| strings | deferred | UTF-8 source policy fixed; runtime string representation not frozen |
| function signatures | supported directly for milestone | exact annotated int64 positional function only |
| lists/dictionaries | deferred | representation spikes required before Phase 11 |
| nested scopes | deferred | stable binding IDs mandatory; closure behavior unsupported initially |
| classes | deferred | explicit static record subset only in Phase 13 |
| helper closure | supported with registered helpers | exact-version deterministic dependency closure, no arbitrary text |
| source/output mapping | supported directly | provenance-driven many-to-many mapping, never string search |
| node identity | supported directly | stable per source revision; synthetic IDs use a distinct domain |
| trace/telemetry isolation | supported directly | separate immutable schemas, budgets, and fingerprint rules |
