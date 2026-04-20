"""
auto_layout.py — Link graph construction and column assignment for mmpviz.

These utilities derive a directed acyclic graph (DAG) from explicit link
entries, then assign each area to a layout column based on topological depth.

Public API
----------
build_link_graph_from_links(entries, view_ids) → {src_id: [tgt_id, ...]}
assign_columns(graph, view_ids)                 → {view_id: column_int}
sort_by_dag_tree(area_configs, columns, link_entries, sec_mid_addrs)
                                                → [area_config, ...]
order_within_column(columns, area_views, link_entries)
                                                → {col: [view_id, ...]}
rebalance_columns(columns, area_configs, ...)   → {view_id: visual_col_int}
plan_routing_lanes(vis_col, link_entries, ...)  → {entry_idx: [lane_dict, ...]}
vertical_align_columns(vis_col, link_entries, area_views, ...)
                                                → {col_int: y_offset_float}
"""
from collections import defaultdict, deque


# ---------------------------------------------------------------------------
# Link graph construction — explicit links
# ---------------------------------------------------------------------------

def build_link_graph_from_links(entries: list, view_ids: list) -> dict:
    """
    Build a directed link graph from explicit link entries.

    Each entry is a dict with ``from_view`` and ``to_view`` keys (as produced
    by ``Links._validate_entries``).  An edge from_view → to_view is added for
    every entry.  Views that appear only as sources (never as targets) become
    layout roots (column 0).

    Parameters
    ----------
    entries : list of dict
        Validated link entry dicts from ``Links.entries``.
    view_ids : list of str
        All view IDs in the diagram.

    Returns
    -------
    dict  {source_id: [target_id, ...]}
        Adjacency list.  Every view id appears as a key.
    """
    graph = {vid: [] for vid in view_ids}
    for entry in entries:
        src = entry.get('from_view')
        tgt = entry.get('to_view')
        if src in graph and tgt in graph and tgt not in graph[src]:
            graph[src].append(tgt)
    return graph


# ---------------------------------------------------------------------------
# Column assignment
# ---------------------------------------------------------------------------

def assign_columns(graph: dict, view_ids: list) -> dict:
    """
    Assign each view to a layout column using BFS + max-depth propagation.

    Roots (views with no incoming edges) are placed in column 0.  Each
    successor is placed at max(current_column, source_column + 1).  This
    handles diamonds and multi-parent cases correctly.

    Disconnected views (no edges) are assigned column 0.

    Parameters
    ----------
    graph : dict  {source_id: [target_id, ...]}
    view_ids : list of str

    Returns
    -------
    dict  {view_id: column_int}
    """
    in_degree = defaultdict(int, {vid: 0 for vid in view_ids})
    children = defaultdict(list)

    for src, targets in graph.items():
        for tgt in targets:
            children[src].append(tgt)
            in_degree[tgt] += 1

    # Kahn's algorithm: process in topological order, propagate max depth.
    column = {vid: 0 for vid in view_ids}
    queue = deque(vid for vid in view_ids if in_degree[vid] == 0)

    while queue:
        src = queue.popleft()
        for tgt in children.get(src, []):
            new_col = column[src] + 1
            if new_col > column.get(tgt, 0):
                column[tgt] = new_col
            in_degree[tgt] -= 1
            if in_degree[tgt] == 0:
                queue.append(tgt)

    return column


# ---------------------------------------------------------------------------
# DAG-tree ordering
# ---------------------------------------------------------------------------

def sort_by_dag_tree(area_configs: list, columns: dict,
                     link_entries: list, sec_mid_addrs: dict) -> list:
    """
    Order views within each DAG column using a tree-expansion rule so that the
    rendered diagram reads like a tree growing left-to-right.

    **Algorithm**

    *Column 0 (roots):* preserve original JSON configuration order.

    *Column N+1:* for each view V, compute a two-part sort key:

    1. **Parent position** — the position (0-based index) of V's parent view in
       column N's already-ordered list.  When V has multiple parents (fan-in),
       take the minimum parent position.  Views with no known parent sort last.

    2. **Source address (descending)** — among siblings that share the same
       parent, the view linked from the *highest* source-section address comes
       first (appears at the top of the column in the SVG, consistent with the
       convention that high addresses render near the top of each view panel).

    The result is that the layout expands like a tree: children of the first
    parent are listed before children of the second parent, and within each
    sibling group the highest-address link is at the top.  Because bin-packing
    processes views in this order, overflow boundaries fall between sibling
    groups rather than splitting them arbitrarily.  ``order_within_column`` is
    thus mostly a no-op — the pre-sort already places each bin's views in the
    correct top-to-bottom visual order.

    Parameters
    ----------
    area_configs : list of dict
        View configs in their current (JSON) order.
    columns : dict  {view_id: col_int}
    link_entries : list of dict
        From ``Links.entries``; each entry has ``from_view``, ``from_sections``
        (list of IDs or None), ``to_view``, and ``to_sections`` keys.
    sec_mid_addrs : dict  {view_id: {section_id: mid_address_float}}
        Pre-computed midpoint address (``address + size/2``) for every section
        in every view.

    Returns
    -------
    list of dict — same configs, re-ordered within each DAG column.
    """
    # Group by DAG column, preserving original JSON index for stable tiebreak.
    by_col: dict = defaultdict(list)
    for i, ac in enumerate(area_configs):
        by_col[columns.get(ac.get('id', ''), 0)].append((i, ac))

    # Build child→parents mapping from link entries.
    child_parents: dict = defaultdict(list)
    for entry in link_entries:
        src = entry.get('from_view', '')
        tgt = entry.get('to_view', '')
        if src and tgt:
            child_parents[tgt].append((src, entry.get('from_sections')))

    result: list = []
    # col_position[vid] = position of vid in its column's ordered list (0-based).
    col_position: dict = {}

    for col in sorted(by_col):
        items = by_col[col]

        if col == 0:
            # Root column — preserve JSON order.
            ordered = [ac for _, ac in sorted(items, key=lambda x: x[0])]
        else:
            def _sort_key(item, _cp=col_position,
                          _le=link_entries, _sm=sec_mid_addrs,
                          _ch=child_parents):
                _, ac = item
                vid = ac.get('id', '')

                # --- Primary: minimum parent position in the previous column ---
                parent_pos = float('inf')
                for parent_vid, _ in _ch.get(vid, []):
                    p = _cp.get(parent_vid, float('inf'))
                    if p < parent_pos:
                        parent_pos = p

                # --- Secondary: mean source-section midpoint address (desc) ---
                addrs = []
                for entry in _le:
                    if entry.get('to_view') != vid:
                        continue
                    from_secs = entry.get('from_sections')
                    # Address-range form: derive mid-address from hex bounds directly.
                    if _is_addr_range_form(from_secs):
                        try:
                            addrs.append(
                                (int(from_secs[0], 16) + int(from_secs[1], 16)) / 2
                            )
                        except ValueError:
                            pass
                    else:
                        for sid, mid in _sm.get(entry.get('from_view', ''), {}).items():
                            if from_secs is None or sid in from_secs:
                                addrs.append(mid)
                src_addr = sum(addrs) / len(addrs) if addrs else 0.0

                return (parent_pos, -src_addr)

            ordered = [ac for _, ac in sorted(items, key=_sort_key)]

        # Record each view's position within this column for the next column.
        for pos, ac in enumerate(ordered):
            col_position[ac.get('id', '')] = pos

        result.extend(ordered)

    return result


