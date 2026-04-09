# diagram.json — Schema Reference

A `diagram.json` file is the single semantic description of a memory map diagram.
It contains the raw memory data (`sections`) and the display layout (`areas`, `links`).
**No visual styling belongs here** — put colors, fonts, and sizes in `theme.json`.

---

## Top-Level Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `title` | string | No | `""` | Document title (informational only) |
| `size` | `[width, height]` | No | `[400, 700]` | SVG canvas dimensions in pixels. Since the output is SVG (vector), the exact values set the aspect ratio and internal coordinate space — the file scales without quality loss to any display size. |
| `sections` | array | Yes | — | Memory section definitions |
| `areas` | array | No | Auto | Display viewport definitions |
| `links` | object | No | — | Cross-area connections |

### Choosing a Canvas Size

Because the output is SVG, the numbers in `size` define the **coordinate space and aspect ratio**, not a fixed pixel size. The diagram scales to any physical size without loss.

Choose values that match your intended output format's aspect ratio and give comfortable spacing for the number of areas you have. See `references/layout-guide.md` for recommended `size`, `pos`, and `size` values for common targets (A4 paper, 16:9 slides, etc.).

---

## `sections[]` — Memory Section Fields

Each entry in `sections` describes one contiguous memory region.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | Yes | — | Unique identifier. Used in `area.sections[].names` references and as theme key. |
| `address` | hex string or int | Yes | — | Start address. Hex strings (`"0x08000000"`) and integers both accepted. |
| `size` | hex string or int | Yes | — | Size in bytes. Hex strings and integers both accepted. |
| `type` | string | No | `"section"` | `"area"` marks a memory region container; `"section"` marks a leaf segment. |
| `flags` | array of strings | No | `[]` | Visual behavior flags (see below). |
| `name` | string | No | `null` | Friendly display name shown in the diagram. Falls back to `id` if absent. |
| `parent` | string | No | `"none"` | Parent section id (informational). |

### `flags` allowed values

| Flag | Effect |
|------|--------|
| `"grows-up"` | Draws an upward growth arrow on this section |
| `"grows-down"` | Draws a downward growth arrow on this section |
| `"break"` | Renders as a height-compressed plain box using `break_fill` as background (falls back to `fill`). Break sections are always exactly `break_size` pixels tall regardless of their byte range — the remaining panel height is redistributed among non-break sections. Use a distinct `break_fill` color and a short label such as `"···"` to signal that the address range is compressed. |
| `"hidden"` | Section is loaded but not rendered |

---

## `areas[]` — Display Viewport Fields

Each entry in `areas` defines one memory view panel in the SVG diagram.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | Yes | — | Unique identifier. **Used as key in `theme.json`** to apply per-area styling. |
| `title` | string | No | `""` | Label shown above the area panel |
| `range` | `[min_addr, max_addr]` | No | All sections | Filter sections to this address range. Addresses as hex strings or ints. |
| `pos` | `[x, y]` | No | **auto** | Top-left pixel position. Omit to use auto-layout (see below). Supply to override auto-layout for this area only. |
| `size` | `[width, height]` | No | **auto** | Pixel dimensions. Omit to use auto-layout (see below). Supply to override auto-layout for this area only. |
| `section_size` | `[min_bytes]` or `[min_bytes, max_bytes]` | No | No filter | Filter sections by byte size |
| `sections` | array | No | `[]` | Per-section overrides within this area (see below) |
| `labels` | array | No | `[]` | Address annotation labels (see below) |

### Auto-layout

When any area omits `pos` or `size`, the auto-layout engine activates for the
whole diagram:

1. **Link graph** — a DAG is derived from address containment: an edge A → B is
   added when area B's full address range is contained within a section that
   belongs to area A.
2. **Column assignment** — BFS from roots (areas with no incoming edges) assigns
   each area to a layout column (`column = max depth from any root`).
3. **Bin-packing** — within each DAG column, areas are greedily stacked until
   the column would overflow; excess areas spill into a new sub-column.
