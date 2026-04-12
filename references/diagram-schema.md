# diagram.json — Schema Reference

A `diagram.json` file is the single semantic description of a memory map diagram.
It contains one or more views, each with its own sections, plus optional cross-view links.
**No visual styling belongs here** — put colors, fonts, and sizes in `theme.json`.

---

## Top-Level Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `title` | string | No | `""` | Document title (informational only) |
| `size` | `[width, height]` | No | **auto** | SVG canvas floor in pixels. When auto-layout is active (any view omits `pos`/`size`), the canvas expands to fit all views and this value is only a minimum. Omit it entirely to let auto-layout size the canvas. Set it only when you need a fixed coordinate space for manual view placement. |
| `views` | array | Yes | — | Display viewport definitions — each view declares its own sections |
| `links` | array | No | `[]` | Cross-view connections |

### Choosing a Canvas Size (manual layout only)

This section applies only when you supply explicit `pos`/`size` on views. With auto-layout, skip it — the canvas is computed automatically.

Because the output is SVG, the numbers in `size` define the **coordinate space and aspect ratio**, not a fixed pixel size. The diagram scales to any physical size without loss.

Choose values that match your intended output format's aspect ratio and give comfortable spacing for the number of views you have. See `references/layout-guide.md` for recommended `size`, `pos`, and `size` values for common targets (A4 paper, 16:9 slides, etc.).

---

## `views[]` — Display Viewport Fields

Each entry in `views` defines one memory view panel in the SVG diagram. A view owns its sections — all section data lives inside the view that displays it.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | Yes | — | Unique identifier — must be unique across the entire diagram. **Format: `[a-z0-9_-]` only** (lowercase letters, digits, underscores, hyphens — no spaces, uppercase, dots, or slashes). Examples: `"flash-view"`, `"apb_detail"`. Used as a key in `theme.json` to apply per-view styling. |
| `title` | string | No | `""` | Label shown above the view panel |
| `pos` | `[x, y]` | No | **auto** | Top-left pixel position. Omit to use auto-layout (see below). Supply to override auto-layout for this view only. |
| `size` | `[width, height]` | No | **auto** | Pixel dimensions. Omit to use auto-layout (see below). Supply to override auto-layout for this view only. |
| `sections` | array | Yes | — | Section definitions for this view (see below) |
| `labels` | array | No | `[]` | Address annotation labels (see below) |

### Auto-layout

When any view omits `pos` or `size`, the auto-layout engine activates for the
whole diagram:

1. **Link graph** — a DAG is built from the `links` array (one directed edge per
   entry, `from.view → to.view`). When `links` is absent or empty, all views have
   no edges and are placed in a single column.
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

---

## `views[].sections[]` — Section Fields

Each entry in a view's `sections` array describes one contiguous memory region
displayed in that view.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | Yes | — | Identifier — must be unique within this view. **Format: `[a-z0-9_-]` only**. Used as a key in `theme.json` under `views[view_id].sections[section_id]`. The same `id` may appear in different views independently. |
| `address` | hex string or int | Yes | — | Start address. Hex strings (`"0x08000000"`) and integers both accepted. |
| `size` | hex string or int | Yes | — | Size in bytes. Hex strings and integers both accepted. |
| `name` | string | Yes | — | Display text shown inside the section box. No uniqueness requirement — duplicates are allowed. May be an empty string `""` to suppress the label. |
| `flags` | array of strings | No | `[]` | Visual behavior flags (see below). |

### `flags` allowed values

| Flag | Effect |
|------|--------|
| `"grows-up"` | Draws an upward growth arrow on this section |
| `"grows-down"` | Draws a downward growth arrow on this section |
| `"break"` | Renders as a height-compressed plain box using `break_fill` as background (falls back to `fill`). Break sections are always exactly `break_height` pixels tall regardless of their byte range — the remaining panel height is redistributed among non-break sections. Use a distinct `break_fill` color and a short label such as `"···"` to signal that the address range is compressed. |

---

## `views[].labels[]` — Address Annotations

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `address` | hex string or int | Yes | — | Memory address where the label points |
| `text` | string | No | `"Label"` | Label text |
| `length` | int | No | `20` | Length of the annotation line in pixels |
| `side` | string | No | `"right"` | Which side: `"left"` or `"right"` |
| `directions` | string or array | No | `[]` | Arrow directions: `"in"`, `"out"`, or `["in", "out"]` |

---

## `links` — Cross-View Connections

`links` is an **array** of link entry objects. Each entry connects a source view
to a destination view with a rendered band (trapezoid or curve).

```json
"links": [
  {"from": {"view": "overview",  "sections": ["flash"]},          "to": {"view": "flash-view"}},
  {"from": {"view": "overview",  "sections": ["peripherals"]},    "to": {"view": "apb-view"}},
  {"from": {"view": "apb-view",  "sections": ["dma"]},            "to": {"view": "dma-view"}},
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
| `sections` | both | No | Determines which address range the band anchors to on this view (see below). Omit to use the view's full address range. Supported on both `from` and `to`. |

### `sections` Specifier

Controls the **vertical span of the band on each endpoint** — the address range the band connects to on that view. Both `from.sections` and `to.sections` accept the same three forms:

| Form | Example | Meaning |
|------|---------|---------|
| Omitted | _(absent)_ | Full address range of the view |
| Single section ID | `["flash"]` | The named section's own `[address, address + size]` range — must exist in the referenced view |
| Multiple section IDs | `["flash", "sram"]` | Span from the lowest `address` to the highest `address + size` across all named sections — all must exist in the referenced view |
| Address range | `["0x08000000", "0x08020000"]` | Explicit hex start and end (detected when both elements match `^0x[0-9a-fA-F]+$`) |

When `to.sections` is omitted, the destination-side band height is derived by
clamping the source address range to the destination view's extent (the common
zoom case where a large parent section connects to a detail view that shows only
a sub-range). When `to.sections` is specified, the destination-side band height
is anchored to the explicitly resolved range, independently of the source range.
This allows the band's two endpoints to sit at **different** address positions
(e.g. address-aliasing, cross-bus routing, or DMA channel mappings).

### Multiple Sources → Same Destination (fan-in)

To map two source views to the same detail view, add two entries with the same
`to.view`:

```json
"links": [
  {"from": {"view": "cpu-view",      "sections": ["sysperiph"]}, "to": {"view": "periph-detail"}},
  {"from": {"view": "debugger-view", "sections": ["sysperiph"]}, "to": {"view": "periph-detail"}}
]
```

Two separate bands are rendered, one per entry.

### Cross-Address Mapping (`to.sections` at a different address)

When `to.sections` resolves to an address range that does not overlap the source
range, the band is drawn as a skewed trapezoid connecting two different address
positions. This is useful for address aliases, remaps, or DMA channel mappings:

```json
"links": [
  {
    "from": {"view": "overview", "sections": ["itcm_alias"]},
    "to":   {"view": "overview", "sections": ["flash"]}
  }
]
```

### Visual Style

Band style (shape, fill, stroke, dash pattern) is controlled in `theme.json`
under `links`. See `theme-schema.md` for the full property list.

---

## Examples

Worked `diagram.json` files are in `examples/` — each subdirectory is a self-contained
diagram with a `diagram.json`, optional `theme.json`, and a rendered `golden.svg`.
