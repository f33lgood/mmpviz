# Layout Guide — Sizing Diagrams for Different Output Targets

mmpviz produces SVG, which is a **vector format**: the numbers in `diagram.json`
define a coordinate space and aspect ratio, not a fixed physical size. The rendered
SVG scales to any display or print size without quality loss.

**Auto-layout is the default.** When areas omit `pos` and `size`, the tool
builds a column layout from the address-containment link graph, sizes each area
so all sections reach `min_section_height`, and expands the canvas to fit.  You
only need to set `size` (canvas) and supply `pos`/`size` (area) manually when
you want to override the auto-layout for a specific output target.

When setting a manual canvas size:
- Exact pixel values do not need to match a screen resolution.
- What matters is **aspect ratio** (portrait page, landscape, or slide) and
  **coordinate scale** (room for text and boxes).
- Area `pos` and `size` values must be chosen **relative to the canvas `size`** —
  they live in the same coordinate space.

---

## Output Format Reference

| Target | Aspect ratio | Recommended canvas `size` | Notes |
|--------|-------------|--------------------------|-------|
| A4 portrait (paper) | 1 : 1.414 | `[600, 849]` | Tall and narrow; suits single or two-area maps |
| A4 landscape (paper) | 1.414 : 1 | `[849, 600]` | Wide; suits 2–4 area maps with links |
| 16:9 slide | 1.778 : 1 | `[960, 540]` | Wide; suits 2–3 area overview diagrams |
| 4:3 slide | 1.333 : 1 | `[800, 600]` | Moderate width; suits 2-area maps |

These canvas values are starting points. Scale them up (e.g. double to `[1200, 1698]`
for A4) if you need more room for many sections or longer labels. The numbers only
matter relative to each other.

---

## Layout Constants

When placing areas explicitly, reserve space for:

| Element | Typical reservation |
|---------|---------------------|
| Outer padding (left/right/bottom) | 40–60 px |
| Title row above areas | 50–70 px |
| Gap between areas | 30–50 px |

---

## Area Layout Templates (Manual Override)

These templates are for situations where you want to fix the canvas size and
area positions for a specific output target rather than relying on auto-layout.
Adjust font sizes in `theme.json` to match (see the note at the end).

### A4 Portrait — 1 area

```json
"size": [600, 849],
"views": [
  {
    "id": "main-view",
    "title": "Memory Map",
    "pos": [50, 70],
    "size": [500, 730]
  }
]
```

### A4 Portrait — 2 areas with link

```json
"size": [600, 849],
"views": [
  {
    "id": "overview",
    "title": "Overview",
    "pos": [40, 70],
    "size": [200, 730]
  },
  {
    "id": "detail",
    "title": "Detail",
    "pos": [290, 70],
    "size": [270, 730]
  }
]
```

### A4 Landscape — 3 areas with links

```json
"size": [849, 600],
"views": [
  {
    "id": "source",
    "title": "Overview",
    "pos": [40, 70],
    "size": [200, 490]
  },
  {
    "id": "detail-a",
    "title": "Flash Detail",
    "pos": [290, 70],
    "size": [230, 490]
  },
  {
    "id": "detail-b",
    "title": "SRAM Detail",
    "pos": [570, 70],
    "size": [239, 490]
  }
]
```

### 16:9 Slide — 2 areas with link

```json
"size": [960, 540],
"views": [
  {
    "id": "source",
    "title": "Memory Map",
    "pos": [50, 70],
    "size": [280, 430]
  },
  {
    "id": "detail",
    "title": "Flash Detail",
    "pos": [390, 70],
    "size": [520, 430]
  }
]
```

### 16:9 Slide — 3 areas with links

```json
"size": [960, 540],
"views": [
  {
    "id": "source",
    "title": "Overview",
    "pos": [40, 70],
    "size": [200, 430]
  },
  {
    "id": "detail-a",
    "title": "Flash",
    "pos": [290, 70],
    "size": [290, 430]
  },
  {
    "id": "detail-b",
    "title": "SRAM",
    "pos": [630, 70],
    "size": [290, 430]
  }
]
```

