#!/usr/bin/env python3
"""
render_auto_layout.py — Render chip examples with auto-layout and a chosen theme.

Strips explicit pos/size from all area configs so _auto_layout() and the
link-graph column assignment take full control of placement.

Usage:
    python scripts/render_auto_layout.py [-t theme.json] [-o output_dir]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from links import Links
from loader import load
from mmpviz import get_area_views, _auto_layout, _auto_canvas_size
from renderer import MapRenderer
from theme import Theme


CHIPS_DIR = os.path.join(os.path.dirname(__file__), '..', 'examples', 'chips')
DEFAULT_THEME = os.path.join(os.path.dirname(__file__), '..', 'examples', 'themes',
                              'plantuml', 'theme.json')


def render_chip(chip_name: str, theme_path: str, output_dir: str) -> str:
    chip_dir = os.path.join(CHIPS_DIR, chip_name)
    diagram_path = os.path.join(chip_dir, 'diagram.json')
    if not os.path.isfile(diagram_path):
        print(f"  [skip] {chip_name}: no diagram.json found")
        return None

    diagram = load(diagram_path)

    theme = Theme(theme_path)
    base_style = theme.resolve('')

    links_config = diagram.get('links', {})
    links_style = theme.resolve_links()
    links = Links(links_config=links_config, style=links_style)

    area_views = get_area_views(base_style, diagram, theme, links=links)
    if not area_views:
        print(f"  [skip] {chip_name}: no area views produced")
        return None

    # Canvas always auto-sizes to content.
    doc_w, doc_h, left_overflow, top_overflow = _auto_canvas_size(area_views)
    document_size = (doc_w, doc_h)
    origin = (-left_overflow, -top_overflow)

    svg_str = MapRenderer(
        area_views=area_views,
        links=links,
        style=base_style,
        size=document_size,
        origin=origin,
    ).draw()

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f'{chip_name}_auto.svg')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n')
        f.write(svg_str)
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--theme', default=DEFAULT_THEME,
                        help='Path to theme.json (default: plantuml theme)')
    parser.add_argument('-o', '--output', default='/tmp/mmpviz_auto',
                        help='Output directory for rendered SVGs')
    args = parser.parse_args()

    chips = sorted(
        d for d in os.listdir(CHIPS_DIR)
        if os.path.isdir(os.path.join(CHIPS_DIR, d))
    )
    print(f"Rendering {len(chips)} chips → {args.output}/")
    for chip in chips:
        print(f"  {chip} ...", end=' ', flush=True)
        out = render_chip(chip, args.theme, args.output)
        if out:
            print(f"OK  →  {out}")

    print("Done.")


if __name__ == '__main__':
    main()
