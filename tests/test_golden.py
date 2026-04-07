"""
Golden-file regression tests.

For every example directory that contains diagram.json + theme.json + golden.svg,
this module re-renders the diagram and compares the output geometrically to the
stored golden SVG.

How to update golden files after an intentional change:
    python scripts/mmpviz.py -d examples/<name>/diagram.json \
                             -t examples/<name>/theme.json   \
                             -o examples/<name>/golden.svg
"""
import copy
import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

from area_view import AreaView
from links import Links
from loader import load, parse_int
from mmpviz import get_area_views
from renderer import MapRenderer
from sections import Sections
from theme import Theme

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
EXAMPLES_DIR = os.path.join(REPO, 'examples')
SVG_NS = 'http://www.w3.org/2000/svg'
TOL = 0.01  # pixel tolerance


# ---------------------------------------------------------------------------
# SVG geometry extraction (same logic as /tmp/compare_stack/compare.py)
# ---------------------------------------------------------------------------

def _parse_translate(transform_str):
    if not transform_str:
        return (0.0, 0.0)
    m = re.search(r'translate\(\s*([+-]?\d*\.?\d+)[,\s]+([+-]?\d*\.?\d+)\s*\)',
                  transform_str)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'translate\(\s*([+-]?\d*\.?\d+)\s*\)', transform_str)
    if m:
        return float(m.group(1)), 0.0
    return (0.0, 0.0)


def _walk(elem, ox=0.0, oy=0.0):
    dx, dy = _parse_translate(elem.get('transform'))
    cx, cy = ox + dx, oy + dy
    yield elem, cx, cy
    for child in elem:
        yield from _walk(child, cx, cy)


