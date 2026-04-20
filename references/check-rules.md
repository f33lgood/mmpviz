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

Theme resolution matches `mmpviz.py`: if `-t` is omitted, `check.py` picks up
a sibling `theme.json` next to `diagram.json` before falling back to the
built-in default. Providing `-t` always wins over a sibling. See
[`references/theme-schema.md`](theme-schema.md#theme-resolution-order) for
the full resolution table.

Exit codes: **0** = no issues, **1** = one or more ERRORs, **2** = warnings only.

- **ERROR** — the rendered diagram is definitively wrong: a structural constraint is violated, a referenced element is missing, or panels physically collide. Treat the output as unusable until these are resolved.
- **WARN** — the diagram renders but may be hard to read or visually misleading. Whether to act is a judgment call.

Some rules are **layout-engine bug guards**: they cannot fire on a valid `diagram.json` rendered by the current engine. They exist to catch regressions. If one fires, it is a tool bug — no user edit can prevent it. These are marked **Bug — report** in the Fixer column.

---

## Rule Summary

| Rule | Level | Fixer |
|------|-------|-------|
| `section-height-conflict` | ERROR | Human/AI |
| `break-overlaps-section` | ERROR | Human/AI |
| `unresolved-section` | ERROR | Human/AI |
| `link-address-range-order` | ERROR | Human/AI |
| `link-anchor-out-of-bounds` | ERROR | Human/AI (address-range form) |
| `section-overlap` | WARN | Human/AI |
| `uncovered-gap` | WARN | Human/AI |
| `section-name-overflow` | WARN | Human/AI (shorten name) |
| `min-height-below-global` | WARN | Human/AI |
| `min-height-on-break` | WARN | Human/AI |
| `label-out-of-range` | WARN | Human/AI |
| `link-self-referential` | WARN | Human/AI |
| `link-address-range-mappable` | WARN | Human/AI |
| `link-redundant-sections` | WARN | Human/AI |
| `title-overlap` | WARN | Human/AI (horizontal); Bug — report (vertical) |
| `min-height-violated` | WARN | Bug — report |
| `panel-overlap` | ERROR | Bug — report |
| `out-of-canvas` | ERROR | Bug — report |
| `label-overlap` | WARN | Bug — report |
| `addr-64bit-column-width` | WARN | Bug — report |

---

## Per-Section Rules

### `min-height-violated` — WARN

**Violated when:** A section's rendered height falls below its effective minimum.
The effective minimum is the largest of four floors:

1. **Global floor** — `min_section_height` in the theme (recommended baseline for all sections).
2. **Per-section floor** — `"min_height"` on the section in `diagram.json` (use only when a section needs a floor *higher* than the global one; setting it lower than the global floor triggers `min-height-below-global`).
3. **Label-conflict floor** — `30 + font_size` px, applied automatically when the size label and name label would overlap horizontally (geometry-dependent, not a fixed value — typically 0 for wide views).
4. **Grows-arrow neighbor floor** — `2 × 20 × growth_arrow.size + font_size` px, applied automatically to any non-break section immediately adjacent (in address order) to a section with a `grows-up` or `grows-down` flag, so the arrow tip clears the neighbor's text label center.

In the floor-stack model the layout engine assigns every section exactly its floor height — floors are always satisfied by construction; this rule firing indicates a layout engine bug, not a configuration problem.

**Fix:** Report as a bug if observed on a well-formed diagram. The check is retained
as a guard to catch regressions in the layout engine.

---

### `min-height-below-global` — WARN

**Violated when:** A section's `"min_height"` is set lower than the global
`min_section_height` in the theme, undercutting the global floor for that section.

The most common cause is copying a `min_height` value from an older diagram or
setting it to a small number (e.g. `0`) without realising it silently overrides
the global baseline downward.

**Preferred pattern:** use `min_section_height` in the theme as the universal
baseline. Only set a per-section `"min_height"` when a specific section needs a
floor *higher* than the global one — never lower.

**Fix:** Human/AI — edit `diagram.json`.

**How:** Set `"min_height" ≥ min_section_height` for the flagged section, or
remove the field entirely to inherit the global floor.

---

### `min-height-on-break` — WARN

**Violated when:** A section has `"min_height"` set but is also flagged `"break"`.
The layout engine ignores `min_height` on break sections — they always render at
`break_height` px (default 20 px) regardless of the configured floor.

The most common cause is adding `"flags": ["break"]` to an existing section without
removing its `"min_height"` field.

**Fix:** Human/AI — edit the section in `diagram.json`.

**How:** Either remove `"min_height"` from the break section, or remove the `"break"`
flag and keep `"min_height"` if the intent was to give the section a visible height floor.

---

### `section-name-overflow` — WARN

**Violated when:** A section's name text is estimated to be wider than the section
panel, even when the name occupies a line of its own (two-line layout).

Section names are rendered as a single horizontal SVG `<text>` element centred in
the panel — there is no automatic text wrapping.  When the estimated width exceeds
the available panel width the text visually overflows the section box and overlaps
adjacent sections.  This cannot be corrected by the layout engine; the name must be
shortened in `diagram.json`.

**Estimated name width** = `len(name) × 0.6 × font_size`  (Helvetica width ratio).

**Available panel width** = `size_x − 8 px` (4 px margin from each border edge).

**Relationship to label-conflict floor.**  There are two distinct horizontal
constraints on section names:

1. **Same-line** (size label and name share a Y-level): the name must not overlap
   the size label on the left.  Available name width ≈ `size_x − 2 × size_label_width`.
   At default settings (`font_size=12`, `size_x=230`, 5–6 char size label) this limits
   names to roughly 19 characters — the guideline in `create-diagram.md`.  Exceeding
   this triggers the label-conflict floor (`30 + font_size` px), which the layout
   engine resolves automatically by moving the name to its own Y-line.

2. **Two-line** (name on its own line): the name can use the full panel width.
   Available = `size_x − 8 px`.  This rule (`section-name-overflow`) checks this
   wider bound.  If the name still overflows here, the engine cannot help — shorten
   the name.

**Fix:** Human/AI — edit the section in `diagram.json`.

**How:** Shorten `"name"` to fit within the panel width.  To stay under the
same-line limit (avoiding forced two-line layout), keep names to approximately
`(size_x − 2 × size_label_width) / (0.6 × font_size)` characters.  At default
settings this is roughly 19 characters.

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

Also fires (WARN) when two break sections have overlapping address ranges — the breaks are redundant. Fix: resize the breaks so their ranges are non-overlapping.

**Fix:** Human/AI — edit `sections[]` in `diagram.json`.

**How:** Separate levels of detail into separate views. Put the parent block in an
overview view and the named children in a detail view — never both in the same view.

---

### `break-overlaps-section` — ERROR

**Violated when:** A `break`-flagged section's address range overlaps a non-break
(real, named) section's range.

When a break extends into a real named section, the layout engine treats the
overlapping region as part of the break and silently drops the real section from
the rendered output — the section exists in `diagram.json` but its rectangle and
label never appear in the SVG.

The usual cause is an off-by-N slip when computing a large-address gap hole, so
the break extends past the address where the next real section begins:

```json
{ "id": "gap",  "address": "0x0000000001600000", "size": "0x1FFFFFFFFFFE0000", "name": "···", "flags": ["break"] },
{ "id": "next", "address": "0x2000000000000000", "size": "0x0000000100000000", "name": "NEXT" }
```

Here the break ends at `0x20000000015E0000`, which is past `NEXT`'s base, so
`NEXT` gets swallowed.

**Fix:** Human/AI — edit the break's `size` in `diagram.json` so it ends exactly
at the next real section's base:

```
break.size = next_section.address − break.address
```

The error message prints the exact correct size for the offending break.

---

### `uncovered-gap` — WARN

**Violated when:** Any address range within the view's extent `[Lo, Hi]` is not
covered by any section — break or non-break.

`Lo` is the lowest section start address; `Hi` is the highest section end address
(both derived from the sections in the view). Coverage is the union of all sections'
`[address, address+size)` intervals walked in address order. Any hole in that union
is reported as a separate WARN issue naming the sections on either side.

Two sections that touch exactly (`s1.end == s2.start`) are fully covered and do not
trigger this rule. Overlapping sections (already flagged by `section-overlap`) do not
produce additional gap issues here.

Example: `Flash` at `0x0800_0000` (128 KB) followed by `SRAM` at `0x2000_0000`
(64 KB) — the range `[0x0802_0000, 0x2000_0000)` has no section defined, so the
rule fires for that hole.

**Fix:** Human/AI — add break section(s) in `diagram.json` spanning each uncovered
range.

**How:** Add a break section whose `address` equals the hole start and whose `size`
equals the hole size reported in the warning message:

```json
{ "id": "gap0", "address": "0x08020000", "size": "0x17FE0000",
  "name": "···", "flags": ["break"] }
```

Multiple consecutive breaks are also valid — ensure each break's start address
equals `previous_break.address + previous_break.size` with no gaps between them.

---

### `panel-overlap` — ERROR

**Violated when:** Two panels' bounding rectangles physically intersect.

The auto-layout engine stacks views in each column with a fixed padding gap and
auto-expands the canvas vertically. With the floor-stack model computing exact
view heights before layout, each view's allocated slot equals its rendered height;
panels cannot overlap. If this rule fires, it is a tool bug.

**Fix:** Bug — report with your `diagram.json`. No user edit can prevent this.

---

### `title-overlap` — WARN

**Violated when:** Two panel titles overlap — either vertically or horizontally:

- **Vertical** — a panel's title intrudes into the body of the panel directly above
  it in the same column. Titles render 20 px above the panel top edge; the checker
  uses a 25 px clearance zone. The inter-panel padding (50 px) exceeds the clearance
  zone (25 px), so this should never fire for diagrams rendered by the current
  auto-layout engine — if it does, it is a layout bug.

- **Horizontal** — two panel titles at the same vertical level (e.g. adjacent columns
  in the top row) overlap in the inter-column gap. Title width is estimated from
  character count × font size. This is a user configuration issue.

**Fix (vertical):** Bug — report with your `diagram.json`.

**Fix (horizontal):** Human/AI — shorten the view `"title"` field in `diagram.json`.

---

### `label-overlap` — WARN

**Violated when:** Address labels extending from the right edge of a panel reach the
left edge of the adjacent panel in the next column.

The inter-column gap is computed from the actual label width and font size of each
source column (§8 of `../docs/auto-layout-algorithm.md`), so this rule should never fire for
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

For **section-ID specifiers** this is a layout-engine bug guard — sections are always
placed within their panel's pixel range by the layout engine and this case should
never fire. For **address-range form** (`["0xLO", "0xHI"]`) this is a user
configuration error: the explicit addresses extend beyond the view's actual address
range.

**Fix:** Human/AI — edit `links[]` in `diagram.json`.

**How:** Correct the address values in `from.sections` or `to.sections` so they
stay within the referenced view's address extent, or remove the explicit range to
span the full view.

---

### `link-address-range-mappable` — WARN

**Violated when:** A link's `from.sections` or `to.sections` uses the address-range
form `["0xA", "0xB"]` and the range resolves exactly to one or more defined
non-break sections in the referenced view. The address-range form is intended for
cases where the anchor range doesn't correspond to any named section (e.g.
virtual→physical remappings); using it when the range *does* match a section is
harder to read and silently drifts if addresses change later.

