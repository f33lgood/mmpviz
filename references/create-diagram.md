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

The SVG canvas and panel positions are computed automatically — `pos` and `size`
are optional and rarely needed.

**When the same region appears in multiple views:** declare the section inline in
each view. Duplication is intentional and makes each view self-contained:

```json
"views": [
  { "id": "overview",   "sections": [{ "id": "flash", "address": "0x08000000", "size": "0x20000", "name": "Flash" }] },
  { "id": "flash-zoom", "sections": [{ "id": "flash", "address": "0x08000000", "size": "0x20000", "name": "Flash" }] }
]
```

**Manual placement:** supply `pos` and `size` on any view where you need precise
control (auto-layout is used for views without them):

```json
{
  "id": "flash-view",
  "title": "Flash Memory",
  "pos": [50, 80],
  "size": [180, 700],
  "sections": [...]
}
```

---

## Step 3: Add optional features

### Break sections (compressed regions)

Mark a section as a break to compress a large empty or unimportant region:

```json
{ "id": "unused", "address": "0x0800B000", "size": "0x00005000", "name": "···", "flags": ["break"] }
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
python scripts/mmpviz.py -d diagram.json -t themes/light.json -o output.svg
```

Validate before rendering:
```bash
python scripts/mmpviz.py --validate diagram.json
```

---

## Step 5: Iterate

Auto-layout handles placement by default — you rarely need to touch `pos` or
`size`. Typical iteration focuses on:

- **Section label overflow**: if a section is shorter than `font_size` px, its name
  label overflows the box. Increase `min_section_height` in `theme.json`, or flag the
  section as `"break"` to compress it.
- **Column arrangement**: the auto-layout derives columns from the `links[]` graph.
  If a view lands in the wrong column, check that its `links` entries correctly
  reference it, or use `pos`/`size` to override placement.
- **Styling**: move colors, fonts, and link styles to `theme.json`.
  See `references/theme-schema.md` for all available style properties.