def _fa(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _parse_points(pts_str):
    nums = [float(v) for v in re.findall(r'[+-]?\d*\.?\d+', pts_str)]
    return [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]


def _local_tag(elem):
    return elem.tag.replace(f'{{{SVG_NS}}}', '')


def _parse_path_nums(d_str):
    """Extract all numbers from a SVG path data string."""
    return [float(v) for v in re.findall(r'[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', d_str)]


def extract_geometry(root):
    """Return (rects, texts, polylines, paths) with absolute coordinates."""
    canvas_w = _fa(root.get('width'))
    canvas_h = _fa(root.get('height'))

    rects, texts, polys, paths = [], [], [], []

    for elem, ox, oy in _walk(root):
        t = _local_tag(elem)

        if t == 'rect':
            w = _fa(elem.get('width'))
            h = _fa(elem.get('height'))
            if w is None:           # percentage-based (linkerscope canvas bg)
                continue
            x = (_fa(elem.get('x')) or 0.0) + ox
            y = (_fa(elem.get('y')) or 0.0) + oy
            # skip the explicit canvas background rect
            if (abs(x) < TOL and abs(y) < TOL
                    and canvas_w is not None and abs(w - canvas_w) < TOL
                    and canvas_h is not None and abs(h - canvas_h) < TOL):
                continue
            rects.append((x, y, w, h, elem.get('fill', '').lower()))

        elif t == 'text':
            x = (_fa(elem.get('x')) or 0.0) + ox
            y = (_fa(elem.get('y')) or 0.0) + oy
            texts.append((x, y, elem.get('fill', '').lower(),
                          (elem.text or '').strip()))

        elif t == 'polyline':
            pts = [(px + ox, py + oy)
                   for px, py in _parse_points(elem.get('points', ''))]
            polys.append((pts, elem.get('fill', '').lower()))

        elif t == 'path':
            nums = _parse_path_nums(elem.get('d', ''))
            paths.append((nums,
                          elem.get('fill', '').lower(),
                          elem.get('stroke', '').lower()))

    return rects, texts, polys, paths


def _close(a, b):
    return abs(a - b) <= TOL


def _pts_equal(p1, p2):
    return (len(p1) == len(p2)
            and all(_close(a[0], b[0]) and _close(a[1], b[1])
                    for a, b in zip(p1, p2)))


# ---------------------------------------------------------------------------
# Renderer helper (mirrors mmpviz.py main() without file I/O)
# ---------------------------------------------------------------------------

def render_example(example_dir):
    """Render diagram.json + theme.json and return the SVG string."""
    import json
    diagram_path = os.path.join(example_dir, 'diagram.json')
    theme_path = os.path.join(example_dir, 'theme.json')

    raw_sections, diagram = load(diagram_path)
    theme = Theme(theme_path)
    base_style = theme.resolve('')

    doc_size = diagram.get('size', [400, 700])
    doc_size = tuple(doc_size) if isinstance(doc_size, list) else doc_size

    links_config = diagram.get('links', {})
    links = Links(links_config=links_config, style=theme.resolve_links())

    area_views = get_area_views(raw_sections, base_style, diagram, theme)

    return MapRenderer(
        area_views=area_views,
        links=links,
        style=base_style,
        size=doc_size,
    ).draw()


# ---------------------------------------------------------------------------
# Test discovery and parametric cases
# ---------------------------------------------------------------------------

def _find_examples():
    """Return list of (name, example_dir) for every complete example."""
    examples = []
    if not os.path.isdir(EXAMPLES_DIR):
        return examples
    for name in sorted(os.listdir(EXAMPLES_DIR)):
        d = os.path.join(EXAMPLES_DIR, name)
        if not os.path.isdir(d):
            continue
        if all(os.path.isfile(os.path.join(d, f))
               for f in ('diagram.json', 'theme.json', 'golden.svg')):
            examples.append((name, d))
    return examples


class GoldenTest(unittest.TestCase):
    """Parametric golden-file tests — one sub-test per example directory."""

    def _compare(self, name, example_dir):
        golden_path = os.path.join(example_dir, 'golden.svg')
        golden_root = ET.parse(golden_path).getroot()
        golden_rects, golden_texts, golden_polys, golden_paths = extract_geometry(golden_root)

        fresh_svg = render_example(example_dir)
        fresh_root = ET.fromstring(fresh_svg)
        fresh_rects, fresh_texts, fresh_polys, fresh_paths = extract_geometry(fresh_root)

        def sort_rects(rs):
            return sorted(rs, key=lambda r: (round(r[1], 1), round(r[0], 1), r[4]))

        def sort_texts(ts):
            return sorted(ts, key=lambda t: (t[3], round(t[1], 1)))

        def sort_polys(ps):
            return sorted(ps,
                          key=lambda p: (round(p[0][0][1], 1) if p[0] else 0, p[1]))

        gr = sort_rects(golden_rects)
        fr = sort_rects(fresh_rects)
        gt = sort_texts(golden_texts)
        ft = sort_texts(fresh_texts)
        gp = sort_polys(golden_polys)
        fp = sort_polys(fresh_polys)

        # --- rects ---
        self.assertEqual(
            len(gr), len(fr),
            f"[{name}] rect count: golden={len(gr)} fresh={len(fr)}\n"
            f"  golden: {gr}\n  fresh:  {fr}")
        for i, (g, f) in enumerate(zip(gr, fr)):
            self.assertTrue(
                _close(g[0], f[0]) and _close(g[1], f[1])
                and _close(g[2], f[2]) and _close(g[3], f[3])
                and g[4] == f[4],
                f"[{name}] rect #{i + 1} mismatch\n"
                f"  golden: x={g[0]:.2f} y={g[1]:.2f} w={g[2]:.2f} h={g[3]:.2f} fill={g[4]}\n"
                f"  fresh:  x={f[0]:.2f} y={f[1]:.2f} w={f[2]:.2f} h={f[3]:.2f} fill={f[4]}")

        # --- texts ---
        self.assertEqual(
            len(gt), len(ft),
            f"[{name}] text count: golden={len(gt)} fresh={len(ft)}")
        for i, (g, f) in enumerate(zip(gt, ft)):
            self.assertEqual(
                g[3], f[3],
                f"[{name}] text #{i + 1} content: golden={g[3]!r} fresh={f[3]!r}")
            self.assertTrue(
                _close(g[0], f[0]) and _close(g[1], f[1]),
                f"[{name}] text #{i + 1} {g[3]!r} position: "
                f"golden=({g[0]:.2f},{g[1]:.2f}) fresh=({f[0]:.2f},{f[1]:.2f})")
            self.assertEqual(
                g[2], f[2],
                f"[{name}] text #{i + 1} {g[3]!r} fill: golden={g[2]} fresh={f[2]}")

        # --- polylines ---
        self.assertEqual(
            len(gp), len(fp),
            f"[{name}] polyline count: golden={len(gp)} fresh={len(fp)}")
        for i, (g, f) in enumerate(zip(gp, fp)):
            self.assertTrue(
                _pts_equal(g[0], f[0]),
                f"[{name}] polyline #{i + 1} points mismatch\n"
                f"  golden: {g[0]}\n  fresh:  {f[0]}")

        # --- paths (section band links) ---
        def sort_paths(ps):
            return sorted(ps, key=lambda p: (round(p[0][0], 1) if p[0] else 0, p[1], p[2]))

        gpa = sort_paths(golden_paths)
        fpa = sort_paths(fresh_paths)
        self.assertEqual(
            len(gpa), len(fpa),
            f"[{name}] path count: golden={len(gpa)} fresh={len(fpa)}")
        for i, (g, f) in enumerate(zip(gpa, fpa)):
            self.assertEqual(
                g[1], f[1],
                f"[{name}] path #{i + 1} fill: golden={g[1]} fresh={f[1]}")
            self.assertEqual(
                g[2], f[2],
                f"[{name}] path #{i + 1} stroke: golden={g[2]} fresh={f[2]}")
            self.assertEqual(
                len(g[0]), len(f[0]),
                f"[{name}] path #{i + 1} coordinate count: golden={len(g[0])} fresh={len(f[0])}")
            for j, (gv, fv) in enumerate(zip(g[0], f[0])):
                self.assertTrue(
                    _close(gv, fv),
                    f"[{name}] path #{i + 1} coord #{j}: golden={gv:.4f} fresh={fv:.4f}")

    def test_stack(self):
        self._run_named('stack')

    def test_break(self):
        self._run_named('break')

    def test_labels(self):
        self._run_named('labels')

    def test_link_cortex_m3(self):
        self._run_path('link', 'cortex_m3')

    def test_link_polygon_fill(self):
        self._run_path('link', 'polygon_fill')

    def test_link_polygon_stroke(self):
        self._run_path('link', 'polygon_stroke')

    def test_link_polygon_stroke_dashed(self):
        self._run_path('link', 'polygon_stroke_dashed')

    def test_link_curve_fill(self):
        self._run_path('link', 'curve_fill')

    def test_link_curve_stroke(self):
        self._run_path('link', 'curve_stroke')

    def test_link_curve_stroke_dashed(self):
        self._run_path('link', 'curve_stroke_dashed')

    def test_stm32f103(self):
        self._run_named('stm32f103')

    def _run_named(self, name):
        d = os.path.join(EXAMPLES_DIR, name)
        if not all(os.path.isfile(os.path.join(d, f))
                   for f in ('diagram.json', 'theme.json', 'golden.svg')):
            self.skipTest(f"example '{name}' is missing files")
        self._compare(name, d)

    def _run_path(self, *rel_parts):
        """Run a golden test for a nested example directory."""
        d = os.path.join(EXAMPLES_DIR, *rel_parts)
        label = '/'.join(rel_parts)
        if not all(os.path.isfile(os.path.join(d, f))
                   for f in ('diagram.json', 'theme.json', 'golden.svg')):
            self.skipTest(f"example '{label}' is missing files")
        self._compare(label, d)


if __name__ == '__main__':
    unittest.main()
