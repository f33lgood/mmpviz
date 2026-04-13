# How to Create a Memory Map Diagram

This guide walks through authoring a `diagram.json` from scratch.

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
`size`, and `name`.

```json
"views": [
  {
    "id": "flash-view",
    "title": "Flash Memory",
    "sections": [
      { "id": "code",   "address": "0x08000000", "size": "0x09000", "name": "Code"       },
      { "id": "consts", "address": "0x08009000", "size": "0x02000", "name": "Const Data" }
    ]
  },
  {
    "id": "sram-view",
    "title": "SRAM",
    "sections": [
      { "id": "bss",   "address": "0x20000000", "size": "0x00800", "name": ".bss"   },
      { "id": "stack", "address": "0x20004000", "size": "0x01000", "name": "Stack"  }
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

### Links

When one view is a zoomed-in expansion of a section in another view, connect them
with a `links` entry. This draws a band between the two panels showing the
correspondence:

```json
"links": [
  { "from": { "view": "flash-view", "sections": ["code"] }, "to": { "view": "code-detail-view" } }
]
```

Each entry draws one band. `from.sections` specifies which sections define the
vertical anchor on the source side; omit it to span the full source view.
`to.sections` optionally pins the destination anchor to a different address range
(useful for virtual→physical mappings).

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
| One specific section is tiny relative to its neighbours | `"min_height"` on that section in `diagram.json` — per-section floor |
| One specific section dominates the view | `"max_height"` on that section in `diagram.json` — per-section ceiling |
| Name and size labels overlap inside a box | Nothing — the renderer inflates that section automatically |

**Gap continuity:** every section (including breaks) must be exactly contiguous with its neighbours. Even a 1-byte error leaves a blank stripe in the panel:

```
section[i].address + section[i].size == section[i+1].address
```

**Break section names:** address labels are auto-hidden at the default 20 px break height. Embed the address range in the `name` field so the break remains informative:

```json
{ "id": "gap0", "address": "0x10000000", "size": "0x0FF00000", "name": "··· (0x1000_0000, 256 MiB)", "flags": ["break"] }
```

### Growth-direction markers

For stack or heap sections whose address range grows toward a boundary, add a
`grows-up` or `grows-down` flag to render a directional arrow marker inside the
box. See `references/diagram-schema.md` for the full list of supported flags.

```json
{ "id": "stack", "address": "0x20004000", "size": "0x01000", "name": "Stack", "flags": ["grows-down"] }
```

### Labels

Annotate a specific address with a label line:

```json
"labels": [
  { "address": "0x08009000", "text": "End of code", "length": 80, "side": "right", "directions": ["in"] }
]
```

---

## Further Reference

| File | Contents |
|------|----------|
| `references/diagram-schema.md` | Complete field reference for `diagram.json` — all properties, types, defaults, and allowed values |
| `references/theme-schema.md` | Complete field reference for `theme.json` — all style properties, examples, and tips |
| `schemas/diagram.schema.json` | Machine-readable JSON Schema for `diagram.json` (used by the validator) |
| `schemas/theme.schema.json` | Machine-readable JSON Schema for `theme.json` (used by the validator) |

