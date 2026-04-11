# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Versioning rule of thumb:**
- `x` (major) — a user must edit existing files to get equivalent output.
- `y` (minor) — new capability added; existing files work unchanged.
- `z` (patch) — something was wrong and is now correct; no schema change.

**Writing guide for entries:**
- Write from the user's perspective: "you can now do X", "X now works
  differently", "X was broken and is now correct".
- Keep each bullet to **2 lines or fewer**. Technical details belong in commit
  messages or reference docs, not here.
- Group closely related small changes into one bullet rather than listing each
  individually.
- Use `Added` / `Changed` / `Fixed` / `Removed` sections consistently.

---

## [1.3.0] - 2026-04-11

### Added

- **`links.sub_sections` explicit target** — entries now accept an optional third
  element `[source_view_id, section_id, target_view_id]`. The band is drawn directly
  to the named target view, bypassing first-match routing. Enables *fan-in* patterns
  where multiple source views connect to the same detail panel (e.g., a CPU view and
  a debugger view both linking to a shared "System Peripherals" detail).

- **`examples/chips/arm_coresight_dual_view/`** — new annotated example showing a
  dual CPU + CoreSight Debugger (DAP) memory map. Demonstrates how the same physical
  address space is shared by the CPU's AXI master port and the debugger's AXI-AP, while
  the Debug APB (`0x20000000`) is accessible only via the debugger's APB-AP.

### Fixed

- **`check.py` validates explicit target view IDs** — `unresolved-section` now also
  reports when the `target_view_id` in a three-element `sub_sections` entry does not
  match any view in the diagram.

---

## [1.2.0] - 2026-04-11

### Added

- **Auto-layout engine** — column placement and area heights are computed
  automatically from address ranges. No `pos` or `size` needed in `diagram.json`.

- **Canvas auto-expansion** — the SVG canvas grows to fit all auto-placed areas;
  `diagram.json` `size` is now a floor, not a hard limit.

- **`themes/default.json`** — new neutral black/white/gray built-in theme. Loaded
  automatically when `-t` is omitted.

- **Theme inheritance** — add `"extends": "light"` (or any built-in name, or a
  relative path) to a custom theme to inherit all settings and override only what
  changes. Circular and missing-file references raise an error at load time.

- **`schema_version`** — integer field in theme files tracks format generation.
  Absent = silently compatible. Older than current = warning. Future = error.

- **`-t <name>` shorthand** — pass a built-in theme name directly without a file
  path: `-t default`, `-t light`, `-t monochrome`, `-t plantuml`.

- **`references/auto-layout-algorithm.md`** — implementation reference for the
  auto-layout algorithm with a planned-vs-implemented comparison table.

- **`examples/stack/basic/`** — Cortex-M SRAM layout with colored heap and
  stack regions and directional growth arrows.

- **`examples/stack/guard_page/`** — MPU stack guard page: heap and stack each
  split into used/free regions, with a no-access guard page between them.

- **`examples/stack/shadow_stack/`** — Shadow stack: a second, separate region
  mirroring only return addresses alongside the main call stack.

### Fixed

- **Auto-layout column placement** — the bin-packing threshold is now computed
  per-column from the tallest view in that column rather than globally from the
  canvas height. This prevents small views from being wrongly spilled to a new
  column when the same column also contains one very large view.

- **Auto-layout rangeless views** — a view with no explicit `range` now derives
  its range from the full set of sections, so it can appear as a detail view to
  the right of any view whose sections it contains. Previously it always landed
  in column 0 with no outgoing link-graph edges.

- **Address labels always use view-level text color** — boundary address labels
  no longer inherit section-specific `text_fill` overrides. A section with a
  dark background and `"text_fill": "#ffffff"` no longer rendered its boundary
  labels (outside the section box) in white.

- **`check.py` canvas bounds** — the validator now uses the actual auto-expanded
  canvas dimensions instead of `diagram.json` `size`, eliminating false positives
  for areas that lie within the expanded canvas but outside the declared `size`.

- Sections now reliably reach `min_section_height` even when the same view
  contains both very large and very small sections.

- Link bands align exactly with rendered section box edges (previously misaligned
  when sections had height overrides).

- Address labels are no longer obscured by adjacent area boxes; inter-column
  spacing is now sized to accommodate them.

- **Auto-layout column width** — columns were sized from the default document width
  (400 px), making them too narrow in multi-column layouts. Column width is now
  always 230 px; the canvas auto-expands via `_auto_canvas_size()`.

### Changed

- **`theme.json` `"weight"` renamed to `"label_arrow_size"`** — the arrow-head
  size multiplier for address annotation labels. Update any custom theme files.
  Breaking rename.

- **`theme.json` `"break_size"` renamed to `"break_height"`** — the fixed pixel
  height of break sections. Update any custom theme files. Breaking rename.

- **`diagram.json` `"areas"` renamed to `"views"`** — the top-level display array
  is now `"views"`. Rename the key in existing files. Breaking rename.

