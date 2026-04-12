# mmpviz — Guide for AI/LLM Diagram Generation

This guide provides rules of thumb, worked patterns, and an inspection workflow for
AI/LLM agents generating `diagram.json` + `theme.json` pairs for mmpviz.

---

## 1. Understand the Two-File Model

| File | Purpose |
|------|---------|
| `diagram.json` | **Addresses and layout** — sections (memory regions), views (display panels), links (connections) |
| `theme.json` | **Visual style** — colors, fonts, link style, visibility flags |

Keep them separate. `diagram.json` is machine-accurate (from datasheets/RTL); `theme.json` is human-readable styling.

---

## 2. Section Height — The 20 px Rule

**The most common failure mode is sections that are too small to display text.**

mmpviz renders each section with height proportional to its byte range within the
display panel. All labels (name, address, size) are always rendered.

### Calculate section height before writing the diagram

For a panel of height `H` px displaying address range `R` bytes:

```
section_height_px = H × section_bytes / R
```

**If any important section falls below 20 px, you must use breaks or resize the panel.**

### Example

APB view: `size: [200, 880]`, range `0x1A100000–0x1A122000` = 139264 bytes

FLL (4 KiB = 4096 bytes):
```
4096 / 139264 × 880 = 25.9 px  ✓  (name + address visible)
```

If the range were the full SoC (`0x10000000–0x1C100000` ≈ 200 MB) without breaks:
```
4096 / 200_000_000 × 880 ≈ 0.02 px  ✗  (invisible)
```

---

## 3. Break Compression for Large Address Gaps

When a memory map has large gaps between interesting regions (typical of SoC address
maps), use **break sections** to compress the empty space.

### Pattern

1. Create a gap section spanning the empty range with a filler name (e.g. `"···"`).
2. In the view's `sections` list, apply `"flags": ["break"]` to that section.
3. The break renders as a fixed-height zigzag symbol (`break_height` px, default 20).
4. All non-break sections are redistributed to fill the remaining panel height.

```json
"views": [
  {
    "sections": [
      { "id": "gap0", "address": "0x00100000", "size": "0x0FF00000", "name": "···", "flags": ["break"] }
    ]
  }
]
```

### How many breaks are needed?

Compute the **compression ratio**: `total_gap_bytes / total_range_bytes`. If this
exceeds ~90%, you almost certainly need breaks or the interesting sections will be
sub-pixel.

### Break vs. height clamping — when to use each

| Situation | Use |
|-----------|-----|
| Address hole / reserved range with no hardware behind it | **Break** — it is a genuine gap in the address space |
| Functional section that is tiny relative to its neighbours (e.g., 4 KiB peripheral in a 256 KiB panel) | **`min_section_height`** in `theme.json` defaults — guarantees every visible section is at least N px tall |
| One very large subarea is squeezing small neighbours | **`max_section_height`** in `theme.json` defaults — caps overly dominant subareas |
| Section name and size label overlap in the rendered box | Nothing — the renderer detects x-axis label conflict automatically and inflates only that section's height |

Using breaks on functional sections hides them visually; use height clamping instead so they remain readable.

**`themes/plantuml.json` already sets** `"min_section_height": 20, "max_section_height": 300`. If you use the default theme (no `-t` flag), these are active without any additional configuration.

---

## 4. Link Bands — How Section Links Work

`links` is an array of entry objects.  Each entry draws a trapezoid (or curve) band
from a source view to an explicit destination view.

```json
"links": [
  {"from": {"view": "overview",  "sections": ["Flash"]},       "to": {"view": "flash-view"}},
  {"from": {"view": "overview",  "sections": ["Peripherals"]}, "to": {"view": "apb-view"}},
  {"from": {"view": "apb-view",  "sections": ["DMA"]},         "to": {"view": "dma-view"}}
]
```

### Rules

- **`from.view` and `to.view` are always required.** There are no implicit defaults.
- **`from.sections` is optional.** Omit it to span the source view's full address range.
- **`to.sections` is optional.** When specified, the destination anchor is pinned to that address range independently of the source — useful for cross-address mappings (virtual→physical, DMA aliases).
- **Section IDs must exist in the specified view's `sections[]` list.** Links resolve section addresses from the view they reference.
- **Multiple entries → same destination.** To fan-in from two source views to the same
  detail panel, add two entries with the same `to.view`.

### Multi-section span

To draw a single band spanning several non-contiguous sections, list all their IDs in
`from.sections`:

```json
{"from": {"view": "full-view", "sections": ["Bit band region", "Bit band alias"]}, "to": {"view": "bit-view"}}
```

The band spans from the lowest start address to the highest end address across all
named sections.

### Address-range form

Use hex strings when you want to anchor the band to a raw address range that may not
have a named section:

```json
{"from": {"view": "overview", "sections": ["0x40000000", "0x40010000"]}, "to": {"view": "detail"}}
```

