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

## [1.2.0] - 2026-04-09

### Added

- **Auto-layout engine** — column placement and area heights are computed
  automatically from address ranges. No `pos` or `size` needed in `diagram.json`.

- **Canvas auto-expansion** — the SVG canvas grows to fit all auto-placed areas;
  `diagram.json` `size` is now a floor, not a hard limit.

- **`references/auto-layout-algorithm.md`** — implementation reference for the
  auto-layout algorithm with a planned-vs-implemented comparison table.

### Fixed

- Sections now reliably reach `min_section_height` even when the same area
  contains both very large and very small sections.

- Link bands align exactly with rendered section box edges (previously misaligned
  when sections had height overrides).

- Address labels are no longer obscured by adjacent area boxes; inter-column
  spacing is now sized to accommodate them.

### Changed

- Auto-layout splits overflowing columns into sub-columns rather than compressing
  areas below `min_section_height`.

- Area box width is capped at 230 px in auto-layout for consistent readability
  across different canvas sizes.

- All bundled chip examples now use auto-layout; explicit `pos`/`size` removed
  from `caliptra`, `stm32f103`, and `opentitan_earlgrey` diagram files.

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
  behaviour (fixed `break_size` height, independent panel proportioning) is
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
