"""
auto_layout.py — Link graph construction and column assignment for mmpviz.

These utilities derive a directed acyclic graph (DAG) from explicit link
entries, then assign each area to a layout column based on topological depth.

Public API
----------
build_link_graph_from_links(entries, view_ids) → {src_id: [tgt_id, ...]}
assign_columns(graph, view_ids)                 → {view_id: column_int}
order_within_column(graph, columns, area_views) → {col: [view_id, ...]}
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
# Column ordering (crossing minimisation)
# ---------------------------------------------------------------------------

def order_within_column(graph: dict, columns: dict, area_views: list) -> dict:
    """
    Sort areas within each column to minimise link-band crossings.

    For each area B in column C+1, compute a *source midpoint*:
    the vertical midpoint (in source-area pixel coordinates) of the section
    that links to B.  Sorting column C+1 by ascending source midpoint places
    targets in the same top-to-bottom order as their sources.

    When a target has no computed source midpoint (e.g., it is a root or
    has no AreaView data), it is placed last in its column.

    Parameters
    ----------
    graph : dict  {source_id: [target_id, ...]}
    columns : dict  {view_id: column_int}
    area_views : list of AreaView
        Used to look up the pixel position of link sections in source views.

    Returns
    -------
    dict  {column_int: [view_id, ...]}
        Views ordered top-to-bottom within each column.
    """
    # Build area_view lookup  {view_id: AreaView}
    av_by_id = {av.view_id: av for av in area_views}

    # Build reverse map: target → list of (source, section_midpoint_px)
    source_midpoints = defaultdict(list)

    for src_id, targets in graph.items():
        src_av = av_by_id.get(src_id)
        if src_av is None:
            continue
        for tgt_id in targets:
            tgt_av = av_by_id.get(tgt_id)
            if tgt_av is None:
                continue
            # Find the section in src_av whose range contains tgt_av's range
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


def _find_link_midpoint(src_av, tgt_av) -> float | None:
    """
    Return the pixel midpoint (within src_av) of the section that links to tgt_av.

    The linking section is the one in src_av whose address range contains
    tgt_av's full address range.  Returns None if no such section is found.
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