# ---------------------------------------------------------------------------
# Column ordering (crossing minimisation)
# ---------------------------------------------------------------------------

def order_within_column(columns: dict, area_views: list,
                        link_entries: list) -> dict:
    """
    Sort areas within each column to minimise link-band crossings.

    For each area B in column C+1, compute a *source midpoint*:
    the vertical midpoint (in source-area pixel coordinates) of the section(s)
    that link to B.  Sorting column C+1 by ascending source midpoint places
    targets in the same top-to-bottom order as their sources.

    Section IDs from each link entry's ``from_sections`` field are used
    directly, which correctly handles multi-section links (e.g. two sections
    linking to one target).

    When a target has no computed source midpoint (e.g., it is a root or
    has no AreaView data), it is placed last in its column.

    Parameters
    ----------
    columns : dict  {view_id: column_int}
    area_views : list of AreaView
        Used to look up the pixel position of link sections in source views.
    link_entries : list of dict
        Validated link entries from ``Links.entries``.  Each entry has
        ``from_view``, ``from_sections`` (list of IDs or None), ``to_view``,
        and ``to_sections`` keys.

    Returns
    -------
    dict  {column_int: [view_id, ...]}
        Views ordered top-to-bottom within each column.
    """
    # Build area_view lookup  {view_id: AreaView}
    av_by_id = {av.view_id: av for av in area_views}

    source_midpoints = defaultdict(list)

    # Use explicit section IDs from each link entry.  Handles multi-section
    # links where a single section does not contain the full target address
    # range.
    for entry in link_entries:
        src_id = entry.get('from_view')
        tgt_id = entry.get('to_view')
        from_sections = entry.get('from_sections')  # list of IDs or None
        src_av = av_by_id.get(src_id)
        if src_av is None:
            continue
        mid = _find_link_midpoint_by_sections(src_av, from_sections)
        if mid is not None:
            source_midpoints[tgt_id].append(src_av.pos_y + mid)

    # Compute mean source midpoint per target
    def key(aid):
        mids = source_midpoints.get(aid, [])
        if not mids:
            return float('inf')
        return sum(mids) / len(mids)

    # Group views by column and sort within each column
    by_column = defaultdict(list)
    for vid, col in columns.items():
        by_column[col].append(vid)

    result = {}
    for col, vids in by_column.items():
        result[col] = sorted(vids, key=key)

    return result


def _is_addr_range_form(from_sections) -> bool:
    """Return True when from_sections is the address-range form ["0xLO", "0xHI"]."""
    return (isinstance(from_sections, list) and len(from_sections) == 2
            and isinstance(from_sections[0], str)
            and from_sections[0].startswith('0x'))


def _find_link_midpoint_by_sections(src_av, from_sections) -> float | None:
    """
    Return the pixel midpoint of the link band in src_av for named sections.

    Collects all sections in src_av matching ``from_sections`` (by ID), then
    returns the pixel midpoint of the span from the lowest start address to the
    highest end address across those sections.

    When ``from_sections`` is None (link covers the whole source view), uses
    every non-zero-size section.

    Address-range form (``["0xLO", "0xHI"]``): computes the midpoint address
    directly from the two hex bounds and converts it to pixels without requiring
    a matching section ID.  This handles partial-section ranges that do not
    align with any named section boundary.

    Returns None if no matching sections are found.
    """
    # Address-range form: ["0xLO", "0xHI"] — compute mid-address directly.
    if _is_addr_range_form(from_sections):
        try:
            lo = int(from_sections[0], 16)
            hi = int(from_sections[1], 16)
        except ValueError:
            return None
        mid_addr = (lo + hi) / 2
        for sub in src_av.get_split_area_views():
            if sub.start_address <= mid_addr <= sub.end_address:
                return sub.address_to_py_actual(mid_addr) + sub.pos_y - src_av.pos_y
        return None

    # Section-ID list (or None = whole view).
    found = []
    for sub in src_av.get_split_area_views():
        for sec in sub.sections.get_sections():
            if sec.size == 0:
                continue
            if from_sections is None or sec.id in from_sections:
                found.append((sec, sub))

    if not found:
        return None

    lo_addr = min(sec.address for sec, sub in found)
    hi_addr = max(sec.address + sec.size for sec, sub in found)
    mid_addr = (lo_addr + hi_addr) / 2

    # Find the sub-area that contains mid_addr and convert to pixels
    for sub in src_av.get_split_area_views():
        if sub.start_address <= mid_addr <= sub.end_address:
            return sub.address_to_py_actual(mid_addr) + sub.pos_y - src_av.pos_y

    # Fallback: average of individual section pixel midpoints
    total = 0.0
    for sec, sub in found:
        mid = sec.address + sec.size / 2
        total += sub.address_to_py_actual(mid) + sub.pos_y - src_av.pos_y
    return total / len(found)


# ---------------------------------------------------------------------------
# Algo-2: height-rebalancing column assignment
# ---------------------------------------------------------------------------

