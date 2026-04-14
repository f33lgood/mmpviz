# theme.json — Schema Reference

A `theme.json` file controls the visual appearance of the diagram. It is completely
separate from `diagram.json` — themes are reusable across different diagrams.

The machine-readable contract for this format lives in `schemas/theme.schema.json`
(JSON Schema draft 2020-12).

---

## Built-in Themes

Two ready-to-use themes live in the `themes/` directory at the repository root.
Pass either by name or by path:

```bash
python scripts/mmpviz.py -d diagram.json -t plantuml -o map.svg   # by name
python scripts/mmpviz.py -d diagram.json -t themes/plantuml.json -o map.svg  # by path
```

| Name | File | Description |
|------|------|-------------|
| `default` | `themes/default.json` | Neutral black/white/gray palette. **Loaded automatically when `-t` is omitted.** |
| `plantuml` | `themes/plantuml.json` | PlantUML-style pastel fills with red outlines. |

`themes/default.json` defines the complete set of all `base`, `links`, `labels`, and `growth_arrow` properties; it is the authoritative baseline for link configuration. `themes/plantuml.json` uses `extends: "default"` and overrides only the visual appearance (fill, stroke, opacity, font) while inheriting the link geometry. Both themes have no view- or section-specific overrides, so they work with any `diagram.json` without modification.

---

## Structure Overview

```
theme.json
├── schema_version   → integer; theme file format generation (optional)
├── extends          → built-in name or path to inherit from (optional)
├── base             → global baseline (cascade vocabulary: fill, stroke, font, …)
├── views
│   └── <view-id>    → overrides for a specific view (by id from diagram.json)
│       ├── sections
│       │   └── <section-id>  → overrides for a specific section within that view
│       └── labels
│           └── <label-id>    → overrides for a specific label within that view
├── links            → feature: cross-view connection bands + per-link overrides
├── labels           → feature: address annotation leader lines
└── growth_arrow     → feature: grows-up/grows-down arrow styling
```

**Resolution order for `base` properties** (later overrides earlier):
1. Built-in fallback defaults (`Theme.DEFAULT` in `theme.py`)
2. `theme.base` (global baseline from the loaded theme file, or its `extends` ancestor)
3. `theme.views[view_id]`
4. `theme.views[view_id].sections[section_id]`

**Resolution order for `links` properties** — resolved through the `extends` chain with two-level merging: `connector` and `band` sub-objects are merged shallowly, so a child can override individual keys (e.g. `connector.fill`) without losing keys it did not mention. When both `connector` and `band` are present in the resolved style, `band` takes priority. `themes/default.json` defines the complete `connector` baseline; themes using `extends: "default"` inherit it and need only override what changes.

---

## `schema_version` — Format Tracking

An optional integer at the top level. Tracks theme file format generation,
independent of mmpviz's semantic version.

```json
{ "schema_version": 1, "base": { ... } }
```

| Value | Behaviour |
|-------|-----------|
| Absent | Silent — treated as compatible |
| Equal to current (`1`) | No-op |
| Older than current | `logger.warning` — file may use a deprecated key |
| Newer than current | `ThemeError` — mmpviz is too old to read this file |

Official themes always declare `"schema_version": 1`.

---

## `extends` — Theme Inheritance

Inherit all settings from another theme and override only what changes:

```json
{
  "schema_version": 1,
  "extends": "plantuml",
  "base": { "stroke": "#cc2200" }
}
```

The `extends` value is resolved in order:
1. A built-in name (`"default"`, `"plantuml"`) → loaded from `themes/`
2. A relative path → resolved relative to the inheriting file's directory
3. An absolute path → used as-is

**Merge semantics:**
- `base`, `labels`, `growth_arrow` — shallow merge; child values override parent
- `links` — two-level merge: `connector`, `band`, and `overrides` sub-objects are merged shallowly, so a child can override `connector.fill` without losing `connector.source.width` inherited from the parent; individual `overrides[link_id]` entries are merged by key
- `views` — two-level merge (view properties, then `sections[section_id]` and `labels[label_id]` entries within each view)
- `schema_version` and `extends` are stripped from the merged result

**Circular or missing references** raise `ThemeError` at load time.

---

## Style Properties

All property names use `snake_case`. The renderer translates them to SVG `kebab-case`.

