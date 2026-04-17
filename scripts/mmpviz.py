#!/usr/bin/env python3
"""
mmpviz — Memory Map SVG Visualizer

Usage:
    python scripts/mmpviz.py -d diagram.json -o out.svg [-t theme.json]
        Schema validate → layout check → render SVG.
        Aborts on check ERRORs; prints WARNINGs but still renders.

    python scripts/mmpviz.py -d diagram.json --fmt
        Format diagram.json in-place only (no render).

    python scripts/mmpviz.py -d diagram.json -o out.svg --fmt
        Format diagram.json, then schema validate → layout check → render SVG.
"""
import argparse
import copy
import math
import os
import sys

from area_view import AreaView
from auto_layout import (build_link_graph_from_links, assign_columns,
                         sort_by_dag_tree, order_within_column,
                         rebalance_columns, plan_routing_lanes,
                         vertical_align_columns)
from helpers import safe_element_list_get, safe_element_dict_get, DefaultAppValues
from links import Links
from fmt_diagram import format_diagram
from loader import load, validate, parse_int, resolve_view_sections
from logger import logger
from renderer import MapRenderer
from sections import Sections
from theme import Theme
from version import __version__


# ---------------------------------------------------------------------------
# Address label geometry — keep in sync with check.py panel-layout constants
# ---------------------------------------------------------------------------
_ADDR_LABEL_H_OFFSET  = 10       # px from panel right edge to label start
_ADDR_CHARS_32        = 10       # len("0x00000000")
_ADDR_CHARS_64        = 18       # len("0x0000000000000000")
_ADDR_64BIT_THRESHOLD = 0xFFFF_FFFF
_HELVETICA_W_RATIO    = 0.6


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Generate an SVG memory map diagram from a diagram.json file.')
    parser.add_argument('--diagram', '-d',
                        help='Path to the diagram.json file',
                        required=False)
    parser.add_argument('--theme', '-t',
                        help=('Visual styling. Resolution order (first match wins): '
                              '(1) -t <name>  built-in theme by name: default, plantuml; '
                              '(2) -t <path>  path to a custom theme.json file; '
                              '(3) omit -t    theme.json in the same directory as diagram.json, if present; '
                              '(4) omit -t    built-in default theme. '
                              'Providing -t always takes priority over a sibling theme.json. '
                              'Custom themes support "extends" to inherit from a built-in base.'),
                        default=None)
    parser.add_argument('--output', '-o',
                        help='Path for the generated SVG file. '
                             'Required to produce SVG output; omit to run fmt/check only.',
                        default=None)
    parser.add_argument('--fmt',
                        help='Format diagram.json in-place before rendering '
                             '(or as a standalone operation when -o is omitted).',
                        action='store_true',
                        default=False)
    parser.add_argument('--layout',
                        choices=['algo1', 'algo2', 'algo3', 'algo4'],
                        default='algo3',
                        help=('Auto-layout algorithm: '
                              'algo1 = one visual column per DAG level; '
                              'algo2 = height-rebalancing with outlier extraction; '
                              'algo3 = algo2 + routing lanes for non-adjacent links (default); '
                              'algo4 = algo3 + fixed lane assignment + vertical column alignment to minimise link length.'))
    parser.add_argument('--version', '-v',
                        action='version',
                        version=f'mmpviz {__version__}')
    return parser.parse_args()


