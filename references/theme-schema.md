# theme.json — Schema Reference

A `theme.json` file controls the visual appearance of the diagram. It is completely
separate from `diagram.json` — themes are reusable across different diagrams.

---

## Built-in Themes

Three ready-to-use themes live in the `themes/` directory at the repository root.
Pass any of them with the `--theme` flag:

```
python scripts/mmpviz.py -d diagram.json -t themes/light.json -o map.svg
```

| File | Description |
|------|-------------|
| `themes/plantuml.json` | PlantUML-style color palette — pastel fills matching the PlantUML component diagram aesthetic. **Loaded automatically when `-t` is omitted.** |
| `themes/light.json` | Professional light theme — white backgrounds, steel-blue fills, dark text. Suitable for printed documents and light-background slides. |
| `themes/monochrome.json` | Grayscale theme — neutral fills, no color, high contrast. Suitable for black-and-white printing. |

These themes set only `defaults` and `links`/`labels` blocks — no area- or section-specific
overrides — so they work with any `diagram.json` without modification.

To use `themes/plantuml.json` as an editable baseline, simply run without `-t`:

```bash
python scripts/mmpviz.py -d diagram.json -o map.svg
```

Edit `themes/plantuml.json` directly to change the global default style without writing a new file.

---

## Structure Overview

```
theme.json
├── defaults          → global baseline (applies to everything)
├── areas
│   └── <area-id>    → overrides for a specific area (by id from diagram.json)
│       └── sections
│           └── <section-id>  → overrides for a specific section within that area
├── links            → style for cross-area connection bands
└── labels           → style for address annotation lines
```

**Resolution order** (later overrides earlier):
1. Built-in fallback defaults (`Theme.DEFAULT` in `theme.py`; active only when `themes/plantuml.json` is absent)
2. `theme.defaults` (the default `themes/plantuml.json` supplies values here)
3. `theme.areas[area_id]`
4. `theme.areas[area_id].sections[section_id]`

---

## `palette` — Automatic Section Colors

An optional top-level array of color strings. When present, sections that have **no
explicit `fill`** at the area or section level are assigned colors from the palette in
address order (first section → `palette[0]`, second → `palette[1]`, wrapping around).
Break sections do not consume a palette slot.

```json
{
  "palette": ["#b8d4e8", "#a8d5ba", "#c9b8d4", "#d4c4a8"],
  "defaults": { ... }
}
```

**Override precedence:**
1. `theme.areas[area_id].sections[section_id].fill` — wins over palette
2. `theme.areas[area_id].fill` — wins over palette
3. `palette[index % len(palette)]` — applied when neither above is set
4. `theme.defaults.fill` — used when no palette is defined

This makes colorful themes fully **portable**: a theme with a palette assigns
distinct colors to whatever sections it encounters, without knowing their IDs.

---

## Style Properties

All property names use `snake_case`. The renderer translates them to SVG `kebab-case`.

### Color and Stroke

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `background` | color string | `"white"` | Area frame background fill |
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
| `text_fill` | color string | `"black"` | Text color |
| `text_stroke` | color string | `"black"` | Text outline color |
| `text_stroke_width` | number | `0` | Text outline thickness |

### Break Sections

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `break_size` | number | `20` | Height in pixels of a break section |
| `break_fill` | color string | *(same as `fill`)* | Background fill of a break-section box. Useful for giving break sections a distinct muted color without changing the normal section fill. Falls back to `fill` when unset. |

### Section Height Clamping

Controls how pixel height is distributed across subareas (regions between break sections).

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `min_section_height` | number | `20` ¹ | Guarantees every visible section renders at least this many pixels tall. The renderer redistributes height so that the smallest visible section meets this threshold. |
| `max_section_height` | number | `300` ¹ | Caps the pixel height of any single section so it cannot crowd out neighbors. |

¹ Default values come from `themes/plantuml.json`. Without a theme file these properties are unset and height is purely proportional.

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
| `weight` | number | `2` | Arrow head size multiplier for labels |

---

## `links` — Section Band Style

The `links` block in `theme.json` controls the visual style of section band connectors drawn between the source stack and detail stacks. All properties are optional.

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `shape` | `"polygon"` \| `"curve"` | `"polygon"` | Band edge shape. `"polygon"` uses straight diagonal lines; `"curve"` uses cubic Bézier curves (Sankey style) |
| `fill` | color string \| `"none"` | `"none"` | Fill color for the band interior. Set to a color for a filled band; `"none"` for stroke-only |
| `stroke` | color string \| `"none"` | `"black"` | Stroke color for the top and bottom band edges. Set to `"none"` for fill-only |
| `stroke_width` | number | `1` | Stroke thickness in pixels |
| `stroke_dasharray` | string | *(none)* | SVG dash pattern for stroke edges, e.g. `"8,4"`. Omit for solid stroke |
| `opacity` | number 0–1 | `1` | Overall opacity of the band |

**Composing styles:** `fill` and `stroke` are independent. Setting both draws a filled closed band plus stroked top/bottom edges. The stroked edges are drawn as open paths (no right vertical) so they never overlap the detail stack's own border.

**Six standard styles:**

| Style | Config |
|-------|--------|
| Polygon, fill only | `"shape": "polygon", "fill": "<color>", "stroke": "none"` |
| Polygon, solid stroke | `"shape": "polygon", "fill": "none", "stroke": "<color>"` |
| Polygon, dashed stroke | `"shape": "polygon", "fill": "none", "stroke": "<color>", "stroke_dasharray": "8,4"` |
| Curve, fill only | `"shape": "curve", "fill": "<color>", "stroke": "none"` |
| Curve, solid stroke | `"shape": "curve", "fill": "none", "stroke": "<color>"` |
| Curve, dashed stroke | `"shape": "curve", "fill": "none", "stroke": "<color>", "stroke_dasharray": "8,4"` |

---

## Color Values

Any valid SVG color string is accepted:
- Named colors: `"white"`, `"black"`, `"lightgrey"`, `"none"`
- Hex: `"#212b38"`, `"#08c6ab"`
- RGB: `"rgb(33, 43, 56)"`

---

## Full Example

```json
{
  "defaults": {
    "background": "#1a1a2e",
    "fill": "#16213e",
    "stroke": "#0f3460",
    "stroke_width": 1,
    "font_size": 13,
    "font_family": "Helvetica",
    "text_fill": "#a8dadc",
    "text_stroke_width": 0,
    "opacity": 1,
    "break_size": 24,
    "growth_arrow_size": 1,
    "growth_arrow_fill": "#e94560",
    "growth_arrow_stroke": "#e94560",
  },
  "areas": {
    "flash-view": {
      "background": "#212b38",
      "fill": "#08c6ab",
      "text_fill": "white",
      "sections": {
        "text":   { "fill": "#1d6fa4" },
        "rodata": { "fill": "#2a9d8f" }
      }
    },
    "sram-view": {
      "fill": "#6b3fa0",
      "text_fill": "#e8d5f5",
      "sections": {
        "stack": { "fill": "#9b72cf" }
      }
    }
  },
  "links": {
    "stroke": "#37465b",
    "fill": "#212b38",
    "opacity": 0.6
  },
  "labels": {
    "stroke": "#a8dadc",
    "stroke_dasharray": "5,3"
  }
}
```