def rebalance_columns(
    columns: dict,
    area_configs: list,
    area_heights: dict,
    link_entries: list,
    target_ratio: float = 1.3,
    outlier_factor: float = 1.5,
    col_width: float = 230.0,
    col_gap: float = 120.0,
    padding: float = 50.0,
) -> dict:
    """
    Algo-2: rebalance visual column heights to improve the canvas aspect ratio.

    Starting from the DAG column assignment produced by ``assign_columns()``,
    this function adjusts which *visual* column each view lands in so that no
    column is taller than ``target_ratio × canvas_width``.

    **Algorithm (per column, processed left to right)**

    For each column whose total stacked height exceeds the target:

    Pass 1 — outlier extraction
        A view whose estimated height exceeds ``outlier_factor × column_average``
        is moved to the next visual column.  This handles a single dominant view
        sitting in the middle of the column (e.g. a large peripheral map).
        The tallest outlier is extracted first; the column is re-evaluated
        before looking for further outliers.

    Pass 2 — trailing overflow
        If no outlier is found but the column is still over target, the bottom
        view in tree order is moved to the next visual column.  This handles
        the case where several moderately sized views collectively overflow.

    After each move the target height is recomputed from the new (wider) canvas
    width, giving subsequent columns a larger budget (rolling budget update).

    Descendant propagation
        When a view is moved from visual column N to N+1, every descendant
        currently assigned to column ≤ N+1 is pushed to N+2 (recursively),
        preserving the invariant ``visual_col[child] > visual_col[parent]``.

    Non-adjacent links
        A moved view's parent is now two or more visual columns to its left.
        Such non-adjacent link bands are accepted by the renderer and are
        visually acceptable for memory-map diagrams.

    Parameters
    ----------
    columns : dict  {view_id: dag_col_int}
        Initial DAG column assignment from ``assign_columns()``.  Not modified.
    area_configs : list of dict
        Views in tree order, as returned by ``sort_by_dag_tree()``.
        The ordering of each visual column is derived from this list.
    area_heights : dict  {view_id: float}
        Estimated pixel height per view from ``_estimate_area_height()``.
    link_entries : list of dict
        From ``Links.entries``; each entry has ``from_view`` and ``to_view``
        keys used to build the parent→child graph for descendant propagation.
    target_ratio : float
        Desired max(column_height) / canvas_width ratio (default 1.3).
    outlier_factor : float
        Outlier threshold as a multiple of column average height (default 1.5).
    col_width : float
        Visual column width in pixels used for canvas-width estimation (default 230).
    col_gap : float
        Gap between adjacent visual columns used for estimation (default 120).
    padding : float
        Vertical gap between stacked views within a column (default 50).

    Returns
    -------
    dict  {view_id: visual_col_int}
        Updated column assignment.  Values may differ from the input DAG
        columns when views have been extracted or overflowed.
    """
    if not area_configs:
        return dict(columns)

    all_ids = [ac.get('id', '') for ac in area_configs if ac.get('id')]

    # Build directed children map from link entries.
    children: dict = {vid: [] for vid in all_ids}
    for entry in link_entries or []:
        src = entry.get('from_view', '')
        tgt = entry.get('to_view', '')
        if src in children and tgt in children and tgt not in children[src]:
            children[src].append(tgt)

    vis_col = dict(columns)

    _CANVAS_LEFT = 50.0  # left-side padding, matches _auto_layout PADDING

    def _canvas_width() -> float:
        n = max(vis_col.values(), default=0) + 1
        return _CANVAS_LEFT + n * col_width + (n - 1) * col_gap

    def _col_height(c: int) -> float:
        vids = [vid for vid in all_ids if vis_col.get(vid, 0) == c]
        if not vids:
            return 0.0
        hs = [area_heights.get(vid, 400.0) for vid in vids]
        return sum(hs) + padding * max(0, len(hs) - 1)

    def _views_ordered(c: int) -> list:
        """IDs of views in column c, in area_configs (tree) order."""
        return [ac.get('id', '') for ac in area_configs
                if ac.get('id') and vis_col.get(ac.get('id', ''), 0) == c]

    def _push_descendants(vid: str, min_col: int) -> None:
        """Ensure every descendant of vid is at visual column >= min_col."""
        for child in children.get(vid, []):
            if vis_col.get(child, 0) < min_col:
                vis_col[child] = min_col
                _push_descendants(child, min_col + 1)

    c = 0
    while True:
        vids = _views_ordered(c)
        if not vids:
            break  # no more populated columns

        target_h = _canvas_width() * target_ratio

        if _col_height(c) <= target_h or len(vids) <= 1:
            c += 1
            continue

        # --- Pass 1: outlier extraction ---
        heights = {vid: area_heights.get(vid, 400.0) for vid in vids}
        avg_h = sum(heights.values()) / len(heights)
        outliers = [vid for vid in vids if heights[vid] > outlier_factor * avg_h]
        if outliers:
            tallest = max(outliers, key=lambda v: heights[v])
            vis_col[tallest] = c + 1
            _push_descendants(tallest, c + 2)
            continue  # re-evaluate column c; target_h also updates (rolling budget)

        # --- Pass 2: trailing overflow ---
        # No outlier found; overflow the bottom view in tree order.
        vids_now = _views_ordered(c)
        if len(vids_now) > 1:
            bottom = vids_now[-1]
            vis_col[bottom] = c + 1
            _push_descendants(bottom, c + 2)
        # Re-evaluate column c (don't advance c yet).

    return vis_col


# ---------------------------------------------------------------------------
# Algo-3: routing lane planning for non-adjacent links
# ---------------------------------------------------------------------------