4. **Height estimation** — each area's height is set to
   `n_visible × min_section_height + n_breaks × (break_size + 4) + 20`,
   guaranteeing all sections can reach `min_section_height`.
5. **Canvas expansion** — the SVG canvas grows to fit all placed areas; the
   `size` value in `diagram.json` acts as a floor, not a hard limit.

You can mix explicit and auto layout: supply `pos`/`size` on the areas where
you need precise control and omit them on the rest.

### `areas[].sections[]` — Per-Section Overrides

Within an area, you can override the flags, address, size, or type for specific sections. **No style here — style goes in `theme.json`.**

| Field | Type | Description |
|-------|------|-------------|
| `names` | array of strings | Section ids this override applies to |
| `flags` | array of strings | Additional flags to append (e.g. `["break"]`) |
| `address` | hex string or int | Override the section's start address for display |
| `size` | hex string or int | Override the section's size for display |
| `type` | string | Override the section's type for display |

### `areas[].labels[]` — Address Annotations

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `address` | hex string or int | Yes | — | Memory address where the label points |
| `text` | string | No | `"Label"` | Label text |
| `length` | int | No | `20` | Length of the annotation line in pixels |
| `side` | string | No | `"right"` | Which side: `"left"` or `"right"` |
| `directions` | string or array | No | `[]` | Arrow directions: `"in"`, `"out"`, or `["in", "out"]` |

---

## `links` — Cross-Area Connections

| Field | Type | Description |
|-------|------|-------------|
| `addresses` | array | Hex strings or ints — draw horizontal connector lines at these addresses across areas |
| `sections` | array of strings | Section ids — draw a band from `areas[0]` (the source/overview stack) to the first detail area whose address range covers the named section |
| `sub_sections` | array of `[area_id, section_id]` pairs | Draw bands from a non-source area to the next area covering that section's address range. Enables multi-level zoom chains (e.g., bus view → peripheral detail). |

**Design convention:** The first entry in `areas` is treated as the **source** (full/overview) stack and is always positioned on the left. All subsequent areas are **expanded/detail** stacks and are positioned to the right. `links.sections` always originates from the source stack. `links.sub_sections` originates from any named area.

**Band routing:** For both `sections` and `sub_sections`, the band connects to the **first** subsequent area (in `areas[]` order) whose `lowest_memory` ≤ section start and `highest_memory` ≥ section end. Hidden sections still count toward `lowest_memory`/`highest_memory`, so a hidden terminator section can extend a detail area's effective range to accept a link.

Section band visual style is controlled in `theme.json` under `links`. See `theme-schema.md` for the full property list including `shape`, `fill`, `stroke`, and `stroke_dasharray`.

---

## Full Example

```json
{
  "title": "STM32F103 Memory Map",
  "size": [500, 900],

  "sections": [
    { "id": "Flash",      "address": "0x08000000", "size": "0x00020000", "type": "area" },
    { "id": "text",       "address": "0x08000000", "size": "0x00009000", "name": "Code",       "flags": ["grows-up"] },
    { "id": "rodata",     "address": "0x08009000", "size": "0x00002000", "name": "Const Data" },
    { "id": "gap",        "address": "0x0800FFFF", "size": "0x00000001",                       "flags": ["break"] },

    { "id": "SRAM",  "address": "0x20000000", "size": "0x00005000", "type": "area" },
    { "id": "stack", "address": "0x20004000", "size": "0x00001000", "name": "Stack", "flags": ["grows-down"] }
  ],

  "areas": [
    {
      "id": "flash-view",
      "title": "Flash Memory",
      "range": ["0x08000000", "0x08020000"],
      "sections": [
        { "names": ["gap"], "flags": ["break"] }
      ],
      "labels": [
        { "address": "0x08009000", "text": "End of code", "length": 80, "side": "right", "directions": ["in"] }
      ]
    },
    {
      "id": "sram-view",
      "title": "SRAM",
      "range": ["0x20000000", "0x20005000"]
    }
  ],

  "links": {
    "addresses": ["0x20000000"],
    "sections": [["Flash", "SRAM"]]
  }
}
```