Detection rule: if the first element of `sections` matches `/^0x[0-9a-fA-F]+$/` exactly,
the pair is treated as an address range — not section IDs.

---

## 5. Source-View Link Alignment With Breaks

When the source view (overview) uses break compression, the link band's anchor point
on the source side is computed from the **compressed** subarea position, not a naive
proportional scaling. This means link bands visually align with the colored section
boxes in the overview even when large gaps are compressed.

**Do not expect the source-side band to align proportionally** if the overview has
breaks. The renderer handles the coordinate mapping automatically.

---

## 6. Title Sizing and Panel Positioning

The panel title is always rendered at font size 24 px, horizontally centered over the
panel. Auto-layout reserves adequate top padding automatically. The pitfalls below
apply only when using **manual `pos`/`size`**:

1. **Title clipped on the left.** A long title on a narrow panel will extend outside
   the SVG canvas. Keep titles short (10–15 characters) or use a wider panel.

2. **Title above the SVG top.** Titles render at `panel_pos_y − 20`. If `panel_pos_y`
   is 0, the title is invisible. Reserve at least 50–70 px at the top of the canvas.

### Formula

For a title of `N` characters at 24 px Helvetica, the approximate rendered width is:
```
title_px ≈ N × 13   (rough rule of thumb for Helvetica)
```
The title must fit within `panel_width` (ideally with ≥ 20 px margin on each side).

**Safe title length:** `floor((panel_width − 40) / 13)` characters.

---

## 7. Color Strategy (No Auto-Palette Yet)

mmpviz supports a `palette` array in `theme.json`. Each non-break section in a view
is assigned the next palette color cyclically, based on address order. Sections with
explicit per-section color overrides in `theme.views.<view-id>.sections.<section-id>`
skip this.

### Tips for multi-view diagrams

- Group **functionally related** regions with the same color family.
- Use muted / desaturated colors; bright colors make text hard to read.
- Reserved / gap sections: use a light gray (`#eeeeee`, `#f0f0f0`) with a dimmed text color.
- Reserved sections that use the `break` flag inherit the style of their section slot.

### Recommended palette (light theme)

```json
"palette": [
  "#b8d4e8",  // soft blue
  "#a8d5ba",  // soft green
  "#c9b8d4",  // soft purple
  "#d4c4a8",  // soft amber
  "#a8c4d4",  // slate blue
  "#d4a8b8",  // soft rose
  "#c4d4a8"   // soft olive
]
```

---

## 8. SVG Inspection Workflow

After generating an SVG, run these checks to catch visual problems before committing.

### Step 1 — Run check.py

`scripts/check.py` validates the diagram against nine layout and display rules without
generating SVG output.  It is the primary automated check — run it first.

```
python3 scripts/check.py -d diagram.json -t theme.json
```

Exit codes: **0** = OK, **1** = ERRORs (broken diagram), **2** = warnings only.

Run a subset of rules with `--rules`:

```
python3 scripts/check.py -d diagram.json -t theme.json --rules panel-overlap,label-overlap
```

See `references/check-rules.md` for the full rule list, thresholds, and remediation
guidance for each rule.

### Step 2 — Check for renderer warnings

Run the renderer and scan for `WARNING` lines:

```
python scripts/mmpviz.py -d diagram.json -t theme.json -o map.svg
```

Common warnings and their causes:

| Warning | Root cause |
|---------|-----------|
| `Link: section '...' not found in view '...'` | Section ID in `from.sections` does not exist in the specified view's `sections[]`. Check spelling and confirm the section is declared in that view. |
| `could not resolve source range, skipping` | The link's source anchor could not be determined (section missing or view has no sections). Fix the section reference or add the section to the source view. |

### Step 3 — Visual spot-check (human)

Open the SVG in a browser and verify:

- [ ] Panel titles are fully visible and not clipped
- [ ] All major sections show their name and start address
- [ ] Link bands connect the overview to the correct detail panels
- [ ] Link bands visually originate from the correct section in the overview
- [ ] No large blank regions (usually means a break is needed)
- [ ] Colors are distinguishable; reserved/gap sections are clearly dimmed

---

## 9. Multi-Level Zoom

Because every link entry specifies both `from.view` and `to.view` explicitly, multi-level
zoom is just a natural extension of the flat link array — no special field needed.

```json
"links": [
  {"from": {"view": "overview",  "sections": ["APB Bus"]},   "to": {"view": "apb-view"}},
  {"from": {"view": "apb-view",  "sections": ["uDMA"]},      "to": {"view": "udma-view"}},
  {"from": {"view": "apb-view",  "sections": ["Chip Ctrl"]}, "to": {"view": "chip-ctrl-view"}}
]
```

The renderer processes every entry independently; the source and destination can be any
two views in the diagram, at any depth of zoom.

**Fan-in** (two source views → same detail panel):