def _auto_layout(area_configs: list, columns: dict = None,
                 area_heights: dict = None,
                 area_font_sizes: dict = None) -> list:
    """
    Assign ``pos`` and ``size`` for area configs using auto-layout.

    Areas are grouped by DAG column (from ``assign_columns()``) and stacked
    vertically within each column.  One visual column is produced per DAG level;
    the SVG canvas auto-expands via ``_auto_canvas_size()`` to fit all content.

    Areas are never scaled down — each area keeps its full estimated height so
    that all sections can reach ``min_section_height``.

    Column width is capped at 230 px so section text and address labels remain
    readable at any scale.

    Layout constants (all in pixels):
      PADDING       = 50   left canvas margin / gap between stacked views
      INTER_COL_GAP      per-column: 120 px for 32-bit columns, wider for
                         64-bit (computed from actual label width + font size)
      TITLE_SPACE   = 60   vertical space reserved above views for titles
    """
    N = len(area_configs)
    if N == 0:
        return area_configs

    PADDING = 50
    TITLE_SPACE = 60

    if columns is None:
        # Single-column fallback: stack all views vertically
        MAX_COL_WIDTH = 230.0
        result = []
        y = float(TITLE_SPACE)
        for i, cfg in enumerate(area_configs):
            new_cfg = dict(cfg)
            aid = cfg.get('id', '')
            auto_h = max(100.0, float((area_heights or {}).get(aid, 400.0)))
            new_cfg['pos'] = [float(PADDING), round(y, 1)]
            new_cfg['size'] = [MAX_COL_WIDTH, round(auto_h, 1)]
            y += auto_h + PADDING
            result.append(new_cfg)
        return result

    # --- DAG-based column layout (one visual column per DAG level) ---
    # All views assigned to the same DAG column are stacked in a single visual
    # column; the SVG canvas auto-expands via _auto_canvas_size() to fit.
    # No bin-packing / height-based splitting is applied.
    MAX_COL_WIDTH = 230.0
    # Breathing room beyond the address label (same for 32-bit and 64-bit).
    # For 32-bit at 12 pt: 10 + 10×0.6×12 + 38 = 120 px (historical default).
    _INTER_BREATHING = 38

    raw_heights = dict(area_heights or {})

    def _area_h(cfg: dict) -> float:
        """Effective height of a config (explicit or estimated)."""
        if 'size' in cfg:
            return float(cfg['size'][1])
        return max(100.0, float(raw_heights.get(cfg.get('id', ''), 400.0)))

    # Group configs by DAG column
    col_cfgs: dict = {}
    for cfg in area_configs:
        aid = cfg.get('id', '')
        col = columns.get(aid, 0)
        col_cfgs.setdefault(col, []).append(cfg)

    # One visual column per DAG column — no splitting.
    final_cols: list = []
    dag_col_indices = sorted(col_cfgs.keys())

    for dag_col in dag_col_indices:
        final_cols.append(list(col_cfgs[dag_col]))

    # Areas are NOT scaled down — each keeps its full estimated height so that
    # all sections can reach min_section_height.  The SVG canvas is expanded by
    # the caller via _auto_canvas_size() to accommodate the actual content.

    # Assign pixel positions
    # Use MAX_COL_WIDTH directly — the SVG canvas auto-expands via _auto_canvas_size()
    # so the initial document_size width does not constrain column width.
    col_width = MAX_COL_WIDTH

    def _col_gap(bin_cfgs: list) -> int:
        """Inter-column gap for bin_cfgs based on their address width and font size."""
        fs = max(
            (float((area_font_sizes or {}).get(c.get('id', ''), 12.0))
             for c in bin_cfgs),
            default=12.0,
        )
        for c in bin_cfgs:
            for s in c.get('sections', []):
                try:
                    if parse_int(s.get('address', '0')) > _ADDR_64BIT_THRESHOLD:
                        return round(
                            _ADDR_LABEL_H_OFFSET
                            + _ADDR_CHARS_64 * _HELVETICA_W_RATIO * fs
                            + _INTER_BREATHING)
                except (ValueError, TypeError):
                    pass
        return round(
            _ADDR_LABEL_H_OFFSET
            + _ADDR_CHARS_32 * _HELVETICA_W_RATIO * fs
            + _INTER_BREATHING)

    # Cumulative x start positions: gap right of bin[n] → left edge of bin[n+1]
    x_starts: list = [float(PADDING)]
    for bin_idx in range(len(final_cols) - 1):
        x_starts.append(x_starts[-1] + col_width + _col_gap(final_cols[bin_idx]))

    result_by_id: dict = {}
    for col_idx, bin_cfgs in enumerate(final_cols):
        x = round(x_starts[col_idx], 1)
        y = float(TITLE_SPACE)
        for cfg in bin_cfgs:
            new_cfg = dict(cfg)
            aid = cfg.get('id', '')
            if 'pos' not in cfg:
                new_cfg['pos'] = [x, round(y, 1)]
            if 'size' not in cfg:
                auto_h = max(100.0, float(raw_heights.get(aid, 400.0)))
                new_cfg['size'] = [round(col_width, 1), round(auto_h, 1)]
            h = new_cfg.get('size', [0, 400])[1]
            y += h + PADDING
            result_by_id[aid] = new_cfg

    # Preserve original input order
    return [result_by_id.get(cfg.get('id', ''), dict(cfg)) for cfg in area_configs]


