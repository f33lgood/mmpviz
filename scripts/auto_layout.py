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
order_within_column(graph, columns, area_views, link_entries)
                                                → {col: [view_id, ...]}
rebalance_columns(columns, area_configs, ...)   → {view_id: visual_col_int}
plan_routing_lanes(vis_col, link_entries, ...)  → {entry_idx: [lane_dict, ...]}
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

def order_within_column(graph: dict, columns: dict, area_views: list,
                        link_entries: list = None) -> dict:
    """
    Sort areas within each column to minimise link-band crossings.

    For each area B in column C+1, compute a *source midpoint*:
    the vertical midpoint (in source-area pixel coordinates) of the section(s)
    that link to B.  Sorting column C+1 by ascending source midpoint places
    targets in the same top-to-bottom order as their sources.

    When ``link_entries`` is provided (recommended), section IDs from the link
    entry's ``from_sections`` field are used directly, which correctly handles
    multi-section links (e.g. two sections linking to one target).  Without
    ``link_entries``, a legacy address-containment fallback is used.

    When a target has no computed source midpoint (e.g., it is a root or
    has no AreaView data), it is placed last in its column.

    Parameters
    ----------
    graph : dict  {source_id: [target_id, ...]}
    columns : dict  {view_id: column_int}
    area_views : list of AreaView
        Used to look up the pixel position of link sections in source views.
    link_entries : list of dict, optional
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

    if link_entries:
        # Preferred path: use explicit section IDs from each link entry.
        # This correctly handles multi-section links where a single section
        # does not contain the full target address range.
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
    else:
        # Legacy fallback: address-containment search.
        for src_id, targets in graph.items():
            src_av = av_by_id.get(src_id)
            if src_av is None:
                continue
            for tgt_id in targets:
                tgt_av = av_by_id.get(tgt_id)
                if tgt_av is None:
                    continue
                mid = _find_link_midpoint(src_av, tgt_av)
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


def _find_link_midpoint_by_sections(src_av, from_sections) -> float | None:
    """
    Return the pixel midpoint of the link band in src_av for named sections.

    Collects all sections in src_av matching ``from_sections`` (by ID), then
    returns the pixel midpoint of the span from the lowest start address to the
    highest end address across those sections.

    When ``from_sections`` is None (link covers the whole source view), uses
    every non-hidden, non-zero-size section.

    Returns None if no matching sections are found.
    """
    found = []
    for sub in src_av.get_split_area_views():
        for sec in sub.sections.get_sections():
            if sec.is_hidden() or sec.size == 0:
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
            return sub.to_pixels_relative(mid_addr) + sub.pos_y - src_av.pos_y

    # Fallback: average of individual section pixel midpoints
    total = 0.0
    for sec, sub in found:
        mid = sec.address + sec.size / 2
        total += sub.to_pixels_relative(mid) + sub.pos_y - src_av.pos_y
    return total / len(found)


def _find_link_midpoint(src_av, tgt_av) -> float | None:
    """
    Return the pixel midpoint (within src_av) of the section that links to tgt_av.

    The linking section is the one in src_av whose address range contains
    tgt_av's full address range.  Returns None if no such section is found.

    This is the legacy address-containment approach used when link entries are
    not available.  Prefer ``_find_link_midpoint_by_sections`` instead.
    """
    tgt_lo = tgt_av.start_address
    tgt_hi = tgt_av.end_address

    for sub in src_av.get_split_area_views():
        for sec in sub.sections.get_sections():
            if sec.is_hidden() or sec.size == 0:
                continue
            sec_lo = sec.address
            sec_hi = sec.address + sec.size
            if sec_lo <= tgt_lo and sec_hi >= tgt_hi:
                # Found the linking section; return its midpoint in the source area
                sec_mid_addr = (sec_lo + sec_hi) / 2
                # to_pixels_relative gives pixels from top of sub-area
                px = sub.to_pixels_relative(sec_mid_addr) + sub.pos_y - src_av.pos_y
                return px

    return None


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
    # lane_requests[col_i] = list of (entry_idx, y_ideal, zci_lo, zci_hi)
    lane_requests = defaultdict(list)

    for idx, entry in enumerate(link_entries):
        fc = vis_col.get(entry.get('from_view', ''))
        tc = vis_col.get(entry.get('to_view', ''))
        if fc is None or tc is None or tc <= fc + 1:
            continue  # not non-adjacent
        y_src = src_y.get(idx)
        if y_src is None:
            continue

        for col_i in range(fc + 1, tc):
            # Adjacent links from col_{i-1} to col_i
            adj_raw = col_pair_links.get((col_i - 1, col_i), [])
            adj = [
                (aidx, sy, dy)
                for aidx, e in adj_raw
                for sy, dy in [(src_y.get(aidx), dst_y.get(aidx))]
                if sy is not None and dy is not None
            ]
            adj.sort(key=lambda t: t[1])  # sort by source y

            INF = float('inf')
            if not adj:
                zci_lo, zci_hi, y_ideal = -INF, INF, y_src
            elif y_src <= adj[0][1]:
                zci_lo, zci_hi = -INF, adj[0][2]
                y_ideal = adj[0][2] - lane_height
            elif y_src >= adj[-1][1]:
                zci_lo, zci_hi = adj[-1][2], INF
                y_ideal = adj[-1][2] + lane_height
            else:
                # Find bracket
                zci_lo = zci_hi = None
                for k in range(len(adj) - 1):
                    if adj[k][1] <= y_src <= adj[k + 1][1]:
                        # Normalise so zci_lo ≤ zci_hi regardless of dst order
                        d0, d1 = adj[k][2], adj[k + 1][2]
                        zci_lo, zci_hi = min(d0, d1), max(d0, d1)
                        s0, s1 = adj[k][1], adj[k + 1][1]
                        t = ((y_src - s0) / (s1 - s0)) if s1 > s0 else 0.5
                        y_ideal = d0 + t * (d1 - d0)
                        break
                if zci_lo is None:
                    zci_lo, zci_hi, y_ideal = -INF, INF, y_src

            lane_requests[col_i].append((idx, y_ideal, zci_lo, zci_hi))

    if not lane_requests:
        return {}

    # ------------------------------------------------------------------
    # Assign lane positions within each column
    # ------------------------------------------------------------------
    needed = lane_height + 2 * lane_padding
    col_lane_assignments = defaultdict(list)  # {col_i: [(entry_idx, y), ...]}

    for col_i, requests in lane_requests.items():
        requests.sort(key=lambda r: r[1])  # sort by y_ideal
        x_left, x_right = _col_x_bounds(col_i)
        if x_left is None:
            continue
        gaps = _col_gaps(col_i)
        assigned = []  # [(y_center, height), ...] already placed in this col

        for entry_idx, y_ideal, zci_lo, zci_hi in requests:
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

                # Avoid overlapping already-assigned lanes in this gap
                ok = True
                for ey, eh in assigned:
                    min_sep = (lane_height + eh) / 2 + lane_padding
                    if abs(candidate - ey) < min_sep:
                        # Try to nudge past the blocking lane
                        if candidate <= ey:
                            candidate = ey - min_sep
                        else:
                            candidate = ey + min_sep
                        if candidate < y_lo or candidate > y_hi:
                            ok = False
                            break
                if not ok:
                    continue

                dist = abs(candidate - y_ideal)
                if dist < best_dist:
                    best_dist = dist
                    best_y = candidate

            if best_y is None:
                # Fallback: use y_ideal clamped to the closest gap
                for gap_top, gap_bot in gaps:
                    if gap_bot - gap_top >= needed:
                        best_y = max(gap_top + lane_height / 2 + lane_padding,
                                     min(gap_bot - lane_height / 2 - lane_padding,
                                         y_ideal))
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

    # Sort lanes by column for each entry
    return {idx: sorted(lanes, key=lambda d: d['col'])
            for idx, lanes in result.items()}
