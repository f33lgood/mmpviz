# diagram.json — Schema Reference

A `diagram.json` file is the single semantic description of a memory map diagram.
It contains one or more views, each with its own sections, plus optional cross-view links.
**No visual styling belongs here** — put colors, fonts, and sizes in `theme.json`.

The machine-readable contract for this format lives in `schemas/diagram.schema.json`
(JSON Schema draft 2020-12). The validation script loads it automatically when the
`jsonschema` Python package is available.

---

## Top-Level Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `title` | string | No | `""` | Document title (informational only) |
| `views` | array | Yes | — | Display viewport definitions — each view declares its own sections |
| `links` | array | No | `[]` | Cross-view connections |

---

## `views[]` — Display Viewport Fields

Each entry in `views` defines one memory view panel in the SVG diagram. A view owns its sections — all section data lives inside the view that displays it.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | Yes | — | Unique identifier — must be unique across the entire diagram. **Format: `[a-z0-9_-]` only** (lowercase letters, digits, underscores, hyphens — no spaces, uppercase, dots, or slashes). Examples: `"flash-view"`, `"apb_detail"`. Used as a key in `theme.json` to apply per-view styling. |
| `title` | string | No | `""` | Label shown above the view panel |
| `sections` | array | Yes | — | Section definitions for this view (see below) |
| `labels` | array | No | `[]` | Address annotation labels (see below) |

### Auto-layout

The auto-layout engine always runs — view positions and canvas size are computed
automatically:

1. **Link graph** — a DAG is built from the `links` array (one directed edge per
   entry, `from.view → to.view`). When `links` is absent or empty, all views have
   no edges and are placed in a single column.
2. **Column assignment** — BFS from roots (views with no incoming edges) assigns
   each view to a layout column (`column = max depth from any root`).
3. **Bin-packing** — within each DAG column, views are greedily stacked until
   the column would overflow; excess views spill into a new sub-column.
4. **Height estimation** — each view's height is set to
   `Σ max(min_section_height, section.min_height) + n_breaks × (break_height + 4) + 20`,
   guaranteeing all sections can reach their effective minimum height.
5. **Canvas sizing** — the SVG canvas is sized to exactly contain all placed views.

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
| `min_height` | number (≥ 0) | No | `null` | Per-section pixel height floor. Effective floor = `max(min_height, theme min_section_height)`. Use for sections whose proportional height would be too small to read. |
| `max_height` | number (≥ 0) | No | `null` | Per-section pixel height ceiling. Effective ceiling = `min(max_height, theme max_section_height)`. Use for sections whose proportional height would dominate the view. `min_height` must not exceed `max_height`. |

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
| `id` | string | Yes | — | Unique identifier within this view. **Format: `[a-z0-9_-]` only**. Used as a key in `theme.json` under `views[view_id].labels[label_id]` for per-label style overrides. |
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
  {"id": "flash-link",   "from": {"view": "overview",  "sections": ["flash"]},          "to": {"view": "flash-view"}},
  {"id": "periph-link",  "from": {"view": "overview",  "sections": ["peripherals"]},    "to": {"view": "apb-view"}},
  {"id": "dma-link",     "from": {"view": "apb-view",  "sections": ["dma"]},            "to": {"view": "dma-view"}},
  {"id": "detail-link",  "from": {"view": "overview",  "sections": ["0x4000", "0x5000"]}, "to": {"view": "detail-view"}}
]
```

### Link Entry Object

Each entry has three required fields:

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique identifier across all links. **Format: `[a-z0-9_-]` only**. Used as a key in `theme.json` under `links.overrides[link_id]` for per-link style overrides. |
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
  {"id": "cpu-periph",   "from": {"view": "cpu-view",      "sections": ["sysperiph"]}, "to": {"view": "periph-detail"}},
  {"id": "dbg-periph",   "from": {"view": "debugger-view", "sections": ["sysperiph"]}, "to": {"view": "periph-detail"}}
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
    "id":   "alias-link",
    "from": {"view": "overview", "sections": ["itcm_alias"]},
    "to":   {"view": "overview", "sections": ["flash"]}
  }
]
```

### Visual Style

Band style (shape, fill, stroke, dash pattern) is controlled in `theme.json` under `links`. Global defaults live in `links.connector` or `links.band`. Per-link overrides are placed in `links.overrides[link_id]`, where `link_id` matches the `id` field here. See `theme-schema.md` for the full property list.

---

## Examples

Worked `diagram.json` files are in `examples/` — each subdirectory is a self-contained
diagram with a `diagram.json`, optional `theme.json`, and a rendered `golden.svg`.