def _auto_canvas_size(area_views: list,
                      right_pad: int = 110, bottom_pad: int = 30) -> tuple:
    """
    Return ``(W, H, left_overflow, top_overflow)`` — SVG canvas dimensions and
    origin shift needed to contain all *area_views* without clipping.

    ``right_pad`` is the default clearance for address labels to the right of
    the rightmost column (≈ 82 px label + 10 px offset + 18 px breathing room).
    User labels with large ``length`` or long text may require more; this is
    computed automatically and ``right_pad`` is expanded if needed.

    ``left_overflow`` > 0 means content extends left of x = 0 (e.g. left-side
    labels).  The caller must shift the SVG viewBox origin by ``−left_overflow``
    and increase the canvas width accordingly.  ``top_overflow`` is reserved for
    future use (currently always 0).
    """
    if not area_views:
        return (1100, 1000, 0, 0)

    max_right  = max(av.pos_x + av.size_x for av in area_views)
    max_bottom = max(av.pos_y + av.size_y for av in area_views)

    # Scan user labels to find actual left/right content extents.
    _SPACER   = 3    # line_label_spacer constant in renderer.py
    _CHAR_W   = 0.6  # Helvetica character width ratio
    _MARGIN   = 10   # breathing room (px)

    min_x = 0.0
    for av in area_views:
        if not av.labels or not av.labels.labels:
            continue
        fs = av.style.get('font_size', 12)
        for lbl in av.labels.labels:
            tw = len(lbl.text) * _CHAR_W * fs
            if lbl.side == 'left':
                x_end = av.pos_x - lbl.length - _SPACER - tw
                min_x = min(min_x, x_end)
            else:
                x_end = av.pos_x + av.size_x + lbl.length + _SPACER + tw
                right_pad = max(right_pad, int(x_end - max_right) + _MARGIN)

    # Scan view titles: 24 px, center-anchored above each view at pos_x + size_x/2.
    _TITLE_FONT_SIZE = 24
    for av in area_views:
        if not av.title:
            continue
        title_half = len(av.title) * _CHAR_W * _TITLE_FONT_SIZE / 2
        title_cx = av.pos_x + av.size_x / 2
        min_x = min(min_x, title_cx - title_half)
        right_over = math.ceil(title_cx + title_half - max_right) + _MARGIN
        if right_over > right_pad:
            right_pad = right_over

    # Widen right_pad for 64-bit address labels on the rightmost column.
    # Default right_pad (110) = _ADDR_LABEL_H_OFFSET(10) + 32-bit label(72) + 28 breathing.
    # 64-bit labels are wider; use the same 28 px breathing room.
    _ADDR_RIGHT_BREATHING = 28
    for av in area_views:
        if av.pos_x + av.size_x < max_right - 0.5:
            continue  # not in the rightmost column
        fs = float(av.style.get('font_size', 12))
        for sub in av.get_split_area_views():
            for s in sub.sections.get_sections():
                if s.is_hidden() or s.is_break() or s.size == 0:
                    continue
                if s.address > _ADDR_64BIT_THRESHOLD:
                    needed = round(
                        _ADDR_LABEL_H_OFFSET
                        + _ADDR_CHARS_64 * _HELVETICA_W_RATIO * fs
                        + _ADDR_RIGHT_BREATHING)
                    right_pad = max(right_pad, needed)
                    break

    left_overflow = (math.ceil(-min_x) + _MARGIN) if min_x < 0 else 0
    W = int(max_right + right_pad) + left_overflow
    H = int(max_bottom + bottom_pad)
    return (W, H, left_overflow, 0)


def _apply_area_section_flags(sections: list, area_config: dict) -> list:
    """
    No-op in the new schema: flags are already applied during section
    resolution in resolve_view_sections().  Kept for API compatibility.
    """
    return sections


def _estimate_area_height(sections: list, style: dict) -> float:
    """
    Estimate a suitable pixel height for an area from its section list.

    Uses the theme's min_section_height (default 40) as the per-section budget
    (min_h already includes label space per the proposal), then adds space for
    break sections and internal padding.

    Sections are expected to already have the correct flags applied (breaks /
    hidden) so no additional flag processing is done here.
    """
    user_min_h = float(style.get('min_section_height', 0))
    break_height = float(style.get('break_height', 20))
    top_bottom_pad = 20.0  # area-internal padding

    n_breaks = sum(1 for s in sections if s.is_break())

    # Sum per-section floors: each visible section contributes at least
    # max(global_min_h, section.min_height).  Per-section label-conflict
    # inflation is applied during actual rendering in AreaView._process();
    # the estimate only needs to be in the right ballpark.
    visible_floor_sum = sum(
        max(user_min_h, s.min_height if s.min_height is not None else 0.0)
        for s in sections
        if not s.is_hidden() and not s.is_break() and s.size > 0
    )
    estimated = (visible_floor_sum
                 + n_breaks * (break_height + 4)
                 + top_bottom_pad)
    return max(200.0, estimated)


