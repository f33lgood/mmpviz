# mmpviz check.py — Rule Reference

`scripts/check.py` validates a `diagram.json` + `theme.json` pair against nine
layout and display rules without generating SVG output.

## Quick Usage

```
python3 scripts/check.py -d diagram.json -t theme.json
python3 scripts/check.py -d diagram.json -t theme.json --format json
python3 scripts/check.py -d diagram.json -t theme.json --rules panel-overlap,label-overlap
```

Exit codes: **0** = no issues, **1** = one or more ERRORs, **2** = warnings only.

---

## Rule Summary

| Rule | Level | What it detects |
|------|-------|----------------|
| `min-height-violated` | WARN | Section height fell below `min_section_height` |
| `out-of-canvas` | ERROR | Panel extends beyond the canvas boundary |
| `panel-overlap` | ERROR | Two panels' bounding rectangles physically intersect |
| `band-too-wide` | WARN | Link band horizontal span exceeds readability guideline |
| `unresolved-section` | ERROR | `links.sections` entry not found in any view |
| `title-overlap` | WARN | Panel title intrudes into the panel above it |
| `label-overlap` | WARN | Address labels of one panel overlap the next panel |

---

## Per-Section Rules

### `min-height-violated` — WARN

**What it detects:** A section's rendered height is below `min_section_height`. This
means the proportional-fallback algorithm was triggered: `_compute_clamped_heights`
could not satisfy all minimum-height constraints simultaneously within the available
panel space, so it fell back to pure proportional rendering. All minimums are then
violated equally.

**Threshold:** `section.size_y < min_section_height` (with 1e-6 tolerance)

**How to fix:**
- Increase the panel `size` (height) in `diagram.json`.
- Add more break sections to reduce total non-break section count competing for
  the available height.
- Lower `min_section_height` in `theme.json` to a value the panel can satisfy.
- Set `min_section_height: null` to disable the minimum (pure proportional rendering).

---

## Area-Level Rules

### `out-of-canvas` — ERROR

**What it detects:** A panel's right edge (`pos_x + size_x`) or bottom edge
(`pos_y + size_y`) extends beyond the canvas boundary defined by `diagram.json`'s
top-level `"size": [width, height]`.

**How to fix:**
- Increase the canvas `"size"` in `diagram.json`.
- Move the panel left/up by reducing `pos_x` or `pos_y`.
- Reduce the panel `size_x` or `size_y`.

---

### `panel-overlap` — ERROR

**What it detects:** Two panels' bounding rectangles physically intersect. Overlapping
panels guarantee that sections, borders, and labels from one panel bleed into the other.
All pairs are checked.

**Geometry:** Panel A overlaps panel B when:
```
A.pos_x < B.pos_x + B.size_x  AND  A.pos_x + A.size_x > B.pos_x   (horizontal)
A.pos_y < B.pos_y + B.size_y  AND  A.pos_y + A.size_y > B.pos_y   (vertical)
```

**How to fix:**
- Adjust `pos` coordinates in `diagram.json` to give panels distinct, non-overlapping
  positions.
- Shrink a panel's `size` if it is accidentally oversized.

---

### `title-overlap` — WARN

**What it detects:** A panel's title text intrudes into the body of the panel directly
above it. Titles are rendered 20 px above the panel's top edge. Check.py uses a
clearance zone of **25 px** above each panel's `pos_y` to account for the title's cap
height plus a small margin. If another panel's bottom edge falls inside this zone and
the two panels share horizontal extent, the title is overlapping.

**Threshold:** `_TITLE_CLEARANCE_PX = 25 px`

**Trigger condition:** `(panel_above.pos_y + panel_above.size_y) > (panel_below.pos_y − 25)`

**How to fix:**
- Increase the vertical gap between panels to at least 25 px (ideally 50 px to also
  accommodate address label text near the panel bottom edge).
- In `diagram.json`, adjust `pos_y` of the lower panel downward, or reduce the `size_y`
  of the upper panel.

---

### `label-overlap` — WARN

**What it detects:** The estimated right extent of a panel's address labels overlaps the
left edge of the panel to its right, where the two panels share a vertical range.

Address labels are drawn starting at `panel_right_edge + 10 px` with `text-anchor: start`.
The width is estimated as:
```
label_width = 10 chars × font_size × 0.6  (Helvetica width ratio)
             = font_size × 6  px
```
At the default `font_size: 12`, this is **72 px**, so the full label extent is
`panel_right + 10 + 72 = panel_right + 82 px`.

**Threshold constants:**
```
_ADDR_LABEL_H_OFFSET = 10 px   (offset from panel right edge to label start)
_ADDR_LABEL_CHARS    = 10      (characters in "0x00000000")
_HELVETICA_W_RATIO   = 0.6     (character width / font-size)
```

**At default font_size 12:** minimum horizontal gap needed = 82 px. Recommended
gap is **≥ 150 px** (see `references/layout-guide.md`) to allow breathing room.

**How to fix:**
- Increase the horizontal gap between panels in `diagram.json`. Move the right panel's
  `pos_x` further right, or reduce the left panel's `size_x`.
- As a minimum, ensure `next_panel.pos_x ≥ prev_panel.pos_x + prev_panel.size_x + 150`.
- If font size is increased in `theme.json`, labels become wider — recheck spacing.

---

## Link Rules

### `band-too-wide` — WARN

**What it detects:** The horizontal span of a link band (from the source view's right
edge to the target detail panel's left edge) exceeds the readability guideline.

**Thresholds:**
- Span **> 200 px** for the nearest detail panel (first non-source view in `views[]`
  that covers the linked section): warns that the ideal is ≤ 200 px.
- Span **> 600 px** for any detail panel: warns that opacity should be reduced to
  0.3–0.4 to keep the long band from dominating the diagram.

**How to fix:**
- Move panels closer together horizontally in `diagram.json`.
- If a long band is intentional, set `"opacity": 0.3` (or lower) in the `links`
  section of `theme.json`.

---

### `unresolved-section` — ERROR

**What it detects:** A section ID listed in `links.sections` (or `links.sub_sections`)
does not appear in any view's filtered section set after all range, size, and flag
filters are applied. The renderer silently skips unresolved links, so this check catches
the resulting missing band before visual inspection.

**Common causes:**
- Typo in the section ID.
- The section exists in `sections[]` but is excluded by the view's `range` or
  `section_size` filter.
- The section has the `hidden` flag applied in all views that cover it.
- The section was deleted from `sections[]` but the link entry was not updated.

**How to fix:**
- Correct the section ID spelling in `links.sections`.
- Extend the relevant detail view's `range` so the section falls within it.
- Remove the hidden flag, or add a separate (non-hidden) copy of the section in a
  detail view that covers its address range.
- Remove the stale entry from `links.sections`.

---

## Geometry Constants Reference

| Constant | Value | Source |
|----------|-------|--------|
| `_TITLE_CLEARANCE_PX` | 25 px | `check.py` — title clearance zone above panel |
| `_ADDR_LABEL_H_OFFSET` | 10 px | `section.py` `label_offset` |
| `_ADDR_LABEL_CHARS` | 10 | length of `"0x00000000"` |
| `_HELVETICA_W_RATIO` | 0.6 | Helvetica character width / font-size |
| Title render offset | −20 px | `renderer.py` `_make_title` — y position relative to `pos_y` |
