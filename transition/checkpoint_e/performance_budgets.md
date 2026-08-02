# Checkpoint E Performance and Liveness Budgets

Status: mandatory candidate gates  
Measurement surface: real PyQt application on every declared release platform

## Test envelope

Performance evidence must include:

1. a fixture approaching 1,000,000 aggregate UTF-8 source bytes;
2. a fixture approaching 100,000 aggregate source lines;
3. a fixture approaching 250,000 aggregate tokens;
4. a fixture approaching 100,000 aggregate AST nodes;
5. a valid fixture simultaneously within all four ceilings;
6. one cleanly rejected fixture over each ceiling; and
7. large generated-C, 1,000-diagnostic, 5,000-visible-mapping, 10,000-trace
   event, and 10,000-telemetry-event projections.

The fixtures must exercise the closed SourceBundle and may be distributed over
up to 64 explicit documents. Each metric is recorded with corpus identity,
machine CPU/RAM, operating system, Qt/PyQt version, display backend, scaling,
warm/cold status, and at least 20 measured repetitions where repetition is
practical.

## Event-loop gate

A monotonic probe driven by a 16 ms Qt timer records event-loop service during
open, edit, search, convert, cancel, result publication, inspector expansion,
file-change handling, and close.

| Interaction | Required budget |
|---|---:|
| worst event-loop service gap during conversion | no gap over 100 ms |
| worst event-loop service gap during result publication | no gap over 100 ms |
| worst event-loop service gap during editor/search/menu use | no gap over 100 ms |
| any interval treated as a visible hang | 250 ms or more |
| allowed visible-hang intervals | 0 |

The 100 ms budget is an upper bound, not a target. Median and p95 gaps must also
be reported. A passing average cannot hide one long freeze.

## Command and editing latency

| Action | Required budget |
|---|---:|
| menu/context-menu opening | p95 <= 50 ms; max <= 100 ms |
| keystroke to painted editor revision | p95 <= 50 ms; max <= 100 ms |
| cursor move or scroll to painted viewport | p95 <= 50 ms; max <= 100 ms |
| Convert to visible converting state | <= 100 ms |
| Cancel to visible cancel-requested state | <= 100 ms |
| view toggle, tab switch, or panel activation | p95 <= 75 ms; max <= 100 ms |
| window-close acceptance after user decision | <= 250 ms |

Source synchronization and stale-state invalidation must meet the editing
budget at the maximum source-byte fixture. Full semantic fingerprints may
settle asynchronously, but Save C and Convert remain disabled until the latest
revision is committed and authenticated.

## Conversion supervision

- Cooperative cancellation receives a 750 ms grace period.
- If the worker remains active, termination begins immediately after grace.
- Worker termination and resource reclamation complete within 2 seconds of the
  cancel request.
- A latest pending request starts within 250 ms after the prior worker exits or
  is terminated.
- The queue contains no more than one active and one pending request.
- Twenty rapid edit/convert/cancel cycles leave no obsolete pending requests,
  orphan process, result publication, or accumulating worker resource.
- Closing PyCForge must not wait for the converter to cooperate.

Conversion throughput is reported but does not replace responsiveness. No
fixed total conversion time is promised for every maximum-complexity source;
the liveness guarantee is that the application remains responsive, shows
truthful stage/elapsed state, and can cancel or close.

## Result publication

- Terminal state and summary chrome appear within 100 ms of a valid result
  envelope reaching the GUI.
- The first visible generated-C viewport is available within 250 ms.
- Remaining generated C, syntax spans, mappings, and details may populate
  incrementally without violating the event-loop gate.
- Hidden generated C and hidden detail tabs incur no eager widget population.
- No progress-only event performs work proportional to full source, generated
  output, or observer-record size.
- A mapping or diagnostic position index is built once per text revision, not
  once per marker.

## Search, highlighting, and markers

- Find input is debounced by 100–200 ms and older searches are cancelable.
- First visible results appear within 250 ms at the maximum source-byte
  fixture.
- Total counts may continue asynchronously. Marker rendering is bounded by the
  viewport and overview aggregation, not by total matches.
- Closing Find disconnects expensive live scans even if the query text remains.
- A one-character query with a match on nearly every line must not allocate one
  `ExtraSelection` per match.
- Syntax highlighting and bracket matching stay within the event-loop gate for
  a 100,000-line file and for a near-limit single long line.
- Unmatched brackets must not cause a whole-document character-by-character Qt
  scan on every cursor move.

## File-system and memory liveness

- Reads, hashes, path existence checks, and external-change comparisons on
  linked files never block the GUI thread.
- Injected 5-second file-system latency leaves menus, editors, Cancel, and
  window close responsive.
- Repeating the same maximum-result display and discard cycle 20 times must
  show no monotonic retained-memory growth; after reclamation, retained growth
  is limited to the larger of 32 MiB or 5 percent of the first-cycle steady
  state.
- Worker out-of-memory, abrupt exit, malformed IPC, oversized envelope, and
  broken pipe are recoverable failures and publish no C.

## Platform matrix

The candidate must pass visibly on:

- Windows 11 with a supported PyQt5 5.15 build; and
- at least one declared Linux desktop backend using real visible widgets.

Tests cover 100%, 125%, 150%, and 200% effective scaling where supported, a
small 960x620 window, the normal 1420x880 layout, keyboard-only navigation, and
screen-edge menu placement. Offscreen CI repeats deterministic behavior and
failure injection but is supplemental.

## Failure policy

Any missed worst-case latency, orphan worker, stale publication, editable
generated C, inaccessible menu, or unresponsive close is a failed gate. The
candidate is not promoted by averaging, increasing timeouts, hiding the
progress surface, shrinking fixtures below the declared ceilings, or disabling
the failing platform claim.