def plan_routing_lanes(
    vis_col: dict,
    link_entries: list,
    area_views: list,
    col_width: float = 230.0,
    lane_height: float = 20.0,
    lane_padding: float = 5.0,
    title_space: float = 60.0,
) -> dict:
    """
    Algo-3: plan horizontal routing lanes for non-adjacent links.

    When ``rebalance_columns()`` moves a view so that a link spans
    col N-1 → col N+1 (skipping col N), the middle Bezier crosses all of
    col N's content.  This function computes a horizontal routing lane in
    each skipped column so the link can be re-routed around it.

    **Algorithm (per intermediate column col_i)**

    1. Collect all *adjacent* links col_{i-1} → col_i, sorted by source y.
    2. Find the bracket pair whose source y straddles the non-adjacent link's
       source y.  Their destination y values define the *zero-crossing
       interval* (ZCI) — placing the lane within this interval guarantees the
       routed path crosses none of the adjacent connectors.
    3. Enumerate gaps between views in col_i that overlap the ZCI and are
       tall enough for ``lane_height + 2*lane_padding``.
    4. Pick the gap whose best valid position is closest to the ideal y
       (interpolated from ZCI bounds).
    5. For multiple non-adjacent links sharing the same intermediate column,
       requests are sorted by ideal y and assigned greedily so they do not
       overlap.

    Parameters
    ----------
    vis_col : dict  {view_id: col_int}
        Visual column assignment after ``rebalance_columns()``.
    link_entries : list of dict
        From ``Links.entries``; each entry has ``from_view``, ``to_view``,
        ``from_sections``, ``to_sections`` keys.
    area_views : list of AreaView
        After ``_auto_layout()``; used to look up pixel positions and
        section midpoints.
    col_width : float
        View width in pixels (default 230).
    lane_height : float
        Height of the routing lane rectangle (default 20).
    lane_padding : float
        Vertical padding around each lane (default 5).
    title_space : float
        Y reserved above views for column titles (default 60).

    Returns
    -------
    dict  {entry_index: [lane_dict, ...]}
        Keyed by 0-based index into ``link_entries``.  Each lane dict::

            {'col': int, 'x_left': float, 'x_right': float,
             'y': float, 'height': float}

        Multiple dicts per entry when the link skips more than one column.
        Entries without non-adjacent routing lanes are absent from the dict.
    """
    if not link_entries or not area_views:
        return {}

    av_by_id = {av.view_id: av for av in area_views}

    # ------------------------------------------------------------------
    # Per-link pixel y (absolute SVG coordinates)
    # ------------------------------------------------------------------
    def _abs_y(av, sections):
        rel = _find_link_midpoint_by_sections(av, sections)
        if rel is None:
            return av.pos_y + av.size_y / 2
        return av.pos_y + rel

    src_y = {}  # entry_idx → float
    dst_y = {}
    for idx, entry in enumerate(link_entries):
        src_av = av_by_id.get(entry.get('from_view', ''))
        dst_av = av_by_id.get(entry.get('to_view', ''))
        src_y[idx] = _abs_y(src_av, entry.get('from_sections')) if src_av else None
        dst_y[idx] = _abs_y(dst_av, entry.get('to_sections')) if dst_av else None

    # ------------------------------------------------------------------
    # Column geometry helpers
    # ------------------------------------------------------------------
    col_to_views = defaultdict(list)
    for av in area_views:
        c = vis_col.get(av.view_id)
        if c is not None:
            col_to_views[c].append(av)

    def _col_x_bounds(c):
        views = col_to_views.get(c, [])
        if not views:
            return None, None
        return (min(av.pos_x for av in views),
                max(av.pos_x + av.size_x for av in views))

    def _col_gaps(c):
        """Return list of (gap_top, gap_bottom) intervals in column c."""
        views = col_to_views.get(c, [])
        if not views:
            return []
        intervals = sorted((av.pos_y, av.pos_y + av.size_y) for av in views)
        # Merge overlapping view intervals.
        merged = [list(intervals[0])]
        for a, b in intervals[1:]:
            if a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        gaps = []
        if merged[0][0] > title_space + 0.5:
            gaps.append((title_space, merged[0][0]))
        for i in range(len(merged) - 1):
            gt, gb = merged[i][1], merged[i + 1][0]
            if gb > gt + 0.5:
                gaps.append((gt, gb))
        # Trailing gap below the bottommost view (needed for bracket case C).
        gaps.append((merged[-1][1], merged[-1][1] + 2000))
        return gaps

    # ------------------------------------------------------------------
    # Adjacent links grouped by (from_col, to_col)
    # ------------------------------------------------------------------
    col_pair_links = defaultdict(list)  # {(fc, tc): [(idx, entry), ...]}
    for idx, entry in enumerate(link_entries):
        fc = vis_col.get(entry.get('from_view', ''))
        tc = vis_col.get(entry.get('to_view', ''))
        if fc is not None and tc is not None:
            col_pair_links[(fc, tc)].append((idx, entry))

    # ------------------------------------------------------------------
    # Find non-adjacent links and compute routing requests per column
    # ------------------------------------------------------------------
    # lane_requests[col_i] = list of (entry_idx, y_ideal, zci_lo, zci_hi, src_y)
    lane_requests = defaultdict(list)

    for idx, entry in enumerate(link_entries):
        fc = vis_col.get(entry.get('from_view', ''))
        tc = vis_col.get(entry.get('to_view', ''))
        if fc is None or tc is None or tc <= fc + 1:
            continue  # not non-adjacent
        y_src = src_y.get(idx)
        y_dst_link = dst_y.get(idx)
        if y_src is None:
            continue

        for col_i in range(fc + 1, tc):
            # Interpolated natural path Y for this link at column col_i.
            # This is where a straight connector line would pass through.
            if y_dst_link is not None and tc != fc:
                y_through = y_src + (y_dst_link - y_src) * (col_i - fc) / (tc - fc)
            else:
                y_through = y_src

            # Adjacent links from col_{i-1} to col_i
            adj_raw = col_pair_links.get((col_i - 1, col_i), [])
            adj = [
                (aidx, sy, dy)
                for aidx, e in adj_raw
                for sy, dy in [(src_y.get(aidx), dst_y.get(aidx))]
                if sy is not None and dy is not None
            ]
            adj.sort(key=lambda t: t[2])  # sort by destination y

            INF = float('inf')
            if not adj:
                zci_lo, zci_hi, y_ideal = -INF, INF, y_through
            elif y_through <= adj[0][2]:        # bracket A: above all adj destinations
                zci_lo, zci_hi = -INF, adj[0][2]
                y_ideal = y_through
            elif y_through >= adj[-1][2]:       # bracket C: below all adj destinations
                zci_lo, zci_hi = adj[-1][2], INF
                y_ideal = y_through
            else:                               # bracket B: between two adj destinations
                zci_lo = zci_hi = None
                for k in range(len(adj) - 1):
                    if adj[k][2] <= y_through <= adj[k + 1][2]:
                        zci_lo, zci_hi = adj[k][2], adj[k + 1][2]
                        y_ideal = y_through
                        break
                if zci_lo is None:
                    zci_lo, zci_hi, y_ideal = -INF, INF, y_through

            lane_requests[col_i].append((idx, y_ideal, zci_lo, zci_hi, y_src))

    if not lane_requests:
        return {}

    # ------------------------------------------------------------------
    # Assign lane positions within each column
    # ------------------------------------------------------------------
    needed = lane_height + 2 * lane_padding
    col_lane_assignments = defaultdict(list)  # {col_i: [(entry_idx, y), ...]}

    for col_i, requests in lane_requests.items():
        # Sort by y_ideal; use source y as tiebreak so same-bracket requests
        # get a deterministic spread order.
        requests.sort(key=lambda r: (r[1], r[4]))
        # Pre-spread: when multiple requests share the same y_ideal (e.g. all
        # bracket case C), push each successive one forward by one lane pitch
        # so the nudge loop has distinct starting points and can place them
        # without collision.
        _step = lane_height + 2 * lane_padding
        for _i in range(1, len(requests)):
            if requests[_i][1] < requests[_i - 1][1] + _step:
                _ei, _, _zlo, _zhi, _sy = requests[_i]
                requests[_i] = (_ei, requests[_i - 1][1] + _step, _zlo, _zhi, _sy)
        x_left, x_right = _col_x_bounds(col_i)
        if x_left is None:
            continue
        gaps = _col_gaps(col_i)
        assigned = []  # [(y_center, height), ...] already placed in this col

        for entry_idx, y_ideal, zci_lo, zci_hi, _sy in requests:
            INF = float('inf')
            best_y = None
            best_dist = INF

            for gap_top, gap_bot in gaps:
                if gap_bot - gap_top < needed:
                    continue
                # Gap must overlap ZCI
                if zci_hi != INF and gap_top >= zci_hi:
                    continue
                if zci_lo != -INF and gap_bot <= zci_lo:
                    continue

                # Feasible y range within gap
                y_lo = gap_top + lane_height / 2 + lane_padding
                y_hi = gap_bot - lane_height / 2 - lane_padding
                if zci_lo != -INF:
                    y_lo = max(y_lo, zci_lo + lane_height / 2)
                if zci_hi != INF:
                    y_hi = min(y_hi, zci_hi - lane_height / 2)
                if y_hi < y_lo:
                    continue

                candidate = max(y_lo, min(y_hi, y_ideal))

                # Avoid overlapping already-assigned lanes in this gap.
                # Sweep upward past any blocking lanes (sorted ascending),
                # which is correct because requests are also sorted ascending
                # by y_ideal — earlier requests occupy lower positions.
                for ey, eh in sorted(assigned, key=lambda t: t[0]):
                    min_sep = (lane_height + eh) / 2 + lane_padding
                    if abs(candidate - ey) < min_sep:
                        candidate = ey + min_sep   # push up past this lane
                        if candidate > y_hi:
                            candidate = None
                            break

                # If upward sweep exceeded y_hi (e.g. y_ideal > y_hi and lanes
                # are packed at the top of the gap), try sweeping downward instead.
                if candidate is None:
                    candidate = max(y_lo, min(y_hi, y_ideal))
                    for ey, eh in sorted(assigned, key=lambda t: t[0], reverse=True):
                        min_sep = (lane_height + eh) / 2 + lane_padding
                        if abs(candidate - ey) < min_sep:
                            candidate = ey - min_sep  # push down past this lane
                            if candidate < y_lo:
                                candidate = None
                                break

                if candidate is None:
                    continue

                # Final collision check (catches any edge case in the sweep)
                if any(abs(candidate - ey) < (lane_height + eh) / 2 + lane_padding
                       for ey, eh in assigned):
                    continue

                dist = abs(candidate - y_ideal)
                if dist < best_dist:
                    best_dist = dist
                    best_y = candidate

            if best_y is None:
                # Fallback: place in the closest gap ignoring ZCI, with collision
                # avoidance (bidirectional sweep so clamped-to-top lanes pack down).
                for gap_top, gap_bot in gaps:
                    if gap_bot - gap_top < needed:
                        continue
                    fb_lo = gap_top + lane_height / 2 + lane_padding
                    fb_hi = gap_bot - lane_height / 2 - lane_padding
                    if fb_hi < fb_lo:
                        continue
                    fb = max(fb_lo, min(fb_hi, y_ideal))
                    # Upward sweep
                    for ey, eh in sorted(assigned, key=lambda t: t[0]):
                        sep = (lane_height + eh) / 2 + lane_padding
                        if abs(fb - ey) < sep:
                            fb = ey + sep
                            if fb > fb_hi:
                                fb = None
                                break
                    # Downward sweep if upward failed
                    if fb is None:
                        fb = max(fb_lo, min(fb_hi, y_ideal))
                        for ey, eh in sorted(assigned, key=lambda t: t[0], reverse=True):
                            sep = (lane_height + eh) / 2 + lane_padding
                            if abs(fb - ey) < sep:
                                fb = ey - sep
                                if fb < fb_lo:
                                    fb = None
                                    break
                    if fb is None:
                        continue
                    if any(abs(fb - ey) < (lane_height + eh) / 2 + lane_padding
                           for ey, eh in assigned):
                        continue
                    best_y = fb
                    break
                if best_y is None:
                    best_y = y_ideal  # last resort

            assigned.append((best_y, lane_height))
            col_lane_assignments[col_i].append((entry_idx, best_y))

    # ------------------------------------------------------------------
    # Build result dict indexed by entry_idx
    # ------------------------------------------------------------------
    result = defaultdict(list)
    for col_i, lane_list in col_lane_assignments.items():
        x_left, x_right = _col_x_bounds(col_i)
        for entry_idx, y in lane_list:
            result[entry_idx].append({
                'col': col_i,
                'x_left': x_left,
                'x_right': x_right,
                'y': y,
                'height': lane_height,
            })

    # Sort lanes left-to-right (by x_left) so waypoints are in traversal order.
    return {idx: sorted(lanes, key=lambda d: d['x_left'])
            for idx, lanes in result.items()}


