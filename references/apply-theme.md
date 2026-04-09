# How to Apply and Customize a Theme

This guide explains how to use an existing theme and how to write your own.

---

## Step 1: Choose a starting theme

Two ready-to-use themes are included in `examples/`:

| File | Description |
|------|-------------|
| `examples/light_theme.json` | Light background, pastel section colors |
| `examples/dark_theme.json`  | Dark background, saturated accent colors |

Apply a theme with `-t`:

```bash
python scripts/mmpviz.py -d diagram.json -t examples/light_theme.json -o output.svg
python scripts/mmpviz.py -d diagram.json -t examples/dark_theme.json  -o output.svg
```

Omit `-t` entirely to use built-in defaults (light gray sections on a white background).

---

## Step 2: Understand the resolution order

When rendering a section, styles are merged in this order (later overrides earlier):

1. Built-in defaults (hardcoded in `theme.py`)
2. `theme.defaults` — your global baseline
3. `theme.areas[area_id]` — overrides for one area panel
4. `theme.areas[area_id].sections[section_id]` — overrides for one specific section

This means you can set a default fill for all sections, then override only the ones that matter.

---

## Step 3: Create your own theme file

Start from `examples/light_theme.json` and adjust values. The minimal structure is:

```json
{
  "defaults": {
    "background": "white",
    "fill": "lightgrey",
    "stroke": "#adb5bd",
    "text_fill": "#212529",
    "font_size": 13
  }
}
```

Add `areas` to style specific panels and sections within them:

```json
{
  "defaults": {
    "background": "#f8f9fa",
    "fill": "#e9ecef",
    "stroke": "#adb5bd",
    "text_fill": "#212529",
    "font_size": 13,
    "font_family": "Helvetica"
  },
  "areas": {
    "flash-view": {
      "background": "white",
      "fill": "#caf0f8",
      "text_fill": "#023e8a",
      "sections": {
        "text":   { "fill": "#48cae4" },
        "rodata": { "fill": "#90e0ef" }
      }
    },
    "sram-view": {
      "fill": "#d8f3dc",
      "text_fill": "#1b4332",
      "sections": {
        "stack": { "fill": "#52b788" }
      }
    }
  }
}
```

The `area_id` keys (`"flash-view"`, `"sram-view"`) must match the `id` fields in `diagram.json`'s `areas` array.
The `section_id` keys under `sections` must match `id` fields in `diagram.json`'s `sections` array.

---

## Step 4: Style properties reference

### Layout and color

| Property | Type | Default | Effect |
|----------|------|---------|--------|
| `background` | color | `"white"` | Area panel background |
| `fill` | color | `"lightgrey"` | Section box fill |
| `stroke` | color | `"black"` | Box and panel outline color |
| `stroke_width` | number | `1` | Outline thickness in pixels |
| `stroke_dasharray` | string | `"3,2"` | SVG dash pattern (`"none"` for solid) |
| `opacity` | 0–1 | `1` | Element opacity |

### Text

| Property | Type | Default | Effect |
|----------|------|---------|--------|
| `font_size` | number | `16` | Font size in pixels |
| `font_family` | string | `"Helvetica"` | Font family |
| `text_fill` | color | `"black"` | Text color |
| `text_stroke` | color | `"black"` | Text outline color |
| `text_stroke_width` | number | `0` | Text outline thickness |

### Break sections

| Property | Type | Default | Effect |
|----------|------|---------|--------|
| `break_size` | number | `20` | Height in pixels of each break |

### Growth arrows

| Property | Type | Default | Effect |
|----------|------|---------|--------|
| `growth_arrow_size` | number | `1` | Arrow size multiplier |
| `growth_arrow_fill` | color | `"white"` | Arrow body fill |
| `growth_arrow_stroke` | color | `"black"` | Arrow outline color |

### Auto-hide labels

| Property | Allowed values | Default | Effect |
|----------|---------------|---------|--------|
| `hide_size` | `"auto"`, `true`, `false` | `"auto"` | Hide size label when section is tiny |
| `hide_name` | `"auto"`, `true`, `false` | `"auto"` | Hide name label when section is tiny |
| `hide_address` | `"auto"`, `true`, `false` | `"auto"` | Hide address label when section is tiny |

`"auto"` hides when the rendered section height falls below 20 px.

---

## Step 5: Style links and labels

Add `"links"` and `"labels"` keys at the top level of your theme:

```json
{
  "links": {
    "stroke": "#adb5bd",
    "fill": "#dee2e6",
    "opacity": 0.5
  },
  "labels": {
    "stroke": "#6c757d",
    "stroke_width": 1,
    "stroke_dasharray": "4,2"
  }
}
```

Links are the connecting bands between areas. Labels are the annotated address lines drawn inside or beside an area panel.

---

## Step 6: Accepted color formats

Any valid SVG color string works:

```
"white"           named color
"#caf0f8"         hex
"rgb(33, 43, 56)" RGB function
"none"            transparent / no fill
```

---

## Tips

- Keep theme files small — only set properties you want to change from the defaults.
- Use one shared theme for a family of diagrams (e.g. all boards in a product line).
- The `sections` key inside an area override only accepts section `id` values, not section `name` values.
- `stroke_dasharray: "none"` disables dashing for solid outlines.
