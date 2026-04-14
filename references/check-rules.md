# mmpviz — Check Rules Reference

**When to read this document:** whenever the render outputs an `[ERROR]` or `[WARNING]`
line. Look up the rule name in the table below, read its description and fix guidance,
then edit `diagram.json` accordingly and re-render.

These rules are validated by loading `diagram.json` + `theme.json`, running the same
layout engine as the renderer (`get_area_views()`), and checking the computed section
heights and panel positions. They do **not** parse the SVG output.

The validation runs **automatically** as part of every `mmpviz.py` render:
`[ERROR]` issues abort before SVG generation; `[WARNING]` issues are printed but
rendering continues. The same rules are also available standalone via `check.py` for
CI pipelines that need machine-readable output (`--format json`) or selective rule
runs (`--rules`).

| Command | What happens |
|---------|-------------|
| `python scripts/mmpviz.py -d diagram.json -o out.svg` | Schema validate → layout check → render SVG |
| `python scripts/mmpviz.py -d diagram.json -o out.svg --fmt` | Format JSON → schema validate → layout check → render SVG |
| `python scripts/mmpviz.py -d diagram.json --fmt` | Format JSON only |
| `python scripts/check.py -d diagram.json` | Layout check only (standalone; no format or render) |

## Quick Usage

```
python3 scripts/check.py -d diagram.json
python3 scripts/check.py -d diagram.json -t theme.json
python3 scripts/check.py -d diagram.json -t theme.json --format json
python3 scripts/check.py -d diagram.json -t theme.json --rules panel-overlap,label-overlap
```

Exit codes: **0** = no issues, **1** = one or more ERRORs, **2** = warnings only.

- **ERROR** — the rendered diagram is definitively wrong: a structural constraint is violated, a referenced element is missing, or panels physically collide. Treat the output as unusable until these are resolved.
- **WARN** — the diagram renders but may be hard to read or visually misleading. Whether to act is a judgment call.

---

## Rule Summary

| Rule | Level | Fixer |
|------|-------|-------|
| `min-height-violated` | WARN | Human/AI |
| `section-height-conflict` | ERROR | Human/AI |
| `out-of-canvas` | ERROR | Bug — report |
| `section-overlap` | WARN | Human/AI |
| `uncovered-gap` | WARN | Human/AI |
| `panel-overlap` | ERROR | Human/AI |
| `link-anchor-out-of-bounds` | ERROR | Human/AI |
| `unresolved-section` | ERROR | Human/AI |
| `title-overlap` | WARN | Human/AI (shorten title or reduce view height) |
| `label-overlap` | WARN | Bug — report |
| `addr-64bit-column-width` | WARN | Bug — report |

---

## Per-Section Rules

### `min-height-violated` — WARN

**Violated when:** The panel contains too many sections competing for limited height.
When satisfying all minimum-height constraints would require more pixels than the
panel has, the renderer falls back to pure proportional layout — all sections
render at their proportional size and minimums are violated.

**Fix:** Human/AI — edit `diagram.json`.

**How:**
- Set `"min_height"` on sections that are too thin to read in `diagram.json` — gives them a guaranteed pixel floor.
- Set `"max_height"` on sections that dominate the view in `diagram.json` — caps their pixel budget; the freed height is redistributed to floor-locked sections first.
- Add `"flags": ["break"]` to unimportant sections in `diagram.json` — compresses them to `break_height` px (default 20 px), freeing proportional height for the rest.

---

### `section-height-conflict` — ERROR

**Violated when:** A section declares `"min_height"` greater than `"max_height"` —
a contradictory constraint the height algorithm cannot satisfy:

```json
{ "id": "code", "address": "0x08000000", "size": "0x9000", "name": "Code",
  "min_height": 100, "max_height": 50 }
```

**Fix:** Human/AI — edit the section in `diagram.json`.

**How:** Ensure `min_height ≤ max_height` for every section that declares both fields.

---

## Panel-Level Rules

### `out-of-canvas` — ERROR

**Violated when:** A panel's computed right or bottom edge falls outside the canvas
boundary. Because the canvas is always auto-sized to content, this indicates an
internal auto-layout inconsistency.

**Fix:** Tool bug — no user fix available. Report the issue with your `diagram.json`.

---

### `section-overlap` — WARN

**Violated when:** Two visible (non-break) sections in the same view have overlapping
address ranges. The most common cause is including a parent region and its named
children in the same view:

```json
"sections": [
  { "id": "apb1",  "address": "0x40000000", "size": "0x10000", "name": "APB1"  },
  { "id": "uart0", "address": "0x40000000", "size": "0x400",   "name": "UART0" }
]
```

`APB1` spans the entire range and visually covers `UART0`, making labels unreadable.

**Fix:** Human/AI — edit `sections[]` in `diagram.json`.

**How:** Separate levels of detail into separate views. Put the parent block in an
overview view and the named children in a detail view — never both in the same view.

---

### `uncovered-gap` — WARN

