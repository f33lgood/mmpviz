#!/usr/bin/env python3
"""
mmpviz — Memory Map SVG Visualizer

Usage:
    python scripts/mmpviz.py -d diagram.json [-t theme.json] [-o map.svg]
    python scripts/mmpviz.py --validate diagram.json
"""
import argparse
import copy
import sys

from area_view import AreaView
from auto_layout import build_link_graph_from_links, assign_columns
from helpers import safe_element_list_get, safe_element_dict_get, DefaultAppValues
from links import Links
from loader import load, validate, parse_int, resolve_view_sections
from logger import logger
from renderer import MapRenderer
from sections import Sections
from theme import Theme
from version import __version__


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Generate an SVG memory map diagram from a diagram.json file.')
    parser.add_argument('--diagram', '-d',
                        help='Path to the diagram.json file (memory sections + display layout)',
                        required=False)
    parser.add_argument('--theme', '-t',
                        help=('Visual styling. Three forms accepted: '
                              '(omit) = use the built-in default theme; '
                              '-t <name> = use a built-in theme: default, light, monochrome, plantuml; '
                              '-t <path> = use a custom theme.json file. '
                              'Custom themes support "extends" to inherit from a built-in base.'),
                        default=None)
    parser.add_argument('--output', '-o',
                        help='Path for the generated SVG file (default: map.svg)',
                        default='map.svg')
    parser.add_argument('--validate',
                        help='Validate the diagram.json file and exit (no SVG generated)',
                        metavar='DIAGRAM_PATH',
                        default=None)
    parser.add_argument('--version', '-v',
                        action='version',
                        version=f'mmpviz {__version__}')
    return parser.parse_args()


