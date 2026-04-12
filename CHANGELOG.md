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

### Removed
- **Top-level `sections[]` array** — superseded by inline sections per view. Each view is self-contained.
- **`ref_id`** — reference to a global section; no longer exists. Declare sections inline in each view.
- **`views[].range`**, **`views[].section_size`** — implicit section filters; superseded by the explicit `sections[]` list.
- **`sections[].flags: ["hidden"]`** — hide a section without removing it; simply omit the section from the view instead.
- **`links.sub_sections`**, **`links.addresses`** — superseded by the new `links` array format.
- **Address-containment auto-layout** — views are no longer placed by implicit address containment; explicit `links[]` is required for column placement of related views.

### Fixed
- **`min-height-violated` false positives** — `check.py` was measuring raw proportional section height instead of actual rendered height; sections correctly raised to the `min_section_height` floor by the layout algorithm were incorrectly flagged.
- **`AreaView.apply_section_geometry()`** — section geometry assignment (size/position fields) is now a single shared method called by both the renderer and `check.py`, eliminating the duplicated code that caused the above bug.

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