```json
"links": [
  {"from": {"view": "cpu-view",      "sections": ["SysPeriph"]}, "to": {"view": "periph-detail"}},
  {"from": {"view": "debugger-view", "sections": ["SysPeriph"]}, "to": {"view": "periph-detail"}}
]
```

Two separate bands are drawn, one per entry.

---

## 10. Gap Continuity Rule

Every gap section must be **exactly contiguous** with its neighbours — no holes, no
overlaps. A gap that starts at the wrong address leaves an unmapped blank stripe in
the panel.

### Check

For each consecutive pair of sections displayed in a view (in address order):
```
section[i].address + section[i].size == section[i+1].address
```

**Common failure:** You copy a gap address from a rough estimate instead of computing
`previous_section.address + previous_section.size`. Even a 1-byte error creates a
visible blank band.

---

## 11. Section Exclusivity Per View

When a section is **expanded** in a detail view (i.e., the detail view shows its
sub-sections), the parent section should not also appear in the same view. Each
view declares only what it wants to display.

### Rule

For each view at a higher zoom level (overview, intermediate view):
1. Include the parent section (e.g., `"udma"`) but not its sub-sections.
2. In the detail view, include the sub-sections but not the parent.
3. Since each view has its own `sections[]` list, simply omit whichever layer
   should not be visible — no flags required.

**Symptom when violated:** An unexpected colored section appears in the overview
or intermediate panel, usually covering the area of the expanded region.

---

## 12. Horizontal Spacing Between Panels

Address labels for a panel are rendered to the **right** of the panel's right edge.
If the next panel starts too close, these labels appear to belong to the wrong panel.
Auto-layout reserves a 110 px right-pad when computing the canvas, so this is only
a concern when placing panels manually.

### Minimum gap (manual layout)

Leave at least **150 px** between any panel's right edge and the next panel's left
edge. For panels that display many narrow sections with long hex addresses, increase
this to 200 px.

```
panel[i].pos_x + panel[i].size_x + 150 ≤ panel[i+1].pos_x
```

---

## 13. Break Sections Show Names

Break sections render their name label. Since break sections are only `break_height` px
tall (default 20 px) and all labels are always rendered, the name will overlap the box
unless `break_height` is increased to at least `font_size` px.

**Best practice for large break regions:** Embed the address range and size in the
`name` field, because the address label itself is auto-hidden at 20 px:

```json
{ "id": "AXI Plug", "address": "0x10000000", "size": "0x400000",
  "name": "AXI Plug / Cluster (0x1000_0000, 4 MiB)" }
```

This ensures the break section is still informative in tools that render the name
even at small heights (e.g., tooltips, exported metadata).

---

## 14. Common Mistakes and Fixes

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Overview panel looks blank or all sections are invisible | No breaks; huge address range compresses everything to sub-pixel | Add break sections for large gaps |
| Title first character clipped | Title too long for panel width | Shorten title or widen panel |
| Title not visible at all | `panel_pos_y` = 0 in manual layout | Set `panel_pos_y` ≥ 50, or switch to auto-layout |
| Link band missing (warning in logs) | Section ID not found in the source view | Check spelling; confirm the section is declared in that view's `sections[]` |
| Link band connects to the wrong detail panel | Wrong `to.view` specified | Set `to.view` to the exact `id` of the intended target view |
| Link band visible but band origin is at wrong vertical position | Source view has breaks; anchor is computed from compressed subarea — this is correct behaviour | No fix needed; the renderer handles compressed coordinates automatically |
| Unexpected colored section overlapping others in a view | Parent and sub-sections both included in the same view | Remove the layer that should not be visible from the view's `sections[]` |
| Blank/empty stripe inside a panel | Gap section starts at wrong address, leaving an unmapped range | Recompute gap address as `previous.address + previous.size` |
| Address labels appear to belong to wrong panel | Panels too close horizontally | Increase horizontal gap to ≥ 150 px between right edge of one panel and left edge of next |

---

## 15. Checklist for New Diagrams

Before submitting a new example:

- [ ] Every section has `id`, `address`, `size`, and `name` (use `""` to suppress label)
- [ ] Section IDs are unique within each view; they use only `[a-z0-9_-]` characters
- [ ] Every view's `pos` + `size` fits within the diagram `size` canvas (if `size` is set)
- [ ] Panel titles are ≤ `floor((panel_width − 40) / 13)` characters
- [ ] All important sections are ≥ 20 px tall in their display panel (use breaks if not)
- [ ] Each `links` entry has both `from.view` and `to.view` referencing valid view IDs
- [ ] Section IDs in `from.sections` exist in the referenced view's `sections[]` list
- [ ] Gap sections are contiguous: `gap.address == previous.address + previous.size`
- [ ] Horizontal gap between panels ≥ 150 px
- [ ] Break section names include address/size info (since address labels hide at 20 px)
- [ ] Running `check.py` produces no ERRORs (exit 0 or 2)
- [ ] Running `mmpviz.py` produces no `WARNING` output
