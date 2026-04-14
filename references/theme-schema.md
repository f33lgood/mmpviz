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

`themes/default.json` defines the complete set of all `style`, `links`, and `labels` properties; it is the authoritative baseline for link configuration. `themes/plantuml.json` uses `extends: "default"` and overrides only the visual appearance (fill, stroke, opacity, font) while inheriting the link geometry. Both themes have no view- or section-specific overrides, so they work with any `diagram.json` without modification.

---

## Structure Overview

```
theme.json
├── schema_version   → integer; theme file format generation (optional)
├── extends          → built-in name or path to inherit from (optional)
├── style            → global baseline (applies to everything)
├── views
│   └── <view-id>    → overrides for a specific view (by id from diagram.json)
│       └── sections
│           └── <section-id>  → overrides for a specific section within that view
├── links            → style for cross-view connection bands
└── labels           → style for address annotation lines
```

**Resolution order for `style` properties** (later overrides earlier):
1. Built-in fallback defaults (`Theme.DEFAULT` in `theme.py`)
2. `theme.style` (global baseline from the loaded theme file, or its `extends` ancestor)
3. `theme.views[view_id]`
4. `theme.views[view_id].sections[section_id]`

**Resolution order for `links` properties** — resolved solely through the `extends` chain: the merged `links` block across all ancestors, with child values overriding parent. `themes/default.json` defines the complete baseline; any theme using `extends: "default"` (directly or transitively) inherits all link properties.

---

## `schema_version` — Format Tracking

An optional integer at the top level. Tracks theme file format generation,
independent of mmpviz's semantic version.

```json
{ "schema_version": 1, "style": { ... } }
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
  "style": { "stroke": "#cc2200" }
}
```

The `extends` value is resolved in order:
1. A built-in name (`"default"`, `"plantuml"`) → loaded from `themes/`
2. A relative path → resolved relative to the inheriting file's directory
3. An absolute path → used as-is

**Merge semantics:**
- `style`, `links`, `labels` — shallow merge; child values override parent
- `views` — two-level merge (view properties, then section properties within each view)
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

### Growth Arrows

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `growth_arrow_size` | number | `1` | Arrow size multiplier |
| `growth_arrow_fill` | color string | `"white"` | Arrow fill color |
| `growth_arrow_stroke` | color string | `"black"` | Arrow outline color |

### Labels and Links

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `label_arrow_size` | number | `2` | Arrow head size multiplier for labels |

---

## `links` — Section Band Style

The `links` block controls the visual style of section band connectors drawn between the source stack and detail stacks.

A band is composed of three independent segments:

```
source view                                           dest view
    │  ←─ source_seg ──→│←────── middle_seg ────────→│←─ dest_seg ─→  │
    │      (src_w px)    │       (fills remainder)     │   (dst_w px)   │
```

Each segment has a configurable shape, and independently configurable heights for its left and right edges.

**Center alignment (automatic):** The vertical center of every edge is fixed by which segment it belongs to — no configuration needed:

| Segment | Left edge center | Right edge center |
|---------|-----------------|------------------|
| `source_seg` | source region center | source region center |
| `middle_seg` | source region center | destination region center |
| `dest_seg` | destination region center | destination region center |

**Height references** (`lheight` / `rheight`) select the **span** (pixel height) of the band at that edge:
- `"source"` — band spans the `from.sections` pixel height
- `"destination"` — band spans the `to.sections` pixel height (or clamped full dest view when `to.sections` is absent)

The edge y-coordinates are then: `center ± span/2`. This lets the band maintain source width through the curve while naturally shifting its center to align with the destination.

### Segment properties

The **Default** column shows the values defined in `themes/default.json`, which is the authoritative baseline for link configuration. Custom themes that use `extends: "default"` inherit all these values and only need to set the keys that differ.

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `source_seg_shape` | `"polygon"` \| `"curve"` | `"polygon"` | Edge shape of the source outreach segment |
| `source_seg_width` | number ≥ 0 | `0` | Width in pixels of the source outreach; `0` = no outreach |
| `source_seg_lheight` | `"source"` \| `"destination"` | `"source"` | Height at the source-view edge of this segment |
| `source_seg_rheight` | `"source"` \| `"destination"` | `"source"` | Height at the junction with the middle segment |
| `middle_seg_shape` | `"polygon"` \| `"curve"` | `"curve"` | Edge shape of the middle connecting segment |
| `middle_seg_lheight` | `"source"` \| `"destination"` | `"source"` | Height at the left edge of the middle segment |
| `middle_seg_rheight` | `"source"` \| `"destination"` | `"source"` | Height at the right edge of the middle segment |
| `dest_seg_shape` | `"polygon"` \| `"curve"` | `"curve"` | Edge shape of the destination outreach segment |
| `dest_seg_width` | number ≥ 0 | `30` | Width in pixels of the destination outreach; `0` = no outreach |
| `dest_seg_lheight` | `"source"` \| `"destination"` | `"source"` | Height at the junction with the middle segment |
| `dest_seg_rheight` | `"source"` \| `"destination"` | `"destination"` | Height at the destination-view edge of this segment |

