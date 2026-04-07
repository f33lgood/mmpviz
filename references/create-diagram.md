# How to Create a Memory Map Diagram

This guide walks through authoring a `diagram.json` from scratch and generating an SVG.

---

## Step 1: List your memory regions

Identify every memory region you want to show. For each one, note:
- Its start address (hex preferred)
- Its size in bytes (hex preferred)
- Whether it's a top-level region ("area") or a sub-section

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

## Step 2: Write the `sections` array

Each memory region becomes one entry. Use `"type": "area"` for top-level containers.
Mark growth direction with `"flags": ["grows-up"]` or `"flags": ["grows-down"]`.

```json
"sections": [
  { "id": "Flash",  "address": "0x08000000", "size": "0x20000", "type": "area" },
  { "id": "code",   "address": "0x08000000", "size": "0x09000", "name": "Code",       "flags": ["grows-up"] },
  { "id": "consts", "address": "0x08009000", "size": "0x02000", "name": "Const Data" },

  { "id": "SRAM",  "address": "0x20000000", "size": "0x05000", "type": "area" },
  { "id": "bss",   "address": "0x20000000", "size": "0x00800", "name": ".bss" },
  { "id": "stack", "address": "0x20004000", "size": "0x01000", "name": "Stack",  "flags": ["grows-down"] }
]
```

---

## Step 3: Define the display areas

Each `area` in the `areas` array is one panel in the diagram. The only required
field is `id`. Everything else is optional — `pos` and `size` are auto-computed
when absent.

**Auto-layout (recommended):** omit `pos` and `size` and the tool distributes
areas evenly left-to-right on the canvas:

```json
"areas": [
  { "id": "flash-view", "title": "Flash Memory", "range": ["0x08000000", "0x08020000"] },
  { "id": "sram-view",  "title": "SRAM",         "range": ["0x20000000", "0x20005000"] }
]
```

**Manual layout:** supply `pos` and `size` when you need precise control:

```json
"areas": [
  {
    "id": "flash-view",
    "title": "Flash Memory",
    "range": ["0x08000000", "0x08020000"],
    "pos": [50, 80],
    "size": [180, 700]
  },
  {
    "id": "sram-view",
    "title": "SRAM",
    "range": ["0x20000000", "0x20005000"],
    "pos": [270, 80],
    "size": [180, 700]
  }
]
```

You can mix: supply `pos`/`size` on some areas and omit them on others.

---

## Step 4: Add optional features

### Break sections (compressed regions)

Mark a section as a break to compress a large empty or unimportant region:

```json
{ "id": "unused", "address": "0x0800B000", "size": "0x00005000", "flags": ["break"] }
```

Or add the break flag only for a specific area (without changing the section globally):

```json
"sections": [{ "names": ["unused"], "flags": ["break"] }]
```

### Labels

Annotate a specific address with a label line:

```json
"labels": [
  { "address": "0x08009000", "text": "End of code", "length": 80, "side": "right", "directions": ["in"] }
]
```

### Links

Connect matching regions across two areas:

```json
"links": {
  "sections": [["Flash", "SRAM"]]
}
```

---

## Step 5: Generate the SVG

```bash
python scripts/mmpviz.py -d diagram.json -o output.svg
```

With a theme:
```bash
python scripts/mmpviz.py -d diagram.json -t examples/dark_theme.json -o output.svg
```

Validate before rendering:
```bash
python scripts/mmpviz.py --validate diagram.json
```

---

## Step 6: Iterate

Adjust `pos` and `size` in your `areas` to control layout.
Move styling (colors, fonts) to a `theme.json` file so the diagram stays clean.
See `references/theme-schema.md` for all available style properties.
