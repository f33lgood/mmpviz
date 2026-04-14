# How to Create a Memory Map Diagram

This guide walks through authoring a `diagram.json` from scratch.

---

## Step 1: Collect memory region context

### Identify the initiator viewpoints

A system bus fabric can be observed from different initiators, each seeing a potentially different address map:

- **Primary viewpoint** — the main CPU that runs software. This is the primary bus initiator and the most important perspective. Always work out the full hierarchical memory map from this viewpoint first.
- **Secondary viewpoints** — other bus initiators such as a secondary CPU core, a DMA engine, or a debug/JTAG port. Each may see a remapped or restricted address space. Add secondary-viewpoint root views only after the primary map is complete.

The primary and secondary viewpoints each become a **root view** in the diagram.

### Build the hierarchy top-down

A system memory map is naturally a tree. Work from the top level down — do not start at the register level and try to aggregate upward.

| Scope | Hierarchy level | Typical drill-down depth |
|-------|----------------|--------------------------|
| Full chip / SoC | system → subsystem → device | 3 levels |
| One subsystem | subsystem → device → device page | 3 levels |
| One peripheral | device → device page → registers | 3 levels |

The deepest hierarchy supported is: **system → subsystem → device → device page → registers** (5 levels, 4 links). In practice, most diagrams use 2–3 levels.

### Gather region data from sources

Different source types expose this information differently:

| Source | What to extract |
|--------|----------------|
| **Datasheet / memory map table** | Region name, base address, size (or end address), access type (R/W/RO), sub-region breakdowns, bus aperture assignments |
| **Linker script (`.ld` / `.icf`)** | `MEMORY` block entries (origin + length), `SECTIONS` assignments splitting a region into sub-sections (`.text`, `.data`, `.bss`, stack, heap) |
| **RTL / hardware description** | Address decoder ranges, bus fabric apertures, peripheral base addresses and their sizes, per-initiator address remappings |
| **C/C++ header (`#define`)** | `BASE_ADDR` + `SIZE` macros; peripheral register block sizes; guard-page or reserved-range constants |

For each region record:
- **Start address** (hex preferred, e.g. `0x08000000`)
- **Size** (hex preferred, e.g. `0x20000`); compute from end address if needed: `size = end − base`
- **Name** — keep to ≤19 characters; omit size annotations (the tool renders them automatically)
- **Level in the hierarchy** — system, subsystem, device, device page, or register

---

## Step 2: Design the view structure

Sketch the panel layout before writing any JSON. Getting the structure right prevents rework later.

### Map hierarchy levels to views

Each diagram covers one scope. Choose the scope first, then select which hierarchy levels become views:

| Diagram scope | Root view | Drill-down views |
|--------------|-----------|-----------------|
| System map | Primary CPU address space | Subsystem → device (one column per level) |
| Subsystem map | Subsystem address space | Device → device page |
| Device map | Device address space | Device page → registers |

For a system-level diagram, start with the primary CPU root view. Add a secondary CPU or debug-port root view as a separate root view alongside it when their address maps differ.

### Layout rules

- **One view per distinct address space.** A contiguous address space belongs in a single view. Do **not** split one address space across multiple root views.
- **Use break sections for large gaps.** When the gap-to-range ratio exceeds ~90%, compress the gap with a `break`-flagged section; without it, the surrounding sections collapse to sub-pixel height.
- **Drill-down only, never sideways.** An overview links to a zoom-in, which may link to a sub-detail — each link adds exactly one column. Do not create more levels than the chosen scope requires.
- **Cross-address-space links require `to.sections`.** When source and destination views use different address spaces (e.g. a 64-bit global map linking into a 24-bit peripheral space), always specify `to.sections` so the destination anchor is expressed in the destination view's own address range.

### Checklist before writing JSON

- [ ] Primary CPU viewpoint is the first root view
- [ ] Secondary viewpoints (if any) are separate root views
- [ ] Hierarchy levels are chosen to match the diagram scope
- [ ] Every contiguous address space maps to exactly one view
- [ ] Every large address gap has a break section planned
- [ ] Drill-down relationships are expressed as links, not extra root views
- [ ] Cross-address-space links have `to.sections` planned
- [ ] Section names are ≤19 characters

---

## Step 3: Define views with their sections

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
  { "id": "code-link", "from": { "view": "flash-view", "sections": ["code"] }, "to": { "view": "code-detail-view" } }
]
```

The `id` field is required and must be unique across all links. It is used as a key in `theme.json` under `links.overrides[link_id]` for per-link style overrides.

Each entry draws one band. `from.sections` specifies which sections define the
vertical anchor on the source side; omit it to span the full source view.
`to.sections` optionally pins the destination anchor to a different address range
(useful for virtual→physical mappings).

**Cross-address-space links.** When the source and destination views use different
address spaces (e.g. a 64-bit global address map linking into a 32-bit peripheral
address space), always specify `to.sections` using section IDs from the destination
view. Without `to.sections`, the tool attempts to use the source address as a
y-anchor on the destination side — which is outside the destination view's address
range and produces a `link-anchor-out-of-bounds` error.

---

## Step 4: Add optional features

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
| Name and size labels overlap inside a box | Keep the name short (see note below) |

**Section name length.** Keep names to ~19 characters or fewer. Do **not** embed size annotations (e.g. `4 KB`, `1036 KB`) in the `name` field — the tool renders size and address labels automatically. Names longer than ~20 characters can inflate the effective height floor to 43 px (the label-conflict floor formula: `label_min_h = 30 + font_size`) and trigger proportional fallback across the entire view, causing small sections to render at near-zero height.

Self-check: `len(name) × 3.9 < 113 − len(size_str) × 7.2` (where `size_str` is the auto-generated size label, e.g. `"512 KB"`). If this inequality fails, shorten the name.

**Gap continuity:** every section (including breaks) must be exactly contiguous with its neighbours. Even a 1-byte error leaves a blank stripe in the panel:

```
section[i].address + section[i].size == section[i+1].address
```

**Break section names:** address labels are auto-hidden at the default 20 px break height. Embed the address range in the `name` field so the break remains informative:

```json
{ "id": "gap0", "address": "0x10000000", "size": "0x0FF00000", "name": "··· (0x1000_0000, 256 MiB)", "flags": ["break"] }
```

**Gap size computation.** For large address gaps (especially in 64-bit spaces), compute the break size programmatically rather than by hand — a single-nibble error in a 16-digit hex number is invisible visually but produces an `uncovered-gap` warning with the break falling short of the next section:

```
gap_size = next_section_address − current_section_end
```

Verify with: `hex(int(gap_address, 16) + int(gap_size, 16)) == next_address`

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
  { "id": "end-of-code", "address": "0x08009000", "text": "End of code", "length": 80, "side": "right", "directions": ["in"] }
]
```

The `id` field is required and must be unique within its view. It is used as a key in `theme.json` under `views[view_id].labels[label_id]` for per-label style overrides.

---

## Further Reference

| File | Contents |
|------|----------|
| `references/diagram-schema.md` | Complete field reference for `diagram.json` — all properties, types, defaults, and allowed values |
| `references/theme-schema.md` | Complete field reference for `theme.json` — all style properties, examples, and tips |
| `schemas/diagram.schema.json` | Machine-readable JSON Schema for `diagram.json` (used by the validator) |
| `schemas/theme.schema.json` | Machine-readable JSON Schema for `theme.json` (used by the validator) |