def get_area_views(base_style: dict, diagram: dict, theme: Theme,
                   links=None, layout_algo: str = 'algo3') -> tuple:
    """
    Build AreaView objects from diagram config.

    Each view fully declares its own ``sections[]`` array.  There is no global
    section pool — sections live entirely inside the view that displays them.

    Auto-layout always runs: ``pos`` and ``size`` on individual views and the
    diagram-level ``size`` field are deprecated and ignored with a warning.

    Returns
    -------
    (area_views, routing_lanes) : tuple
        ``area_views`` is a list of AreaView objects.
        ``routing_lanes`` is a dict ``{entry_idx: [lane_dict, ...]}`` (non-empty
        only when ``layout_algo == 'algo3'`` and non-adjacent links exist).
    """
    area_configurations = diagram.get('views', []) or []

    if not area_configurations:
        logger.warning("No views configured in diagram.json — nothing to render.")
        return []

    # Warn about deprecated fields but do not abort — they are silently ignored.
    if 'size' in diagram:
        logger.warning(
            "diagram.json: top-level 'size' is deprecated and ignored — "
            "canvas dimensions are computed automatically"
        )
    for cfg in area_configurations:
        vid = cfg.get('id', '?')
        if 'pos' in cfg:
            logger.warning(
                f"view '{vid}': 'pos' is deprecated and ignored — "
                "placement is controlled by auto-layout"
            )
        if 'size' in cfg:
            logger.warning(
                f"view '{vid}': 'size' is deprecated and ignored — "
                "dimensions are controlled by auto-layout"
            )

    # --- Link-graph column assignment ---
    view_ids = [c['id'] for c in area_configurations if 'id' in c]
    if links is not None and links.entries:
        graph = build_link_graph_from_links(links.entries, view_ids)
    else:
        graph = {vid: [] for vid in view_ids}
    columns = assign_columns(graph, view_ids)

    # Pre-resolve sections per view to estimate heights and collect font sizes
    area_heights = {}
    area_font_sizes = {}
    for area_config in area_configurations:
        vid = area_config.get('id', '')
        area_style = theme.resolve(vid)
        view_sections = copy.deepcopy(resolve_view_sections(area_config))
        area_heights[vid] = _estimate_area_height(view_sections, area_style)
        area_font_sizes[vid] = float(area_style.get('font_size', 12))

    # --- DAG-tree ordering: sort each column by (parent position, -source addr) ---
    # Column 0 keeps JSON order; each subsequent column is ordered so that
    # children of an earlier parent come first, and among siblings the view
    # linked from the highest source-section address is placed at the top.
    # Bin-packing then processes views in this order, so overflow boundaries
    # fall between sibling groups rather than splitting them arbitrarily.
    if links is not None and links.entries:
        sec_mid_addrs = {
            ac.get('id', ''): {
                s.id: s.address + s.size / 2
                for s in copy.deepcopy(resolve_view_sections(ac))
            }
            for ac in area_configurations
        }
        area_configurations = sort_by_dag_tree(
            area_configurations, columns, links.entries, sec_mid_addrs)

    # --- Algo-2/3/4: height-rebalancing column reassignment (optional) ---
    if layout_algo in ('algo2', 'algo3', 'algo4') and links is not None and links.entries:
        columns = rebalance_columns(
            columns=columns,
            area_configs=area_configurations,
            area_heights=area_heights,
            link_entries=links.entries,
        )

    # --- Single layout pass ---
    area_configurations = _auto_layout(
        area_configurations, columns=columns, area_heights=area_heights,
        area_font_sizes=area_font_sizes)

    # --- Crossing minimisation: reorder within existing bins ---
    # Sort column C+1 views so their top-to-bottom order matches the vertical
    # order of their source sections in column C, eliminating band crossings.
    # Only y-positions within each visual bin are adjusted; bin assignment and
    # bin membership never change, so stm32f103-style bin splits are preserved.
    # Views whose midpoint cannot be computed (section-span links, fan-in with
    # multiple sources) keep their current order (stable sort with key=inf).
    if links is not None and links.entries:
        # Build temporary AreaViews to compute pixel midpoints
        area_views_for_order = []
        for area_config in area_configurations:
            vid = area_config.get('id', '')
            secs = copy.deepcopy(resolve_view_sections(area_config))
            if not secs:
                continue
            area_views_for_order.append(AreaView(
                sections=Sections(sections=secs),
                style=theme.resolve(vid),
                area_config=area_config,
                theme=theme,
            ))

        col_order = order_within_column(graph, columns, area_views_for_order,
                                        link_entries=links.entries)

        # Group configs by x-position (same x = same visual bin)
        PADDING = 50
        TITLE_SPACE = 60
        bins_by_x: dict = {}
        for cfg in area_configurations:
            x = cfg.get('pos', [0, 0])[0]
            bins_by_x.setdefault(x, []).append(cfg)

        for bin_cfgs in bins_by_x.values():
            if len(bin_cfgs) <= 1:
                continue
            # All configs in a bin share the same DAG column
            col = columns.get(bin_cfgs[0].get('id', ''), 0)
            id_to_rank = {vid: i for i, vid in enumerate(col_order.get(col, []))}
            bin_cfgs.sort(
                key=lambda c: id_to_rank.get(c.get('id', ''), float('inf')))
            # Reassign y-positions to match new order
            y = float(TITLE_SPACE)
            for cfg in bin_cfgs:
                cfg['pos'][1] = round(y, 1)
                y += cfg.get('size', [0, 400])[1] + PADDING

    # --- Expand inter-panel gaps for columns with multiple routing lanes ---
    # When N non-adjacent links must pass routing lanes through a column that
    # has stacked panels, the gap between those panels must be wide enough to
    # hold all N lanes.  Required gap = N*lane_pitch + PADDING (breathing room).
    # Applied for algo3 and above so every routing-lane layout benefits.
    if layout_algo in ('algo3', 'algo4') \
            and links is not None and links.entries:
        _LANE_PITCH = 30   # lane_height(20) + 2 × lane_padding(5)
        _lane_counts: dict = {}
        for _entry in links.entries:
            _fc = columns.get(_entry.get('from_view', ''))
            _tc = columns.get(_entry.get('to_view', ''))
            if _fc is not None and _tc is not None and _tc > _fc + 1:
                for _c in range(_fc + 1, _tc):
                    _lane_counts[_c] = _lane_counts.get(_c, 0) + 1
        for _c, _n in _lane_counts.items():
            if _n < 2:
                continue
            _required_gap = _n * _LANE_PITCH + PADDING   # e.g. 3*30+50 = 140 px
            _col_cfgs = sorted(
                [cfg for cfg in area_configurations
                 if columns.get(cfg.get('id', '')) == _c],
                key=lambda cfg: cfg.get('pos', [0, 0])[1],
            )
            for _i in range(len(_col_cfgs) - 1):
                _above_bot = (_col_cfgs[_i]['pos'][1]
                              + _col_cfgs[_i].get('size', [0, 400])[1])
                _current_gap = _col_cfgs[_i + 1]['pos'][1] - _above_bot
                _extra = _required_gap - _current_gap
                if _extra > 0.5:
                    for _j in range(_i + 1, len(_col_cfgs)):
                        _col_cfgs[_j]['pos'][1] = round(
                            _col_cfgs[_j]['pos'][1] + _extra, 1)

    area_views = []
    for i, area_config in enumerate(area_configurations):
        view_id = area_config.get('id', f'view-{i}')

        view_sections = copy.deepcopy(resolve_view_sections(area_config))

        if len(view_sections) == 0:
            logger.warning(
                f"View '{view_id}' (index {i}) has no sections. "
                "This view will be omitted.")
            continue

        area_style = theme.resolve(view_id)

        area_views.append(AreaView(
            sections=Sections(sections=view_sections),
            style=area_style,
            area_config=area_config,
            theme=theme,
        ))

    # --- Algo-4: vertical column alignment to minimise link length ---
    # Uses preliminary top-aligned area_views to compute link attachment y-coords,
    # then applies per-column offsets to the configs and rebuilds area_views.
    if layout_algo == 'algo4' and links is not None and links.entries:
        col_offsets = vertical_align_columns(
            vis_col=columns,
            link_entries=links.entries,
            area_views=area_views,
            top_margin=TITLE_SPACE,
        )
        if col_offsets and any(abs(v) > 0.5 for v in col_offsets.values()):
            for cfg in area_configurations:
                c = columns.get(cfg.get('id', ''))
                if c is not None:
                    cfg['pos'][1] = round(cfg['pos'][1] + col_offsets.get(c, 0.0), 1)
            # Rebuild area_views with the shifted positions (no repeat warnings)
            area_views = []
            for i, area_config in enumerate(area_configurations):
                view_id = area_config.get('id', f'view-{i}')
                view_sections = copy.deepcopy(resolve_view_sections(area_config))
                if not view_sections:
                    continue
                area_views.append(AreaView(
                    sections=Sections(sections=view_sections),
                    style=theme.resolve(view_id),
                    area_config=area_config,
                    theme=theme,
                ))

    # --- Algo-3/4: plan routing lanes for non-adjacent links ---
    routing_lanes = {}
    if layout_algo in ('algo3', 'algo4') and links is not None and links.entries:
        routing_lanes = plan_routing_lanes(
            vis_col=columns,
            link_entries=links.entries,
            area_views=area_views,
        )

    return area_views, routing_lanes


