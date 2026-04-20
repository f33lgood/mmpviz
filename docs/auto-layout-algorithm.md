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
   - [7.2 Algo-2: Height-Rebalancing](#72-algo-2-height-rebalancing)
   - [7.3 Algo-3: Routing Lanes for Non-Adjacent Links (default)](#73-algo-3-routing-lanes-for-non-adjacent-links-default)
   - [7.4 Algo-4: Vertical Column Alignment](#74-algo-4-vertical-column-alignment)
8. [Link Visual Anatomy](#8-link-visual-anatomy)
9. [Column Width and Inter-Column Spacing](#9-column-width-and-inter-column-spacing)
10. [Canvas Sizing](#10-canvas-sizing)
11. [Link Band Endpoint Positioning](#11-link-band-endpoint-positioning)
12. [Remaining Work](#12-remaining-work)

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
    ├─ _estimate_area_height()        # mmpviz.py — exact height estimate per view
    ├─ sort_by_dag_tree()             # auto_layout.py — DAG-tree ordering pre-sort
    ├─ rebalance_columns()            # auto_layout.py — algo-2/3/4: height rebalancing
    ├─ _auto_layout()                 # mmpviz.py — DAG column placement, assigns pos + size
    ├─ order_within_column()          # auto_layout.py — crossing minimisation post-sort
    ├─ AreaView(...)                  # area_view.py — section height algorithm per view
    ├─ vertical_align_columns()       # auto_layout.py — algo-4 only: vertical column offsets
    └─ plan_routing_lanes()           # auto_layout.py — algo-3/4: routing lane planning
```

`get_area_views()` returns a 2-tuple `(area_views, routing_lanes)`.  `routing_lanes`
is an empty dict for algo1/algo2; for algo3 and algo4 it maps each non-adjacent link
entry index to the list of lane dicts computed by `plan_routing_lanes()`.

The layout algorithm is selected with the `--layout` CLI flag:

| Flag | Algorithm | Default |
|------|-----------|---------|
| `--layout algo1`  | One visual column per DAG level | |
| `--layout algo2`  | Height-rebalancing with outlier extraction | |
| `--layout algo3`  | Algo-2 + routing lanes for non-adjacent links | ✓ |
| `--layout algo4`  | Algo-3 + fixed lane assignment + vertical column alignment to minimise link length | |

When `links` is absent or empty, all views get an empty adjacency list (all
column 0), and auto-layout stacks them vertically in a single column.

After `get_area_views()` returns, the caller uses `_auto_canvas_size()` to
size the SVG canvas to fit all placed views:

```python
document_size = _auto_canvas_size(area_views)
```

---

## 2. Section Height Sizing

**Location:** `section_label_min_h()`, `AreaView._process()` in `scripts/area_view.py`

Called during `AreaView._process()` for each view.  Each visible section is
assigned an effective **floor height** and sections are stacked contiguously
from high address (SVG top) to low address (bottom).  The view height equals
the sum of all section heights — there is no proportional scaling by byte
range and no minimum view height beyond the floor sum.

### Per-section effective floor

```
for each section s (sorted high-address-first):
    if s.is_break():
        floor = break_height_val                # theme break_height (default 20 px)
    else:
        floor = max(
            user_min_h_val,                     # theme min_section_height
            s.min_height or 0,                  # per-section override
            section_label_min_h(s, font_size, size_x),
            1.0,                                # hard minimum
        )
    s.size_y_override = floor
```

`section_label_min_h(s, font_size, size_x)` detects whether the size label
(top-left, 12 px font) and the name label (horizontally centred, `font_size` px)
would overlap on the x-axis at the current section width:

```
size_label_right = 2 + len(format_size(s.size)) × 0.6 × 12
name_label_left  = size_x/2 − len(name_text) × 0.6 × font_size / 2

if size_label_right > name_label_left:
    return 30 + font_size      # inflate just enough to separate labels vertically
else:
    return 0.0                 # no conflict — keep the floor at its other driver
```

### Grows-arrow neighbor constraint

When a section carries the `grows-up` or `grows-down` flag, the immediately
adjacent non-break neighbor's floor is raised so the rendered growth arrow
does not overlap the neighbor's text label:

```
arrow_neighbor_floor = 2 × 20 × growth_arrow_size + font_size

for i, s in enumerate(sorted_sections):
    if s.is_grow_up() and i > 0:
        nb = sorted_sections[i-1]              # SVG-above (next-higher address)
        if not nb.is_break():
            nb.size_y_override = max(nb.size_y_override, arrow_neighbor_floor)
    if s.is_grow_down() and i < len(sorted_sections)-1:
        nb = sorted_sections[i+1]              # SVG-below (next-lower address)
        if not nb.is_break():
            nb.size_y_override = max(nb.size_y_override, arrow_neighbor_floor)
```

Break neighbors are skipped (no text label to protect).

### Stacking

Sections are stacked top-to-bottom at their floor heights; the view's
`size_y` is updated to the stack total so `address_to_pxl` stays consistent:

```
y = 0.0
for s in sorted_sections:
    s.pos_y_in_subarea = y
    y += s.size_y_override
self.size_y = y
```

`size_y_override` and `pos_y_in_subarea` are read by `apply_section_geometry()`
when the renderer and checker need the canonical `size_y / pos_y` fields.

**Constants (from theme / default.json defaults):**

| Theme key              | default.json | Meaning                                          |
|------------------------|--------------|--------------------------------------------------|
| `min_section_height`   | 20 px         | Global section height floor (all sections)      |
| `break_height`         | 20 px         | Fixed height for break sections                 |
| `max_section_height`   | 300 px        | **Accepted but ignored** in the floor-stack model (reserved) |

**Per-section overrides (diagram.json):**

| Section field | Effective value                                                   |
|---------------|-------------------------------------------------------------------|
| `min_height`  | `max(min_height, min_section_height, label_conflict_floor)` — highest wins |
| `max_height`  | **Accepted but ignored**; `section-height-conflict` still validates `min_height ≤ max_height` for forward compatibility |

The label-conflict floor (`30 + font_size` px) is derived automatically from
the section geometry — it is not a user-visible theme property.

Break sections participate in the same stacking pass as non-break sections;
they are assigned a fixed `break_height` instead of the derived floor.

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

Used by `_auto_layout()` and `rebalance_columns()` for column placement and
initial size assignment.  Produces the **exact** rendered view height by
mirroring `AreaView._process()` — including the label-conflict floor and the
grows-arrow neighbor constraint — so no post-layout canvas expansion is
needed to absorb a discrepancy.

```python
# Pass 1 — per-section floor
sorted_secs = sorted(visible_sections, key=lambda s: s.address + s.size, reverse=True)
floors = []
for s in sorted_secs:
    if s.is_break():
        floors.append(break_height)
    else:
        floors.append(max(
            user_min_h,
            s.min_height or 0,
            section_label_min_h(s, font_size, size_x),
            1.0,
        ))

# Pass 2 — grows-arrow neighbor constraint
arrow_neighbor_floor = 2 × 20 × growth_arrow_size + font_size
for i, s in enumerate(sorted_secs):
    if s.is_grow_up()   and i > 0                      and not sorted_secs[i-1].is_break():
        floors[i-1] = max(floors[i-1], arrow_neighbor_floor)
    if s.is_grow_down() and i < len(sorted_secs) - 1   and not sorted_secs[i+1].is_break():
        floors[i+1] = max(floors[i+1], arrow_neighbor_floor)

return sum(floors)
```

Because the estimator and the renderer apply the same two passes, the
pre-layout estimate and the final rendered view height match exactly.

---

## 7. Layout Algorithms

### Effect on example diagrams

| Diagram | Algo-1 | Algo-2 | Algo-3 | Algo-4 |
|---------|--------|--------|--------|--------|
| `chips/stm32f103` | 740×1812 H/W=2.45 | 1090×1062 H/W=0.97 | 1090×1062 (routed, no crossings) | 1090×1062 (columns vertically aligned to minimise link length) |
| `chips/opentitan_earlgrey` | 740×1558 H/W=2.11 | 1090×890 H/W=0.82 | 1090×890 (routed, no crossings) | 1090×890 (columns vertically aligned) |
| All other examples | — | identical (already within target) | identical to algo-2 (no non-adjacent links) | identical to algo-3 when all columns share the same y-extent |

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
y-range is derived by computing the **interpolated y** (`y_through`) — where a
straight-line path from source to destination would cross column C — and
comparing it against the **destination-band y-positions** of adjacent links
(direct neighbours in C):

```
y_through = y_src + (y_dst − y_src) × (C − src_col) / (dst_col − src_col)

adjacent = links whose source is in column C−1 and destination is in column C,
           sorted by destination-band y (ascending)
```

ZCI bracket is determined by which pair of adjacent destination Ys bracket `y_through`:

| Bracket | Condition | ZCI |
|---------|-----------|-----|
| **A** | `y_through ≤ adj[0].dst_y` | `(−∞, adj[0].dst_y)` |
| **B** | `adj[k].dst_y ≤ y_through ≤ adj[k+1].dst_y` | `[adj[k].dst_y, adj[k+1].dst_y]` |
| **C** | `y_through ≥ adj[-1].dst_y` | `(adj[-1].dst_y, +∞)` |
| (none) | no adjacent links | `(−∞, +∞)` unconstrained |

Placing the bridge within ZCI guarantees zero additional link-band crossings
with the adjacent connectors.

#### Gap expansion pre-pass

Before `plan_routing_lanes` runs, `mmpviz.py` widens inter-panel gaps in columns
that need to host N ≥ 2 routing lanes simultaneously.  The minimum required gap is:

```
minimum_gap = N × lane_pitch    (lane_pitch = lane_height + 2 × lane_padding = 30 px)
```

This is exact: the feasible centre range within a gap of height G is
`[gap_top + lane_pitch/2, gap_bot − lane_pitch/2]`, spanning `G − lane_pitch`.
For N lane centres at `lane_pitch` spacing the required span is `(N−1) × lane_pitch`, so
`G − lane_pitch ≥ (N−1) × lane_pitch` → `G ≥ N × lane_pitch`.

Each view below the widened gap shifts down by the extra pixels; views above are
unaffected.  Single-lane columns (N = 1) always fit in the initial PADDING = 50 px
gap and are not expanded.

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

#### Collision avoidance

After the initial candidate y is clamped to `[y_lo, y_hi]` and to the ZCI, already-placed
lanes in the same gap are avoided via a two-phase sweep:

1. **Upward sweep** (default): push the candidate up past any blocking lane one at a time
   (ascending order); if this exceeds `y_hi` the candidate is discarded for this gap.
2. **Downward sweep** (fallback): if the upward sweep failed (e.g. `y_ideal > y_hi` and
   lanes are packed near the top), retry with a downward sweep from the initial clamped
   position.

A final collision check catches any residual overlap before accepting the candidate.

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
3. **Middle path** — a sequence of waypoints (see §8 for term definitions):

   ```
   [(lx_j, src_center),          ← source junction
    (lane.x_left,  lane.y),      ← bridge entry waypoint
    (lane.x_right, lane.y),      ← bridge exit waypoint
    (rx_j, dst_center)]          ← destination junction
   ```

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

### 7.4 Algo-4: Vertical Column Alignment

**Location:** `vertical_align_columns()` in `scripts/auto_layout.py`;
selected with `--layout algo4`.  Applied in `mmpviz.py:get_area_views()`
between the initial `_auto_layout()` call and `plan_routing_lanes()` (§7.3).

Algo-4 runs algo-3's pipeline end-to-end first (height-rebalancing + routing
lanes), then inserts an additional pass that shifts each DAG column vertically
to minimise total link length.  Columns keep their widths and view orderings;
only the y-coordinates of every view in a non-anchor column change.

Unlike algo-3, algo-4 uses the routing-lane y-positions it **plans to produce**
as hard constraints on column placement — "fixed lane assignment": the lane y
for each non-adjacent link is computed up front and fed back as a desired
offset for the column that owns it, so the rebalancing step already knows
where every bridge will land.

#### Anchor column

The **tallest** column (largest `max(pos_y + size_y) − min(pos_y)` across its
views) is chosen as the anchor and keeps offset 0.  The anchor's pixel span
is therefore the diagram's final height; every other column's offset is
clamped (Phase 3 below) so it cannot push the diagram taller than the anchor
already requires.

Ties are broken by whichever column `max()` reports first.

#### Link attachment y

For every link entry, the algorithm computes an **absolute SVG y** for both
endpoints using the preliminary top-aligned `AreaView`s:

```python
def _abs_y(av, sections):
    rel = _find_link_midpoint_by_sections(av, sections)
    return (av.pos_y + rel) if rel is not None else (av.pos_y + av.size_y / 2)
```

`rel` is the section midpoint (or multi-section midpoint) inside the view;
when sections are unresolved it falls back to the view's vertical centre.

Only **adjacent** links (column span `|to_col − from_col| == 1`) drive
vertical alignment directly.  Non-adjacent links are handled via routing-lane
desired offsets (next subsection) so they don't pull a column toward a
distant neighbour it doesn't physically connect to.

#### Routing-lane desired offsets

For each non-adjacent link L with source in column `efc` and destination in
column `etc`, the algorithm computes the desired routing-lane y in gap
`(efc, efc+1)` using the **nearest inter-view gap midpoint** in column `efc+1`:

```
y_through = y_src + (y_dst − y_src) / (etc − efc)   # interpolated at gap efc+1
y_ideal   = _best_gap_midpoint(efc+1, y_through)     # midpoint of nearest gap in col efc+1

desired_δ = y_ideal − L.source_y
```

`_best_gap_midpoint(c, y_ref)` returns the midpoint of the inter-view gap in
column `c` whose centre is closest to `y_ref`.  Using the gap midpoint instead
of `y_through` makes the desire position-independent: at `vertical_align_columns`
time the non-anchor destination views have not yet been shifted, so `y_through`
computed from their raw top-aligned positions is unreliable.  The gap midpoint is
derived from the column's structural layout and is stable regardless of offset.

Phase 2c likewise uses `_best_gap_midpoint` for the final-gap estimate when
pulling destination-only columns toward the already-placed source side.

#### Cascade for multi-hop links

`_gap_groups` only covers the first gap of each non-adjacent link.  For a
link that skips ≥ 2 columns (`etc − efc > 2`) the intermediate columns from
`efc + 2` onward receive no routing-lane desire, so their adjacent-link
medians can park the cascaded lanes far from the source — producing long
diagonal middle segments.

Phase 2.5 fixes this by computing the first-gap lane y under the
already-placed offsets and adding a hosting desire for every later
intermediate column so each cascaded lane lands at the same y:

```
prev_y = lane_y at gap (efc, efc+1) using effective offsets
for c in range(efc + 2, etc):
    lane_y0 = col_bottom[c] + lane_height/2 + lane_padding
    _cascade_extra[c].append(prev_y − lane_y0)
    # prev_y propagates unchanged: the cascade holds the lane flat
```

A second BFS pass then re-runs Phase 2 with the cascade extras so the
affected columns and their adjacent-link descendants all pick up updated
offsets.  Columns isolated from the anchor cluster (Phase 2b) receive the
same treatment in a post-step.

#### Phase 1 — BFS ordering

A breadth-first traversal rooted at the anchor visits every column reachable
via adjacent links.  The BFS order is used only to establish **processing
order**; it does not commit offsets.

```
bfs_order = [anchor]
queue     = deque([anchor])
while queue:
    cur = queue.popleft()
    for each adjacent link touching cur:
        other = the other endpoint's column
        if other not yet visited: append to bfs_order, enqueue
```

This ordering matters because each column's offset depends on already-placed
neighbours, not just the column that discovered it.

#### Phase 2 — L1-optimal median

For each column in `bfs_order[1:]` (the anchor is already fixed at 0), the
algorithm collects every *desired offset* implied by already-placed
neighbours:

```
for each adjacent link (fc, sy, tc, dy):
    if fc == col and tc already placed: desired ← dy + offsets[tc] − sy
    if tc == col and fc already placed: desired ← sy + offsets[fc] − dy

desired += routing_lane_desired[col]          # source-side lane alignment
desired += host-column desires                # bracket-C hosting

offsets[col] = median(desired)                # L1-optimal placement
```

The median minimises total L1 wire length because the sum of absolute
deviations is minimised at the median of the target positions.  Using the
mean (L2) would be pulled by outliers; using one anchor neighbour would
ignore the rest.

Columns with no desired offsets default to 0.

#### Phase 2b — isolated clusters

Columns unreachable from the anchor via adjacent links never appear in
`bfs_order`.  For these, the algorithm runs a mirror of Phase 2 in
column-index order so that earlier non-BFS offsets propagate into later ones
within the same isolated cluster.

#### Phase 2c — destination-pull for non-adjacent links

A view that appears only as a non-adjacent destination (no adjacent link
pulling it toward anything) sits at offset 0 after Phases 2 and 2b.  Phase 2c
uses the already-computed source offset to estimate the routing-lane y at
the **final gap** (`etc − 1, etc`) and pulls the destination column toward
it:

```
for each non-adjacent link with dest column etc ∉ in_order:
    esrc_y_eff = L.source_y + offsets[efc]
    y_ideal_dst = ZCI_y_ideal(esrc_y_eff, adj_links_in_final_gap)
    _dst_desired[etc].append(y_ideal_dst − L.dest_y)

for c, desires in _dst_desired.items():
    combined = routing_lane_desired[c] + desires
    offsets[c] = median(combined)
```

This step does not revisit columns already placed by Phase 2 (those already
have their adjacent-link median).

#### Phase 3 — anchor-bounding clamp

Each non-anchor column's offset is clamped so the column's top stays at or
below the anchor's top and its bottom stays at or above the anchor's bottom:

```
anchor_top    = min(av.pos_y              for av in anchor_views)
anchor_bottom = max(av.pos_y + av.size_y  for av in anchor_views)

for c ≠ anchor:
    col_top    = min(av.pos_y             for av in col_views[c])
    col_bottom = max(av.pos_y + av.size_y for av in col_views[c])
    lo = anchor_top    − col_top     # top must not go above anchor top
    hi = anchor_bottom − col_bottom  # bottom must not go below anchor bottom
    if lo > hi:
        offsets[c] = (lo + hi) / 2   # column taller than anchor: centre it
    else:
        offsets[c] = clamp(offsets[c], lo, hi)
```

This guarantees the overall diagram height is unchanged from the
top-aligned baseline — the anchor column is the sole determinant of height.

#### Offset application and view rebuild

`vertical_align_columns()` returns `{col_int: y_offset_float}`.  The caller
applies offsets only when at least one column would shift by more than 0.5 px:

```python
if col_offsets and any(abs(v) > 0.5 for v in col_offsets.values()):
    for cfg in area_configurations:
        c = columns.get(cfg.get('id', ''))
        if c is not None:
            cfg['pos'][1] = round(cfg['pos'][1] + col_offsets.get(c, 0.0), 1)
    # Rebuild AreaViews with the shifted positions
    area_views = [AreaView(...) for cfg in area_configurations]
```

Routing lanes are then planned against the shifted positions, so the lanes
produced by `plan_routing_lanes()` match the lane y-values that Phase 2 used
as desired offsets (subject to clamping).

#### When algo-4 ≡ algo-3

If the tallest column already spans the full diagram height and no non-anchor
column has desired offsets exceeding 0.5 px, every column is clamped to 0
and algo-4 produces the same output as algo-3.  Single-column diagrams and
diagrams with no links also early-return with `{}` (no shift).

---

## 8. Link Visual Anatomy

All connector and band links share the same three-part structure.  These terms are
used consistently throughout this document and the codebase.

### Trapezoid

The **trapezoid** is the filled polygon at each end of a link.  It fans the full
pixel span of the linked source (or destination) sections at the panel edge down to
the `middle.width` stroke width at the junction.

- **Source trapezoid** — left end.  Outer edge spans the source sections at the
  panel's right edge (`lx`); inner edge collapses to `middle.width` at the source
  junction (`lx_j`).
- **Destination trapezoid** — right end.  Inner edge at `middle.width` at the
  destination junction (`rx_j`); outer edge spans the destination sections at the
  panel's left edge (`rx`).

In `connector` style the horizontal extent of each trapezoid is set by
`connector.source.width` and `connector.destination.width` (default 25 px each).
In `band` style the same widths come from the `source` and `destination` segment
sub-objects.

### Junction

The **junction** is the x-coordinate where a trapezoid's inner (narrow) edge meets
the middle segment — the point where the tapered shape ends and the fixed-width line
begins.

| Variable | Definition |
|----------|-----------|
| `lx_j`   | Source junction x = `lx + source.width` |
| `rx_j`   | Destination junction x = `rx − destination.width` |

In `band` style, `source.dheight` and `destination.sheight` set the link height
**at** the junction edge (the inner edge of the respective trapezoid).

### Waypoint

A **waypoint** is one `(x, y)` coordinate pair in the middle segment's path.  The
renderer walks the waypoint list in order, connecting each consecutive pair with a
straight line (same y) or an S-curve Bézier (different y).

For an **unrouted** (adjacent-column) link the waypoint sequence is:

```
[(lx_j, src_center),   ← source junction
 (rx_j, dst_center)]   ← destination junction
```

For a **routed** (non-adjacent, algo-3) link each intermediate routing lane
contributes two additional waypoints — an **entry waypoint** and an **exit
waypoint** — at the left and right edges of the bridge:

```
[(lx_j,          src_center),   ← source junction
 (lane.x_left,   lane.y),       ← bridge entry waypoint
 (lane.x_right,  lane.y),       ← bridge exit waypoint
 (rx_j,          dst_center)]   ← destination junction
```

The horizontal segment between the entry and exit waypoints is the **bridge** —
the straight line that crosses the gap in the intermediate column at `lane.y`.

---

## 9. Column Width and Inter-Column Spacing

`col_width` is always `MAX_COL_WIDTH` (230 px). The inter-column gap is computed
per-column from the actual address width and font size of the source column:

```python
gap = _ADDR_LABEL_H_OFFSET                         # offset from panel right edge
    + addr_chars * _HELVETICA_W_RATIO * font_size  # label width
    + _INTER_BREATHING                            # breathing room (link band + margin)
```

**Address label geometry constants** (defined in `mmpviz.py`, mirrored in `check.py`):

| Constant                | Value         | Purpose                                                |
|-------------------------|---------------|--------------------------------------------------------|
| `_ADDR_LABEL_H_OFFSET`  | 10 px         | Horizontal offset from panel right edge to label start |
| `_ADDR_CHARS_32`        | 10            | `len("0x00000000")` — 8 hex digits                     |
| `_ADDR_CHARS_64`        | 18            | `len("0x0000000000000000")` — 16 hex digits            |
| `_ADDR_64BIT_THRESHOLD` | `0xFFFF_FFFF` | Start addresses above this need 64-bit format          |
| `_HELVETICA_W_RATIO`    | 0.6           | Estimated character width / font-size for Helvetica    |
| `_INTER_BREATHING`      | 38 px         | Breathing room past the label for link bands + margin (defined locally in `_auto_layout()`) |

A column is "64-bit" when ANY section's **start address** exceeds `_ADDR_64BIT_THRESHOLD`.
All sections in that view then use the 16-digit label format for visual consistency.

**Example gaps at the default `font_size: 13`:**
- 32-bit column: `_ADDR_LABEL_H_OFFSET + _ADDR_CHARS_32 × _HELVETICA_W_RATIO × 13 + _INTER_BREATHING = 10 + 10 × 0.6 × 13 + 38 = 126 px`
- 64-bit column: `_ADDR_LABEL_H_OFFSET + _ADDR_CHARS_64 × _HELVETICA_W_RATIO × 13 + _INTER_BREATHING = 10 + 18 × 0.6 × 13 + 38 = 188 px`

Column x-positions are cumulative:

```python
x_starts = [PADDING]
for bin_idx in range(len(final_cols) - 1):
    x_starts.append(x_starts[-1] + col_width + _col_gap(final_cols[bin_idx]))
```

The rightmost-column canvas margin (`right_pad`) uses the same label-width formula
with 28 px breathing room instead of 38 (no link band beyond the last column).

---

## 10. Canvas Sizing and Viewport Origin

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

## 11. Link Band Endpoint Positioning

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

## 12. Remaining Work

Items worth implementing in future iterations. Fully implemented items, dropped
decisions, and superseded approaches have been removed.

| Topic | Current state | Notes |
|-------|---------------|-------|
| **Box width from label length** | Fixed `MAX_COL_WIDTH = 230 px` | Long section names clip silently; compute during height pre-pass using `max(120, longest_name × font × 0.55)`. |
| **`max_height` / `max_section_height`** | Accepted but ignored in the floor-stack model; `section-height-conflict` still validates `min_height ≤ max_height` for forward compat | Either re-enable as a true ceiling (requires redistribution logic) or remove the fields from the schema and drop the check. |

---

*End of document.*
