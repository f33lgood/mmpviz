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
7. [Layout Algorithms](#7-layout-algorithms)
   - [7.1 Algo-1: One Visual Column per DAG Level](#71-algo-1-one-visual-column-per-dag-level)
   - [7.2 Algo-2: Height-Rebalancing (default)](#72-algo-2-height-rebalancing-default)
   - [7.3 Algo-3: Routing Lanes for Non-Adjacent Links](#73-algo-3-routing-lanes-for-non-adjacent-links)
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
    ├─ sort_by_dag_tree()             # auto_layout.py — DAG-tree ordering pre-sort
    ├─ rebalance_columns()            # auto_layout.py — algo-2/3: height rebalancing
    ├─ _auto_layout()                 # mmpviz.py — DAG column placement, assigns pos + size
    ├─ order_within_column()          # auto_layout.py — crossing minimisation post-sort
    ├─ AreaView(...)                  # area_view.py — section height algorithm per view
    └─ plan_routing_lanes()           # auto_layout.py — algo-3 only: routing lane planning
```

`get_area_views()` returns a 2-tuple `(area_views, routing_lanes)`.  `routing_lanes`
is an empty dict for algo1/algo2; for algo3 it maps each link entry index to the list
of lane dicts computed by `plan_routing_lanes()`.

The layout algorithm is selected with the `--layout` CLI flag:

| Flag | Algorithm | Default |
|------|-----------|---------|
| `--layout algo1` | One visual column per DAG level | |
| `--layout algo2` | Height-rebalancing with outlier extraction | |
| `--layout algo3` | Algo-2 + routing lanes for non-adjacent links | ✓ |

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

Two separate ordering passes run in `get_area_views()` — one before `_auto_layout()`
and one after.

### 5.1 DAG-Tree Pre-Sort (`sort_by_dag_tree`)

**Location:** `sort_by_dag_tree()` in `scripts/auto_layout.py`;
called from `get_area_views()` before `_auto_layout()`.

Reorders views within each DAG column so the layout expands like a tree from
left to right.

**Column 0 (roots):** original `diagram.json` order is preserved exactly.

**Column N+1:** each view is sorted by a two-part key:

```
key(V) = (min_parent_position, -mean_source_section_address)

where:
    min_parent_position = min position of V's parents in column N's ordered list
                          (float('inf') if no known parent → sorts last)
    mean_source_section_address = mean of (s.address + s.size/2)
                          for every source section s in every link that targets V
```

The result: children of an earlier-positioned parent appear before children
of a later-positioned parent; among siblings sharing the same parent, the view
linked from the **highest** source address appears first (top of column in the SVG,
consistent with the convention that higher addresses render near the top of a panel).

```python
for col in sorted(by_col):
    if col == 0:
        ordered = JSON order
    else:
        ordered = sort by (min_parent_position, -mean_src_addr)
    record col_position[vid] for next column
    result.extend(ordered)
```

Because views in column N+1 are processed in this order by `_auto_layout()`,
overflow boundaries (if any were applied) would fall between sibling groups
rather than splitting them arbitrarily.

### 5.2 Crossing Minimisation Post-Sort (`order_within_column`)

**Location:** `order_within_column()` in `scripts/auto_layout.py`;
called from `get_area_views()` after `_auto_layout()`.

After positions are assigned, views within each column (same x-position) are
reordered to minimise link-band crossings, then y-positions are recomputed to
match the new order.

Section midpoints are looked up by section ID from each link entry's
`from_sections` field (not by address containment), which correctly handles
multi-section links:

```
for each link entry (from_view A → to_view B, from_sections = [s1, s2, ...]):
    find sections matching from_sections in A's rendered AreaView
    compute pixel span from lowest to highest address across matched sections
    mid = pixel midpoint of that span, in absolute y coordinates
    source_midpoints[B].append(mid)

sort column views by mean(source_midpoints[B])   ascending → top to bottom
```

**Within-column y-reassignment** (after sort):

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

**Fallback:** views with no computable source midpoint receive `key = inf`
and sort stably to the bottom, preserving the pre-sort order for those views.

Because `sort_by_dag_tree` already places high-address sources near the top,
the crossing-minimisation pass is largely a no-op for well-structured diagrams.
It remains active as a correctness backstop.

---

## 6. View Height Estimation

**Location:** `_estimate_area_height()` in `scripts/mmpviz.py`

A lightweight estimate used by `_auto_layout()` and `rebalance_columns()` for
column height decisions and initial size assignment.  Does not run the full
section-height algorithm.

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

## 7. Layout Algorithms

#### Effect on example diagrams

| Diagram | Algo-1 | Algo-2 | Algo-3 |
|---------|--------|--------|--------|
| `chips/stm32f103` | 740×1812 H/W=2.45 | 1090×1062 H/W=0.97 | 1090×1062 (routed, no crossings) |
| `chips/opentitan_earlgrey` | 740×1558 H/W=2.11 | 1090×890 H/W=0.82 | 1090×890 (routed, no crossings) |
| All other examples | — | identical (already within target) | identical to algo-2 (no non-adjacent links) |

---

**Shared entry point:** `_auto_layout()` in `scripts/mmpviz.py` receives a
`columns` dict and assigns pixel `pos` and `size` to every view.  All three
algorithms ultimately feed into `_auto_layout()`; they differ in which
`columns` dict is passed and whether routing lanes are computed afterwards.

**Layout constants (shared by all):**

| Constant              | Value   | Purpose                                           |
|-----------------------|---------|---------------------------------------------------|
| `PADDING`             | 50 px   | Left canvas margin; gap between stacked views     |
| `TITLE_SPACE`         | 60 px   | Vertical space above views (titles)               |
| `MAX_COL_WIDTH`       | 230 px  | Maximum box width (readability cap)               |
| Title render offset   | −20 px  | Title text y-position relative to panel `pos_y`  |
| `_TITLE_CLEARANCE_PX` | 25 px   | Vertical clearance zone above each panel checked by `check.py` for `title-overlap` |

---

### 7.1 Algo-1: One Visual Column per DAG Level

**Location:** `_auto_layout()` in `scripts/mmpviz.py`; selected with `--layout algo1`.

All views assigned to the same DAG column are placed in a single visual column.
No height-based splitting is applied; the SVG canvas expands vertically to fit.

```python
col_cfgs = {dag_col: [area_configs in that column]}
final_cols = [col_cfgs[c] for c in sorted(col_cfgs)]

for col_idx, bin_cfgs in enumerate(final_cols):
    x = x_starts[col_idx]
    y = TITLE_SPACE
    for cfg in bin_cfgs:
        cfg['pos']  = [x, y]
        cfg['size'] = [col_width, estimated_height]
        y += estimated_height + PADDING
```

Views are never scaled down: each keeps its full estimated height so all
sections reach their effective minimum.

**Characteristic behaviour:** when a single DAG column contains many or very
tall views (e.g. a star topology where one child view has 40+ sections), the
resulting canvas can be very tall relative to its width (H/W > 2).

---

### 7.2 Algo-2: Height-Rebalancing

**Location:** `rebalance_columns()` in `scripts/auto_layout.py`;
selected with `--layout algo2`.

`rebalance_columns()` runs after `sort_by_dag_tree()` and before `_auto_layout()`.
It takes the initial DAG column assignment and adjusts visual column indices so
that no column's stacked height exceeds `target_ratio × canvas_width` (default 1.3).
The resulting column dict is then handed to `_auto_layout()` unchanged.

#### Target height and rolling budget

```python
target_h = canvas_width() * target_ratio   # recomputed after every column addition
canvas_width = CANVAS_LEFT + n_cols * col_width + (n_cols - 1) * col_gap
```

Because adding a column widens the canvas, the target height grows with each
split.  Subsequent columns therefore get a larger budget — later splits are
conservative and only happen when the column is genuinely too tall.

#### Per-column loop

Columns are processed left to right.  For each column whose height exceeds
`target_h` and which has more than one view:

**Pass 1 — outlier extraction**

A view is an outlier if its estimated height exceeds
`outlier_factor × column_average` (default 1.5×).  The tallest outlier is
moved to visual column `C + 1`; the column is re-evaluated (another outlier
may now exist).  This handles a single dominant view sitting in the middle of
an otherwise short column.

```
avg = mean(heights in column C)
if any view height > 1.5 × avg:
    move tallest such view to column C+1
    → re-evaluate column C
```

**Pass 2 — trailing overflow**

When no outlier exists but the column is still over budget, the bottom view in
tree order is moved to column `C + 1`.  This handles the case where several
moderately sized views collectively overflow.

```
if no outlier found and col_height > target_h:
    move last view (in tree order) to column C+1
    → re-evaluate column C
```

#### Descendant propagation

Whenever a view V moves from column N to column N+1, every descendant
currently at column ≤ N+1 is recursively pushed to column N+2+, preserving
`visual_col[child] > visual_col[parent]`:

```python
def _push_descendants(vid, min_col):
    for child in children[vid]:
        if vis_col[child] < min_col:
            vis_col[child] = min_col
            _push_descendants(child, min_col + 1)
```

#### Non-adjacent links

A view extracted to column N+1 has its parent in column N−1, making that
link non-adjacent (spanning over column N).  With algo-2 the renderer draws
the band spanning the full horizontal distance.  Algo-3 routes these links
through a crossing-free bridge line in the intermediate column (see §7.3).

---

### 7.3 Algo-3: Routing Lanes for Non-Adjacent Links (default)

**Location:** `plan_routing_lanes()` in `scripts/auto_layout.py`;
selected with `--layout algo3` (the default).

Algo-3 runs algo-2's height-rebalancing first, then post-processes any
non-adjacent links (links whose source column and destination column differ
by more than one after rebalancing) by planning a routing lane — a horizontal
bridge line — in each skipped intermediate column.

The rendered connector is an S-curve from the source trapezoid to the bridge
entry, a straight horizontal segment across the bridge, and a second S-curve
from the bridge exit to the destination trapezoid.

#### Identifying non-adjacent links

After `rebalance_columns()` and `_auto_layout()`, a link entry `(A → B)` is
non-adjacent when `|vis_col[B] − vis_col[A]| > 1`.  The intermediate columns
are the columns strictly between `vis_col[A]` and `vis_col[B]`.

#### Zero-crossing interval (ZCI)

For each non-adjacent link L and each intermediate column C, a crossing-free
y-range is derived from the adjacent links (direct neighbours in C) whose
source-section midpoints **bracket** L's source midpoint.

```
adjacent = links whose source views are in vis_col[A] and destination
           views are in column C, sorted by source-section midpoint (ascending)

find the pair (L_lo, L_hi) that brackets L's source midpoint:
    y_lo = destination-band y of L_lo   (top constraint)
    y_hi = destination-band y of L_hi   (bottom constraint)
    ZCI  = [y_lo, y_hi]
```

Placing the bridge within ZCI guarantees zero additional link-band crossings
with the adjacent connectors.

If no adjacent links exist for column C, the full column height is used as
the ZCI (unconstrained).

#### Gap selection

Valid bridge positions are gaps between views in column C that overlap the ZCI
and have enough height for the bridge (≥ `lane_height + 2 × lane_padding`).

`_col_gaps(c)` builds the gap list from the merged view extents in column C.
It always produces three kinds of gaps:

1. **Leading gap** — from `title_space` (60 px) to the top edge of the first
   view.  Present only when the first view starts below the title space.
2. **Between-view gaps** — from the bottom edge of one view to the top edge
   of the next, for every pair of consecutive views.  Present only when the
   inter-view space exceeds 0.5 px.
3. **Trailing gap** — from the bottom edge of the last view downward (open-ended;
   represented as `last_bottom + 2000 px`).  Always present.  This is the gap
   used by **bracket case C** (source y below all adjacent destinations), which
   wants to route the lane below every view in the column.

```
gaps = []
if first_view.top > title_space + 0.5:
    gaps.append((title_space, first_view.top))        # leading gap
for each consecutive pair (view_i, view_{i+1}):
    if view_{i+1}.top > view_i.bottom + 0.5:
        gaps.append((view_i.bottom, view_{i+1}.top))  # between-view gap
gaps.append((last_view.bottom, last_view.bottom + 2000))  # trailing gap

valid_gaps = [g for g in gaps
              if g.height >= lane_height + 2*lane_padding
              and g overlaps ZCI]

if valid_gaps:
    gap = the valid gap whose centre is closest to the ZCI midpoint
    lane_y = clamp(ZCI_mid, gap.top + lane_padding + lane_height/2,
                            gap.bottom - lane_padding - lane_height/2)
else:
    lane_y = ZCI_mid           # fallback: centre of ZCI, no gap constraint
```

**Bracket case C** specifically: when the non-adjacent link's source y is below
all adjacent destination y values, ZCI is `[adj_last.dst_y, +∞)`.  The only
gap overlapping this half-open interval is the trailing gap; `_col_gaps` always
provides it, so the lane is placed just below the last view in the column.
Without the trailing gap entry this case silently fell back to `lane_y = ZCI_mid`,
which placed the bridge through the middle of an existing view.

#### Lane dictionary

```python
{
    'col':    C,           # intermediate visual column index
    'x_left': col_x,       # left edge of the source column's section width (col_x = PADDING + ... )
    'x_right': col_x + col_width,  # right edge (col_width = 230 px)
    'y':      lane_y,      # vertical centre of the bridge line
    'height': lane_height, # 20 px default
}
```

`plan_routing_lanes()` returns `{entry_idx: [lane_dict, ...]}` — one list per
non-adjacent link entry.

#### Rendering

`MapRenderer._render_routed_connector()` is called in place of
`_render_connector()` when `routing_lanes` is non-empty for a link entry.
It draws:

1. **Source trapezoid** — same shape as the unrouted connector.
2. **Destination trapezoid** — same shape as the unrouted connector.
3. **Middle path** — a sequence of waypoints:
   `[(src_right, src_center), (lane_x_left, lane_y), (lane_x_right, lane_y), (dst_left, dst_center)]`

   Each consecutive pair of waypoints is connected by an S-curve Bézier
   (`C mx,y1 mx,y2 x2,y2`, where `mx = (x1 + x2) / 2`) if the endpoints
   differ vertically, or a straight line segment if they are at the same height.

**Bridge constants:**

| Parameter | Value |
|-----------|-------|
| `lane_height` | 20 px |
| `lane_padding` | 5 px (clearance above/below bridge within its gap) |
| `title_space` | 60 px (top margin; bridges can use this gap too) |
| Bridge x-span | `col_width` (230 px) — bridge width equals one section panel width |

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

Items worth implementing in future iterations. Fully implemented items, dropped
decisions, and superseded approaches have been removed.

| Topic | Current state | Notes |
|-------|---------------|-------|
| **View height computation** | `_estimate_area_height()`: sums per-section `max(global_min_h, section.min_height)` + break budget; returns `max(200.0, estimated)` | Estimate still under-counts label-conflict inflation; canvas over-expansion absorbs the difference. Replace with exact per-section computation using the Phase 1 algorithm. |
| **Minimum view height** | `max(200.0, estimated)` — hardcoded 200 px floor | Replace with principled formula: `max(H_view, 3 × min_h)`. |
| **Box width from label length** | Fixed `MAX_COL_WIDTH = 230 px` | Long section names clip silently; compute during height pre-pass using `max(120, longest_name × font × 0.55)`. |
| **Address clearance + inter-column gap** | Implemented: `_col_gap()` computes gap per column from actual address width and font size | 32-bit columns: 126 px at default 13 pt; 64-bit columns: 188 px. |

---

*End of document.*
