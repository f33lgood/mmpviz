# Auto Layout Algorithm — Current Implementation

This document describes the auto layout algorithm as it is actually implemented.
It is authoritative for understanding and maintaining the code.

---

## Contents

1. [Entry Points and Activation](#1-entry-points-and-activation)
2. [Section Height Sizing](#2-section-height-sizing)
3. [Link Graph Construction](#3-link-graph-construction)
4. [Column Assignment](#4-column-assignment)
5. [View Ordering Within a Column](#5-view-ordering-within-a-column)
6. [View Height Estimation](#6-view-height-estimation)
7. [Column Bin-Packing and Overflow Handling](#7-column-bin-packing-and-overflow-handling)
8. [Column Width and Inter-Column Spacing](#8-column-width-and-inter-column-spacing)
9. [Canvas Sizing](#9-canvas-sizing)
10. [Link Band Endpoint Positioning](#10-link-band-endpoint-positioning)
11. [Remaining Work](#11-remaining-work)

---

## 1. Entry Points and Activation

Auto layout **always** runs.  The diagram-level `"size"` field and view-level
`"pos"` / `"size"` fields are deprecated; any occurrence triggers a warning and
is silently ignored.  The main orchestrator is `get_area_views()` in
`scripts/mmpviz.py`.

```
get_area_views()
    │
    ├─ build_link_graph_from_links()  # auto_layout.py — DAG from explicit links[]
    ├─ assign_columns()               # auto_layout.py — BFS depth → column index
    ├─ _estimate_area_height()        # mmpviz.py — quick height estimate per view
    ├─ _auto_layout()                 # mmpviz.py — bin-packing, assigns pos + size
    └─ AreaView(...)                  # area_view.py — section height algorithm per view
```

When `links` is absent or empty, all views get an empty adjacency list (all
column 0), and auto-layout stacks them vertically in a single column.

After `get_area_views()` returns, the caller uses `_auto_canvas_size()` to
size the SVG canvas to fit all placed views:

```python
document_size = _auto_canvas_size(area_views)
```

---

## 2. Section Height Sizing

**Location:** `AreaView._section_label_min_h()`, `AreaView._compute_per_section_heights()`,
`AreaView._process()` in `scripts/area_view.py`

Called during `AreaView._process()` for each sub-area.  First, a per-section
minimum-height dict is built; then heights are distributed in two phases.

### Per-section effective floor

`_process()` builds a per-section floor dict `{id(s): effective_floor_px}` for
all visible sections:

```
for each visible section s:
    user_global  = style.get('min_section_height', 0)
    section_min  = s.min_height  (from diagram.json, or None)
    label_min    = _section_label_min_h(s, font_size)
    effective_floor = max(user_global, section_min or 0, label_min)
    per_section_min_h[id(s)] = effective_floor
```

`_section_label_min_h(s, font_size)` detects whether the size label
(top-left, 12 px font) and the name label (horizontally centred, `font_size` px)
would overlap on the x-axis at the current section width (`size_x`):

```
size_label_right = 2 + len(format_size(s.size)) × 0.6 × 12
name_label_left  = size_x/2 − len(name_text) × 0.6 × font_size / 2

if size_label_right > name_label_left:
    return 30 + font_size      # inflate just enough to separate labels vertically
else:
    return 0.0                 # no conflict — keep proportional height
```

### Per-section effective ceiling

```
for each visible section s:
    global_max   = style.get('max_section_height', None)
    section_max  = s.max_height  (from diagram.json, or None)
    if section_max is not None:
        effective_ceiling = min(section_max, global_max) if global_max else section_max
    else:
        effective_ceiling = global_max  (scalar passed to algorithm)
```

### Phase 1 — Floor locking (min_h)

`_compute_per_section_heights(sections, available_px, min_h, max_h)` accepts
`min_h` as either a scalar (backward-compatible) or the per-section dict built
above.  `max_h` may similarly be a scalar or a per-section dict.

```
heights = proportional(section.size / total_bytes) * available_px

repeat up to N+1 times:
    lo = min_h[id(s)] if dict else float(min_h)
    new_locks = {s: lo for s in unlocked if heights[s] < lo}
    if not new_locks: break                    # converged
    if sum(locked) + sum(new_locks) >= available_px:
        return proportional(available_px)      # cannot honour all floors
    lock those sections; re-proportionalise unlocked remainder
```

**Exclusion:** hidden sections and break sections are skipped entirely;
size-0 sections are ignored.

### Phase 2 — Ceiling application (max_h)

After Phase 1 converges, any section exceeding its effective ceiling is capped
and its surplus is redistributed proportionally to floored (min_h-locked)
sections first, then to any remaining uncapped section.

**Constants (from theme / default.json defaults):**

| Theme key              | default.json | Meaning                                          |
|------------------------|--------------|--------------------------------------------------|
| `min_section_height`   | 20 px         | Global section height floor (all sections)      |
| `max_section_height`   | 300 px        | Global section height ceiling (all sections)    |
| `break_height`         | 20 px         | Fixed height for break sections                 |

**Per-section overrides (diagram.json):**

| Section field   | Effective value                                       |
|-----------------|-------------------------------------------------------|
| `min_height`    | `max(min_height, min_section_height)` — higher wins  |
| `max_height`    | `min(max_height, max_section_height)` — lower wins   |

Break sections use a separate code path (`break_height` fixed height) and do
**not** participate in `_compute_per_section_heights`.

The label-conflict floor (`30 + font_size` px) is derived automatically from
the section geometry — it is not a user-visible theme property.

### Section geometry assignment

After `_process()` runs, the computed heights live in `section.size_y_override`
and `section.pos_y_in_subarea`.  Both the renderer and the checker need to
resolve these into the canonical `size_x / size_y / pos_x / pos_y` fields that
all downstream code reads.  This step is centralised in:

```python
AreaView.apply_section_geometry(section)
    # sets section.size_x, size_y, pos_x, pos_y
    # uses size_y_override / pos_y_in_subarea when set;
    # falls back to proportional mapping otherwise
```

`scripts/renderer.py` (`_make_section`) and `scripts/check.py`
(`_populate_section_heights`) both call this method, ensuring they share one
code path and cannot drift apart.

---

## 3. Link Graph Construction

**Location:** `build_link_graph_from_links()` in `scripts/auto_layout.py`

The DAG is built directly from the diagram's `links[]` array.
Each `{"from": {"view": A}, "to": {"view": B}}` entry adds edge A → B:

```
for each link entry:
    add edge entry.from_view → entry.to_view   (deduplicated)
```

Returns an adjacency list `{source_id: [target_id, ...]}` where every view ID
appears as a key.  Duplicate edges are suppressed.

When `links` is absent or empty, every view maps to an empty adjacency list
(all column 0 — stacked in a single column).

---

## 4. Column Assignment

**Location:** `assign_columns()` in `scripts/auto_layout.py`

BFS with max-depth propagation (Kahn's algorithm variant):

```
column[A] = 0   for all A with in-degree 0   (roots)
queue = deque(roots)

while queue:
    src = queue.popleft()
    for tgt in children[src]:
        column[tgt] = max(column[tgt], column[src] + 1)
        in_degree[tgt] -= 1
        if in_degree[tgt] == 0:
            queue.append(tgt)
```

Taking `max` instead of first-assignment handles diamonds: if B is reachable
from two paths of different depths, it is placed at the deeper column.
Disconnected views default to column 0.

---

## 5. View Ordering Within a Column

**Location:** `order_within_column()` in `scripts/auto_layout.py`;
called from `get_area_views()` in `scripts/mmpviz.py`

After `_auto_layout()` assigns positions, views within each visual bin (same
x-position = same bin) are reordered to minimise link-band crossings, then
y-positions within the bin are recomputed to match the new order.  Bin
membership never changes — only the order of views already sharing a bin.

```
for each target view B (column C+1):
    for each source view A that links to B:
        mid = pixel midpoint of the section in A that contains B's range
        source_midpoints[B].append(A.pos_y + mid)

sort column C+1 views by mean(source_midpoints[B])   ascending → top to bottom
```

**Within-bin y-reassignment** (after sort, same PADDING/TITLE_SPACE constants):

```python
bins_by_x = group area_configurations by cfg['pos'][0]
for bin_cfgs in bins_by_x.values():
    if len(bin_cfgs) <= 1: continue
    bin_cfgs.sort(key=rank_from_col_order)
    y = TITLE_SPACE
    for cfg in bin_cfgs:
        cfg['pos'][1] = y
        y += cfg['size'][1] + PADDING
```

**Fallback:** views whose midpoint cannot be computed — because their link spans
multiple source sections or has fan-in from multiple sources — receive
`key = inf` and sort stably to the end of the bin, preserving diagram.json
order for those views.

---

## 6. View Height Estimation

**Location:** `_estimate_area_height()` in `scripts/mmpviz.py`

A lightweight estimate used by `_auto_layout()` for bin-packing and initial
size assignment.  Does not run the full section-height algorithm.

```python
for each visible section s:
    floor = max(global_min_h, s.min_height or 0)
    visible_floor_sum += floor

estimated = visible_floor_sum
          + n_breaks  * (break_height + 4)
          + 20                          # top/bottom padding
return max(200.0, estimated)
```

Per-section label-conflict inflation (§2) is applied during actual rendering in
`AreaView._process()` and is not included in the estimate — any resulting
height increase is absorbed by canvas auto-expansion (§9).

---

## 7. Column Bin-Packing and Overflow Handling

**Location:** `_auto_layout()` in `scripts/mmpviz.py`

### 7.1 Grouping by DAG column

```python
col_cfgs = {dag_col: [area_configs in that column]}
```

### 7.2 Greedy bin-packing per DAG column (spill-first)

`DEFAULT_H = 800 px` is used as the initial bin-packing target height.

```
base_available_h = DEFAULT_H - TITLE_SPACE - BOTTOM_PAD  # 710 px

for each view in DAG column:
    trial = current_bin + [view]
    if stack_height(trial) ≤ available_h  OR  current_bin is empty:
        append view to current_bin
    else:
        if len(current_bin) ≥ 2:
            # Spill: commit bin, start new one
            final_cols.append(current_bin)
            current_bin = [view]
        else:
            # 1-view bin: accept overflow, canvas will expand
            current_bin.append(view)
commit current_bin
```

**Key:** views are never scaled down.  Each keeps its full estimated height so
all sections can reach their effective minimum.  Canvas expansion (§9) handles
the extra height.

### 7.3 Position assignment

```python
for col_idx, bin_cfgs in enumerate(final_cols):
    x = PADDING + col_idx * (col_width + INTER_COL_GAP)
    y = TITLE_SPACE
    for cfg in bin_cfgs:
        cfg['pos']  = [x, y]
        cfg['size'] = [col_width, estimated_height]
        y += estimated_height + PADDING
```

**Layout constants:**

| Constant              | Value   | Purpose                                           |
|-----------------------|---------|---------------------------------------------------|
| `PADDING`             | 50 px   | Left canvas margin; gap between stacked views     |
| `TITLE_SPACE`         | 60 px   | Vertical space above views (titles)               |
| `BOTTOM_PAD`          | 30 px   | Margin below last view                            |
| `INTER_COL_GAP`       | 120 px  | Gap between column right edge and next left       |
| `MAX_COL_WIDTH`       | 230 px  | Maximum box width (readability cap)               |
| `DEFAULT_H`           | 800 px  | Default bin-packing height target                 |
| Title render offset   | −20 px  | Title text y-position relative to panel `pos_y`  |
| `_TITLE_CLEARANCE_PX` | 25 px   | Vertical clearance zone above each panel checked by `check.py` for `title-overlap`; derived from title render offset + cap-height margin |

---

## 8. Column Width and Inter-Column Spacing

`col_width` is always `MAX_COL_WIDTH` (230 px). The inter-column gap is computed
per-column from the actual address width and font size of the source column:

```python
gap = _ADDR_LABEL_H_OFFSET                        # 10 px: offset from panel right edge
    + addr_chars * _HELVETICA_W_RATIO * font_size  # label width
    + 38                                            # breathing room (link band + margin)
```

**Address label geometry constants** (defined in `mmpviz.py`, mirrored in `check.py`):

| Constant               | Value | Purpose                                               |
|------------------------|-------|-------------------------------------------------------|
| `_ADDR_LABEL_H_OFFSET` | 10 px | Horizontal offset from panel right edge to label start |
| `_ADDR_CHARS_32`       | 10    | `len("0x00000000")` — 8 hex digits                   |
| `_ADDR_CHARS_64`       | 18    | `len("0x0000000000000000")` — 16 hex digits           |
| `_ADDR_64BIT_THRESHOLD`| `0xFFFF_FFFF` | Start addresses above this need 64-bit format |
| `_HELVETICA_W_RATIO`   | 0.6   | Estimated character width / font-size for Helvetica   |

A column is "64-bit" when ANY section's **start address** exceeds `_ADDR_64BIT_THRESHOLD`.
All sections in that view then use the 16-digit label format for visual consistency.

**Example gaps at the default `font_size: 13`:**
- 32-bit column: `10 + 10 × 0.6 × 13 + 38 = 126 px`
- 64-bit column: `10 + 18 × 0.6 × 13 + 38 = 188 px`

Column x-positions are cumulative:

```python
x_starts = [PADDING]
for bin_idx in range(len(final_cols) - 1):
    x_starts.append(x_starts[-1] + col_width + _col_gap(final_cols[bin_idx]))
```

The rightmost-column canvas margin (`right_pad`) uses the same label-width formula
with 28 px breathing room instead of 38 (no link band beyond the last column).

---

## 9. Canvas Sizing and Viewport Origin

**Location:** `_auto_canvas_size()` in `scripts/mmpviz.py`;
`SVGBuilder.__init__()` in `scripts/svg_builder.py`

After `get_area_views()` returns, the canvas is sized to contain all placed
views plus label extents without clipping:

```python
max_right  = max(av.pos_x + av.size_x for av in area_views)
max_bottom = max(av.pos_y + av.size_y for av in area_views)

# Scan user labels for actual left/right extents
for av in area_views:
    for lbl in av.labels.labels:
        tw = len(lbl.text) * 0.6 * font_size
        if lbl.side == 'left':
            min_x = min(min_x, av.pos_x - lbl.length - 3 - tw)
        else:
            right_pad = max(right_pad, av.pos_x + av.size_x + lbl.length + 3 + tw - max_right + 10)

# Scan view titles: 24 px, center-anchored at (av.pos_x + av.size_x/2, av.pos_y - 20)
for av in area_views:
    title_half = len(av.title) * 0.6 * 24 / 2
    title_cx = av.pos_x + av.size_x / 2
    min_x = min(min_x, title_cx - title_half)
    right_pad = max(right_pad, ceil(title_cx + title_half - max_right) + 10)

left_overflow = (ceil(-min_x) + 10) if min_x < 0 else 0
W = int(max_right + right_pad) + left_overflow
H = int(max_bottom + bottom_pad)
return (W, H, left_overflow, 0)
```

Returns a 4-tuple `(W, H, left_overflow, top_overflow)`.  The caller uses
`left_overflow` to set `viewBox="{-left_overflow} 0 {W} {H}"` so that content
at negative x-coordinates (e.g. long titles or left-side labels) becomes visible
without moving any panel or section coordinates.

**Right padding (default 110 px)** accommodates address labels:
`10 px offset + 10 chars × 0.6 × 12 pt = 82 px`, plus 18 px breathing room.
User labels with large `length` or long text, and view titles wider than their
column, automatically expand `right_pad` or `left_overflow` as needed.

**Left overflow** is non-zero when a left-side label or view title extends past
x = 0.  The SVG `viewBox` is shifted accordingly; the background rect is drawn
at `(−left_overflow, 0, W, H)` to cover the full visible area.

The canvas is always derived from content — the diagram-level `"size"` field
is deprecated and ignored.

---

## 10. Link Band Endpoint Positioning

**Location:** `AreaView.address_to_py_actual()` in `scripts/area_view.py`;
used by `Renderer._get_points_for_address()` in `scripts/renderer.py`.

When sections have non-proportional heights (due to `min_h` / `max_h`
overrides), the simple proportional mapping `to_pixels_relative()` would
misplace link band endpoints.  `address_to_py_actual()` corrects this:

```python
for s in sections:
    if s.size_y_override is None or s.pos_y_in_subarea is None: continue
    if s.address ≤ address ≤ s.address + s.size:
        frac = (s.address + s.size - address) / s.size  # 0=top, 1=bottom
        return s.pos_y_in_subarea + frac * s.size_y_override
return to_pixels_relative(address)   # fallback
```

---

## 11. Remaining Work

Items from the original proposal judged worth implementing. Fully implemented
items, dropped decisions, and superseded approaches have been removed.

| Topic | Proposal calls for | Current state | Notes |
|-------|--------------------|---------------|-------|
| **View ordering: crossing minimisation** | Sort column C+1 by source midpoint of linking section (§6.3) | Implemented and wired: `order_within_column()` called in `get_area_views()`; within-bin y-positions reassigned after sort | Section-span / fan-in links fall back to diagram.json order |
| **View height computation** | Run full Phase 1 algorithm per view for exact height before bin-packing (§5.1) | `_estimate_area_height()`: sums per-section `max(global_min_h, section.min_height)` + break budget; returns `max(200.0, estimated)` | Estimate still under-counts label-conflict inflation; canvas over-expansion absorbs the difference |
| **Minimum view height** | `max(H_view, 3 × min_h)` (§5.2) | `max(200.0, estimated)` — hardcoded 200 px floor | Replace with principled formula |
| **Box width from label length** | `max(120, longest_name × font × 0.55)` (§8.1) | Fixed `MAX_COL_WIDTH = 230 px` | Long section names clip silently; compute during height pre-pass |
| **Address clearance + inter-column gap** | Per-column: `max_box_width[C] + addr_clearance[C] + LINK_BAND_MIN` (§8.2–8.4) | Implemented: `_col_gap()` in `_auto_layout()` computes gap per column from actual address width and font size | 32-bit columns: 126 px at default 13 pt; 64-bit columns: 188 px |

---

*End of document.*
