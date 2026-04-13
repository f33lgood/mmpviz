# How to Create a Memory Map Diagram

This guide walks through authoring a `diagram.json` from scratch and generating an SVG.

---

## Step 1: List your memory regions

Identify every memory region you want to show. For each one, note:
- Its start address (hex preferred)
- Its size in bytes (hex preferred)
- Whether it needs its own view panel or is a sub-section shown inside one

**Example memory layout for an STM32:**
```
Flash:  0x08000000, 128KB total
  - Code:       0x08000000, 36KB
  - Constants:  0x08009000,  8KB

SRAM:   0x20000000, 20KB total
  - BSS:        0x20000000,  2KB
  - Stack:      0x20004000,  4KB (grows down)
```

---

## Step 2: Define views with their sections

Each entry in the `views` array is one panel in the diagram. Each view declares
its `sections` — the ordered list of memory regions to display. Sections are
defined inline directly inside the view. Every section requires `id`, `address`,
`size`, and `name`. Mark growth direction with `"flags": ["grows-up"]` or
`"flags": ["grows-down"]`.

```json
"views": [
  {
    "id": "flash-view",
    "title": "Flash Memory",
    "sections": [
      { "id": "code",   "address": "0x08000000", "size": "0x09000", "name": "Code",       "flags": ["grows-up"] },
      { "id": "consts", "address": "0x08009000", "size": "0x02000", "name": "Const Data"  }
    ]
  },
  {
    "id": "sram-view",
    "title": "SRAM",
    "sections": [
      { "id": "bss",   "address": "0x20000000", "size": "0x00800", "name": ".bss"                     },
      { "id": "stack", "address": "0x20004000", "size": "0x01000", "name": "Stack", "flags": ["grows-down"] }
    ]
  }
]
```

The SVG canvas and panel positions are computed automatically.

**When the same region appears in multiple views:** declare the section inline in
each view. Duplication is intentional and makes each view self-contained:

```json
"views": [
  { "id": "overview",   "sections": [{ "id": "flash", "address": "0x08000000", "size": "0x20000", "name": "Flash" }] },
  { "id": "flash-zoom", "sections": [{ "id": "flash", "address": "0x08000000", "size": "0x20000", "name": "Flash" }] }
]
```

---

## Step 3: Add optional features

### Break sections (compressed regions)

Mark a section as a break to compress a large empty or unimportant region:

```json
{ "id": "unused", "address": "0x0800B000", "size": "0x00005000", "name": "···", "flags": ["break"] }
```

If the gap-to-range ratio exceeds ~90%, breaks are essential — without them, functional sections compress to sub-pixel height and become invisible.

**Break vs. height clamping — when to use each:**

| Situation | Use |
|-----------|-----|
| Address hole with no hardware behind it | `"break"` flag — compresses the gap visually |
| All sections across all views are too small to read | `min_section_height` in `theme.json` — global height floor |
| All sections across all views are too large | `max_section_height` in `theme.json` — global height ceiling |
| One specific section is tiny relative to its neighbours | `"min_height"` on that section in `diagram.json` — per-section floor, takes precedence over the global minimum |
| One specific section dominates the view | `"max_height"` on that section in `diagram.json` — per-section ceiling, takes precedence over the global maximum |
| Name and size labels overlap inside a box | Nothing — the renderer inflates that section automatically |

**Gap continuity:** every section (including breaks) must be exactly contiguous with its neighbours. Even a 1-byte error leaves a blank stripe in the panel:

```
section[i].address + section[i].size == section[i+1].address
```

**Break section names:** address labels are auto-hidden at the default 20 px break height. Embed the address range in the `name` field so the break remains informative:

```json
{ "id": "gap0", "address": "0x10000000", "size": "0x0FF00000", "name": "··· (0x1000_0000, 256 MiB)", "flags": ["break"] }
```

### Labels

Annotate a specific address with a label line:

```json
"labels": [
  { "address": "0x08009000", "text": "End of code", "length": 80, "side": "right", "directions": ["in"] }
]
```

### Links

Connect regions across two views with a zoom band:

```json
"links": [
  { "from": { "view": "flash-view", "sections": ["code"] }, "to": { "view": "code-detail-view" } }
]
```

Each entry draws one band. `from.sections` specifies which sections define the vertical anchor on the source side; omit it to span the full source view. `to.sections` optionally pins the destination anchor to a different address range (useful for virtual→physical mappings).

---

## Step 4: Generate the SVG

```bash
python scripts/mmpviz.py -d diagram.json -o output.svg
```

With a theme:
```bash
python scripts/mmpviz.py -d diagram.json -t plantuml -o output.svg
```

Validate before rendering:
```bash
python scripts/mmpviz.py --validate diagram.json
```

---

## Step 5: Iterate

Auto-layout handles placement automatically. Typical iteration focuses on:

- **Section label overflow**: if a section is shorter than `font_size` px, its name
  label overflows the box. Increase `min_section_height` in `theme.json` (global) or
  set `"min_height"` on the section in `diagram.json` (per-section), or flag the
  section as `"break"` to compress it.
- **Dominant sections**: if one large section crowds out smaller neighbours, set
  `"max_height"` on that section in `diagram.json` to cap its pixel allocation.
- **Column arrangement**: the auto-layout derives columns from the `links[]` graph.
  If a view lands in the wrong column, check that its `links` entries correctly
  reference it.
- **Styling**: move colors, fonts, and link styles to `theme.json`.
  See `references/theme-schema.md` for all available style properties.

---

## Common Mistakes

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Panel looks blank or sections are invisible | No breaks; large address range compresses everything to sub-pixel | Add `"break"` sections for large gaps |
| Link band missing (warning in logs) | Section ID in `from.sections` not found in the source view | Check spelling; confirm the section is declared in that view's `sections[]` |
| Link band connects to wrong detail panel | Wrong `to.view` | Set `to.view` to the exact `id` of the intended target view |
| Link band origin at wrong vertical position | Source view has breaks; anchor is from compressed position — this is correct | No fix needed; renderer handles compressed coordinates automatically |
| Unexpected section overlapping others in a view | Parent and sub-sections both included in the same view | Remove the layer that should not be visible from that view's `sections[]` |
| Blank stripe inside a panel | Gap section starts at wrong address, leaving an unmapped range | Recompute: `gap.address = previous.address + previous.size` |