def _auto_layout(area_configs: list, document_size: tuple,
                 columns: dict = None, area_heights: dict = None,
                 target_format: str = 'a4') -> list:
    """
    Fill in missing ``pos`` and ``size`` for area configs using auto-layout.

    When ``columns`` is None (default), areas are arranged left-to-right with
    equal width.  When ``columns`` is provided (a dict mapping area_id →
    column_index from assign_columns()), areas are grouped by DAG column and
    packed vertically.

    **Greedy bin-packing with spill-first strategy (proposal §7.3):**
    For each DAG column, areas are greedily stacked until adding another would
    exceed ``available_h``.  When overflow occurs with ≥ 2 areas already in the
    bin, the overflowing area spills into a new adjacent sub-column (prefer
    split).  When the bin has only 1 area, the new area is appended (scale
    accepted, canvas will auto-expand if needed).

    Areas are never scaled down — each area keeps its full estimated height so
    that all sections can reach ``min_section_height``.  The caller is
    responsible for expanding the SVG canvas to fit (use
    ``_auto_canvas_size()``).

    Column width is capped at 230 px (matching the pulpissimo reference layout)
    so box sizes stay readable even on wide canvases.

    Layout constants (all in pixels):
      PADDING     = 50   left canvas margin / minimum area gap
      INTER_COL_GAP = 120  gap between column right edge and next column left
                           edge (fits 32-bit address labels + link-band jog)
      TITLE_SPACE = 60   vertical space reserved above areas for titles
      BOTTOM_PAD  = 30   vertical gap below areas
    """
    W, H = document_size
    N = len(area_configs)
    if N == 0:
        return area_configs

    PADDING = 50
    TITLE_SPACE = 60
    BOTTOM_PAD = 30

    if columns is None:
        # Equal-distribution fallback (original behaviour)
        auto_width = max(50.0, (W - PADDING * (N + 1)) / N)
        auto_height = max(100.0, H - TITLE_SPACE - BOTTOM_PAD)
        result = []
        for i, cfg in enumerate(area_configs):
            new_cfg = dict(cfg)
            if 'pos' not in cfg:
                new_cfg['pos'] = [round(PADDING + i * (auto_width + PADDING), 1), TITLE_SPACE]
            if 'size' not in cfg:
                new_cfg['size'] = [round(auto_width, 1), auto_height]
            result.append(new_cfg)
        return result

    # --- Column-based layout with greedy bin-packing ---
    base_available_h = max(100.0, H - TITLE_SPACE - BOTTOM_PAD)
    # Horizontal gap between a column's right edge and the next column's left edge.
    # Must fit address labels (~82 px at 12 pt / 32-bit) + link-band jog + breathing
    # room — proposal §8.3 LINK_BAND_MIN = addr_width + 20 = 102 px; use 120 for safety.
    INTER_COL_GAP = 120
    # Maximum column (box) width: capped at 230 px to match the pulpissimo reference
    # layout so section text and address labels stay readable on any canvas width.
    MAX_COL_WIDTH = 230.0

    raw_heights = dict(area_heights or {})

    def _area_h(cfg: dict) -> float:
        """Effective height of a config (explicit or estimated)."""
        if 'size' in cfg:
            return float(cfg['size'][1])
        return max(100.0, float(raw_heights.get(cfg.get('id', ''), 400.0)))

    def _col_stack_height(cfgs: list) -> float:
        """Total height of a list of area configs when stacked with gaps."""
        if not cfgs:
            return 0.0
        return sum(_area_h(c) for c in cfgs) + PADDING * (len(cfgs) - 1)

    # Group configs by DAG column
    col_cfgs: dict = {}
    for cfg in area_configs:
        aid = cfg.get('id', '')
        col = columns.get(aid, 0)
        col_cfgs.setdefault(col, []).append(cfg)

    # Build final column list via greedy bin-packing (spill-first, proposal §7.3).
    # Each element of `final_cols` is a list of area configs for that visual column.
    final_cols: list = []
    dag_col_indices = sorted(col_cfgs.keys())

    for dag_col in dag_col_indices:
        areas = list(col_cfgs[dag_col])
        # Per-column available height: at least as tall as the tallest single view in
        # this column.  This prevents the initial document_size (which is just a floor
        # hint) from artificially splitting small views into too many sub-columns while
        # still allowing a genuinely large view (e.g. APB with 30+ sections) to spill
        # into its own sub-column when mixed with smaller views.
        max_item_h = max((_area_h(c) for c in areas), default=base_available_h)
        available_h = max(base_available_h, max_item_h)

        # Greedily fill bin(s) for this DAG column
        current_bin: list = []
        for cfg in areas:
            trial = current_bin + [cfg]
            if _col_stack_height(trial) <= available_h or not current_bin:
                # Fits (or first item — always place it even if already tall)
                current_bin.append(cfg)
            else:
                # Overflow: spill when bin already has ≥2 views (proposal §7.3:
                # prefer split when 3+ views; allow scale only for 1-item bins).
                if len(current_bin) >= 2:
                    # Spill: commit current bin, start a new one with this view
                    final_cols.append(current_bin)
                    current_bin = [cfg]
                else:
                    # Only 1 view already — accept both in the same bin;
                    # canvas will auto-expand to fit (no scaling applied).
                    current_bin.append(cfg)

        if current_bin:
            final_cols.append(current_bin)

    # Areas are NOT scaled down — each keeps its full estimated height so that
    # all sections can reach min_section_height.  The SVG canvas is expanded by
    # the caller via _auto_canvas_size() to accommodate the actual content.

    # Assign pixel positions
    n_cols = len(final_cols)
    # Use MAX_COL_WIDTH directly — the SVG canvas auto-expands via _auto_canvas_size()
    # so the initial document_size width does not constrain column width.
    col_width = MAX_COL_WIDTH

    result_by_id: dict = {}
    for col_idx, bin_cfgs in enumerate(final_cols):
        x = round(PADDING + col_idx * (col_width + INTER_COL_GAP), 1)
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
    Return ``(W, H)`` — the minimum SVG canvas dimensions to contain all
    *area_views* without clipping.

    ``right_pad`` allows room for address labels beyond the rightmost column's
    box edge (≈ 82 px label + 10 px offset + 18 px breathing room = 110 px).
    """
    if not area_views:
        from loader import DefaultAppValues  # noqa: F401 — inline to avoid circular
        return (1100, 1000)
    max_right = max(av.pos_x + av.size_x for av in area_views)
    max_bottom = max(av.pos_y + av.size_y for av in area_views)
    return (int(max_right + right_pad), int(max_bottom + bottom_pad))


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

    n_visible = sum(
        1 for s in sections
        if not s.is_hidden() and not s.is_break() and s.size > 0
    )
    n_breaks = sum(1 for s in sections if s.is_break())

    # Use user-configured min_section_height as the per-section floor.
    # Per-section label-conflict inflation is applied during actual rendering
    # in AreaView._process(); the estimate only needs to be in the right ballpark.
    estimated = (n_visible * user_min_h
                 + n_breaks * (break_height + 4)
                 + top_bottom_pad)
    return max(200.0, estimated)


def get_area_views(base_style: dict, diagram: dict, theme: Theme,
                   links=None) -> list:
    """
    Build AreaView objects from diagram config.

    Each view fully declares its own ``sections[]`` array.  There is no global
    section pool — sections live entirely inside the view that displays them.

    ``pos`` and ``size`` inside each view entry are optional — _auto_layout()
    fills them in when absent.
    """
    area_configurations = diagram.get('views', []) or []

    if not area_configurations:
        logger.warning("No views configured in diagram.json — nothing to render.")
        return []

    document_size = diagram.get('size', list(DefaultAppValues.DOCUMENT_SIZE))

    # --- Link-graph column assignment ---
    # Only run when at least one area is missing pos/size (full auto-layout mode).
    needs_auto = any('pos' not in c or 'size' not in c for c in area_configurations)
    columns = None
    area_heights = None
    if needs_auto:
        view_ids = [c['id'] for c in area_configurations if 'id' in c]
        if links is not None and links.entries:
            graph = build_link_graph_from_links(links.entries, view_ids)
        else:
            graph = {vid: [] for vid in view_ids}
        columns = assign_columns(graph, view_ids)

        # Pre-resolve sections per view to estimate heights
        area_heights = {}
        for area_config in area_configurations:
            if 'size' in area_config:
                continue
            vid = area_config.get('id', '')
            area_style = theme.resolve(vid)
            view_sections = copy.deepcopy(resolve_view_sections(area_config))
            area_heights[vid] = _estimate_area_height(view_sections, area_style)

    area_configurations = _auto_layout(
        area_configurations, tuple(document_size),
        columns=columns, area_heights=area_heights,
    )

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

    return area_views


def main():
    args = parse_arguments()

    # --validate mode: check diagram.json and exit
    if args.validate:
        errors = validate(args.validate)
        if errors:
            print("Validation failed:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print("OK")
            sys.exit(0)

    if not args.diagram:
        print("Error: --diagram / -d is required unless using --validate")
        sys.exit(1)

    # Load diagram
    try:
        diagram = load(args.diagram)
    except (ValueError, OSError) as e:
        print(f"Error loading diagram: {e}")
        sys.exit(1)

    # Load theme (or use built-in defaults)
    try:
        theme = Theme(args.theme)
    except (OSError, Exception) as e:
        print(f"Error loading theme: {e}")
        sys.exit(1)

    base_style = theme.resolve('')  # global defaults for areas without explicit id

    # Document size
    document_size = diagram.get('size', list(DefaultAppValues.DOCUMENT_SIZE))
    if isinstance(document_size, list) and len(document_size) == 2:
        document_size = tuple(document_size)
    else:
        document_size = DefaultAppValues.DOCUMENT_SIZE

    # Links
    links_config = diagram.get('links', [])
    links_style = theme.resolve_links()
    links = Links(links_config=links_config, style=links_style)

    # Build area views
    area_configs = diagram.get('views', []) or []
    needs_auto = any('pos' not in c or 'size' not in c for c in area_configs)
    area_views = get_area_views(base_style, diagram, theme, links=links)
    if not area_views:
        print("Error: no area views could be created. Check diagram.json configuration.")
        sys.exit(1)

    # In auto-layout mode, expand the canvas to fit all areas (no clipping).
    if needs_auto:
        needed = _auto_canvas_size(area_views)
        document_size = (max(document_size[0], needed[0]),
                         max(document_size[1], needed[1]))

    # Render
    svg_str = MapRenderer(
        area_views=area_views,
        links=links,
        style=base_style,
        size=document_size,
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