### Color and Stroke

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `background` | color string | `"white"` | View frame background fill |
| `fill` | color string | `"lightgrey"` | Section box fill color |
| `stroke` | color string | `"black"` | Outline color for boxes and frames |
| `stroke_width` | number | `1` | Outline thickness in pixels |
| `stroke_dasharray` | string | `"3,2"` | SVG dash pattern (e.g. `"5,3"` or `"none"`) |
| `opacity` | number 0–1 | `1` | Element opacity |

### Text

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `font_size` | number or string | `16` | Font size in px (number or `"16px"`) |
| `font_family` | string | `"Helvetica"` | Font family |
| `text_fill` | color string | `"black"` | Text color for the section **name** label inside the box. Address labels outside the box always use the view-level `text_fill`, so a dark-background section with `"text_fill": "#ffffff"` does not turn its boundary address labels white. |
| `text_stroke` | color string | `"black"` | Text outline color |
| `text_stroke_width` | number | `0` | Text outline thickness |

### Break Sections

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `break_height` | number | `20` | Height in pixels of a break section |
| `break_fill` | color string | *(same as `fill`)* | Background fill of a break-section box. Falls back to `fill` when unset. |

### Section Height Clamping

Controls how pixel height is distributed across subareas (regions between break sections).

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `min_section_height` | number | `20` ¹ | Guarantees every visible section renders at least this many pixels tall. The renderer redistributes height so that the smallest visible section meets this threshold. |
| `max_section_height` | number | `300` ¹ | Caps the pixel height of any single section so it cannot crowd out neighbors. |

¹ Default values come from `themes/default.json`.

**How they interact:**
- When neither is set, sections are sized strictly proportional to their byte range.
- `min_section_height` alone: expands small sections; excess space is taken from larger sections proportionally.
- `max_section_height` alone: shrinks oversized sections; freed space is redistributed proportionally.
- Both set: the minimum floor always wins — a section that needs more than `max_section_height` to satisfy `min_section_height` is given the floor, not the cap.

**Label-conflict inflation (automatic, no setting required):** the renderer also detects when a section's size label (top-left) and name label (centred) would overlap on the x-axis, and inflates that section's height just enough to separate them vertically. This applies independently of `min_section_height`.

---

## `growth_arrow` — Grows-up/Grows-down Arrow Style

The `growth_arrow` block controls the visual style of the directional arrows rendered on sections marked with the `grows-up` or `grows-down` flag. It is a top-level block parallel to `links` and `labels`.

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `size`   | number ≥ 0 | `1` | Arrow size multiplier |
| `fill`   | color string | `"#e8e8e8"` | Arrow body fill color |
| `stroke` | color string | `"#555555"` | Arrow outline color |

```json
"growth_arrow": {
  "size":   1,
  "fill":   "#e8e8e8",
  "stroke": "#555555"
}
```

---

## `labels` — Address Annotation Style

The `labels` block owns all label-specific styling: the leader line, arrow head, and optional text overrides. It is merged on top of the global `base` (so `font_size`, `text_fill`, etc. inherit from there unless overridden here).

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `arrow_size` | number ≥ 0 | `2` | Arrow head size multiplier |
| `stroke` | color string | `"#555555"` | Leader line color |
| `stroke_width` | number ≥ 0 | `1` | Leader line thickness in pixels |
| `stroke_dasharray` | string | `"4,2"` | SVG dash pattern for the leader line |
| `font_size` | number \| string | *(inherited)* | Override label text font size |
| `font_family` | string | *(inherited)* | Override label text font family |
| `text_fill` | color string | *(inherited)* | Override label text color |

```json
"labels": {
  "arrow_size":       2,
  "stroke":           "#555555",
  "stroke_width":     1,
  "stroke_dasharray": "4,2"
}
```

---

## `links` — Section Band Style

The `links` block controls the visual style of section band connectors drawn between the source stack and detail stacks. It has two sub-formats: **`connector`** (recommended) and **`band`** (legacy). Define one or both; when both are present `band` takes priority.

---

### `connector` — Recommended Format

The connector is a two-trapezoid + center-line design:

```
source view       source end     middle line     dest end    dest view
    │        ╔══╗                ─────────      ╔══╗         │
    │        ║  ╚━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  ║         │
    │        ╚══╝                               ╚══╝         │
    │←─ src.width ─→│←──────────────────────────→│←dst.width─→│
```

