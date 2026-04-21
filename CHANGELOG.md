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

Writing guide:
- One bullet per user-facing change. Format: **`key` or feature name** — one sentence.
- Record: schema additions/removals/renames, new capabilities, breaking behavior changes.
- Skip: which file implements it, error message wording, edge-case fallbacks, internal maintenance (example updates, golden regen).
- No sub-bullets — details belong in the schema reference docs.
- For renames use `old → new`; for removals say what supersedes it.

---

## [2026-04-21] (1.1.1)

### Changed
- **Text baseline attribute** — `<text>` elements now emit `dominant-baseline` instead of `alignment-baseline`. Browsers rendered both correctly, but librsvg (`rsvg-convert`) and Inkscape silently ignore `alignment-baseline` on `<text>`, so PNG conversions of the output SVG had labels shifted off their intended positions. `dominant-baseline` is the spec-compliant attribute for `<text>` and is honored by every major renderer.

---

## [2026-04-21] (1.1.0)

### Changed
- **Routing lane ZCI bracket** — crossing-free interval now uses the link's interpolated y (`y_through`) compared against adjacent links' **destination** y-positions; fixes lane placement when source and destination heights differ significantly.
- **Routing lane collision avoidance** — bidirectional sweep: if upward push exceeds the gap bound, retry with a downward sweep; prevents lanes from collapsing to the same boundary position.
- **Algo-3/4 inter-panel gap expansion** — minimum gap for N routing lanes is now `N × lane_pitch` (was `N × lane_pitch + PADDING`); the half-lane margins are already baked into the feasible centre range inside `plan_routing_lanes`.
- **Algo-4 routing-lane desired offset** — uses the nearest inter-view gap midpoint instead of `y_through` from stale initial positions; gap midpoint is position-independent and stable before non-anchor columns are shifted.

---

## [2026-04-20]

### Added
- **Grows-arrow neighbor auto-raise** — when a section carries `"grows-up"` or `"grows-down"`, the layout engine automatically raises the immediately adjacent non-break neighbor section's floor to `(2 × 20 × growth_arrow.size + font_size)` px so the rendered growth arrow does not overlap the neighbor's text label.  No `min_height` annotation is required on the neighbor.
- **`min_height` guidance for small drill-down views** — single-section and small (1–3 section) drill-down views now render at the section's label-conflict floor (~20–46 px), which is typically too short for comfortable reading.  Set `"min_height"` on those sections to give the panel a taller floor.  The floor-stack model makes `min_height` the exact rendered height for sections that have no other height driver.

### Changed
- **Layout model — floor-stack** — each section is assigned its effective floor height (`max(min_section_height, section.min_height, label_conflict_floor)`) and sections are stacked contiguously.  View height equals the sum of all section heights; there is no minimum view height and no frame padding.  Proportional scaling by byte size has been removed; sections that differed only in byte count now render at the same height.
- **Single area per view** — the subarea model that split views into segments around break sections has been removed.  All sections (including breaks) are rendered in one continuous stack.  Break sections appear at their address-ordered position and receive `break_height` px.
- **Height estimation** — `_estimate_area_height` now uses the same formula as the layout engine (exact floor sum, no padding, no 200 px minimum), giving an exact result.  No post-layout view growth is needed.
- **`max_height`** — per-section and global `max_section_height` have no effect in the floor-stack model; every section renders at its floor.  The fields are accepted but ignored.
- **`min-height-violated` check** — redefined as a layout-engine bug guard; it can no longer be triggered by a valid `diagram.json`.  The fix guidance has been updated accordingly.

---

## [2026-04-19]

### Added
- **`label-out-of-range` check (WARN)** — fires when a label's `address` is outside the view's address range `[Lo, Hi]`; such labels are silently not rendered.
- **`link-address-range-order` check (ERROR)** — fires when a link's `from.sections` or `to.sections` address-range form has `lo >= hi`; an inverted or collapsed range produces a crossed or degenerate band.
- **`link-self-referential` check (WARN)** — fires when a link's `from.view` and `to.view` reference the same view; the resulting band overlaps the panel with degenerate geometry.
- **`min-height-below-global` check (WARN)** — fires when a per-section `min_height` is set below the global `min_section_height`, undercutting the global floor.
- **`min-height-on-break` check (WARN)** — fires when a break-flagged section has `min_height` set; the value is silently ignored because breaks always render at `break_height`.
- **`section-name-overflow` check (WARN)** — fires when a section name's estimated text width exceeds the panel width; the renderer cannot wrap names, so the name must be shortened in `diagram.json`.

