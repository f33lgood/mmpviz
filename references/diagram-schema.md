# diagram.json — Schema Reference

A `diagram.json` file is the single semantic description of a memory map diagram.
It contains the raw memory data (`sections`) and the display layout (`views`, `links`).
**No visual styling belongs here** — put colors, fonts, and sizes in `theme.json`.

---

## Top-Level Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `title` | string | No | `""` | Document title (informational only) |
| `size` | `[width, height]` | No | **auto** | SVG canvas floor in pixels. When auto-layout is active (any view omits `pos`/`size`), the canvas expands to fit all views and this value is only a minimum. Omit it entirely to let auto-layout size the canvas. Set it only when you need a fixed coordinate space for manual view placement. |
| `sections` | array | Yes | — | Memory section definitions |
| `views` | array | No | Auto | Display viewport definitions |
| `links` | array | No | `[]` | Cross-view connections |

### Choosing a Canvas Size (manual layout only)

This section applies only when you supply explicit `pos`/`size` on views. With auto-layout, skip it — the canvas is computed automatically.

Because the output is SVG, the numbers in `size` define the **coordinate space and aspect ratio**, not a fixed pixel size. The diagram scales to any physical size without loss.

Choose values that match your intended output format's aspect ratio and give comfortable spacing for the number of views you have. See `references/layout-guide.md` for recommended `size`, `pos`, and `size` values for common targets (A4 paper, 16:9 slides, etc.).

---

## `sections[]` — Memory Section Fields

Each entry in `sections` describes one contiguous memory region.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | Yes | — | Unique identifier. Used in `view.sections[].ids` references and as theme key. |
| `address` | hex string or int | Yes | — | Start address. Hex strings (`"0x08000000"`) and integers both accepted. |
| `size` | hex string or int | Yes | — | Size in bytes. Hex strings and integers both accepted. |
| `flags` | array of strings | No | `[]` | Visual behavior flags (see below). |
| `name` | string | No | `null` | Friendly display name shown in the diagram. Falls back to `id` if absent. |

### `flags` allowed values

| Flag | Effect |
|------|--------|
| `"grows-up"` | Draws an upward growth arrow on this section |
| `"grows-down"` | Draws a downward growth arrow on this section |
| `"break"` | Renders as a height-compressed plain box using `break_fill` as background (falls back to `fill`). Break sections are always exactly `break_height` pixels tall regardless of their byte range — the remaining panel height is redistributed among non-break sections. Use a distinct `break_fill` color and a short label such as `"···"` to signal that the address range is compressed. |
| `"hidden"` | Section is loaded but not rendered |

---

## `views[]` — Display Viewport Fields

Each entry in `views` defines one memory view panel in the SVG diagram.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | Yes | — | Unique identifier. **Used as key in `theme.json`** to apply per-view styling. |
| `title` | string | No | `""` | Label shown above the view panel |
| `range` | `[min_addr, max_addr]` | No | All sections | Filter sections to this address range. Addresses as hex strings or ints. |
| `pos` | `[x, y]` | No | **auto** | Top-left pixel position. Omit to use auto-layout (see below). Supply to override auto-layout for this view only. |
| `size` | `[width, height]` | No | **auto** | Pixel dimensions. Omit to use auto-layout (see below). Supply to override auto-layout for this view only. |
| `section_size` | `[min_bytes]` or `[min_bytes, max_bytes]` | No | No filter | Filter sections by byte size |
| `sections` | array | No | `[]` | Per-section overrides within this view (see below) |
| `labels` | array | No | `[]` | Address annotation labels (see below) |

### Auto-layout

When any view omits `pos` or `size`, the auto-layout engine activates for the
whole diagram:

1. **Link graph** — a DAG is built from the `links` array (one directed edge per
   entry, `from.view → to.view`). When `links` is absent or empty, the DAG falls
   back to address containment: an edge A → B is added when view B's full address
   range is contained within a section that belongs to view A.
2. **Column assignment** — BFS from roots (views with no incoming edges) assigns
   each view to a layout column (`column = max depth from any root`).
3. **Bin-packing** — within each DAG column, views are greedily stacked until
   the column would overflow; excess views spill into a new sub-column.
4. **Height estimation** — each view's height is set to
   `n_visible × min_section_height + n_breaks × (break_height + 4) + 20`,
   guaranteeing all sections can reach `min_section_height`.
5. **Canvas expansion** — the SVG canvas grows to fit all placed views; the
   `size` value in `diagram.json` acts as a floor, not a hard limit.

You can mix explicit and auto layout: supply `pos`/`size` on the views where
you need precise control and omit them on the rest.

