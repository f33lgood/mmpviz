import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import xml.etree.ElementTree as ET
import unittest
from svg_builder import SVGBuilder, translate, rotate

SVG_NS = 'http://www.w3.org/2000/svg'


def tag(name):
    return f'{{{SVG_NS}}}{name}'


class TestSVGBuilderElements(unittest.TestCase):

    def setUp(self):
        self.svg = SVGBuilder(400, 700)

    def test_rect_tag_and_attrs(self):
        r = self.svg.rect(10, 20, 100, 50, fill='red', stroke='black')
        self.assertEqual(r.tag, tag('rect'))
        self.assertEqual(r.get('x'), '10')
        self.assertEqual(r.get('y'), '20')
        self.assertEqual(r.get('width'), '100')
        self.assertEqual(r.get('height'), '50')
        self.assertEqual(r.get('fill'), 'red')
        self.assertEqual(r.get('stroke'), 'black')

    def test_snake_case_to_kebab_case(self):
        r = self.svg.rect(0, 0, 10, 10, stroke_width=2, font_size=16)
        self.assertEqual(r.get('stroke-width'), '2')
        self.assertEqual(r.get('font-size'), '16')

    def test_text_element(self):
        t = self.svg.text('Hello', 50, 100, fill='black', text_anchor='middle')
        self.assertEqual(t.tag, tag('text'))
        self.assertEqual(t.text, 'Hello')
        self.assertEqual(t.get('x'), '50')
        self.assertEqual(t.get('text-anchor'), 'middle')

    def test_polyline_points_format(self):
        pts = [(0, 0), (10, 20), (30, 40)]
        p = self.svg.polyline(pts, stroke='black')
        self.assertEqual(p.get('points'), '0,0 10,20 30,40')

    def test_polyline_float_points(self):
        pts = [(1.5, 2.5), (3.0, 4.0)]
        p = self.svg.polyline(pts)
        self.assertEqual(p.get('points'), '1.5,2.5 3.0,4.0')

    def test_circle_attrs(self):
        c = self.svg.circle(50, 60, 5, fill='white')
        self.assertEqual(c.tag, tag('circle'))
        self.assertEqual(c.get('cx'), '50')
        self.assertEqual(c.get('cy'), '60')
        self.assertEqual(c.get('r'), '5')

    def test_line_attrs(self):
        ln = self.svg.line(0, 0, 100, 100, stroke='black')
        self.assertEqual(ln.tag, tag('line'))
        self.assertEqual(ln.get('x1'), '0')
        self.assertEqual(ln.get('x2'), '100')

    def test_g_element(self):
        g = self.svg.g()
        self.assertEqual(g.tag, tag('g'))

    def test_path_element(self):
        d = 'M 0,0 L 100,0 L 100,100 Z'
        p = self.svg.path(d, fill='blue', stroke='none')
        self.assertEqual(p.tag, tag('path'))
        self.assertEqual(p.get('d'), d)
        self.assertEqual(p.get('fill'), 'blue')
        self.assertEqual(p.get('stroke'), 'none')

    def test_path_dasharray_kebab(self):
        p = self.svg.path('M 0,0 L 10,10', stroke_dasharray='8,4')
        self.assertEqual(p.get('stroke-dasharray'), '8,4')

    def test_none_attrs_omitted(self):
        r = self.svg.rect(0, 0, 10, 10, fill=None, stroke='black')
        self.assertIsNone(r.get('fill'))
        self.assertEqual(r.get('stroke'), 'black')


class TestSVGBuilderOutput(unittest.TestCase):

    def test_to_string_no_ns0_prefix(self):
        svg = SVGBuilder(100, 100)
        result = svg.to_string()
        self.assertNotIn('ns0:', result)
        self.assertIn('<svg', result)

    def test_to_string_is_valid_xml(self):
        svg = SVGBuilder(200, 300)
        r = svg.rect(0, 0, 200, 300, fill='white')
        svg.root.append(r)
        result = svg.to_string()
        # Should parse back without error
        root = ET.fromstring(result)
        self.assertIsNotNone(root)

    def test_root_has_correct_dimensions(self):
        svg = SVGBuilder(500, 800)
        self.assertEqual(svg.root.get('width'), '500')
        self.assertEqual(svg.root.get('height'), '800')

    def test_default_viewbox_starts_at_origin(self):
        svg = SVGBuilder(400, 300)
        self.assertEqual(svg.root.get('viewBox'), '0 0 400 300')

    def test_origin_shifts_viewbox(self):
        svg = SVGBuilder(500, 300, origin_x=-120, origin_y=0)
        self.assertEqual(svg.root.get('viewBox'), '-120 0 500 300')
        self.assertEqual(svg.root.get('width'), '500')
        self.assertEqual(svg.root.get('height'), '300')


class TestTransformHelpers(unittest.TestCase):

    def test_translate(self):
        svg = SVGBuilder(100, 100)
        g = svg.g()
        translate(g, 10, 20)
        self.assertEqual(g.get('transform'), 'translate(10,20)')

    def test_rotate(self):
        svg = SVGBuilder(100, 100)
        elem = svg.g()
        rotate(elem, 90, 0, 0)
        self.assertEqual(elem.get('transform'), 'rotate(90,0,0)')


if __name__ == '__main__':
    unittest.main()
