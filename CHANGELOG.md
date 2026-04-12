# Changelog

All notable changes to this project are documented here, newest first.

Heading format:
- Draft work: `[YYYY-MM-DD]` (e.g. `[2025-04-07]`) — bracketed date, no version
- Official release: `[YYYY-MM-DD] (x.y.z)` (e.g. `[2025-04-22] (1.0.0)`) — bracketed date with version number

Version rules:
- `x` — breaking schema change (existing files need edits); 
- `y` — new feature, existing files unchanged; 
- `z` — bug fix, no schema change.

Sections: **Added** · **Changed** · **Removed**

---

## [2026-04-12]

### Added
- **`links` array format** — `links` is now a flat array of `{from: {view, sections?}, to: {view}}` entries. Each endpoint names its view explicitly. Multi-section spans, address-range anchors, multi-level zoom, and fan-in (multiple sources → same detail view) all work without special syntax. Replaces the previous `{sections, sub_sections, addresses}` object form.

### Changed
- View coordinate system now uses the declared `range` as the pixel basis; previously it fell back to the filtered sections' actual extent, misaligning sections and link-band anchors.
- `min_section_height` now applies to all views; previously it was silently skipped for views with no break sections.
- Link band destination endpoints are clamped to the destination view's address range; previously they could map thousands of pixels off-screen when the source range exceeded the destination view.
- Sections hidden by `section_size` can now be referenced in `from.sections`; the renderer falls back to the global section table.

### Removed
- `links.sub_sections`, `links.addresses` — superseded by the new array format.

---

## [2026-04-11]

### Added
- **Auto-layout engine** — views are placed in columns automatically from the link graph; no `pos`/`size` needed in `diagram.json`. Canvas expands to fit.
- **Theme inheritance** — `"extends": "<name-or-path>"` in `theme.json` inherits from a base theme; override only what changes.
- **`themes/default.json`** — neutral gray theme, loaded automatically when `-t` is omitted. `-t <name>` shorthand works for all built-in themes.
- **Fan-in links** — multiple source views can link to the same detail panel.
- **`scripts/check.py`** — validates `diagram.json` + `theme.json` against layout and display rules without rendering.
- **`examples/stack/`** — three stack layout examples: basic heap/stack, MPU guard page, shadow stack.
- **`examples/chips/arm_coresight_dual_view/`** — dual CPU + CoreSight Debugger fan-in example.
- **`references/`** — `llm-guide.md`, `check-rules.md`, `auto-layout-algorithm.md`.

### Changed
- Several `diagram.json` and `theme.json` keys renamed for clarity: `areas` → `views`, `names` → `ids`, `defaults` → `style`, `weight` → `label_arrow_size`, `break_size` → `break_height`.
- Break sections render as plain filled boxes; `break_type` removed.
- Section height inflation for label overlap is now conflict-driven — only sections where name and size labels collide horizontally are inflated.

### Removed
- `sections[].type`, `sections[].parent` — unused fields.
- `hide_name`, `hide_address`, `hide_end_address`, `hide_size` — all section labels are always rendered.

---

## [2026-04-08]

### Added
- **Link band styles** — `shape` (`polygon`/`curve`), `fill`, `stroke`, `stroke_dasharray`, `opacity` in `theme.json`.
- **Multi-level zoom** — `links.sub_sections` enables bands from any view, not just the overview.
- **`palette`** — cyclic section fill colors by address order in `theme.json`.
- **`min_section_height` / `max_section_height`** — floor and ceiling on rendered section height.
- **`break_fill`** — separate fill color for break sections.
- **Built-in themes** — `light`, `monochrome`, `plantuml`.
- **`examples/link/`**, **`examples/themes/`**, **`examples/chips/`** — link-style demos, theme demos, real-world SoC examples.

### Changed
- Section size labels now show human-readable binary units (`32 KiB`, `4 GiB`).
- Default link band style changed to stroke-only.

---

## [2026-04-07]

### Added
- Initial release of mmpviz, forked from [linkerscope v0.3.1](https://github.com/raulgotor/linkerscope).
- `diagram.json` + `theme.json` two-file model; DSL changed from YAML to JSON.
- Visual styling fully separated from semantic diagram description.