### Visual properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `fill` | color string \| `"none"` | `"#e8e8e8"` | Fill color for the band interior. Set to `"none"` for stroke-only |
| `stroke` | color string \| `"none"` | `"none"` | Stroke color for the top and bottom band edges. Set to a color to draw edges |
| `stroke_width` | number | `1` | Stroke thickness in pixels |
| `stroke_dasharray` | string | *(unset)* | SVG dash pattern for stroke edges, e.g. `"8,4"`. Omit for solid stroke |
| `opacity` | number 0–1 | `0.7` | Overall opacity of the band |

**Composing styles:** `fill` and `stroke` are independent. Setting both draws a filled closed band plus stroked top/bottom edges. The stroked edges are drawn as open paths (no right vertical) so they never overlap the detail stack's own border.

**Continuity:** for a seamless band, adjacent segment heights should match at their shared junction — e.g. `source_seg_rheight` should equal `middle_seg_lheight`.

**Example configurations** (all assume `extends: "default"` as base):

| Style | Key overrides | Visual result |
|-------|--------------|---------------|
| **Default theme** | see `themes/default.json` | S-curve + 30 px Bézier dest taper, light-gray fill |
| Fill style | `"fill": "<color>", "stroke": "none"` | Base shape (S-curve + dest taper) in a custom fill color |
| Stroke only | `"fill": "none", "stroke": "<color>", "stroke_width": 2` | Base shape, edges only |
| Dashed stroke | `"fill": "none", "stroke": "<color>", "stroke_width": 2, "stroke_dasharray": "8,4"` | Base shape, dashed edges |
| Polygon middle | `"middle_seg_shape": "polygon", "middle_seg_rheight": "destination", "dest_seg_width": 0` | Straight trapezoidal connector; contrasts the default S-curve |
| All three segments | `"source_seg_shape": "polygon", "source_seg_width": 20, "middle_seg_shape": "polygon", "middle_seg_rheight": "destination", "dest_seg_shape": "polygon", "dest_seg_width": 20` | Three polygon segments; zigzag kinks mark each boundary on both edges |
| Sankey | `"middle_seg_lheight": "source", "middle_seg_rheight": "source", "dest_seg_width": 0` | Constant-width S-curve; band width proportional to source section size |

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
| `examples/themes/default/theme.json` | Minimal override of `default` — global `style`, `links`, `labels` |
| `examples/themes/plantuml/theme.json` | `extends` with no other overrides — inherit a built-in unchanged |
| `examples/stack/basic/theme.json` | `extends` + per-view `sections` overrides — section-level fills |
| `examples/link/cortex_m3/theme.json` | `extends` + `links` visual override (fill + opacity) |
| `examples/link/fill/theme.json` | Default shape (S-curve + dest taper) with fill style |
| `examples/link/stroke/theme.json` | Default shape with stroke-only style |
| `examples/link/stroke_dashed/theme.json` | Default shape with dashed stroke style |
| `examples/link/polygon/theme.json` | Polygon middle (straight trapezoid, no outreach) — contrasts the default S-curve |
| `examples/link/three_segments/theme.json` | All three polygon segments visible: flat source jog → tapered middle → flat dest jog; kinks mark the boundaries |

---

## Tips

- Keep theme files small — use `"extends"` to inherit a built-in and override only what changes.
- Use one shared theme for a family of diagrams (e.g. all boards in a product line).
- The `sections` key inside a view override accepts section `id` values, not `name` values.
- `"stroke_dasharray": "none"` disables dashing for solid outlines.
- `min_section_height` and `max_section_height` are especially useful for chips with both large (GB) and tiny (KB) sections in the same view.
