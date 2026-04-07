# theme.json — Schema Reference

A `theme.json` file controls the visual appearance of the diagram. It is completely
separate from `diagram.json` — themes are reusable across different diagrams.

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
1. Built-in defaults (hardcoded in theme.py)
2. `theme.defaults`
3. `theme.areas[area_id]`
4. `theme.areas[area_id].sections[section_id]`

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

### Visibility (auto-hide logic)

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `hide_size` | `"auto"` / `true` / `false` | `"auto"` | Hide size label. `"auto"` hides when section height < 20px |
| `hide_name` | `"auto"` / `true` / `false` | `"auto"` | Hide name label |
| `hide_address` | `"auto"` / `true` / `false` | `"auto"` | Hide address label |

### Break Sections

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `break_type` | string | `"≈"` | Break pattern style: `"≈"` (double wave), `"~"` (wave), `"/"` (diagonal), `"..."` (dots) |
| `break_size` | number | `20` | Height in pixels of a break section |

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
    "break_type": "≈",
    "break_size": 24,
    "growth_arrow_size": 1,
    "growth_arrow_fill": "#e94560",
    "growth_arrow_stroke": "#e94560",
    "hide_size": "auto",
    "hide_name": "auto",
    "hide_address": "auto"
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