- The **source trapezoid** fans out from the middle-line width (`middle.width`) to the full source region span.
- The **middle line** is a stroked centerline of constant perpendicular thickness.
- The **destination trapezoid** tapers from the destination region span back to the middle-line width.
- A single `fill` color applies to both trapezoid fills and the middle line stroke.

```json
"links": {
  "connector": {
    "source":      { "width": 25 },
    "destination": { "width": 25 },
    "middle":      { "width": 10, "shape": "curve" },
    "fill":        "#e8e8e8",
    "opacity":     0.7
  }
}
```

#### `connector` properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `connector.source.width` | number ≥ 0 | `25` | Horizontal extent in pixels of the source trapezoid |
| `connector.destination.width` | number ≥ 0 | `25` | Horizontal extent in pixels of the destination trapezoid |
| `connector.middle.width` | number ≥ 0 | `10` | Stroke width of the middle line in pixels |
| `connector.middle.shape` | `"curve"` \| `"straight"` | `"curve"` | `"curve"` draws a cubic Bézier S-curve (line cap: butt); `"straight"` draws a direct line (line cap: round) |
| `connector.fill` | color string | `"#e8e8e8"` | Color applied to both trapezoid fills and the middle line stroke |
| `connector.opacity` | number 0–1 | `0.7` | Overall connector opacity |

**Overriding only a subset** (e.g. just fill and opacity) works naturally through the `extends` chain — unmentioned keys are inherited from the parent theme:

```json
{
  "schema_version": 1,
  "extends": "default",
  "links": {
    "connector": { "fill": "#4A7FA5", "opacity": 0.5 }
  }
}
```

---

### `band` — Full Three-Segment Format

Full three-segment control with independent fill/stroke. Use when you need shapes the connector cannot express (e.g. a plain filled trapezoid with no source/dest taper, or a dashed stroke outline). Mirrors the `connector` nested structure: segments (`source`, `middle`, `destination`) are sub-objects, with shared visual properties at the top level.

```
source view                                              dest view
    │  ←─ source ──→│←──────── middle ────────────→│←── destination ──→  │
    │   (.width)    │        (fills remainder)       │      (.width)       │
```

Each segment has an independently configurable `shape` and heights for its source-side (`sheight`) and destination-side (`dheight`) edges. **`sheight`/`dheight` are directional relative to the whole link** — `sheight` is always the edge closer to the source view, `dheight` always the edge closer to the destination view.

**Center alignment (automatic):** the vertical center of every edge is fixed by segment position:

| Segment | Source-side edge center | Destination-side edge center |
|---------|------------------------|------------------------------|
| `source` | source region center | source region center |
| `middle` | source region center | destination region center |
| `destination` | destination region center | destination region center |

**Height references** (`sheight` / `dheight`) select the **span** at that edge:
- `"source"` — spans the `from.sections` pixel height
- `"destination"` — spans the `to.sections` pixel height
- `<number>` — literal pixel span; `0` collapses the edge to a point

#### `band` segment sub-object properties

| Sub-object | Property | Type | Default | Description |
|------------|----------|------|---------|-------------|
| `source` | `shape` | `"straight"` \| `"curve"` | `"straight"` | Edge shape of the source outreach segment |
| `source` | `width` | number ≥ 0 | `0` | Width in pixels; `0` = no outreach |
| `source` | `sheight` | height ref | `"source"` | Height at the source-view (outer) edge |
| `source` | `dheight` | height ref | `"source"` | Height at the junction (inner) edge |
| `middle` | `shape` | `"straight"` \| `"curve"` | `"straight"` | Edge shape of the middle connecting segment |
| `middle` | `sheight` | height ref | `"source"` | Height at the source-side edge |
| `middle` | `dheight` | height ref | `"destination"` | Height at the destination-side edge |
| `destination` | `shape` | `"straight"` \| `"curve"` | `"straight"` | Edge shape of the destination outreach segment |
| `destination` | `width` | number ≥ 0 | `0` | Width in pixels; `0` = no outreach |
| `destination` | `sheight` | height ref | `"destination"` | Height at the junction (inner) edge |
| `destination` | `dheight` | height ref | `"destination"` | Height at the destination-view (outer) edge |