### Changed
- **`section-overlap` check** — now also fires WARN for two break sections with overlapping address ranges (redundant breaks); previously break-vs-break overlap was silently allowed.
- **`uncovered-gap` check** — rewritten to check full `[Lo, Hi]` coverage using the union of all sections (break and non-break); any hole fires regardless of size. Previously used size-based thresholds that allowed small uncovered holes to pass silently.
- **Label rendering** — labels placed at exactly the view's end address (`last_section.address + last_section.size`) now render correctly; previously the half-open `[addr, addr+size)` interval check silently dropped them.
- **`min-height-violated` check** — effective minimum now includes the label-conflict floor (`30 + font_size` px) in addition to global and per-section floors; issue message reports all three components.
- **No-breaks layout path** — now applies the label-conflict floor (`30 + font_size` px) consistently with the breaks path; previously the floor was only enforced when break sections were present.
- **`hidden` flag dead code removed** — the `hidden` section flag was removed from the schema in a prior release; all residual `is_hidden()` guards have been deleted from the layout engine, renderer, and checks.
- **`link-redundant-sections` check** — no longer fires a false positive on cross-address-space links.
- **Layout crossing fix for address-range `from.sections`** — column ordering and vertical alignment now correctly compute source midpoints for address-range form link endpoints (`["0xLO", "0xHI"]`); previously they fell back to a zero midpoint, causing link bands to cross in diagrams with multiple independent link chains.

---

## [2026-04-18] (1.0.0)

### Added
- **`break-overlaps-section` check (ERROR)** — fires when a break section's address range overlaps a visible (non-break) section. The visible section would otherwise be silently swallowed by the layout engine; the error message prints the corrected break size.
- **`link-address-range-mappable` check (WARN)** — fires when a link's `from.sections` or `to.sections` uses the address-range form `["0xA", "0xB"]` but the range resolves exactly to defined section(s). Suggests replacing the range with section IDs.
- **`link-redundant-sections` check (WARN)** — fires when a link's `from.sections` or `to.sections` covers the whole target view (enumerated IDs or an address range spanning the full extent). Suggests omitting the field to use the whole-view default.
- **AreaView degenerate-range guard** — `AreaView` now raises a `ValueError` up front when `size_y <= 0` or `end_address <= start_address`. Previously these produced a division-by-zero or silently bad output downstream.

### Changed
- **Schema validation is always on — no optional dependency.** `validate()` is now a pure-stdlib structural + cross-reference check; the optional `[validation]` extra (which installed `jsonschema`) has been removed. Existing installs keep working — reinstall without the extra.
- **`section-overlap` check** — consolidated with break-vs-visible overlap detection. Visible-vs-visible overlaps still emit `section-overlap` (WARN); break-vs-visible emits `break-overlaps-section` (ERROR) with a fix recipe. Break-vs-break overlaps remain allowed (chained reserved ranges).
- **Auto-layout algorithm doc moved** — `references/auto-layout-algorithm.md` → `docs/auto-layout-algorithm.md`. The doc is developer-facing layout-engine internals and has been pulled out of the author-facing `references/` playbook. Cross-links in `README.md`, `references/diagram-schema.md`, `references/theme-schema.md`, and `references/check-rules.md` updated.

### Removed
- **`[validation]` optional extra** — `pip install mmpviz[validation]` → `pip install mmpviz`. Validation is always on; no `jsonschema` runtime dependency.
- **Legacy auto-layout fields now error instead of warn** — diagram-level `size` and view-level `pos` / `size` (replaced by auto-layout years ago) now produce hard "unknown key" errors from the structural check. The soft-deprecation bridge (`DEPRECATED:` prefix, `split_issues()`, `_scrub_deprecated()`) has been removed.

---

## [2026-04-17]

### Added
- **`--layout algo4`** — layout variant that extends algo-3 with fixed lane assignment and vertical column alignment to minimise total link length.
- **Package distribution** — `pyproject.toml` added; installable via `pip install mmpviz` or `uv pip install mmpviz`.

