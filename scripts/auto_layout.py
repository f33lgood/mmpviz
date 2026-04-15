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
