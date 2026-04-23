#!/usr/bin/env python3
"""
regenerate.py — Regenerate example SVGs for every layout algorithm.

Usage (from repo root):
    python examples/regenerate.py              # regenerate chips/ and layout/
    python examples/regenerate.py chips        # chips/ only
    python examples/regenerate.py layout       # layout/ only
    python examples/regenerate.py --dry-run    # show what would run, write nothing
    python examples/regenerate.py --update-golden  # also overwrite golden.svg

For each example directory under examples/chips/ and examples/layout/ that
contains a diagram.json, this script generates:

    algo1.svg   --layout algo1
    algo2.svg   --layout algo2
    algo3.svg   --layout algo3
    algo4.svg   --layout algo4

golden.svg uses the default layout (algo3) and is only overwritten when
--update-golden is passed.

Exit codes:
    0  all SVGs written successfully
    1  one or more errors occurred
"""
import argparse
import os
import sys

# ---------------------------------------------------------------------------
# Ensure scripts/ is importable from any working directory
# ---------------------------------------------------------------------------
_HERE    = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.abspath(os.path.join(_HERE, '..', 'scripts'))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from links import Links               # noqa: E402
from loader import load               # noqa: E402
from mmpviz import get_area_views, _auto_canvas_size  # noqa: E402
from renderer import MapRenderer      # noqa: E402
from theme import Theme               # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_LAYOUTS = ['algo1', 'algo2', 'algo3', 'algo4']
DEFAULT_LAYOUT = 'algo3'
DEFAULT_SUBDIRS = ['chips', 'layout']

EXAMPLES_DIR = _HERE


# ---------------------------------------------------------------------------
# Render helper
# ---------------------------------------------------------------------------

def render_with_layout(example_dir: str, layout_algo: str) -> str:
    """Render diagram.json (+ optional theme.json) and return the SVG string.

    Theme resolution mirrors mmpviz.py main(): an embedded ``"theme"`` key in
    the diagram is honored when no sidecar theme.json is present.
    """
    diagram_path = os.path.join(example_dir, 'diagram.json')
    theme_path = os.path.join(example_dir, 'theme.json')

    diagram = load(diagram_path)
    if os.path.isfile(theme_path):
        theme_source = theme_path
    else:
        theme_source = diagram.get('theme')  # may be None, str, or dict
    theme = Theme(theme_source)
    base_style = theme.resolve('')

    links_config = diagram.get('links', [])
    links = Links(links_config=links_config, style=theme.resolve_links())
    growth_arrow = theme.resolve_growth_arrow()

    area_views, routing_lanes = get_area_views(
        base_style, diagram, theme, links=links, layout_algo=layout_algo)
    if not area_views:
        raise ValueError(f"No area views created from {diagram_path!r}")

    doc_w, doc_h, left_overflow, _ = _auto_canvas_size(area_views)
    if routing_lanes:
        lane_bottom = max(
            lane['y'] + lane['height'] / 2
            for lanes in routing_lanes.values()
            for lane in lanes
        )
        doc_h = max(doc_h, int(lane_bottom) + 30)

    svg = MapRenderer(
        area_views=area_views,
        links=links,
        style=base_style,
        growth_arrow=growth_arrow,
        size=(doc_w, doc_h),
        origin=(-left_overflow, 0),
        routing_lanes=routing_lanes or None,
    ).draw()
    return '<?xml version="1.0" encoding="utf-8"?>\n' + svg


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def find_examples(subdirs: list) -> list:
    """Return [(label, example_dir), ...] for every dir with a diagram.json."""
    result = []
    for sub in subdirs:
        d = os.path.join(EXAMPLES_DIR, sub)
        if not os.path.isdir(d):
            print(f'warning: examples subdir not found: {d}', file=sys.stderr)
            continue
        for name in sorted(os.listdir(d)):
            ed = os.path.join(d, name)
            if os.path.isdir(ed) and os.path.isfile(os.path.join(ed, 'diagram.json')):
                result.append((f'{sub}/{name}', ed))
    return result


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate_for_example(example_dir: str, label: str, layouts: list,
                          update_golden: bool, dry_run: bool) -> tuple:
    """Generate layout SVGs for one example.  Returns (ok, errors)."""
    targets = list(layouts)
    if update_golden:
        targets = targets + ['golden']

    ok = errors = 0
    for algo in targets:
        layout_algo = DEFAULT_LAYOUT if algo == 'golden' else algo
        out_name = f'{algo}.svg'
        out_path = os.path.join(example_dir, out_name)
        print(f'  {out_name}', end='', flush=True)
        if dry_run:
            print(' [dry-run]')
            ok += 1
            continue
        try:
            svg = render_with_layout(example_dir, layout_algo)
            with open(out_path, 'w', encoding='utf-8') as fh:
                fh.write(svg)
            print(' ok')
            ok += 1
        except Exception as exc:
            print(f' ERROR: {exc}')
            errors += 1
    return ok, errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Regenerate example SVGs for every layout algorithm.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split('Exit codes')[0].strip())
    parser.add_argument(
        'subdirs', nargs='*', default=DEFAULT_SUBDIRS,
        help=f'Sub-directories under examples/ to process '
             f'(default: {" ".join(DEFAULT_SUBDIRS)})')
    parser.add_argument(
        '--update-golden', action='store_true',
        help='Also overwrite golden.svg using the default layout (algo3)')
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Print what would be written without creating any files')
    parser.add_argument(
        '--layouts', nargs='+', default=ALL_LAYOUTS,
        choices=ALL_LAYOUTS, metavar='ALGO',
        help='Layout algorithms to generate (default: all)')
    args = parser.parse_args()

    examples = find_examples(args.subdirs)
    if not examples:
        print('No examples found.', file=sys.stderr)
        return 1

    total_ok = total_errors = 0
    for label, example_dir in examples:
        print(f'{label}:')
        ok, errors = generate_for_example(
            example_dir, label,
            layouts=args.layouts,
            update_golden=args.update_golden,
            dry_run=args.dry_run,
        )
        total_ok += ok
        total_errors += errors

    prefix = 'dry-run: would generate' if args.dry_run else 'generated'
    print(f'\n{prefix} {total_ok} SVG(s)', end='')
    if total_errors:
        print(f', {total_errors} error(s)')
        return 1
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
