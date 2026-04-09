# Auto Layout Algorithm Proposal for mmpviz

This document describes a proposed fully-automatic layout algorithm for mmpviz.
The goal is that a user who provides only address-map data (sections, areas, and
link relationships) gets a correctly sized, readable SVG with no manual `pos`,
`size`, or `min_section_height` tuning required.

---

## Contents

1. [Current Limitations](#1-current-limitations)
2. [Section Height Sizing — Revised Algorithm](#2-section-height-sizing--revised-algorithm)
3. [Link Graph Construction](#3-link-graph-construction)
4. [Column Assignment](#4-column-assignment)
5. [Area Height Computation](#5-area-height-computation)
6. [Area Ordering Within a Column](#6-area-ordering-within-a-column)
7. [Area Vertical Placement](#7-area-vertical-placement)
8. [Column Width and Inter-Column Spacing](#8-column-width-and-inter-column-spacing)
9. [Canvas Sizing for Output Formats](#9-canvas-sizing-for-output-formats)
10. [Readability Constraints](#10-readability-constraints)
11. [Implementation Phases](#11-implementation-phases)

---

## 1. Current Limitations

### 1.1 Section height sizing operates at group level, not section level

`_compute_clamped_heights` works on *groups* (contiguous runs of sections between
break sections). `min_required(g)` scales the minimum by the proportion of the
smallest visible section inside the group:

```
min_required(g) = min_section_height / (min_section.size / group_range)
```

When a group contains sections with extreme size ratios — e.g., Flash Memory
(128 KB) in the same group as Aliased (128 MB) — the scaled minimum becomes
`40 / (128 KB / 128 MB) = 40,960 px`, which immediately exceeds `available_px`
and collapses to the proportional fallback. The `min_section_height` parameter
becomes ineffective.

The stm32f103 example worked around this by filtering Flash Memory out of the
overview with `section_size: [1048576, null]`. That workaround is manual and
brittle; a general solution should not need it.

### 1.2 Break sections have special fixed heights

Break sections always get exactly `break_size` pixels regardless of the area's
geometry. This hardcoded path bypasses the clamped-heights algorithm, creating
inconsistency: a regular section that is too small gets auto-hidden, but a break
section at the same pixel height does not.

### 1.3 `pos`, `size`, and `min_section_height` require manual tuning

Every area in every chip example has explicit `pos`, `size`, and often a
per-area `min_section_height` in theme.json. Adding a new chip or changing an
existing chip's memory map requires recomputing all of these by hand.

---

## 2. Section Height Sizing — Revised Algorithm

### 2.1 Design goals

- Operate at the **section level**, not the group level.
- Treat break sections identically to regular sections for height purposes.
- When an area's minimum content does not fit in the assigned height, **expand
  the area** (auto-layout mode) rather than silently dropping labels.
- Converge in O(N) iterations where N = number of sections.

### 2.2 Label-visibility minimum height

From the geometry constants in `section.py`:

```
SIZE_LABEL_TOP    = 2 px   (top offset of size label)
SIZE_LABEL_HEIGHT = 12 px  (fixed small font)

min_h_label(font_size) = font_size + SIZE_LABEL_TOP + SIZE_LABEL_HEIGHT
                       = font_size + 14
```

For both name **and** size labels to be visible without overlap:

```
name_label_top(h, font) = h/2 - font/2            # vertical centre of section
threshold: name_label_top >= SIZE_LABEL_TOP + SIZE_LABEL_HEIGHT = 14
=> h/2 - font/2 >= 14
=> h >= font + 28

min_h(font_size) = font_size + 28
```

For the default `font_size = 12`: `min_h = 40 px`.

This value should be derived automatically from the resolved `font_size` rather
than requiring explicit `min_section_height` configuration.

### 2.3 Per-section iterative algorithm

**Inputs:**
- `sections`: ordered list of Section objects (address-sorted, includes breaks)
- `H`: total available height for this area in pixels
- `font_size`: resolved font size

**Algorithm:**

```
min_h = font_size + 28
total_range = sum(s.size for s in sections)

locked = {}           # {section: assigned_height_px}
unlocked = list(sections)

loop:
    locked_px    = sum(locked.values())
    locked_bytes = sum(s.size for s in locked)
    free_px      = H - locked_px
    free_bytes   = total_range - locked_bytes

    if free_bytes == 0: break          # all sections locked

    # Proportional heights for unlocked sections
    new_locks = {}
    for s in unlocked:
        h = free_px * (s.size / free_bytes)
        if h < min_h:
            new_locks[s] = min_h

    if not new_locks: break            # convergence

    # Overflow check: locking these sections would exceed H
    if locked_px + sum(new_locks.values()) > H:
        # In fixed-height mode: proportional fallback (labels may auto-hide)
        # In auto-height mode:  expand H = sum(min_h for all sections)
        break

    locked.update(new_locks)
    unlocked = [s for s in unlocked if s not in locked]

# Final heights
for s in unlocked:
    heights[s] = free_px * (s.size / free_bytes)
for s, h in locked.items():
    heights[s] = h
```

**Auto-height expansion (auto-layout mode only):**
If the overflow check triggers, compute:

```
H_min = sum(min_h for all sections)
```

Set `H = H_min` and re-run the algorithm. All sections are then at exactly
`min_h`, with the surplus redistributed proportionally in a second pass:

```
for s in sections:
    heights[s] = min_h + (H_total - H_min) * (s.size / total_range)
```

This guarantees every section is at least `min_h` while proportionally
distributing any extra height to larger sections.

### 2.4 Why break sections need no special treatment

Break sections represent large collapsed address ranges (e.g., a 500 MB
reserved block). In proportional sizing they would naturally be very tall.
However:

- If the address range of a break is large, proportional sizing gives it
  appropriate height, and the "≈" visual is drawn inside it at whatever height
  it receives.
- If the address range is small relative to other sections, the iterative
  algorithm may lock the break at `min_h`, just like any other short section.
- The `break_size` theme property can serve as an explicit override: if
  `s.size_bytes < break_threshold` and `break_size` is configured, clamp the
  break section to `break_size` (treat it as a floor). This optional cap prevents
  astronomically-large reserved regions from dominating height.

The key shift: break sections participate in the same iterative algorithm.
Their floor is `min_h` (like all sections), not a hardcoded constant.

---

## 3. Link Graph Construction

### 3.1 What constitutes a link

A link connects a **source area** to a **target area** via a **link section**:

- The *link section* is a section defined globally (in `diagram.sections`) with
  a named `id` (e.g., `"Peripherals"`, `"Flash Memory"`).
- The *source area* is the area that renders the link section at its natural
  address position (the section is not hidden, not filtered out, and its address
  falls within the area's range).
- The *target area* is the area whose `range` is entirely contained within the
  link section's address range `[address, address + size)`.

### 3.2 Algorithm

```
for each area A:
    for each visible section L in A:
        for each area B (B ≠ A):
            if B.range_min >= L.address and B.range_max <= L.address + L.size:
                add edge A → B, labeled with section L
```

This recovers the DAG from the existing data without requiring any new
configuration keys. The current `diagram.links.sections` list acts only as a
rendering hint (which sections get link band polygons drawn); the topology
is already implicit.

### 3.3 Multiple parents

A target area may have multiple source areas (rare but valid). In column
assignment (§4), use the first-encountered source (BFS order). For placement
(§7), use the primary source (most link bands) as the reference.

---

## 4. Column Assignment

### 4.1 Topological depth (BFS)

```
roots = [A for A in areas if A has no incoming edges]
queue = deque(roots)
column[A] = 0 for A in roots

while queue:
    A = queue.popleft()
    for B reachable from A:
        if column[B] not yet assigned:
            column[B] = column[A] + 1
            queue.append(B)
```

If a node would get assigned to two different columns (via different paths),
take the maximum depth (farthest from root). This ensures that a chain
root → A → B places B in column 2, not column 1.

### 4.2 Column count control

The algorithm produces one column per DAG level. To cap at N columns
(recommended N ≤ 4 for readability):

- If the DAG has depth > N−1, merge the deepest levels into column N−1.
- Arrange the merged areas vertically within the shared column with extra
  inter-area spacing.

A practical default: no hard cap, but flag a warning when column count > 3.

### 4.3 Root detection heuristics

When the diagram has no explicit `links` configuration:
- The area with the widest address range is the root.
- If multiple areas tie, prefer the one with the most visible sections.

### 4.4 Column example: stm32f103

```
Link graph:
  overview → m3-periph-view        (via M3 Cortex Internal Peripherals)
  overview → sysmem-zoom-view      (via System Memory)
  overview → flash-zoom-view       (via Flash Memory)
  overview → apb-view              (via Peripherals)

BFS:
  overview:                          column 0
  m3-periph, sysmem, flash, apb:    column 1  (direct successors)

Result: 2 columns (all detail areas in column 1)
```

The current layout uses 3 columns by manually placing `apb-view` in column 2.
The auto-layout algorithm would pack all detail areas into column 1 and arrange
them vertically — or split into column 2 if the combined height exceeds the
canvas. See §7.3 for overflow handling.

---

## 5. Area Height Computation

### 5.1 Process per area

For each area `A`:
1. Collect all visible sections (not flagged `hidden`, within A's address range,
   passing any `section_size` filter).
2. Apply the per-section iterative algorithm from §2.3 with auto-height
   expansion enabled.
3. `H_area[A]` = sum of all section heights from the algorithm.

### 5.2 Minimum area height

Even if all sections converge to their minimum, the area needs room for the
title row above it:

```
H_area_effective[A] = max(H_area[A], 3 × min_h)
```

### 5.3 Maximum section height (readability cap)

When a single section dominates (e.g., a 4 GB region in an overview spanning
0–4 GB), proportional sizing would make it fill hundreds of pixels.

Apply `max_section_height` (default: 200 px) as a per-section ceiling. Surplus
height freed by capping large sections is redistributed to floored (minimum)
sections, the same way the current algorithm handles this.

---

## 6. Area Ordering Within a Column

### 6.1 Goal

Areas in the same column should be ordered so that link bands from the
previous column do not cross each other. Crossed bands are visually
confusing and hard to trace.

### 6.2 Non-crossing condition

Two link bands from source areas in column C to targets in column C+1 do
not cross if and only if their source-midpoints and target-midpoints are
**monotonically ordered** — i.e., if source band A is above source band B,
then target A is placed above target B.

### 6.3 Algorithm

For each area `B` in column `C+1` with a link from column `C` via section `L`:

```
source_midpoint[B] = pos_y[source_of_B] + midpoint_px_of_L_in_source
```

Sort areas in column `C+1` by `source_midpoint` (ascending → top to bottom).

When an area has multiple incoming links, use the mean of the source midpoints.

### 6.4 Example: stm32f103

Source midpoints in `overview` (column 0), ordered top-to-bottom by pixel
position of the linked section:

| Target area | Linked section | Approximate pos in overview |
|-------------|---------------|-----------------------------|
| m3-periph-view | M3 Cortex (0xE0000000–0xE1000000) | near top (~75 px) |
| apb-view | Peripherals (0x40000000) | middle (~810 px) |
| sysmem-zoom-view | System Memory (0x1FFFF000) | bottom area (~1480 px) |
| flash-zoom-view | Flash Memory (0x08000000) | bottom area (~1505 px) |

Sorted column 1 order (top to bottom):
1. m3-periph-view
2. apb-view
3. sysmem-zoom-view
4. flash-zoom-view

This is the crossing-free order. The combined area heights determine whether
they all fit in one column or need to be split across two.

---

## 7. Area Vertical Placement

### 7.1 Initial placement: top-aligned

Within each column, areas are placed from top to bottom:

```
TITLE_H   = 70 px   (space above each area for its title)
TOP_PAD   = 50 px   (top canvas margin)
INTER_GAP = 30 px   (gap between areas in the same column)

y = TOP_PAD
for area in column_order:
    pos_y[area] = y + TITLE_H
    y += TITLE_H + H_area[area] + INTER_GAP
```

All column 0 areas (usually one) start at `y = TOP_PAD`.

### 7.2 Column-top alignment

The topmost area in each column should start at the same y-coordinate so
that titles form a horizontal row. This is achieved by using the same `TOP_PAD`
for all columns regardless of where links connect.

```
for each column C:
    first_area = column_order[C][0]
    pos_y[first_area] = TOP_PAD + TITLE_H
```

### 7.3 Overflow handling (column too tall)

If the total height of all areas in a column exceeds `canvas_H - TOP_PAD - BOTTOM_PAD`:

**Strategy A — split into two sub-columns:**
Split the areas at the median and place the second half in a new column
`C + 0.5` (inserted between the current column and its successor). Adjust
column spacing accordingly.

**Strategy B — scale section heights down:**
Scale all `H_area` values by `fit_factor = available_H / total_area_H`.
Re-run the section height algorithm with the new `H` for each area. Some
sections may fall below `min_h`; their labels auto-hide via `is_name_hidden()`.

Prefer Strategy A when the column has 3+ areas; Strategy B when only 1–2
areas and the shortfall is < 20%.

### 7.4 Vertical nudge to minimise link band length

After initial top-aligned placement, optionally shift each non-root area
vertically to better align with its link source:

```
for area B in column C+1 (not first in column):
    link_band_midpoint = midpoint of link section in source area
    ideal_y = link_band_midpoint - H_area[B] / 2
    ideal_y = clamp(ideal_y, prev_area_bottom + INTER_GAP, column_bottom - H_area[B])
    pos_y[B] = ideal_y
```

Apply this greedily top-to-bottom so that earlier areas constrain later ones.

---

## 8. Column Width and Inter-Column Spacing

### 8.1 Area box width

The box width of an area must accommodate:
- Section name labels (centred inside the box)
- Size labels (`x=2, y=2` top-left corner)

Heuristic: `box_width = max(120, longest_section_name_chars × font_size × 0.55)`

A safe default for most chips: `box_width = 180–240 px`.

For very wide labels (e.g., "M3 Cortex Internal Peripherals" = 30 chars at
font 12 = ~198 px), use `box_width = label_width + 20` (10 px padding each side).

### 8.2 Address label clearance to the right of the box

Address labels are rendered to the right of the area box with a 10 px offset.

```
addr_chars = 10   (32-bit: "0xABCD1234")
addr_chars = 18   (64-bit: "0xABCDEF0012345678")
addr_width = addr_chars × font_size × HELVETICA_W_RATIO + label_offset
           = addr_chars × 0.6 × font_size + 10
```

At `font_size = 12`:
- 32-bit: `10 × 0.6 × 12 + 10 = 82 px`
- 64-bit: `18 × 0.6 × 12 + 10 = 140 px`

The 64-bit extra clearance already has a check rule (`addr-64bit-column-width`).
The auto-layout algorithm must ensure the gap between box right edge and the
next column's left edge is at least `addr_width`.

### 8.3 Inter-column gap (for link bands)

The link band polygon spans from the right edge of the source area to the
left edge of the target area. Minimum gap:

```
LINK_BAND_MIN = addr_width + 20   (address labels + breathing room)
```

When multiple link bands overlap in the same horizontal span, no additional
gap is needed (they share the space, relying on opacity for legibility).

### 8.4 Column x-positions

```
LEFT_PAD = 60 px

x = LEFT_PAD
for column C in order:
    col_x[C] = x
    max_box_width = max(box_width[A] for A in column C)
    x += max_box_width + addr_label_clearance[C] + LINK_BAND_MIN
```

`addr_label_clearance[C]` = address clearance for column C's areas (based on
whether any area in C contains 64-bit addresses).

---

## 9. Canvas Sizing for Output Formats

### 9.1 Compute natural content size

After completing §4–§8:

```
content_W = rightmost column's right edge + LEFT_PAD
content_H = max(total column heights) + TOP_PAD + BOTTOM_PAD
```

### 9.2 Target format scaling

| Format | Aspect | Recommended base size |
|--------|--------|-----------------------|
| A4 portrait | 1 : 1.414 | 794 × 1123 (96 DPI) |
| A4 landscape | 1.414 : 1 | 1123 × 794 |
| 16:9 slide | 16 : 9 | 1280 × 720 |
| 4:3 slide | 4 : 3 | 1024 × 768 |

Scale factor to fit target:

```
scale = min(target_W / content_W, target_H / content_H)
```

The SVG canvas size is `(target_W, target_H)`. All `pos` and `size` values are
multiplied by `scale`.

If the user does not specify a target format, use `content_W × content_H` as
the canvas size (no scaling, natural pixel layout).

### 9.3 Do not scale font size

`font_size` is NOT multiplied by `scale`. Instead:

```
scaled_font_size = font_size / scale   (what the font looks like after SVG scaling)
```

If `scaled_font_size < MIN_READABLE_FONT` (see §10), warn the user and suggest
using a larger base canvas or reducing the number of areas.

---

## 10. Readability Constraints

### 10.1 Minimum readable font size

| Context | Min font_size (px in SVG coords) |
|---------|----------------------------------|
| Printed paper, read at ~40 cm | 10 px (≈ 8 pt at 96 DPI) |
| Screen, normal viewing | 12 px (≈ 9 pt) |
| Slide, read from distance | 18 px (≈ 14 pt) |

The default `font_size = 12` is suitable for screen and print. For slides,
set `font_size = 18` in theme.json.

### 10.2 Area box width for readability

If after §8 any area's `box_width` would be narrower than the longest section
name requires, either:
- Increase `box_width` and recompute column widths and canvas width, or
- Accept truncation (the renderer clips text to the box boundary).

Recommended: use §8.1 to compute box widths from actual section names, so this
never occurs.

### 10.3 Address label overlapping the next column

The check rule `label-overlap` already enforces that address labels do not
visually overlap the adjacent area. The auto-layout algorithm must guarantee
the gap between columns satisfies this rule by construction (§8.3).

---

## 11. Implementation Phases

The full algorithm above can be implemented incrementally. Each phase produces
a testable improvement.

### Phase 1 — Per-section iterative height algorithm (replaces current group-level algorithm)

**Changes:**
- Rewrite `_compute_clamped_heights` to operate at the section level (§2.3).
- Remove the fixed-height path for break sections; breaks participate in the
  same algorithm.
- Auto-compute `min_h` from `font_size` when `min_section_height` is not
  explicitly set in theme.

**Test:** stm32f103 overview-view with no `section_size` filter and no explicit
`min_section_height` should still render M3 Cortex Internal Peripherals with
name and size labels visible.

### Phase 2 — Auto area height (`pos` and `size` computed from content)

**Changes:**
- Add auto-height mode: when `size` is absent from an area config, compute it
  via the Phase 1 algorithm.
- `_auto_layout` distributes columns using content heights (not equal divisions).

**Test:** Remove `pos`/`size` from all areas in a chip example; verify the
output is visually equivalent to the current golden SVG.

### Phase 3 — Link graph construction and column assignment

**Changes:**
- Implement `_build_link_graph(areas, sections)` → DAG.
- Implement `_assign_columns(dag)` → `{area_id: column}`.
- Pass column assignments to `_auto_layout`.

**Test:** stm32f103 with no `pos`/`size` in diagram.json should produce a
layout matching the current golden SVG structure.

### Phase 4 — Area ordering (crossing minimisation) and vertical placement

**Changes:**
- Implement §6.3 (sort by source midpoint).
- Implement §7.2 (top alignment) and §7.4 (vertical nudge).

**Test:** Verify no link band crossings for stm32f103 and caliptra examples.

### Phase 5 — Column width from content and canvas auto-sizing

**Changes:**
- Implement §8 (box width, address clearance, inter-column gap).
- Implement §9 (canvas sizing for output formats).

**Test:** Render a 64-bit chip example; verify `check.py` reports no
`label-overlap` or `addr-64bit-column-width` violations.

---

*End of proposal.*