### 4:3 Slide — 2 areas with link

```json
"size": [800, 600],
"views": [
  {
    "id": "source",
    "title": "Memory Map",
    "pos": [40, 70],
    "size": [250, 490]
  },
  {
    "id": "detail",
    "title": "Detail",
    "pos": [340, 70],
    "size": [420, 490]
  }
]
```

---

## Font Size Guidance

Font size in `theme.json` controls label readability. Scale it relative to your
canvas height so text is neither too small nor too large.

| Output target | Recommended `font_size` |
|---------------|------------------------|
| Paper (A4 portrait, canvas height ~850) | 12–14 |
| Slides (canvas height ~540–600) | 15–18 |

Slides need larger text because they are read from a distance. Paper diagrams can
use smaller text because the reader holds the page.

For address labels, set `font_size` in the `labels` block of `theme.json`
independently of section text if you want finer control.

---

## Multi-Panel Placement Rationale (manual layout only)

> **Auto-layout handles this automatically.** The notes below only apply when you
> override placement with explicit `pos`/`size` on areas.

When a diagram has more than two panels (overview + multiple zoom panels), placement
decisions affect both readability and the visual quality of link bands.

### Column ordering

Place zoom panels in columns ordered by their relationship to the overview:

- **Column immediately right of the overview**: the zoom panel with the most prominent
  or largest link band, or the one whose address range sits near the visual centre
  of the overview. This keeps the most important connection short and direct.
- **Farther columns**: less prominent panels, or panels that benefit from extra
  horizontal distance to allow a taller vertical extent.

### Vertical stacking within a column

When two zoom panels share a column, stack them to match the memory-map convention:

- **Higher-address panel on top** (lower SVG `pos[1]`), **lower-address panel on
  bottom** (higher `pos[1]`). This is consistent with the overview, where higher
  addresses are at the top. It prevents link bands from crossing.

Assign heights proportional to content complexity:

- A panel with few sections (≤ 3) needs only 150–250 px. Anything taller wastes
  whitespace.
- A panel with sections of highly unequal sizes needs extra height. The renderer
  compresses small sections to a minimum of `min_section_height` px (default 15).
  Rule of thumb: if the smallest section is `s_min` bytes and the panel address range
  is `R` bytes, the panel needs at least `font_size × R / s_min` px for name labels
  to fit without overflowing. Cap this against
  `max_section_height` (default 300) and the canvas height.

### Link band width

A link band spans from the right edge of the overview to the left edge of the target
panel. Prefer:

- **≤ 200 px horizontal span** for the most visually important bands (they stay clean
  and easy to trace).
- **≤ 600 px** for secondary bands. Beyond 600 px the bands look thin and arrow-like
  rather than connective.

When all zoom panels must be in distant columns, use `opacity: 0.3–0.4` in the
`links` theme block so overlapping bands remain legible.

### Non-crossing bands

Two bands from the same overview side do not cross if: the panel whose overview
section is higher (smaller SVG `y`) connects to the panel that is higher in the
target column (smaller `pos[1]`). Verify this invariant whenever panels are
repositioned.

### Per-chip layout notes

Each chip example directory contains a `notes.md` that documents the chip's
memory map structure.  With auto-layout active (no `pos`/`size` in the chip's
`diagram.json`), the placement is entirely derived from address ranges and the
link graph.

---

## Recommended Themes by Target

| Target | Suggested theme |
|--------|----------------|
| Printed paper | `themes/light.json` |
| Slides (light background) | `themes/light.json` — increase `font_size` to 16–18 |
| Slides (color) | `themes/plantuml.json` — increase `font_size` to 16–18 |
| Grayscale / print-friendly | `themes/monochrome.json` |
