"""
auto_layout.py — Link graph construction and column assignment for mmpviz.

These utilities derive a directed acyclic graph (DAG) from area address ranges,
then assign each area to a layout column based on topological depth.

Public API
----------
build_link_graph(area_configs, sections) → {src_id: [tgt_id, ...]}
assign_columns(graph, view_ids)          → {view_id: column_int}
order_within_column(graph, columns, area_views) → {col: [view_id, ...]}
"""
from collections import defaultdict, deque

from loader import parse_int


# ---------------------------------------------------------------------------
# Link graph construction
# ---------------------------------------------------------------------------

def build_link_graph(area_configs: list, sections: list) -> dict:
    """
    Build a directed link graph from area configs and global sections.

    An edge A → B is added when there exists a section L such that:
    - L's address range is entirely within area A's range, AND
    - Area B's full range is contained within L's address range.

    This recovers the implicit DAG from address containment alone — no
    explicit `links` configuration is required.

    Parameters
    ----------
    area_configs : list of dict
        Each dict has 'id' and optionally 'range': [min_str, max_str].
    sections : list of Section
        Global Section objects (address + size attributes).

    Returns
    -------
    dict  {source_id: [target_id, ...]}
        Adjacency list.  Every area id appears as a key (possibly with
        an empty target list).
    """
    def _parse_range(cfg):
        r = cfg.get('range')
        if r and len(r) >= 2:
            try:
                return parse_int(r[0]), parse_int(r[1])
            except (TypeError, ValueError):
                pass
        return None, None

    # Build range lookup  {view_id: (lo, hi)}
    area_ranges = {}
    for cfg in area_configs:
        vid = cfg.get('id', '')
        lo, hi = _parse_range(cfg)
        if lo is not None and hi is not None:
            area_ranges[vid] = (lo, hi)

    # For views without an explicit range, derive from the global section extents.
    # This allows rangeless overview views to act as link-graph sources.
    live = [s for s in sections if s.size > 0]
    if live:
        global_lo = min(s.address for s in live)
        global_hi = max(s.address + s.size for s in live)
        for cfg in area_configs:
            vid = cfg.get('id', '')
            if vid not in area_ranges:
                area_ranges[vid] = (global_lo, global_hi)

    graph = {cfg.get('id', ''): [] for cfg in area_configs}

    for src_cfg in area_configs:
        src_id = src_cfg.get('id', '')
        src_range = area_ranges.get(src_id)
        if src_range is None:
            continue
        src_lo, src_hi = src_range

        for sec in sections:
            sec_lo = sec.address
            sec_hi = sec.address + sec.size
            if sec.size == 0:
                continue
            # Section must be within the source area's range
            if sec_lo < src_lo or sec_hi > src_hi:
                continue

            # Find target areas whose full range fits inside this section
            for tgt_cfg in area_configs:
                tgt_id = tgt_cfg.get('id', '')
                if tgt_id == src_id:
                    continue
                tgt_range = area_ranges.get(tgt_id)
                if tgt_range is None:
                    continue
                tgt_lo, tgt_hi = tgt_range
                if tgt_lo >= sec_lo and tgt_hi <= sec_hi:
                    if tgt_id not in graph[src_id]:
                        graph[src_id].append(tgt_id)

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