### Changed
- **Theme resolution** — when `-t` is omitted, `mmpviz` first looks for `theme.json` in the same directory as `diagram.json`; falls back to the built-in default if none is found. Explicit `-t` always takes priority over a sibling `theme.json`.

---

## [2026-04-15]

### Added
- **`--layout algo1|algo2|algo3` flag** — selects the auto-layout algorithm; `algo3` is the default.
- **Algo-2: height-rebalancing layout** — splits over-tall DAG columns by extracting height-outlier views and overflowing trailing views to the next visual column, targeting a canvas H/W ratio ≤ 1.3.
- **Algo-3: routing lanes** — algo-2 height-rebalancing plus automatic routing lanes for non-adjacent links; a link that skips an intermediate column is re-routed through a horizontal bridge line placed in a crossing-free gap between views in that column.
- **`examples/themes/section_styles/`** — demonstrates per-section `fill` overrides via `views[id].sections[id]` in `theme.json`.
- **`examples/themes/per_link/`** — demonstrates per-link `fill`/`opacity` overrides via `links.overrides` in `theme.json`.

### Changed
- **Default layout algorithm** — algo-3 (routing lanes) replaces algo-1 (one visual column per DAG level) as the default; pass `--layout algo1` or `--layout algo2` to select a simpler algorithm.
- **`examples/diagram/`** — new folder for core diagram primitive demos; `examples/break/` and `examples/labels/` moved here.
- **Algo-3 routing lane placement (bracket case C)** — non-adjacent links whose source sat below every adjacent destination were sometimes drawn through the last intermediate panel instead of free space below it because no gap existed past the bottom of that column; layout now reserves trailing space so those lanes can route outside panels.

### Removed
- **`examples/chips/arm_coresight_line_link/`** — superseded by `examples/chips/arm_coresight_dual_view/`.
- **`examples/themes/default/`**, **`examples/themes/plantuml/`** — superseded by chip examples that demonstrate both built-in themes.

---

## [2026-04-14]

### Added
- **`links[].id`** — required identifier on every link entry; used as a key in `theme.json` under `links.overrides` for per-link style overrides.
- **`links.overrides[link_id]`** — per-link style override block in `theme.json` (`fill`, `opacity`, `stroke`, `stroke_width`, `stroke_dasharray`); consistent with how `views[view_id].sections[section_id]` overrides section style.
- **`labels[].id`** — required identifier on every label entry within a view; used as a key in `theme.json` under `views[view_id].labels` for per-label style overrides.
- **`views[view_id].labels[label_id]`** — per-label style override block in `theme.json` (`arrow_size`, `stroke`, `stroke_width`, `stroke_dasharray`, `font_size`, `font_family`, `text_fill`); consistent with the existing `views[view_id].sections[section_id]` pattern.
- **`links.connector` format** — recommended nested link style: `source.width` / `destination.width` (trapezoid extents), `middle.width` + `middle.shape` (`"curve"` or `"straight"` center line), and a single `fill` / `opacity`.
- **`labels.arrow_size`** — arrow head size multiplier now lives in the `labels` block alongside the leader-line stroke properties; replaces `base.label_arrow_size`.
- **`labels` dedicated schema** — `labels` now has its own schema type (`labels_block`) that accepts only label-relevant properties: `arrow_size`, `stroke`, `stroke_width`, `stroke_dasharray`, `font_size`, `font_family`, `text_fill`. Previously it accepted the full `base_block` set.
- **`growth_arrow` top-level block** — grows-up/grows-down arrow styling moved out of `base` into its own top-level block (`size`, `fill`, `stroke`), parallel to `links` and `labels`.
- **`examples/layout/`** — new top-level folder for auto-layout algorithm examples: `column_order` (DAG-tree view ordering and crossing minimisation), `height_override` (per-section `min_height`/`max_height`), `height_global` (global `min_section_height` theme property).
- **`examples/link/` style suite** — five focused link-style examples: `connector` (all connector properties explicit), `band_fill` (straight-edge fill), `band_stroke` (dashed stroke outline), `band_segments` (three explicit segments with numeric `sheight`/`dheight`), `per_link` (three individually-colored links via `links.overrides`).
- **`examples/chips/` plantuml coverage** — `stm32f103`, `opentitan_earlgrey`, and `pulpissimo` now use the plantuml theme; `arm_coresight_dual_view`, `caliptra`, and `riscv64_virt` remain on the default theme.

