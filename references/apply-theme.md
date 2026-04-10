# How to Apply and Customize a Theme

This guide explains how to use an existing theme and how to write your own.

---

## Step 1: Choose a starting theme

Four ready-to-use themes live in `themes/`. Pass them by name or by path:

| Name | File | Description |
|------|------|-------------|
| `default` | `themes/default.json` | Neutral black/white/gray. **Loaded automatically when `-t` is omitted.** |
| `light` | `themes/light.json` | Steel-blue fills, white backgrounds, dark text. Suitable for printed documents. |
| `monochrome` | `themes/monochrome.json` | Grayscale only, high contrast. Suitable for black-and-white printing. |
| `plantuml` | `themes/plantuml.json` | PlantUML-style pastel fills with red outlines. |

```bash
# by name (shorthand)
python scripts/mmpviz.py -d diagram.json -t light      -o output.svg
python scripts/mmpviz.py -d diagram.json -t monochrome -o output.svg

# by path
python scripts/mmpviz.py -d diagram.json -t themes/light.json -o output.svg

# omit -t to use the default theme
python scripts/mmpviz.py -d diagram.json -o output.svg
```

---

## Step 2: Understand the resolution order

When rendering a section, styles are merged in this order (later overrides earlier):

1. Built-in fallback defaults (`Theme.DEFAULT` in `theme.py`)
2. `theme.style` — the global baseline from the loaded theme (or its `extends` ancestor)
3. `theme.areas[area_id]` — overrides for one area panel
4. `theme.areas[area_id].sections[section_id]` — overrides for one specific section

This means you can set a default fill for all sections, then override only the ones
that matter.

---

## Step 3: Create a delta theme with `"extends"`

The easiest way to customize is to inherit from a built-in theme and override only
what you want to change:

```json
{
  "schema_version": 1,
  "extends": "light",
  "style": {
    "stroke": "#cc2200",
    "fill": "#ffe8e8"
  }
}
```

Save this as `my_theme.json` and pass it with `-t my_theme.json`. All unspecified
properties are inherited from `themes/light.json`.

The `extends` value can be:
- A built-in name: `"default"`, `"light"`, `"monochrome"`, `"plantuml"`
- A relative path from the theme file's directory: `"../base_theme.json"`

---

## Step 4: Create a full theme file

To start from scratch without inheriting, omit `"extends"` and supply a complete
`"style"` block:

```json
{
  "schema_version": 1,
  "style": {
    "background": "#f8f9fa",
    "fill": "#e9ecef",
    "stroke": "#adb5bd",
    "text_fill": "#212529",
    "font_size": 13,
    "font_family": "Helvetica"
  }
}
```

Add `areas` to style specific panels and sections within them:

```json
{
  "schema_version": 1,
  "style": {
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

The `area_id` keys (`"flash-view"`, `"sram-view"`) must match the `id` fields in
`diagram.json`'s `areas` array. The `section_id` keys under `sections` must match
`id` fields in `diagram.json`'s `sections` array.

---

## Step 5: Style properties reference

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
| `break_fill` | color | *(same as `fill`)* | Background fill for break-section boxes |

### Section height clamping

| Property | Type | Default | Effect |
|----------|------|---------|--------|
| `min_section_height` | number | `20` | Minimum pixel height per visible section |
| `max_section_height` | number | `300` | Maximum pixel height per section |

### Growth arrows

| Property | Type | Default | Effect |
|----------|------|---------|--------|
| `growth_arrow_size` | number | `1` | Arrow size multiplier |
| `growth_arrow_fill` | color | `"white"` | Arrow body fill |
| `growth_arrow_stroke` | color | `"black"` | Arrow outline color |

---

## Step 6: Style links and labels

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

Links are the connecting bands between areas. Labels are the annotated address lines
drawn inside or beside an area panel.

---

## Step 7: Accepted color formats

Any valid SVG color string works:

```
"white"           named color
"#caf0f8"         hex
"rgb(33, 43, 56)" RGB function
"none"            transparent / no fill
```

---

## Tips

- Keep theme files small — use `"extends"` to inherit a built-in base and only
  override what you need.
- Use one shared theme for a family of diagrams (e.g. all boards in a product line).
- The `sections` key inside an area override only accepts section `id` values, not
  section `name` values.
- `stroke_dasharray: "none"` disables dashing for solid outlines.
- `min_section_height` and `max_section_height` are especially important for chips
  with both large (GB) and tiny (KB) sections in the same area.
