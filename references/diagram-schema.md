# diagram.json — Schema Reference

A `diagram.json` file is the single semantic description of a memory map diagram.
It contains the raw memory data (`sections`) and the display layout (`areas`, `links`).
**No visual styling belongs here** — put colors, fonts, and sizes in `theme.json`.

---

## Top-Level Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `title` | string | No | `""` | Document title (informational only) |
| `size` | `[width, height]` | No | `[400, 700]` | SVG canvas dimensions in pixels |
| `sections` | array | Yes | — | Memory section definitions |
| `areas` | array | No | Auto | Display viewport definitions |
| `links` | object | No | — | Cross-area connections |

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
| `"break"` | Renders as a compressed break (≈ pattern by default) instead of a normal box |
| `"hidden"` | Section is loaded but not rendered |

---

## `areas[]` — Display Viewport Fields

Each entry in `areas` defines one memory view panel in the SVG diagram.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | Yes | — | Unique identifier. **Used as key in `theme.json`** to apply per-area styling. |
| `title` | string | No | `""` | Label shown above the area panel |
| `range` | `[min_addr, max_addr]` | No | All sections | Filter sections to this address range. Addresses as hex strings or ints. |
| `pos` | `[x, y]` | No | **auto** | Top-left pixel position. Omit to use auto-layout (areas distributed evenly left-to-right). |
| `size` | `[width, height]` | No | **auto** | Pixel dimensions. Omit to use auto-layout (equal width, full canvas height minus padding). |
| `section_size` | `[min_bytes]` or `[min_bytes, max_bytes]` | No | No filter | Filter sections by byte size |
| `sections` | array | No | `[]` | Per-section overrides within this area (see below) |
| `labels` | array | No | `[]` | Address annotation labels (see below) |

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
| `sections` | array | Pairs `["from_id", "to_id"]` or single strings — draw filled bands connecting matched sections |

**Note:** Section links require both sections to be visible within the same pair of areas (left area + right area).

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
      "pos": [50, 80],
      "size": [180, 750],
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
      "range": ["0x20000000", "0x20005000"],
      "pos": [270, 80],
      "size": [180, 750]
    }
  ],

  "links": {
    "addresses": ["0x20000000"],
    "sections": [["Flash", "SRAM"]]
  }
}
```