def vertical_align_columns(
    vis_col: dict,
    link_entries: list,
    area_views: list,
    top_margin: float = 60.0,
) -> dict:
    """
    Algo-4: compute per-column y-offsets that minimise total link length.

    All columns are initially top-aligned, which forces short columns to
    connect to distant y-positions in taller neighbours.  This function finds
    the vertical shift for each column that brings its link attachment points
    as close as possible to those of the adjacent column, reducing the overall
    wiring length.

    The tallest column (by vertical pixel span) is the **anchor** and stays
    fixed (offset 0).  Every other column is shifted by the L1-optimal amount
    — the weighted median of the desired offsets implied by all links incident
    to already-placed neighbours.  Columns are processed in BFS order outward
    from the anchor so that offsets propagate through the DAG consistently.

    Every non-anchor column's offset is clamped so that its views remain
    entirely within the anchor column's y-extent [anchor_top, anchor_bottom].
    This guarantees the overall diagram height and height-to-width ratio are
    unchanged by the alignment step: the anchor column is the sole determinant
    of diagram height, exactly as it is in the top-aligned baseline.

    Parameters
    ----------
    vis_col : dict  {view_id: col_int}
    link_entries : list of dict
        Validated link entry dicts from ``Links.entries``.
    area_views : list of AreaView
        Preliminary area views with top-aligned positions (from ``_auto_layout``
        + crossing minimisation).  Used only to read link attachment y-coords;
        the caller rebuilds AreaViews after applying the returned offsets.
    top_margin : float
        Not used directly after the anchor-bounding clamp was introduced;
        retained for API compatibility.

    Returns
    -------
    dict  {col_int: y_offset_float}
    """
    if not area_views or not link_entries:
        return {}

    av_by_id = {av.view_id: av for av in area_views}

    # Group views by visual column
    col_views = defaultdict(list)
    for av in area_views:
        c = vis_col.get(av.view_id)
        if c is not None:
            col_views[c].append(av)

    if len(col_views) <= 1:
        return {}  # single column — nothing to shift

    # Tallest column (by pixel span) is the anchor; it does not move
    def _col_span(c):
        views = col_views[c]
        if not views:
            return 0.0
        return (max(av.pos_y + av.size_y for av in views)
                - min(av.pos_y for av in views))

    anchor = max(col_views.keys(), key=_col_span)

    # Absolute SVG y of a link's attachment point on av
    def _abs_y(av, sections):
        rel = _find_link_midpoint_by_sections(av, sections)
        return (av.pos_y + rel) if rel is not None else (av.pos_y + av.size_y / 2)

    # Build list of (from_col, from_y, to_col, to_y) for every link
    link_data = []
    for entry in link_entries:
        fc = vis_col.get(entry.get('from_view', ''))
        tc = vis_col.get(entry.get('to_view', ''))
        if fc is None or tc is None or fc == tc:
            continue
        src_av = av_by_id.get(entry.get('from_view', ''))
        dst_av = av_by_id.get(entry.get('to_view', ''))
        if src_av is None or dst_av is None:
            continue
        # Only adjacent links (column span == 1) drive vertical placement.
        # Non-adjacent links are handled by routing lanes and should not pull
        # a column away from its nearest neighbour.
        if abs(fc - tc) != 1:
            continue
        sy = _abs_y(src_av, entry.get('from_sections'))
        dy = _abs_y(dst_av, entry.get('to_sections'))
        link_data.append((fc, sy, tc, dy))

    # Pre-compute routing-lane desired offsets for source columns of non-adjacent
    # links.  For a link that skips one or more columns, the routing lane in the
    # first gap (fc → fc+1) represents an additional "desired position" for the
    # source section.
    #
    # Critical for bracket-C (source below all adjacent sources in the gap):
    # the routing lane is placed in the *trailing gap below the last view in
    # col fc+1*, not at adj[-1][1] + 2*_lane_h which lands inside the view
    # body and underestimates the actual lane y by a full view height.  We use
    # col_views to estimate the true gap start, and apply rank-based lane
    # spreading so each link in the bracket gets its own y_ideal (matching the
    # 25-px collision-avoidance step used by plan_routing_lanes).
    _lane_h           = 20.0  # must match plan_routing_lanes lane_height
    _lane_padding_est =  5.0  # must match plan_routing_lanes lane_padding
    _lane_step = _lane_h + _lane_padding_est   # 25 px between consecutive lanes

    _col_pair_adj: dict = defaultdict(list)   # (fc,tc) → [(sy,dy), ...]
    for fc, sy, tc, dy in link_data:
        _col_pair_adj[(fc, tc)].append((sy, dy))

    # Bottom edge of every column's view span — used to locate trailing gaps.
    _col_bottom_edge: dict = {
        c: max(av.pos_y + av.size_y for av in views)
        for c, views in col_views.items() if views
    }

    # Pre-compute inter-view gap midpoints per column (used in Pass 2 below).
    # Routing lanes land in these gaps, so gap midpoints are better estimates
    # for desired source-column offsets than y_through from stale initial positions.
    def _inter_view_gap_midpoints(c):
        """Return sorted list of (gap_top, gap_bot, midpoint) for inter-view gaps."""
        views = col_views.get(c, [])
        if not views:
            return []
        intervals = sorted((av.pos_y, av.pos_y + av.size_y) for av in views)
        merged = [list(intervals[0])]
        for a, b in intervals[1:]:
            if a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        return [
            (merged[i][1], merged[i + 1][0],
             (merged[i][1] + merged[i + 1][0]) / 2)
            for i in range(len(merged) - 1)
            if merged[i + 1][0] > merged[i][1] + 0.5
        ]

    def _best_gap_midpoint(c, y_ref):
        """Midpoint of the inter-view gap in column c nearest to y_ref.
        Falls back to y_ref when no inter-view gap exists."""
        gaps = _inter_view_gap_midpoints(c)
        if not gaps:
            return y_ref
        return min(gaps, key=lambda g: abs(g[2] - y_ref))[2]

    # Pass 1: group non-adjacent links by their first gap (efc, efc+1).
    # Stores (esrc_y, edst_y, entry, efc, etc) so Pass 2 can compute y_through.
    _gap_groups: dict = defaultdict(list)
    for entry in link_entries:
        efc = vis_col.get(entry.get('from_view', ''))
        etc = vis_col.get(entry.get('to_view', ''))
        if efc is None or etc is None or abs(efc - etc) <= 1:
            continue  # adjacent or same-column — already in link_data
        src_av = av_by_id.get(entry.get('from_view', ''))
        dst_av = av_by_id.get(entry.get('to_view', ''))
        if src_av is None or dst_av is None:
            continue
        esrc_y = _abs_y(src_av, entry.get('from_sections'))
        edst_y = _abs_y(dst_av, entry.get('to_sections'))
        _gap_groups[(efc, efc + 1)].append((esrc_y, edst_y, entry, efc, etc))

    routing_lane_desired: dict = defaultdict(list)  # col → [desired_offset, ...]
    _non_adj_info: list = []  # (esrc_y, edst_y, entry, efc, etc) for Phase 2c/2.5
    _host_col_desires: dict = defaultdict(list)  # retained for API; no longer populated

    # Pass 2: compute the routing-lane desired offset for each non-adjacent link's
    # source column.
    #
    # The routing lane for a link efc→etc lands in an inter-view gap of col
    # gap_fc1 (efc+1).  The best estimate of lane y is the midpoint of the
    # inter-view gap nearest to y_through.  This is more accurate than y_through
    # itself because y_through uses the initial top-aligned destination positions,
    # which are stale: all non-anchor columns start stacked at the top before
    # vertical_align_columns applies offsets.  Using the gap midpoint directly
    # aligns the source column's median with the visual middle of the gap where
    # routing lanes actually land.
    for (gap_fc, gap_fc1), group in _gap_groups.items():
        for esrc_y, edst_y, entry, efc, etc in group:
            y_through = esrc_y + (edst_y - esrc_y) / max(1, etc - efc)
            y_ideal = _best_gap_midpoint(gap_fc1, y_through)
            routing_lane_desired[efc].append(y_ideal - esrc_y)
            _non_adj_info.append((esrc_y, edst_y, entry, efc, etc))

    # Phase 1: BFS to establish processing order without committing offsets.
    # We separate discovery (BFS order) from offset computation so that each
    # column's offset is computed using ALL already-placed neighbours, not only
    # the one that happened to discover it in the BFS.
    bfs_order = [anchor]
    in_order  = {anchor}
    queue     = deque([anchor])
    while queue:
        cur = queue.popleft()
        for fc, sy, tc, dy in link_data:
            for nb in (tc if fc == cur else fc if tc == cur else None,):
                if nb is not None and nb not in in_order:
                    in_order.add(nb)
                    bfs_order.append(nb)
                    queue.append(nb)

    # Phase 2: compute offset for each column in BFS order.
    # Each column uses the median of desired offsets from ALL already-placed
    # neighbours (not just the one that triggered BFS discovery).
    offsets = {anchor: 0.0}
    for col in bfs_order[1:]:               # anchor already placed
        desired = []
        for fc, sy, tc, dy in link_data:
            if fc == col and tc in offsets:
                # col is source: want sy + offsets[col] ≈ dy + offsets[tc]
                desired.append(dy + offsets[tc] - sy)
            elif tc == col and fc in offsets:
                # col is dest:   want sy + offsets[fc] ≈ dy + offsets[col]
                desired.append(sy + offsets[fc] - dy)
        # Also include routing-lane alignment for non-adjacent links whose
        # source is in this column.  These offsets carry the same weight as
        # adjacent-link offsets and shift the median toward a placement that
        # avoids near-parallel routing-line collisions at no extra L1 cost.
        desired.extend(routing_lane_desired.get(col, []))
        # Routing-lane hosting desires (bracket C): this column's bottom edge
        # determines where the trailing-gap routing lanes land.  Add a desired
        # offset for each lane so the lane y stays close to its source section.
        for esrc_y, efc, rank in _host_col_desires.get(col, []):
            if efc in offsets:
                source_y_eff = esrc_y + offsets[efc]
                col_bot_h = _col_bottom_edge.get(col)
                if col_bot_h is not None:
                    lane_y0 = col_bot_h + _lane_h / 2 + _lane_padding_est + rank * _lane_step
                    desired.append(source_y_eff - lane_y0)
        if desired:
            desired.sort()
            offsets[col] = desired[len(desired) // 2]   # L1-optimal median
        else:
            offsets[col] = 0.0

    # Any column not reachable from the anchor keeps offset 0
    for c in col_views:
        offsets.setdefault(c, 0.0)

    # Phase 2b: columns isolated from the anchor (no path via adjacent links)
    # do not appear in bfs_order, so Phase 2 never applies their desired
    # offsets.  Mirror Phase 2 for these columns: combine adjacent-link desired
    # (from link_data) with routing_lane_desired, then take the L1 median.
    # Process in column-index order so earlier non-BFS offsets propagate to
    # neighbours within the same isolated cluster.
    for c in sorted(c for c in col_views if c not in in_order):
        desired_c: list[float] = list(routing_lane_desired.get(c, []))
        for fc, sy, tc, dy in link_data:
            if fc == c and tc in offsets:
                desired_c.append(dy + offsets[tc] - sy)
            elif tc == c and fc in offsets:
                desired_c.append(sy + offsets[fc] - dy)
        # Routing-lane hosting desires (bracket C): this column's bottom edge
        # determines where the trailing-gap routing lanes land.  Add a desired
        # offset for each lane so the lane y stays close to its source section.
        for esrc_y, efc, rank in _host_col_desires.get(c, []):
            if efc in offsets:
                source_y_eff = esrc_y + offsets[efc]
                col_bot_h = _col_bottom_edge.get(c)
                if col_bot_h is not None:
                    lane_y0 = col_bot_h + _lane_h / 2 + _lane_padding_est + rank * _lane_step
                    desired_c.append(source_y_eff - lane_y0)
        if desired_c:
            desired_c.sort()
            offsets[c] = desired_c[len(desired_c) // 2]
            in_order.add(c)  # mark placed so Phase 2c can use this offset

    # Phase 2.5: cascade routing desires for multi-hop non-adjacent links.
    # _gap_groups only covers the first gap (efc, efc+1).  For links that skip
    # ≥ 2 columns (span > 2) the intermediate columns from efc+2 onward receive
    # no routing desires, so they are positioned only by adjacent links — which
    # can leave the cascaded routing lanes far from the source section y,
    # producing long diagonal routing wires.
    #
    # Fix: compute the routing-lane y that plan_routing_lanes will assign for
    # the first gap (using post-Phase-2 effective coordinates), then add a
    # hosting desire to every subsequent intermediate column c so its
    # trailing-gap lane also lands at that same y.  Finish with a second BFS
    # pass so adjacent-link children of updated columns pick up the new offsets.
    _cascade_extra: dict = defaultdict(list)   # col → [extra desired_delta, ...]

    for esrc_y, edst_y, entry, efc, etc in _non_adj_info:
        if etc - efc <= 2:
            continue  # span ≤ 2: already fully covered by _gap_groups
        c1 = efc + 1

        # Effective routing-lane y at gap (efc, c1) using y_through + source offset.
        y_through_c1 = esrc_y + (edst_y - esrc_y) / max(1, etc - efc)
        prev_y = y_through_c1 + offsets.get(efc, 0.0)

        # Add hosting desire for each subsequent intermediate column c so its
        # inter-column gap can accommodate the cascaded routing lane at prev_y.
        for c in range(c1 + 1, etc):
            col_bot = _col_bottom_edge.get(c)
            if col_bot is None:
                continue
            # y_through at col c, effective (source offset applied)
            y_through_c = esrc_y + (edst_y - esrc_y) * (c - efc) / max(1, etc - efc)
            y_through_c_eff = y_through_c + offsets.get(efc, 0.0)
            lane_y0 = col_bot + _lane_h / 2 + _lane_padding_est
            _cascade_extra[c].append(y_through_c_eff - lane_y0)

    # Second BFS pass: re-run Phase 2 with cascade extras so affected columns
    # and their adjacent-link descendants all receive updated offsets.
    if _cascade_extra:
        # Second BFS pass: recompute BFS-reachable column offsets using cascade
        # extras.  Use a fresh offsets_2nd dict (seeded only with the anchor) so
        # stale first-pass values for as-yet-unprocessed descendants don't
        # create circular anchoring (e.g. dev2's 210 pulling bus0 back to 210).
        offsets_2nd: dict = {anchor: 0.0}
        for col in bfs_order[1:]:
            desired = []
            for fc, sy, tc, dy in link_data:
                if fc == col and tc in offsets_2nd:
                    desired.append(dy + offsets_2nd[tc] - sy)
                elif tc == col and fc in offsets_2nd:
                    desired.append(sy + offsets_2nd[fc] - dy)
            desired.extend(routing_lane_desired.get(col, []))
            for esrc_y, efc, rank in _host_col_desires.get(col, []):
                if efc in offsets_2nd:
                    source_y_eff = esrc_y + offsets_2nd[efc]
                    col_bot_h    = _col_bottom_edge.get(col)
                    if col_bot_h is not None:
                        lane_y0 = col_bot_h + _lane_h / 2 + _lane_padding_est + rank * _lane_step
                        desired.append(source_y_eff - lane_y0)
            desired.extend(_cascade_extra.get(col, []))
            if desired:
                desired.sort()
                offsets_2nd[col] = desired[len(desired) // 2]
            # else: column has no desires; keep first-pass offset (don't add to offsets_2nd)
        # Merge updated BFS offsets into the main dict; Phase 2b columns that were
        # not in bfs_order retain their first-pass offsets.
        offsets.update(offsets_2nd)
        # Apply cascade desires to isolated (Phase 2b) columns if they appear in
        # _cascade_extra.  Use the now-merged offsets so BFS parents' updated
        # values propagate correctly.
        for c in sorted(c for c in _cascade_extra if c not in offsets_2nd):
            desired_c: list[float] = list(routing_lane_desired.get(c, []))
            for fc, sy, tc, dy in link_data:
                if fc == c and tc in offsets:
                    desired_c.append(dy + offsets[tc] - sy)
                elif tc == c and fc in offsets:
                    desired_c.append(sy + offsets[fc] - dy)
            for esrc_y, efc, rank in _host_col_desires.get(c, []):
                if efc in offsets:
                    source_y_eff = esrc_y + offsets[efc]
                    col_bot_h    = _col_bottom_edge.get(c)
                    if col_bot_h is not None:
                        lane_y0 = col_bot_h + _lane_h / 2 + _lane_padding_est + rank * _lane_step
                        desired_c.append(source_y_eff - lane_y0)
            desired_c.extend(_cascade_extra[c])
            if desired_c:
                desired_c.sort()
                offsets[c] = desired_c[len(desired_c) // 2]

    # Phase 2c: destination-column desired offsets for non-adjacent links.
    # Pure-destination views (no adjacent link pulling them toward their routing
    # lane) sit at offset 0.  Use the already-computed source offsets to
    # estimate where the routing lane will arrive at the destination gap,
    # then pull the destination column toward that y.
    # Only applied to columns that are NOT already in the BFS cluster — those
    # already have the adjacent-link median from Phase 2.
    _dst_desired: dict = defaultdict(list)
    def _zci_y_ideal(esrc_y_eff: float, adj_gap: list) -> float:
        """ZCI bracket ideal-y for a routing lane, mirroring plan_routing_lanes."""
        if not adj_gap:
            return esrc_y_eff
        if esrc_y_eff <= adj_gap[0][0]:
            return adj_gap[0][1] - 2 * _lane_h
        if esrc_y_eff >= adj_gap[-1][0]:
            return adj_gap[-1][1] + 2 * _lane_h
        for k in range(len(adj_gap) - 1):
            if adj_gap[k][0] <= esrc_y_eff <= adj_gap[k + 1][0]:
                s0, s1 = adj_gap[k][0], adj_gap[k + 1][0]
                d0, d1 = adj_gap[k][1], adj_gap[k + 1][1]
                t = (esrc_y_eff - s0) / (s1 - s0) if s1 > s0 else 0.5
                return d0 + t * (d1 - d0)
        return esrc_y_eff

    for esrc_y, edst_y, entry, efc, etc in _non_adj_info:
        if etc in in_order:
            continue  # BFS column: adjacent-link offsets already sufficient
        # Estimate routing-lane y at the last gap (col etc-1) using the gap
        # midpoint, then pull the destination column toward that y.
        y_through_last = esrc_y + (edst_y - esrc_y) * (etc - 1 - efc) / max(1, etc - efc)
        y_through_last_eff = y_through_last + offsets.get(efc, 0.0)
        y_ideal_dst = _best_gap_midpoint(etc - 1, y_through_last_eff)
        _dst_desired[etc].append(y_ideal_dst - edst_y)

    for c, desires in _dst_desired.items():
        if c not in in_order and desires:
            # Combine with any source routing_lane_desired already queued
            combined = sorted(routing_lane_desired.get(c, []) + desires)
            offsets[c] = combined[len(combined) // 2]

    # Phase 3: clamp each column's offset so its views remain within the
    # anchor's y-extent.  This prevents short columns from being pushed so far
    # that they extend above/below the tallest column, which would increase the
    # overall diagram height beyond what the anchor alone requires.
    anchor_top    = min(av.pos_y              for av in col_views[anchor])
    anchor_bottom = max(av.pos_y + av.size_y  for av in col_views[anchor])

    for c, views in col_views.items():
        if c == anchor or not views:
            continue
        col_top    = min(av.pos_y             for av in views)
        col_bottom = max(av.pos_y + av.size_y for av in views)
        # Valid offset range that keeps this column inside [anchor_top, anchor_bottom]
        lo = anchor_top    - col_top     # col top must not go above anchor top
        hi = anchor_bottom - col_bottom  # col bottom must not go below anchor bottom
        if lo > hi:
            # Column is taller than anchor (edge case): centre it
            offsets[c] = (lo + hi) / 2
        else:
            offsets[c] = max(lo, min(hi, offsets[c]))

    return offsets