### Changed
- **`links.band` segment keys nested** — flat prefixed keys (`source_*`, `middle_*`, `dest_*`) replaced by `source`/`middle`/`destination` sub-objects, matching the `connector` structure for consistency. Breaking: keys move from `band.middle_sheight` to `band.middle.sheight`, etc.
- **`links.band` segment renamed** — `dest` → `destination` throughout, matching the `connector` convention.
- **`links.band` shape values unified** — `"polygon"` replaced by `"straight"` across all band segment `shape` fields, aligning with the `connector.middle.shape` vocabulary. Breaking: replace `"polygon"` with `"straight"` in existing band themes.
- **`links` height-reference semantics** — `sheight`/`dheight` select the edge span; accepts `"source"`, `"destination"`, or a non-negative number (literal pixel span; `0` collapses the edge to a point). Vertical center is auto-aligned by segment position.
- **`links` inheritance** — `connector` and `band` sub-objects merge shallowly through `extends`; a child theme can override a single nested key (e.g. `connector.fill`) without losing unmentioned parent keys. When both sub-objects are present in the resolved style, `band` takes priority.
- **Default link band visual** — connector format: 25 px source + dest trapezoids, 10 px S-curve center line, light-gray fill.
- **`themes/default.json`** — migrated to `connector` format; serves as the authoritative baseline for link inheritance. `label_arrow_size` moved to `labels.arrow_size`. Top-level `style` block renamed to `base`.
- **`themes/plantuml`** — migrated to `connector` format; inherits trapezoid geometry from default, overrides fill and opacity. Top-level `style` block renamed to `base`.
- **Auto-layout: DAG-tree view ordering** — views in each column sorted by parent position and source-section address.
- **Auto-layout: column placement** — one visual column per DAG level; bin-packing removed.
- **Link-crossing minimisation** — source-section midpoints resolved by section ID, fixing crossings from multi-section links.
- **`title-overlap` check** — extended to horizontal collision between adjacent-column titles; `check.py` uses the same layout as the renderer.
- **Break section rendering** — size label suppressed; address labels communicate the range.

### Removed
- **`links` flat top-level keys** — `source_seg_*`, `middle_seg_*`, `dest_seg_*` no longer exist at the `links` top level; use `links.band.*` (with renamed keys) or the new `links.connector` format.
- **`base.label_arrow_size`** — superseded by `labels.arrow_size`.
- **`base.growth_arrow_size/fill/stroke`** — superseded by `growth_arrow.size/fill/stroke`.
- **Top-level `style` block** — renamed to `base`; all existing theme files must update the key.
- **`examples/link/fill/`**, **`polygon/`**, **`stroke/`**, **`stroke_dashed/`**, **`three_segments/`** — five theme-variation examples on one identical diagram; superseded by the new style suite above.
- **`examples/link/cortex_m3/`** — contrived diagram; superseded by `examples/chips/arm_coresight_dual_view/` and `examples/chips/arm_coresight_line_link/`.

---

## [2026-04-13]

### Added
- **`schemas/diagram.schema.json` and `schemas/theme.schema.json`** — machine-readable JSON Schema (draft 2020-12) contracts for both input formats; loaded automatically by the render pipeline when the `jsonschema` Python package is available.
- **`sections[].min_height`** — per-section pixel height floor; effective floor = `max(min_height, theme min_section_height)`. Use for sections too small in proportion to read.
- **`sections[].max_height`** — per-section pixel height ceiling; effective ceiling = `min(max_height, theme max_section_height)`. Use for sections that would otherwise dominate the view. `min_height` must not exceed `max_height`.
- **`section-height-conflict` check rule** — reports an ERROR when a section declares `min_height > max_height`.
- **`--fmt` flag** — formats `diagram.json` in-place (canonical column-aligned style) when passed to `mmpviz.py`; combine with `-o` to format then render in one command.
- **Integrated render pipeline** — `mmpviz.py` now runs schema validation and all layout checks automatically before SVG generation; `[ERROR]` issues abort the render, `[WARNING]` issues are printed but SVG is still written.
- **Issue severity levels** — every `check.py` finding is now classified as `ERROR` or `WARNING`; standalone `check.py` exits 1 for errors, 2 for warnings-only, 0 for clean.
- **`link-anchor-out-of-bounds` check rule** — ERROR when a link band's y-anchor (source or destination side) falls outside the panel's rendered pixel range; fires only for explicit address-range `sections` specifiers that extend beyond the view's address extent.

