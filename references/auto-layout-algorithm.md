# Auto Layout Algorithm — Current Implementation

This document describes the auto layout algorithm as it is actually implemented.
It is authoritative for understanding and maintaining the code; the original
proposal (`auto-layout-proposal.md`) remains the reference for future work.

---

## Contents

1. [Entry Points and Activation](#1-entry-points-and-activation)
2. [Section Height Sizing](#2-section-height-sizing)
3. [Link Graph Construction](#3-link-graph-construction)
4. [Column Assignment](#4-column-assignment)
5. [Area Ordering Within a Column](#5-area-ordering-within-a-column)
6. [Area Height Estimation](#6-area-height-estimation)
7. [Column Bin-Packing and Overflow Handling](#7-column-bin-packing-and-overflow-handling)
8. [Column Width and Inter-Column Spacing](#8-column-width-and-inter-column-spacing)
9. [Canvas Sizing](#9-canvas-sizing)
10. [Link Band Endpoint Positioning](#10-link-band-endpoint-positioning)
11. [Planned vs Implemented](#11-planned-vs-implemented)

---

## 1. Entry Points and Activation

Auto layout activates when **any** area in `diagram.json` lacks a `pos` or `size`
field.  The main orchestrator is `get_area_views()` in `scripts/mmpviz.py`.

```
get_area_views()
    │
    ├─ build_link_graph()      # auto_layout.py — DAG from address containment
    ├─ assign_columns()        # auto_layout.py — BFS depth → column index
    ├─ _estimate_area_height() # mmpviz.py — quick height estimate per area
    ├─ _auto_layout()          # mmpviz.py — bin-packing, assigns pos + size
    └─ AreaView(...)           # area_view.py — section height algorithm per area
```

After `get_area_views()` returns, the caller uses `_auto_canvas_size()` to
expand the SVG canvas to fit all placed areas:

```python
# mmpviz.py main() and render_auto_layout.py render_chip()
needed = _auto_canvas_size(area_views)
document_size = (max(orig_w, needed[0]), max(orig_h, needed[1]))
```

---

## 2. Section Height Sizing

**Location:** `AreaView._section_label_min_h()`, `AreaView._compute_per_section_heights()`,
`AreaView._process()` in `scripts/area_view.py`

Called during `AreaView._process()` for each sub-area.  First, a per-section
minimum-height dict is built; then heights are distributed in two phases.

### Per-section min_h derivation

`_process()` builds a dict `{id(s): floor_px}` for all visible sections:

```
for each visible section s:
    user_min  = style.get('min_section_height', 0)
    label_min = _section_label_min_h(s, font_size)
    per_section_min_h[id(s)] = max(user_min, label_min)
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

This means only sections whose size label and name label would genuinely
collide receive an extra height floor; all other sections keep proportional
sizing, keeping diagrams compact.

### Phase 1 — Floor locking (min_h)

`_compute_per_section_heights(sections, available_px, min_h, max_h)` accepts
`min_h` as either a scalar (backward-compatible) or the per-section dict built
above.

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

After Phase 1 converges, any section exceeding `max_h` is capped and its
surplus is redistributed proportionally to floored (min_h-locked) sections
first, then to any remaining uncapped section.

**Constants (from theme / default.json defaults):**

| Theme key              | default.json | Meaning                                          |
|------------------------|--------------|--------------------------------------------------|
| `min_section_height`   | 20 px         | User-controlled section height floor            |
| `max_section_height`   | 300 px        | Section height ceiling                          |
| `break_height`           | 20 px         | Fixed height for break sections                 |

Break sections use a separate code path (`break_height` fixed height) and do
**not** participate in `_compute_per_section_heights`.

The label-conflict floor (`30 + font_size` px) is derived automatically from
the section geometry — it is not a user-visible theme property.

---

## 3. Link Graph Construction

**Location:** `build_link_graph()` in `scripts/auto_layout.py`

Derives the DAG from address containment — no explicit `links` configuration
is required for column assignment.

```
for each source area A:
    for each global section L (L.size > 0, L within A.range):
        for each other area B:
            if B.range ⊆ [L.address, L.address + L.size):
                add edge A → B
```

Returns an adjacency list `{source_id: [target_id, ...]}` where every area ID
appears as a key.  Duplicate edges are suppressed.

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
Disconnected areas default to column 0.

---

## 5. Area Ordering Within a Column

**Location:** `order_within_column()` in `scripts/auto_layout.py`

Sorts areas in column C+1 by the vertical midpoint of their linking section
within column C, minimising link-band crossings:

```
for each target area B (column C+1):
    for each source area A that links to B:
        mid = pixel midpoint of the section in A that contains B's range
        source_midpoints[B].append(A.pos_y + mid)

sort column C+1 by mean(source_midpoints[B])   ascending → top to bottom
```

**Note:** this function is implemented but not yet wired into `get_area_views()`.
The current bin-packing in `_auto_layout()` uses the order areas appear in the
DAG column group (original diagram.json order within each column level).

---

## 6. Area Height Estimation

**Location:** `_estimate_area_height()` in `scripts/mmpviz.py`

A lightweight estimate used by `_auto_layout()` for bin-packing and initial
size assignment.  Does not run the full section-height algorithm.

```python
estimated = n_visible * user_min_h
          + n_breaks  * (break_height + 4)
          + 20                          # top/bottom padding
return max(200.0, estimated)
```

`n_visible` and `n_breaks` are counted after applying the area's `range`,
`section_size` filter, and any per-area section flag overrides (break/hidden).
`user_min_h` is `style.get('min_section_height', 0)`.

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

```
for each area in DAG column:
    trial = current_bin + [area]
    if stack_height(trial) ≤ available_h  OR  current_bin is empty:
        append area to current_bin
    else:
        if len(current_bin) ≥ 2:
            # Spill: commit bin, start new one
            final_cols.append(current_bin)
            current_bin = [area]
        else:
            # 1-area bin: accept overflow, canvas will expand
            current_bin.append(area)
commit current_bin
```

**Key:** areas are never scaled down.  Each keeps its full estimated height so
all sections can reach `min_section_height`.  Canvas expansion (§9) handles
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

| Constant       | Value  | Purpose                                      |
|----------------|--------|----------------------------------------------|
| `PADDING`      | 50 px  | Left canvas margin; gap between stacked areas|
| `TITLE_SPACE`  | 60 px  | Vertical space above areas (titles)          |
| `BOTTOM_PAD`   | 30 px  | Margin below last area                       |
| `INTER_COL_GAP`| 120 px | Gap between column right edge and next left  |
| `MAX_COL_WIDTH`| 230 px | Maximum box width (readability cap)          |

---

## 8. Column Width and Inter-Column Spacing

`col_width` is always `MAX_COL_WIDTH` (230 px). The initial canvas width from
`diagram.json` is not used to derive column width — the SVG canvas is expanded
after layout via `_auto_canvas_size()` (§9), so there is no need to fit columns
within a pre-declared width:

```python
col_width = MAX_COL_WIDTH   # 230 px — fixed regardless of canvas width
```

The `INTER_COL_GAP` of 120 px provides clearance for:
- 32-bit address labels: ≈ 82 px (`10 chars × 0.6 × 12 pt + 10 px offset`)
- Link-band polygon: remaining 38 px breathing room

Column x-positions are uniformly spaced:

```python
x[col_idx] = PADDING + col_idx * (col_width + INTER_COL_GAP)
```

---

## 9. Canvas Sizing

**Location:** `_auto_canvas_size()` in `scripts/mmpviz.py`

After `get_area_views()` returns, the SVG canvas is expanded to the minimum
size that fits all placed areas without clipping:

```python
max_right  = max(av.pos_x + av.size_x for av in area_views)
max_bottom = max(av.pos_y + av.size_y for av in area_views)
needed = (max_right + 110, max_bottom + 30)
```

The `110 px` right padding accommodates address labels extending beyond the
rightmost column's box edge.

The final canvas takes the element-wise maximum of the diagram's specified
size and `needed`, so the canvas never shrinks below what `diagram.json`
requests:

```python
document_size = (max(orig_w, needed[0]), max(orig_h, needed[1]))
```

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

## 11. Planned vs Implemented

| Topic | Proposal | Implementation | Status |
|-------|----------|----------------|--------|
| **Section height: min_h derivation** | Auto-derive `min_h = font_size + 28` | `_section_label_min_h()` computes per-section conflict-driven floor: `30 + font_size` only when size label and name label overlap on x-axis; 0 otherwise. User `min_section_height` applied independently. | Implemented — conflict-driven, per-section |
| **Section height: per-section floor** | Iterative lock-at-min_h with separate min/max phases | `_compute_per_section_heights` Phase 1 (floor, accepts per-section dict) + Phase 2 (ceiling) | Implemented |
| **Section height: max_h ceiling** | Redistribute surplus from capped sections | Phase 2 of `_compute_per_section_heights` | Implemented |
| **Section height: area-level auto-expansion** | When overflow, expand H = Σ(min_h); re-run algorithm | Not at area level; canvas expands via `_auto_canvas_size()` | Partial — expansion is canvas-level, not area-level |
| **Section height: break sections** | Breaks participate in iterative algorithm with min_h floor | Breaks use fixed `break_height` path; excluded from `_compute_per_section_heights` | Not implemented |
| **Link graph construction** | Edge A→B when B.range ⊆ section L in A | `build_link_graph()` — identical logic | Implemented |
| **Multiple parents** | Use first-encountered (BFS) source | `assign_columns()` uses max-depth rule | Implemented (stricter than proposal) |
| **Column assignment: BFS depth** | BFS with max-depth propagation | `assign_columns()` — Kahn's algorithm with max propagation | Implemented |
| **Column assignment: column cap (N ≤ 4)** | Warn when > 3 columns; merge deepest levels | No cap; natural DAG depth used | Not implemented |
| **Root detection heuristics** | Widest range or most sections when no edges | Areas with in-degree 0 (no special tie-breaking) | Simplified |
| **Area height computation** | Run Phase 1 algorithm per area for exact height | `_estimate_area_height`: `n_visible × min_h + n_breaks × (break_height+4) + 20` | Simplified — formula, not full algorithm |
| **Minimum area height (3 × min_h)** | `max(H_area, 3 × min_h)` | `max(200.0, estimated)` — hardcoded 200 px floor | Approximate |
| **Area ordering: crossing minimisation** | Sort column C+1 by source midpoint | `order_within_column()` implemented but not wired into `get_area_views()` | Implemented, not active |
| **Vertical placement: top alignment** | All columns start at same y | TITLE_SPACE = 60 px for every column | Implemented |
| **Overflow: spill strategy** | Strategy A (split) for ≥ 3 areas, Strategy B (scale) for 1–2 | Spill when bin ≥ 2 areas; scale (accept, canvas expands) for 1-area bins | Implemented — threshold lowered to ≥ 2 |
| **Overflow: scale strategy** | Scale H_area by fit_factor; re-run section algorithm | Not used — areas never scaled; canvas expands instead | Replaced by canvas expansion |
| **Vertical nudge toward link source** | Shift area y toward link-band midpoint | Not implemented | Not implemented |
| **Box width from label length** | `max(120, longest_name × font × 0.55)` | Fixed 230 px (`MAX_COL_WIDTH`); canvas auto-expands so initial canvas width is not used | Simplified |
| **Address clearance: formula** | `addr_chars × 0.6 × font_size + 10` (82 px for 32-bit) | INTER_COL_GAP = 120 px fixed constant | Approximated; fixed rather than computed |
| **Inter-column gap: per-column** | `max_box_width[C] + addr_clearance[C] + LINK_BAND_MIN` | Uniform 120 px gap for all columns | Simplified |
| **Canvas sizing: natural content size** | `content_W = rightmost_right + LEFT_PAD` | `_auto_canvas_size()` — identical intent | Implemented |
| **Canvas sizing: target format scaling** | Scale to A4 / slide aspect ratio | No scaling; natural pixel layout only | Not implemented |
| **Link band endpoint alignment** | (not explicitly specified) | `address_to_py_actual()` interpolates within actual rendered section bounds | Implemented beyond proposal |

---

*End of document.*