**Violated when:** A large address gap between two consecutive visible sections is
not fully covered by break sections. Two conditions independently trigger this rule:

1. **No break coverage** and the gap exceeds 5× the total size of all non-break
   sections in that view — proportional layout shrinks the real sections to
   near-invisible slivers.

2. **Partial break coverage** — break sections overlap the gap but leave holes,
   and the gap exceeds the size of its flanking sections. The warning message
   reports the first uncovered address.

Coverage is determined by the **union** of all break sections in the view.
Multiple consecutive breaks that together span the full gap are correctly
recognised as covering it — each break does not need to span the entire gap alone.

Example: `Flash` at `0x0000_0000` (512 KB) and `SRAM` at `0x2000_0000` (128 KB)
share a ~500 MB gap. Without any break, condition 1 fires. With one break ending at
`0x0200_0000` instead of `0x2000_0000`, condition 2 fires.

**Fix:** Human/AI — add or correct break section(s) in `diagram.json`.

**How:** Break sections must be contiguous; their union must span `[gap_lo, gap_hi]`
with no holes. A single break is simplest:

```json
{ "id": "gap0", "address": "0x00080000", "size": "0x1FF80000",
  "name": "···", "flags": ["break"] }
```

Multiple consecutive breaks are also valid — ensure each break's start address
equals `previous_break.address + previous_break.size` with no gaps between them.

---

### `panel-overlap` — ERROR

**Violated when:** Two panels' bounding rectangles physically intersect. This occurs
when stacked panels in the same column grow tall enough to collide — sections,
borders, and labels from one panel bleed into the other.

**Fix:** Human/AI — reduce panel height in `diagram.json`.

**How:**
- Add `"break"` sections to compress large gaps in the taller view.
- Set `"max_height"` on dominant sections in `diagram.json` to cap their pixel
  allocation.

---

### `title-overlap` — WARN

**Violated when:** Two panel titles overlap — either vertically or horizontally:

- **Vertical** — a panel's title intrudes into the body of the panel directly above
  it in the same column. Titles render 20 px above the panel top edge; the checker
  uses a 25 px clearance zone. Fires when the upper panel is too tall, leaving
  insufficient vertical gap for the lower panel's title.

- **Horizontal** — two panel titles at the same vertical level (e.g. adjacent columns
  in the top row) overlap in the inter-column gap. Title width is estimated from the
  character count × font size.

**Fix (vertical):** Human/AI — reduce the height of the upper panel in `diagram.json`.

**How:**
- Add `"break"` sections to compress large gaps in the upper view.
- Set `"max_height"` on dominant sections in the upper view.

**Fix (horizontal):** Human/AI — shorten the view `"title"` field in `diagram.json`.

---

### `label-overlap` — WARN

**Violated when:** Address labels extending from the right edge of a panel reach the
left edge of the adjacent panel in the next column.

The inter-column gap is computed from the actual label width and font size of each
source column (§8 of `auto-layout-algorithm.md`), so this rule should never fire for
diagrams rendered by the current auto-layout engine. If it fires, that is a tool bug.

**Fix:** Bug — report with your `diagram.json`.

---

### `addr-64bit-column-width` — WARN

**Violated when:** The inter-column gap is too narrow for 64-bit address labels
(18 characters: `"0x"` + 16 hex digits) on a panel whose sections have start
addresses above `0xFFFF_FFFF`.

The auto-layout engine computes the gap from actual label width and font size, so
this rule should never fire for diagrams rendered by the current engine. If it fires,
that is a tool bug.

**Fix:** Bug — report with your `diagram.json`.

---

## Link Rules

### `link-anchor-out-of-bounds` — ERROR

**Violated when:** A link band's source-side or destination-side y-anchor falls
outside the panel's rendered pixel range `[pos_y, pos_y + size_y]`. When this
happens the band is drawn partially or fully outside the panel rectangle and no
longer aligns with the sections it is supposed to annotate.

For section-ID specifiers this should never fire — sections are always within
their panel's pixel range. It fires when `links[].from.sections` or
`links[].to.sections` uses an explicit address-range form
(e.g. `["0x0", "0x5000"]`) whose addresses extend beyond the view's actual
address range.

**Fix:** Human/AI — edit `links[]` in `diagram.json`.

**How:** Correct the address values in `from.sections` or `to.sections` so they
stay within the referenced view's address extent, or remove the explicit range to
span the full view.

---

### `unresolved-section` — ERROR

**Violated when:** A view ID or section ID referenced in a `links[]` entry does not
exist in the diagram. The renderer silently skips unresolved links, so the missing
band produces no visual error:

```json
{ "from": {"view": "flash-view", "sections": ["coode"]}, "to": {"view": "flash-detail"} }
```

`"coode"` is a typo — no such section exists in `"flash-view"`.

**Fix:** Human/AI — edit `links[]` in `diagram.json`.

**How:** Correct the section or view ID spelling. Verify the section is declared in
the exact view named by `from.view` (or `to.view`) — a section with the same ID in
a different view does not satisfy the reference.