def main():
    args = parse_arguments()

    if not args.diagram:
        print("Error: --diagram / -d is required")
        sys.exit(1)

    if not args.fmt and not args.output:
        print("Error: specify -o <path> to render SVG, --fmt to format, or both.")
        sys.exit(1)

    # --fmt: format diagram.json in-place
    if args.fmt:
        import json as _json
        try:
            with open(args.diagram, 'r', encoding='utf-8') as f:
                data = _json.load(f)
            formatted = format_diagram(data)
            with open(args.diagram, 'w', encoding='utf-8') as f:
                f.write(formatted)
            print(f"Formatted: {args.diagram}")
        except (OSError, ValueError) as e:
            print(f"Error formatting diagram: {e}")
            sys.exit(1)
        if not args.output:
            sys.exit(0)  # format-only mode, done

    # Schema validation (JSON Schema via jsonschema, if available)
    schema_errors = validate(args.diagram)
    if schema_errors:
        print("Schema validation failed:")
        for e in schema_errors:
            print(f"  {e}")
        sys.exit(1)

    # Load diagram
    try:
        diagram = load(args.diagram)
    except (ValueError, OSError) as e:
        print(f"Error loading diagram: {e}")
        sys.exit(1)

    # Load theme: explicit -t > auto-discovered theme.json next to diagram > built-in default
    _theme_arg = args.theme
    if _theme_arg is None:
        _sibling = os.path.join(os.path.dirname(os.path.abspath(args.diagram)), 'theme.json')
        if os.path.isfile(_sibling):
            _theme_arg = _sibling
    try:
        theme = Theme(_theme_arg)
    except (OSError, Exception) as e:
        print(f"Error loading theme: {e}")
        sys.exit(1)

    base_style = theme.resolve('')

    # Links
    links_config = diagram.get('links', [])
    links_style = theme.resolve_links()
    links = Links(links_config=links_config, style=links_style)

    growth_arrow_style = theme.resolve_growth_arrow()

    # Build area views — auto-layout always runs
    area_views, routing_lanes = get_area_views(base_style, diagram, theme,
                                               links=links,
                                               layout_algo=args.layout)
    if not area_views:
        print("Error: no area views could be created. Check diagram.json configuration.")
        sys.exit(1)

    # Layout checks — deferred import avoids circular dependency
    # (check.py imports get_area_views from mmpviz at module level)
    from check import run_checks, ALL_RULES  # noqa: PLC0415
    issues = run_checks(diagram, area_views, ALL_RULES)
    errors   = [i for i in issues if i.level == 'ERROR']
    warnings = [i for i in issues if i.level == 'WARN']
    for w in warnings:
        print(f"  {w}")
    if errors:
        print("\nErrors found — aborting render. Fix the issues above and re-run.")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)

    # Canvas always auto-sizes to fit all placed views and routing lanes
    doc_w, doc_h, left_overflow, top_overflow = _auto_canvas_size(area_views)
    if routing_lanes:
        lane_bottom = max(
            l['y'] + l['height'] / 2
            for lanes in routing_lanes.values()
            for l in lanes
        )
        # bottom_pad = 30 matches the default in _auto_canvas_size
        doc_h = max(doc_h, int(lane_bottom) + 30)
    document_size = (doc_w, doc_h)
    origin = (-left_overflow, -top_overflow)

    # Render
    svg_str = MapRenderer(
        area_views=area_views,
        links=links,
        style=base_style,
        growth_arrow=growth_arrow_style,
        size=document_size,
        origin=origin,
        routing_lanes=routing_lanes or None,
    ).draw()

    # Write output
    try:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n')
            f.write(svg_str)
        print(f"SVG written to: {args.output}")
    except OSError as e:
        print(f"Error writing output: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