### `views[].sections[]` — Per-Section Overrides

Within a view, you can override the flags, address, or size for specific sections. **No style here — style goes in `theme.json`.**

| Field | Type | Description |
|-------|------|-------------|
| `ids` | array of strings | Section ids this override applies to |
| `flags` | array of strings | Additional flags to append (e.g. `["break"]`) |
| `address` | hex string or int | Override the section's start address for display |
| `size` | hex string or int | Override the section's size for display |

### `views[].labels[]` — Address Annotations

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `address` | hex string or int | Yes | — | Memory address where the label points |
| `text` | string | No | `"Label"` | Label text |
| `length` | int | No | `20` | Length of the annotation line in pixels |
| `side` | string | No | `"right"` | Which side: `"left"` or `"right"` |
| `directions` | string or array | No | `[]` | Arrow directions: `"in"`, `"out"`, or `["in", "out"]` |

---

## `links` — Cross-View Connections

`links` is an **array** of link entry objects.  Each entry connects a source view
to a destination view with a rendered band (trapezoid or curve).

```json
"links": [
  {"from": {"view": "overview",  "sections": ["Flash"]},          "to": {"view": "flash-view"}},
  {"from": {"view": "overview",  "sections": ["Peripherals"]},    "to": {"view": "apb-view"}},
  {"from": {"view": "apb-view",  "sections": ["DMA"]},            "to": {"view": "dma-view"}},
  {"from": {"view": "overview",  "sections": ["0x4000", "0x5000"]}, "to": {"view": "detail-view"}}
]
```

### Link Entry Object

Each entry has two required fields:

| Field | Required | Description |
|-------|----------|-------------|
| `from` | Yes | Source endpoint (see below) |
| `to` | Yes | Destination endpoint (see below) |

`from` and `to` endpoint fields:

| Field | Endpoint | Required | Description |
|-------|----------|----------|-------------|
| `view` | both | Yes | View id. Always required — no implicit defaults. |
| `sections` | `from` only | No | Determines which address range on the source view the band anchors to (see below). Omit to use the source view's full address range. The band always spans the full destination view regardless of any `sections` value on `to`. |

### `sections` Specifier

Controls the **vertical span of the band on the source view** — i.e., which address range the band connects to on `from.view`. Three forms:

| Form | Example | Meaning |
|------|---------|---------|
| Omitted | _(absent)_ | Full address range of the source view |
| Single section ID | `["SysPeriph"]` | The named section's own `[address, address + size]` range |
| Multiple section IDs | `["Flash", "SRAM"]` | Span from the lowest `address` to the highest `address + size` across all named sections |
| Address range | `["0x08000000", "0x08020000"]` | Explicit hex start and end (detected when both elements match `^0x[0-9a-fA-F]+$`) |

The section ID list can include sections that are hidden or filtered by
`section_size` in the source view — the address range is resolved from the
global section table.

### Multiple Sources → Same Destination (fan-in)

To map two source views to the same detail view, add two entries with the same
`to.view`:

```json
"links": [
  {"from": {"view": "cpu-view",      "sections": ["SysPeriph"]}, "to": {"view": "periph-detail"}},
  {"from": {"view": "debugger-view", "sections": ["SysPeriph"]}, "to": {"view": "periph-detail"}}
]
```

Two separate bands are rendered, one per entry.

### Visual Style

Band style (shape, fill, stroke, dash pattern) is controlled in `theme.json`
under `links`. See `theme-schema.md` for the full property list.

---

## Full Example

```json
{
  "title": "STM32F103 Memory Map",

  "sections": [
    { "id": "Flash",      "address": "0x08000000", "size": "0x00020000" },
    { "id": "text",       "address": "0x08000000", "size": "0x00009000", "name": "Code",       "flags": ["grows-up"] },
    { "id": "rodata",     "address": "0x08009000", "size": "0x00002000", "name": "Const Data" },
    { "id": "gap",        "address": "0x0800FFFF", "size": "0x00000001",                       "flags": ["break"] },

    { "id": "SRAM",  "address": "0x20000000", "size": "0x00005000" },
    { "id": "stack", "address": "0x20004000", "size": "0x00001000", "name": "Stack", "flags": ["grows-down"] }
  ],

  "views": [
    {
      "id": "flash-view",
      "title": "Flash Memory",
      "range": ["0x08000000", "0x08020000"],
      "sections": [
        { "ids": ["gap"], "flags": ["break"] }
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

  "links": [
    {"from": {"view": "flash-view", "sections": ["Flash"]}, "to": {"view": "sram-view"}}
  ]
}
```