#### `band` top-level properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `fill` | color string \| `"none"` | `"none"` | Fill color for the band interior |
| `stroke` | color string \| `"none"` | `"none"` | Stroke color for the top and bottom band edges |
| `stroke_width` | number | `1` | Stroke thickness in pixels |
| `stroke_dasharray` | string | *(unset)* | SVG dash pattern for stroke edges, e.g. `"8,4"` |
| `opacity` | number 0–1 | `1` | Overall band opacity |

**Composing `fill` and `stroke`:** both are independent. Setting both draws a filled closed band plus stroked top/bottom open paths. Continuity: set `source.dheight == middle.sheight` and `middle.dheight == destination.sheight` for seamless junctions.

#### `band` example configurations

```json
{
  "schema_version": 1,
  "extends": "default",
  "links": {
    "band": {
      "middle":  { "shape": "straight", "sheight": "source", "dheight": "destination" },
      "fill":    "#4A7FA5",
      "stroke":  "none",
      "opacity": 0.5
    }
  }
}
```

| Style | What to set | Visual result |
|-------|-------------|---------------|
| Plain trapezoid (fill) | `middle: {sheight: "source", dheight: "destination"}`, `fill: <color>` | Filled trapezoid, straight or Bézier edges |
| Stroke only | Same + `fill: "none"`, `stroke: <color>`, `stroke_width: 2` | Outlined trapezoid, no fill |
| Dashed stroke | Add `stroke_dasharray: "8,4"` | Dashed outline |
| Three segments | Set `source: {width: 20, …}`, `destination: {width: 20, …}` with matching heights | Three distinct segments with visible junctions |

---

### `links.overrides` — Per-Link Style Overrides

Override the visual style of individual links by their `id` from `diagram.json`. Entries are merged on top of the resolved `connector` or `band` style.

```json
"links": {
  "overrides": {
    "flash-link":  { "fill": "#3B82F6", "opacity": 0.7 },
    "periph-link": { "fill": "#F97316", "opacity": 0.7 },
    "dma-link":    { "fill": "#22C55E", "opacity": 0.7 }
  }
}
```

| Property | Type | Description |
|----------|------|-------------|
| `fill` | color string | Override connector/band fill for this specific link |
| `opacity` | number 0–1 | Override opacity for this specific link |
| `stroke` | color string | Override stroke color (band format) |
| `stroke_width` | number | Override stroke thickness (band format) |
| `stroke_dasharray` | string | Override dash pattern (band format) |

Any key omitted from the override is inherited from the global `connector` or `band` style.

---

## Color Values

Any valid SVG color string is accepted:
- Named colors: `"white"`, `"black"`, `"lightgrey"`, `"none"`
- Hex: `"#212b38"`, `"#08c6ab"`
- RGB: `"rgb(33, 43, 56)"`

---

## Examples

| Example | What it shows |
|---------|---------------|
| `examples/link/connector/theme.json` | `connector` — all properties explicit: source/dest widths, middle width and shape, fill, opacity |
| `examples/link/band_fill/theme.json` | `band` — filled straight trapezoid spanning source→destination, no source/dest outreach |
| `examples/link/band_stroke/theme.json` | `band` — dashed stroke outline, no fill |
| `examples/link/band_segments/theme.json` | `band` — three explicit segments with matching heights at junctions |
| `examples/link/per_link/theme.json` | `links.overrides` — three individually colored links keyed by link `id` |
| `examples/stack/basic/theme.json` | `extends` + per-view `sections` overrides — section-level fills |
| `examples/chips/stm32f103/theme.json` | `extends: "plantuml"` + per-view overrides — multi-panel chip diagram |
| `examples/chips/caliptra/theme.json` | Per-section colors via `views[id].sections[id]` — six independently styled panels |

---

## Tips

- Keep theme files small — use `"extends"` to inherit a built-in and override only what changes.
- Use one shared theme for a family of diagrams (e.g. all boards in a product line).
- The `sections` key inside a view override accepts section `id` values, not `name` values.
- `"stroke_dasharray": "none"` disables dashing for solid outlines.
- `min_section_height` and `max_section_height` are especially useful for chips with both large (GB) and tiny (KB) sections in the same view.
