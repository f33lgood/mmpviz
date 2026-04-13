# mmpviz check.py — Rule Reference

`scripts/check.py` is a **separate, standalone script** — it is not called by `mmpviz.py`
and does not run automatically during rendering. You must invoke it explicitly.

`check.py` does **not** read or parse the SVG. It loads `diagram.json` + `theme.json`,
runs the same layout engine as `mmpviz.py` (`get_area_views()`), and validates the
computed section heights and panel positions against the rules below. It stops before
SVG generation. This means `check.py` can be run before or instead of rendering.

Three distinct operations exist:

| Command | Input | What it checks |
|---------|-------|---------------|
| `python scripts/mmpviz.py -d diagram.json -o out.svg` | `diagram.json` | Nothing — renders directly |
| `python scripts/mmpviz.py --validate diagram.json` | `diagram.json` | JSON Schema only (structure, required fields, types) |
| `python scripts/check.py -d diagram.json` | `diagram.json` | Layout and display rules (this document) |

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
| `out-of-canvas` | ERROR | Tool bug |
| `section-overlap` | WARN | Human/AI |
| `uncovered-gap` | WARN | Human/AI |
| `panel-overlap` | ERROR | Human/AI |
| `band-too-wide` | WARN | Human/AI |
| `unresolved-section` | ERROR | Human/AI |
| `title-overlap` | WARN | Human/AI |
| `label-overlap` | WARN | Bug — report |
| `addr-64bit-column-width` | WARN | Bug — report |

---

## Per-Section Rules

### `min-height-violated` — WARN

**Violated when:** The panel contains too many sections competing for limited height.
When satisfying all minimum-height constraints would require more pixels than the
panel has, the renderer falls back to pure proportional layout — all sections
render at their proportional size and minimums are violated.

**Fix:** Human/AI — edit `diagram.json`; adjust `theme.json` only if the global floor itself is the problem.

**How:**
- Set `"min_height"` on sections that are too thin to read in `diagram.json` — gives them a guaranteed pixel floor.
- Set `"max_height"` on sections that dominate the view in `diagram.json` — caps their pixel budget; the freed height is redistributed to floor-locked sections first.
- Add `"flags": ["break"]` to unimportant sections in `diagram.json` — compresses them to `break_height` px (default 20 px), freeing proportional height for the rest.
- Lower `"min_section_height"` in `theme.json` — only if the global floor is the limiting factor (all sections, not just one, are being forced too large).

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
not fully compressed by a break section. Two conditions independently trigger this
rule:

1. **No break covers the gap** and the gap exceeds 5× the total size of all
   non-break sections in that view — proportional layout shrinks the real sections
   to near-invisible slivers.

2. **A break starts at the gap but stops short** — the existing break section ends
   before the next visible section begins, leaving part of the gap uncompressed.
   The warning message reports how far short the break falls.

Example: `Flash` at `0x0000_0000` (512 KB) and `SRAM` at `0x2000_0000` (128 KB)
share a ~500 MB gap — without a break, the gap consumes almost all view height.
A break ending at `0x0200_0000` instead of `0x2000_0000` triggers condition 2.

**Fix:** Human/AI — add or correct a break section in `diagram.json`.

**How:** Insert a break section spanning the entire gap:

```json
{ "id": "gap0", "address": "0x00080000", "size": "0x1FF80000",
  "name": "···", "flags": ["break"] }
```

The start address must be exactly `previous_section.address + previous_section.size`,
and the break's end must exactly reach the next section's start.

---

### `panel-overlap` — ERROR

**Violated when:** Two panels' bounding rectangles physically intersect. This occurs
when stacked panels in the same column grow tall enough to collide — sections,
borders, and labels from one panel bleed into the other.

**Fix:** Human/AI — reduce panel height in `diagram.json` or `theme.json`.

**How:**
- Add `"break"` sections to compress large gaps in the taller view.
- Set `"max_height"` on dominant sections in `diagram.json` to cap their pixel
  allocation.
- Lower `"max_section_height"` in `theme.json` to cap all sections globally.

---

### `title-overlap` — WARN

**Violated when:** A panel's title text intrudes into the body of the panel directly
above it. Titles render 20 px above the panel top edge; check.py uses a 25 px
clearance zone. This fires when the upper panel is too tall and leaves insufficient
vertical gap for the lower panel's title.

**Fix:** Human/AI — reduce the height of the upper panel in `diagram.json` or
`theme.json`.

**How:**
- Add `"break"` sections to compress large gaps in the upper view.
- Set `"max_height"` on dominant sections in the upper view.

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

### `band-too-wide` — WARN

**Violated when:** A link band's horizontal span (source panel right edge to
destination panel left edge) is very large — the band may dominate the diagram's
visual composition.

- Span > 200 px for the nearest detail panel: ideally ≤ 200 px.
- Span > 600 px for any detail panel: band is visually very prominent.

**Fix:** Human/AI — edit `theme.json`.

**How:** Set `"opacity": 0.3`–`0.4` in the `links` section of `theme.json` to make
the band recede without removing it. There is no `diagram.json` change that reduces
the span — it is determined entirely by the auto-layout column placement.

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