```json
"to": { "view": "detail-view", "sections": ["0x08000000", "0x08010000"] }
```

If `detail-view` has a section `code` at `[0x08000000, 0x08010000)`, this is
functionally identical to using the section ID.

**Fix:** Human/AI — edit `links[]` in `diagram.json`.

**How:** Replace the address-range form with the section ID(s) the range
resolves to. The warning message names them:

```json
"to": { "view": "detail-view", "sections": ["code"] }
```

---

### `link-redundant-sections` — WARN

**Violated when:** A link's `from.sections` or `to.sections` is equivalent to
the whole-view default — either an ID list whose combined address range covers
the view's full extent, or an address range spanning the whole view — *and*
omitting the field would produce the same band geometry.

```json
"to": { "view": "detail-view", "sections": ["code", "data"] }   // all sections of detail-view
"to": { "view": "detail-view", "sections": ["0x08000000", "0x08020000"] }   // whole view extent
```

**Fix:** Human/AI — edit `links[]` in `diagram.json`.

**How:** Omit the `sections` field entirely. The renderer treats an omitted
`from.sections` or `to.sections` as "span the whole view," producing the same
band geometry with less JSON.

```json
"to": { "view": "detail-view" }
```

**Not a redundancy (cross-address-space links):** When `from` and `to` live in
different address spaces, omitting `to.sections` makes the renderer fall back
to clamping `from_range` into the destination view — *not* the whole-view
default. An enumerated `to.sections` list that spans the destination view is
then load-bearing, and the check correctly declines to warn. Keep the field.

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

