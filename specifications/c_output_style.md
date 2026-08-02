# Generated-C Style — `professional-readable-v1`

- deterministic UTF-8-compatible source, LF, final newline;
- four-space block indentation;
- one declaration or statement per line;
- function and control braces on the following line;
- all prototypes before all definitions;
- named record `typedef struct` declarations before all prototypes, with one
  scalar member per line in source field order;
- internally linked helper prototypes before helper definitions, ordered by the
  resolved dependency plan;
- explicit fixed-width integer and Boolean types with minimal required includes;
- stable binding-backed semantic names and `pycf_...` synthetic temporaries;
- fixed extents adjacent to the declared identifier and correct read-only
  declarators, including `const char * const names[2]`;
- dictionary component suffixes such as `_keys` and `_values`, with the same
  deterministic collision handling as source names;
- fully initialized `const` automatic record aggregates and direct `.` member
  reads, with construction arguments staged in source order;
- Phase 14A signed-64 left, right, and result temporaries in proved evaluation
  order, followed by a direct call to the exact internally linked helper;
- Phase 14B initialized Boolean results and flat sibling guards, with every
  conditional operand's complete prerequisite sequence indented inside its
  branch and no operand-count-deep guard nesting;
- Phase 14C argument temporaries declared in Python source order, followed by a
  direct call containing only pure references in formal parameter order;
- precedence-preserving parentheses, including lexical separation of nested unary operators;
- no compiler-specific attributes, extensions, handwritten rule fragments, or claims of compilation/execution.

Example shape:

```c
#include <stdint.h>

int64_t add(int64_t a, int64_t b);

int64_t add(int64_t a, int64_t b)
{
    return a + b;
}
```

Representative Phase 13 shape:

```c
#include <stdint.h>

typedef struct Point {
    int64_t x;
    int64_t y;
} Point;

int64_t total(void);

int64_t total(void)
{
    int64_t pycf_record_arg_0 = 10LL;
    int64_t pycf_record_arg_1 = 20LL;
    const Point point = {pycf_record_arg_0, pycf_record_arg_1};
    return point.x + point.y;
}
```

The exact generated identifiers are binding-backed and may differ from this
illustrative spelling when collision or module qualification requires it.
