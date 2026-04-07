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
from helpers import safe_element_list_get, safe_element_dict_get, DefaultAppValues
from links import Links
from loader import load, validate, parse_int
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
                        help='Path to the theme.json file (visual styling). '
                             'Uses built-in defaults if omitted.',
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


def _auto_layout(area_configs: list, document_size: tuple) -> list:
    """
    Fill in missing ``pos`` and ``size`` for area configs using auto-layout.

    Areas are arranged left-to-right with equal width and uniform padding.
    Any area that supplies explicit ``pos`` or ``size`` values keeps them;
    the auto-computed value is only used when the key is absent.

    Layout constants (all in pixels):
      PADDING     = 50   horizontal gap between areas and canvas edges
      TITLE_SPACE = 60   vertical space reserved above areas for titles
      BOTTOM_PAD  = 30   vertical gap below areas

    With N areas on a W×H canvas:
      auto_width  = (W - PADDING × (N+1)) / N
      auto_height = H - TITLE_SPACE - BOTTOM_PAD
      auto_x[i]  = PADDING + i × (auto_width + PADDING)
      auto_y      = TITLE_SPACE
    """
    W, H = document_size
    N = len(area_configs)
    if N == 0:
        return area_configs

    PADDING = 50
    TITLE_SPACE = 60
    BOTTOM_PAD = 30

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


def get_area_views(raw_sections: list, base_style: dict, diagram: dict, theme: Theme) -> list:
    """
    Build AreaView objects from diagram config.

    If no 'areas' are configured in the diagram, returns a single default area
    spanning all sections. Otherwise, creates one AreaView per configured area
    with filtering and layout applied.

    ``pos`` and ``size`` inside each area entry are optional — _auto_layout()
    fills them in when absent, distributing areas evenly across the canvas.
    """
    area_configurations = diagram.get('areas', []) or []

    if not area_configurations:
        return [AreaView(
            sections=Sections(sections=raw_sections),
            style=copy.deepcopy(base_style),
            theme=theme,
        )]

    document_size = diagram.get('size', list(DefaultAppValues.DOCUMENT_SIZE))
    area_configurations = _auto_layout(area_configurations, tuple(document_size))

    area_views = []
    for i, area_config in enumerate(area_configurations):
        area_id = area_config.get('id', f'area-{i}')
        memory_range = area_config.get('range', None)
        section_size = area_config.get('section_size', None)

        range_min = None
        range_max = None
        if memory_range:
            range_min = parse_int(memory_range[0]) if len(memory_range) > 0 else None
            range_max = parse_int(memory_range[1]) if len(memory_range) > 1 else None

        size_min = None
        size_max = None
        if section_size:
            size_min = section_size[0] if len(section_size) > 0 else None
            size_max = section_size[1] if len(section_size) > 1 else None

        filtered_sections = (
            Sections(sections=copy.deepcopy(raw_sections))
            .filter_address_min(range_min)
            .filter_address_max(range_max)
            .filter_size_min(size_min)
            .filter_size_max(size_max)
        )

        if len(filtered_sections.get_sections()) == 0:
            logger.warning(
                f"Area '{area_id}' (index {i}) has no sections after filtering. "
                f"Check range and section_size settings. This area will be omitted.")
            continue

        area_style = theme.resolve(area_id)

        area_views.append(AreaView(
            sections=filtered_sections,
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
        raw_sections, diagram = load(args.diagram)
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
    links_config = diagram.get('links', {})
    links_style = theme.resolve_links()
    links = Links(links_config=links_config, style=links_style)

    # Build area views
    area_views = get_area_views(raw_sections, base_style, diagram, theme)
    if not area_views:
        print("Error: no area views could be created. Check diagram.json configuration.")
        sys.exit(1)

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
