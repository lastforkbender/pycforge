# PyCForge 0.12.2 actual-widget review

Review date: 2026-07-22  
Platform: Qt offscreen  
Runtime: Python 3.12.13, PyQt 5.15.11, Qt 5.15.14

The v0.12.2 workspace was exercised through a real `QApplication` and
`MainWindow`, not a mock widget tree. Keyboard actions were delivered through
Qt, and the resulting normal-scale and DPR-2 surfaces were inspected directly.

The review covered:

- keyboard focus, Ctrl+F, Ctrl+H, case/whole-word search, Unicode replacement,
  bundle reorder, primary selection, and rail accessibility metadata;
- two explicit modules, structured details, a real source-to-C mapping, and
  immutable generated C;
- fresh atomic linked-C save, stale save rejection, source-reversion rejection,
  pending identity commit, reconversion, and last-known-good file custody;
- bounded typed settings restoration and corrupt/incompatible settings tests;
- vector icons, visible toolbar Save C, readable two-row bundle navigation,
  balanced Python/C panes, and usable details at DPR 1 and DPR 2.

The first screenshot pass exposed Qt splitter values that had been supplied as
ratios even though Qt interprets them as pixels. That collapsed the Python
editor and navigator list. The workspace now computes real pixel allocations,
uses a compact navigator, keeps the linked filename visible, and reserves a
distinct vector icon for generated-C visibility. The smoke asserts these
layout properties so the original defect cannot pass the release gate.

Both final reports passed all 28 required behavior checks plus screenshot
custody. No unexpected modal dialog appeared. Generated C was not compiled,
linked, loaded, or executed.

Evidence:

- `qt_widget_smoke_scale_1.json` — SHA-256
  `20e56b687a38ab5925bfb8c4990b4274fc250e56e0444154c98f3b43c3e2ecc3`
- `qt_widget_smoke_scale_1.png` — SHA-256
  `89aed586ec4c5daf98f204ea439bc5789891551930f4dd37682295ec96a04718`
- `qt_widget_smoke_scale_2.json` — SHA-256
  `c0b4e1af301a9032304650f83953ce3765a33933aff9636fbb02b24f48e015ab`
- `qt_widget_smoke_scale_2.png` — SHA-256
  `b86b8957470130f10dda9ce9a70379e1a655a0f523395561c13b71b3ba248170`

This is offscreen actual-widget evidence. It does not claim a physical-display,
screen-reader, compositor, or platform-native assistive-technology session.