---

### `label-out-of-range` — WARN

**Violated when:** A label's `address` field falls outside the view's address range
`[start_address, end_address]`.

The renderer only draws a label when its address falls within a section's half-open
`[addr, addr+size)` interval or at exactly the view's end address (the end of the
last section). A label whose address lies outside `[Lo, Hi]` is silently not rendered
— it exists in `diagram.json` but produces no line or text in the SVG.

**Fix:** Human/AI — edit the label's `address` in `diagram.json`.

**How:** Set `address` to a value within the view's address range `[Lo, Hi]`. The
warning message shows the current address and the valid range.

---

### `link-address-range-order` — ERROR

**Violated when:** A link's `from.sections` or `to.sections` uses the address-range
form `["0xLO", "0xHI"]` but `LO >= HI` (inverted or collapsed range).

The renderer passes the range directly to the band-geometry code without checking
order, so an inverted range produces a crossed or collapsed band in the SVG.

**Fix:** Human/AI — edit `links[]` in `diagram.json`.

**How:** Swap the two values so the first element is the lower address and the second
is the higher address (`LO < HI` strictly):

```json
"sections": ["0x08000000", "0x08020000"]   // correct: lo < hi
```

---

### `link-self-referential` — WARN

**Violated when:** A link's `from.view` and `to.view` reference the same view.

A self-referential band is drawn from the right edge of the panel back to its left
edge, producing a degenerate shape that overlaps or wraps around the panel body. The
geometry is typically invisible or visually incorrect.

**Fix:** Human/AI — edit `links[]` in `diagram.json`.

**How:** Ensure `from.view` and `to.view` reference two different views. A link is
meaningful only when it connects distinct panels.