### Changed
- **Agentic skill documentation** — `SKILL.md` description expanded with embedded-domain trigger phrases and informal-phrasing guidance; `references/check-rules.md` rewritten to reflect the integrated pipeline; `references/create-diagram.md` streamlined to a pure authoring reference (rendering and iteration steps moved to the skill workflow).
- **Left-side label visibility** — labels with `"side": "left"` were clipped when their text extended past the left canvas edge; the SVG viewport now shifts to expose the full text. Right-side labels with long text or large `length` likewise expand the right-side canvas margin automatically.
- **View title clipping** — view titles wider than their column panel no longer clip at the canvas edge; the SVG viewport now expands to expose the full title text on both sides.
- **`uncovered-gap` detection improved** — coverage is now determined by the union of all break sections; consecutive chained breaks that together span the full gap are correctly recognised as covering it and no longer produce a false positive.
- **Link-crossing minimisation** — views in each column are automatically reordered to match the vertical order of their source sections, reducing link-band crossings in multi-column diagrams.
- **64-bit address label support** — views whose sections have start addresses above `0xFFFFFFFF` now render all address labels in 16-digit hex format (`0x0000000300000000`), and the inter-column gap widens automatically to fit; 32-bit columns are unaffected.

### Removed
- **`light` and `monochrome` built-in themes** — `default` and `plantuml` are the two supported built-ins; `light`/`monochrome` are no longer documented, tested, or shipped as examples.
- **`palette`** — automatic address-order section coloring removed; use explicit `views[id].sections[id].fill` overrides instead.
- **`diagram.json` top-level `"size"`** — canvas is always auto-sized from content; `"size"` is now a deprecated no-op (triggers a validation warning).
- **`views[].pos`** — view position is always computed by auto-layout; `"pos"` is now a deprecated no-op (triggers a validation warning).
- **`views[].size`** — view dimensions are always computed by auto-layout; `"size"` is now a deprecated no-op (triggers a validation warning).
- **`mmpviz.py --validate`** — superseded by the integrated pipeline; schema validation now runs automatically on every render.
- **`band-too-wide` check rule** — replaced by `link-anchor-out-of-bounds`; the horizontal span of a link band is a layout consequence, not an error indicator.

---

## [2026-04-12]

### Added
- **Flat, self-contained view schema** — each view fully declares its own `sections[]` inline; no global section pool, no references. Each section requires `id`, `address`, `size`, `name`; `flags` is optional. Section `id`s are unique within a view.
- **`links` array format** — flat array of `{"from": {"view", "sections?"}, "to": {"view", "sections?"}}` entries; supports multi-section spans, address-range anchors, multi-level zoom, and fan-in.
- **`to.sections`** — link destination can specify its own address anchor independently of the source, enabling cross-address mappings (aliases, virtual→physical, DMA).
- **`sections[].name` required** — use `""` to suppress the label.
- **ID format and uniqueness enforced** — section ids must match `[a-z0-9_-]`; duplicates within a view are rejected at load time.
- **`section-overlap` / `uncovered-gap` checks** — warns on overlapping visible sections and large uncompressed address gaps.
- **New link examples** — `anchor_to_section`, `anchor_cross_addr`, `anchor_addr_range`.

### Changed
- View coordinate space is derived solely from the view's own `sections[]`; no implicit filtering.
- Link destination bands clamp to the destination view's extent when `to.sections` is absent.
- `min_section_height` now applies to all views, not only those with break sections.
- **`min-height-violated` check** — no longer reports false positives when the layout raises sections to the `min_section_height` floor; validation uses the same section geometry as rendering.

### Removed
- **Top-level `sections[]` array** — superseded by inline sections per view. Each view is self-contained.
- **`ref_id`** — reference to a global section; no longer exists. Declare sections inline in each view.
- **`views[].range`**, **`views[].section_size`** — implicit section filters; superseded by the explicit `sections[]` list.
- **`sections[].flags: ["hidden"]`** — hide a section without removing it; simply omit the section from the view instead.
- **`links.sub_sections`**, **`links.addresses`** — superseded by the new `links` array format.
- **Address-containment auto-layout** — views are no longer placed by implicit address containment; explicit `links[]` is required for column placement of related views.

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
