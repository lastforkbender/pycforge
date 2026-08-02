# Phase 15B Application Shell and Visual-System Decision

Status: accepted  
Distribution: PyCForge `0.15.1`  
Workspace contract: `pycforge-workspace/0.4`

## Action authority

Every persistent application command is declared once in an import-safe action
contract. Stable identifiers own its visible label, mnemonic, icon, shortcut,
tooltip, status explanation, accessible name, checkability, tone, and allowed
surfaces.

The optional Qt adapter creates and binds each persistent `QAction` once.
Menus, toolbars, context surfaces, and bounded recent-file entries consume the
registry instead of creating undeclared commands. Presentation enablement never
replaces the controller's exact revision, bundle-fingerprint, and Save C
revalidation.

## Menu behavior

The main File, Edit, View, and Transpile menus and every required context menu
use native `QMenu` and `QAction` mechanics inside custom PyCForge subclasses.
This preserves native keyboard traversal, mnemonics, shortcut columns, focus
return, Escape dismissal, assistive-technology exposure, and screen-edge
placement.

Context menus exist for:

- the editable Python source surface;
- the read-only generated-C inspector;
- the closed Source Bundle navigator;
- diagnostics;
- source-to-C mappings; and
- conversion summary, decision trace, and telemetry inspectors.

The generated-C menu has an exact read-only allowlist. It cannot expose Undo,
Cut, Paste, Replace, formatting, or another mutating command.

## Visual language

The PyCForge visual system uses semantic graphite surfaces, high-contrast text,
blue and violet focus/selection accents, a restrained warm transpilation
accent, and explicit success, warning, and error states. Custom self-contained
SVGs use logical sizes and contain no raster image, embedded data, remote
reference, font glyph, or fixed physical dimension.

The custom menu language includes:

- graphite gradients and bounded radii;
- visible icons and text labels;
- a native shortcut column;
- distinct hover, focus, pressed, checked, disabled, and danger treatments;
- separators, submenu indication, and selection rails; and
- state communication through text, shape, check state, and contrast rather
  than color alone.

The interface has no animation, making the visual system reduced-motion safe
by construction.

## High-DPI and accessibility

Qt high-DPI scaling and SVG pixmaps are enabled before application
construction. Logical icon sizes are used for menus, toolbars, navigator
controls, and window branding. Every icon-only control has a visible tooltip
and accessible name. Menu and context surfaces have stable accessible names.

Headless contract and optional offscreen-widget evidence support Phase 15B.
Visible Windows 11 and Linux desktop certification remains exclusively Phase
15D and is not inferred here.

## Exact product boundary

This phase adds no command palette, project explorer, recursive scan, outline,
breadcrumb system, LSP, formatter, refactoring, completion engine, plugin,
macro, build/run/debug command, terminal, toolchain integration, or
generated-C editing. Those exclusions remain fail-closed.

