# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Versioning rule of thumb:**
- `x` (major) — a user must edit existing files to get equivalent output.
  Example: a field is renamed (`stroke_color` → `stroke`), or a default changes
  silently (old diagrams now render differently without any config change).
- `y` (minor) — new capability added; existing files work unchanged.
- `z` (patch) — something was wrong and is now correct; no schema change.

---

## [1.1.0]

### Added

- **Flexible section band link styles.** `shape` (`polygon` / `curve`) combined
  with three fill/stroke modes (fill-only, solid-stroke, dashed-stroke). Configured
  via `shape`, `fill`, `stroke`, and `stroke_dasharray` in the theme `links` block.
  Source-side retains a 30 px outward jog; detail-side connects flush with the panel.
  Sub-pixel openings are expanded to a 4 px minimum so bands remain visible when a
  section is tiny in the source stack.

- **`links.sub_sections`** — array of `[source_area_id, section_id]` pairs that draw
  bands from any detail area (not just the overview) to the next area covering that
  section's address range. Enables multi-level zoom chains (e.g., overview → bus view
  → µDMA channel view).

- **`palette`** — optional top-level array of color strings in `theme.json`. Assigns
  fill colors to sections in address order without per-section overrides, making
  themes portable across different diagrams. Break sections do not consume a palette
  slot. Area- and section-level explicit `fill` values always take precedence.

- **`hide_end_address`** — theme property (default `true`). Set to `"auto"` to show
  the end address whenever section height ≥ 20 px, or `false` to always show it.
  Rendered at the top-right of each section box alongside the existing start address.

- **`break_fill`** — theme property for the background color of break-section boxes,
  independent of the `fill` used for normal sections. Falls back to `fill` then to
  `lightgrey` when unset.

- **`min_section_height`** and **`max_section_height`** — theme defaults for section
  height clamping. `min_section_height` guarantees every visible section in a subarea
  renders at least N pixels tall by back-calculating the required subarea height.
  `max_section_height` caps any single subarea so it cannot crowd out neighbours. The
  minimum floor always wins when the two constraints conflict. An iterative
  floor/ceiling algorithm converges in at most 50 rounds; proportional sizing is used
  as fallback if constraints cannot be satisfied simultaneously.

- **`mmpviz --version`** — prints the current version number.

- **`scripts/check.py`** — post-generation rule checker that validates
  `diagram.json` + `theme.json` without producing SVG output. Nine rules across
  three categories:
  - *Per-section*: `text-overflow`, `addr-auto-hidden`, `min-height-violated`
  - *Area-level*: `out-of-canvas`, `panel-overlap`, `title-overlap`, `label-overlap`
  - *Link-level*: `band-too-wide`, `unresolved-section`

  Supports `--rules` for selective checks and `--format json` for machine-readable
  output. Exit codes: 0 = OK, 1 = errors, 2 = warnings only.

- **Built-in themes** in `themes/`: `light.json` (professional light, white
  backgrounds), `monochrome.json` (grayscale), and `plantuml.json` (PlantUML
  color palette). All three set only `defaults` and `links` blocks so they work
  unmodified with any `diagram.json`.

- **`examples/link/`** — six subfolders demonstrating all link style variants
  (`polygon_fill`, `polygon_stroke`, `polygon_stroke_dashed`, `curve_fill`,
  `curve_stroke`, `curve_stroke_dashed`) plus the `cortex_m3` reference example.

- **`examples/themes/`** — visual demos of each built-in theme (`light/`,
  `monochrome/`, `plantuml/`) on a shared generic MCU diagram.

- **`examples/chips/`** — real-world SoC memory map examples with annotated source
  notes and public URL references:
  - `stm32f103/` — ARM Cortex-M3 microcontroller (ST RM0008 + ARMv7-M ARM)
  - `caliptra/` — Caliptra RoT RISC-V security subsystem
    ([chipsalliance/caliptra-rtl](https://github.com/chipsalliance/caliptra-rtl))
  - `opentitan_earlgrey/` — OpenTitan Earl Grey TL-UL crossbar SoC with 65+
    peripherals ([lowrisc/opentitan](https://github.com/lowrisc/opentitan))
  - `pulpissimo/` — PULP RISC-V SoC with multi-level zoom and µDMA channel
    detail ([pulp-platform/pulpissimo](https://github.com/pulp-platform/pulpissimo))

- **`references/layout-guide.md`** — aspect-ratio and panel-positioning reference
  for common output targets (A4 portrait/landscape, 16:9 and 4:3 slides).

- **`references/llm-guide.md`** — rules of thumb, worked patterns, and inspection
  workflow for AI/LLM agents generating `diagram.json` + `theme.json` files.

- **`references/check-rules.md`** — full reference for all nine `check.py` rules:
  trigger conditions, exact thresholds, geometry constants, and remediation guidance.

### Changed

- **Size labels now show in human-readable binary units** (`32 KiB`, `256 MiB`, `4 GiB`)
  instead of raw hex (`0x8000`). The `format_size()` helper in `helpers.py` performs the
  conversion; fractional values are rounded to one decimal place (e.g. `1.5 KiB`).

- **`hide_size` default changed from `"auto"` to `false`** — size labels are now shown by
  default for all sections. Set `hide_size: "auto"` to hide them when a section is shorter
  than 20 px, or `hide_size: true` to suppress them entirely. Chip examples updated from
  `hide_size: true` to `hide_size: "auto"` so sizes appear for any section large enough to
  hold a label.

- **`area`-type break sections render as plain boxes.** A section with `"type": "area"` in
  the global `sections` array that is also assigned the `"break"` flag now renders as a
  filled box (same as a regular section), showing its name and size label. Only sections
  with the default `"type": "section"` use the gap-indicator pattern (≈ wave, dots, etc.).
  This allows large real memory regions (e.g. a peripheral cluster) to appear visually
  meaningful in an overview panel while still being height-compressed by the break
  mechanism.

- Default link style changed from implicit gray fill to **stroke-only** (`fill: none`).
  Themes that relied on the previous implicit fill should add `"fill": "gray"` to
  their `links` block.

- Link band source anchor corrected for break-compressed source areas — the band
  now aligns with the visible colored block rather than the raw proportional address
  position.

- `examples/link/` reorganised into named subfolders; the previous flat layout
  (`examples/link/diagram.json`) is removed.

- `examples/stm32f103/` moved to `examples/chips/stm32f103/`.

### Removed

- `examples/dark_theme.json` and `examples/light_theme.json` — area-specific
  overrides tied them to one example diagram; replaced by the theme-agnostic
  files in `themes/`.

---

## [1.0.0] - 2026-04-07

### Added

- Initial release of mmpviz, based on
  [linkerscope v0.3.1](https://github.com/raulgotor/linkerscope).
- DSL changed from YAML to JSON (`diagram.json`).
- Visual styling separated into a standalone `theme.json`, decoupled from the
  semantic diagram description.
- Initial support of SKILL (Claude Code skill integration).