- **`views[].sections[].names` renamed to `ids`** — the per-view section-override
  selector is now `"ids"`. The old name `"names"` was misleading — it matched
  section `id` fields, not `name` fields. Breaking rename.

- **`theme.json` `"areas"` renamed to `"views"`** — the per-view style block is
  now `"views"`. Rename the key in existing theme files. Breaking rename.

- **`"defaults"` renamed to `"style"`** — the top-level baseline block in
  `theme.json` is now `"style"`. Update any custom theme files by renaming the key.
  This is a breaking rename.

- **Default theme is `themes/default.json`** — omitting `-t` loads
  `themes/default.json` (neutral gray) instead of hardcoded built-in values.

- **Section height inflation is conflict-driven** — the label-height floor
  (`30 + font_size` px) is now applied only to sections where the size label
  (top-left, 12 px) and name label (centred, `font_size` px) overlap on the x-axis.
  Sections without overlap keep proportional height, producing more compact diagrams.

- Auto-layout splits overflowing columns into sub-columns rather than compressing
  areas below `min_section_height`.

- All bundled chip examples now use auto-layout; explicit `pos`/`size` removed
  from `caliptra`, `stm32f103`, and `opentitan_earlgrey` diagram files.

### Removed

- **`sections[].type`** — stored but never read by the renderer. Remove from
  existing `diagram.json` files (silently ignored if present).

- **`sections[].parent`** — stored but never used. Remove from existing files.

- **Visibility control** — `hide_name`, `hide_address`, `hide_end_address`, and
  `hide_size` theme properties are gone. All section labels are always rendered.

---

## [1.1.0] - 2026-04-08

### Added

- **Flexible link band styles** — choose polygon or curve shape with fill-only,
  solid-stroke, or dashed-stroke rendering via `shape`, `fill`, `stroke` in theme.

- **`links.sub_sections`** — draw bands from any detail area (not just the
  overview), enabling multi-level zoom chains (bus view → peripheral detail).

- **`palette`** — assign fill colors to sections by address order in `theme.json`
  without per-section overrides; portable across different diagrams.

- **`hide_end_address`** — show the section end address at the top-right of each
  box; set to `"auto"` to show it only when the section is tall enough.

- **`break_fill`** — separate background color for break-section boxes,
  independent of the normal section fill.

- **`min_section_height` / `max_section_height`** — guarantee every section is
  at least N pixels tall; cap very large sections from crowding out neighbors.

- **`mmpviz --version`** — prints the current version number.

- **`scripts/check.py`** — validates `diagram.json` + `theme.json` without
  rendering; 9 rules covering sections, areas, and links; JSON output supported.

- **Built-in themes** — `themes/light.json`, `themes/monochrome.json`,
  `themes/plantuml.json`; work with any diagram without modification.

- **`examples/link/`** — six link-style variant demos plus a cortex_m3 reference
  example.

- **`examples/themes/`** — visual demos of each built-in theme on a shared MCU
  diagram.

- **`examples/chips/`** — four annotated real-world SoC examples: stm32f103,
  caliptra, opentitan_earlgrey, pulpissimo.

- **`references/layout-guide.md`**, **`references/llm-guide.md`**,
  **`references/check-rules.md`** — new reference documents.

### Fixed

- Link band source anchor corrected for break-compressed source areas — bands
  now align with the visible colored block, not the raw proportional address.

### Changed

- Section size labels now show human-readable binary units (`32 KiB`, `4 GiB`)
  instead of raw hex values.

- `hide_size` default changed from `"auto"` to `false` — size labels are shown
  by default; set `"auto"` or `true` to suppress them.

- `area`-type break sections render as plain filled boxes rather than gap
  indicators, so they show name and size labels when height-compressed.

- Default link band style changed to stroke-only (no fill). Add `"fill": "gray"`
  to the theme `links` block to restore the previous appearance.

- `examples/stm32f103/` moved to `examples/chips/stm32f103/`; `examples/link/`
  reorganised into per-style subfolders.

### Removed

- **`break_type` property removed.** Break sections now always render as a plain
  filled box (using `break_fill` as background). The four visual patterns
  (`"≈"`, `"~"`, `"/"`, `"..."`) have been removed. The structural break
  behaviour (fixed `break_height` height, independent panel proportioning) is
  unchanged. Themes that set `break_type` can safely delete the property — it
  is silently ignored.

- `examples/dark_theme.json` and `examples/light_theme.json` — replaced by the
  theme-agnostic files in `themes/`.

---

## [1.0.0] - 2026-04-07

### Added

- Initial release of mmpviz, based on
  [linkerscope v0.3.1](https://github.com/raulgotor/linkerscope).
- DSL changed from YAML to JSON (`diagram.json`).
- Visual styling separated into a standalone `theme.json`, decoupled from the
  semantic diagram description.
- Initial support of SKILL (Claude Code skill integration).
