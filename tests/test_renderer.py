import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import unittest
from section import Section
from sections import Sections
from area_view import AreaView
from links import Links
from renderer import MapRenderer
from theme import Theme

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def make_section(address, size, id='s', flags=None, name=None):
    return Section(size=size, address=address, id=id, flags=flags, name=name)


def default_style():
    return {
        'background': 'white', 'fill': 'lightgrey', 'stroke': 'black',
        'stroke_width': 1, 'font_size': 16, 'font_family': 'Helvetica',
        'text_fill': 'black', 'text_stroke': 'black', 'text_stroke_width': 0,
        'break_height': 20, 'opacity': 1,
        'arrow_size': 2, 'stroke_dasharray': '3,2',
    }


def build_simple_area(sections_list, style=None):
    style = style or default_style()
    s = Sections(sections_list)
    return AreaView(
        sections=s,
        style=style,
        area_config={
            'id': 'test-area', 'title': 'Test Area',
            'pos': [50, 500], 'size': [200, 500],
        },
    )


class TestRendererBasic(unittest.TestCase):

    def test_draw_returns_string(self):
        s1 = make_section(0x0, 0x400, 'code', name='Code')
        s2 = make_section(0x400, 0x200, 'data', name='Data')
        area = build_simple_area([s1, s2])
        links = Links()
        result = MapRenderer(
            area_views=[area],
            links=links,
            style=default_style(),
            size=(400, 600),
        ).draw()
        self.assertIsInstance(result, str)

    def test_output_is_svg(self):
        s1 = make_section(0x0, 0x400, 'code')
        area = build_simple_area([s1])
        result = MapRenderer(
            area_views=[area],
            links=Links(),
            style=default_style(),
            size=(400, 600),
        ).draw()
        self.assertIn('<svg', result)

    def test_section_id_appears_in_output(self):
        s1 = make_section(0x0, 0x1000, 'mycode', name='MyCode')
        area = build_simple_area([s1])
        result = MapRenderer(
            area_views=[area],
            links=Links(),
            style=default_style(),
            size=(400, 600),
        ).draw()
        self.assertIn('MyCode', result)

    def test_address_appears_in_output(self):
        s1 = make_section(0x1000, 0x800, 'x', name='Seg')
        area = build_simple_area([s1])
        result = MapRenderer(
            area_views=[area],
            links=Links(),
            style=default_style(),
            size=(400, 600),
        ).draw()
        self.assertIn('0x00001000', result)


class TestRendererBreakSection(unittest.TestCase):

    def test_break_section_renders(self):
        s1 = make_section(0x0, 0x400, 's1', name='Before')
        brk = make_section(0x400, 0x200, 'brk', flags=['break'])
        s2 = make_section(0x600, 0x400, 's2', name='After')
        area = build_simple_area([s1, brk, s2])
        result = MapRenderer(
            area_views=[area],
            links=Links(),
            style=default_style(),
            size=(400, 800),
        ).draw()
        self.assertIn('<svg', result)
        # Section names before/after break should appear
        self.assertIn('Before', result)
        self.assertIn('After', result)


class TestRendererGrowthArrows(unittest.TestCase):

    def test_grows_up_renders(self):
        s = make_section(0x0, 0x800, 'stack', flags=['grows-up'], name='Stack')
        area = build_simple_area([s])
        result = MapRenderer(
            area_views=[area],
            links=Links(),
            style=default_style(),
            size=(400, 600),
        ).draw()
        # Growth arrows use polyline; result should be valid SVG
        self.assertIn('polyline', result)


class TestRendererFromFixtures(unittest.TestCase):

    def test_full_render_from_fixtures(self):
        from loader import load
        from mmpviz import get_area_views
        diagram = load(os.path.join(FIXTURES, 'sample_diagram.json'))
        theme = Theme(os.path.join(FIXTURES, 'sample_theme.json'))

        links = Links(
            links_config=diagram.get('links', []),
            style=theme.resolve_links()
        )
        area_views, _routing_lanes = get_area_views(
            base_style=theme.resolve(''),
            diagram=diagram,
            theme=theme,
            links=links,
        )

        result = MapRenderer(
            area_views=area_views,
            links=links,
            style=theme.resolve(''),
            size=(400, 600),
        ).draw()

        self.assertIn('<svg', result)
        self.assertNotIn('ns0:', result)


class TestRendererSectionBandStyles(unittest.TestCase):
    """Tests for section band link shape and fill/stroke composability."""

    def _render_two_area(self, link_style: dict) -> str:
        """Render a two-area diagram with a section link.

        link_style may be:
        - ``{}`` to exercise renderer fallback defaults (no band/connector key)
        - a band shorthand: 'shape' maps to middle.shape; fill/stroke/etc. are
          passed through; the dict is wrapped under the 'band' key automatically
        """
        s_a = make_section(0x0, 0x10000, 'Region A', name='Region A')
        s_b = make_section(0x10000, 0x10000, 'Region B', name='Region B')
        s_c = make_section(0x20000, 0x10000, 'Region C', name='Region C')
        style = default_style()

        source = AreaView(
            sections=Sections([s_a, s_b, s_c]),
            style=style,
            area_config={'id': 'source', 'title': 'Full', 'pos': [50, 80], 'size': [130, 350]},
        )
        detail = AreaView(
            sections=Sections([s_b]),
            style=style,
            area_config={'id': 'detail', 'title': 'Zoomed', 'pos': [320, 155], 'size': [130, 200]},
        )

        if link_style:
            shape = link_style.get('shape', 'straight')
            band = {
                'middle': {'shape': shape, 'sheight': 'source', 'dheight': 'destination'},
            }
            for k in ('fill', 'stroke', 'stroke_width', 'stroke_dasharray', 'opacity'):
                if k in link_style:
                    band[k] = link_style[k]
            normalized = {'band': band}
        else:
            normalized = {}

        links = Links(
            links_config=[{
                'id':   'test-link',
                'from': {'view': 'source', 'sections': ['Region B']},
                'to':   {'view': 'detail'},
            }],
            style=normalized,
        )
        return MapRenderer(
            area_views=[source, detail],
            links=links,
            style=style,
            size=(500, 500),
        ).draw()

    def test_polygon_fill_only_produces_path_with_fill(self):
        svg = self._render_two_area({'shape': 'polygon', 'fill': 'steelblue', 'stroke': 'none'})
        import xml.etree.ElementTree as ET
        root = ET.fromstring(svg)
        ns = 'http://www.w3.org/2000/svg'
        paths = root.findall(f'.//{{{ns}}}path')
        filled = [p for p in paths if p.get('fill') not in (None, 'none')]
        self.assertTrue(len(filled) >= 1, "Expected at least one filled path element")

    def test_polygon_stroke_only_produces_two_open_paths(self):
        svg = self._render_two_area({'shape': 'polygon', 'fill': 'none', 'stroke': 'navy'})
        import xml.etree.ElementTree as ET
        root = ET.fromstring(svg)
        ns = 'http://www.w3.org/2000/svg'
        paths = root.findall(f'.//{{{ns}}}path')
        stroked = [p for p in paths if p.get('stroke') not in (None, 'none')]
        # Two open paths: top edge + bottom edge
        self.assertEqual(len(stroked), 2, f"Expected 2 stroked open paths, got {len(stroked)}")

    def test_curve_fill_uses_bezier_in_path_d(self):
        svg = self._render_two_area({'shape': 'curve', 'fill': 'teal', 'stroke': 'none'})
        # Bézier curves use 'C' command in SVG path data
        self.assertIn(' C ', svg)

    def test_polygon_no_bezier(self):
        svg = self._render_two_area({'shape': 'polygon', 'fill': 'teal', 'stroke': 'none'})
        self.assertNotIn(' C ', svg)

    def test_stroke_dasharray_propagated(self):
        svg = self._render_two_area({
            'shape': 'polygon', 'fill': 'none',
            'stroke': 'gray', 'stroke_dasharray': '8,4',
        })
        self.assertIn('stroke-dasharray', svg)
        self.assertIn('8,4', svg)

    def test_both_fill_and_stroke_renders_three_paths(self):
        # fill → 1 closed path; stroke → 2 open paths = 3 total
        svg = self._render_two_area({'shape': 'polygon', 'fill': 'gray', 'stroke': 'black'})
        import xml.etree.ElementTree as ET
        root = ET.fromstring(svg)
        ns = 'http://www.w3.org/2000/svg'
        paths = root.findall(f'.//{{{ns}}}path')
        band_paths = [p for p in paths if p.get('d', '').startswith('M ')]
        self.assertEqual(len(band_paths), 3)

    def test_minimum_opening_enforced_for_zero_range_section(self):
        """A zero-size section must still produce a visible (>=4px) band opening."""
        # Both start and end address are the same → degenerate case
        s_a = make_section(0x0, 0x10000, 'Region A', name='Region A')
        s_b = make_section(0x10000, 0x1, 'Region B', name='Region B')  # 1-byte section
        s_c = make_section(0x10001, 0x10000, 'Region C', name='Region C')
        style = default_style()
        source = AreaView(
            sections=Sections([s_a, s_b, s_c]),
            style=style,
            area_config={'id': 'source', 'title': 'Full', 'pos': [50, 80], 'size': [130, 350]},
        )
        detail = AreaView(
            sections=Sections([s_b]),
            style=style,
            area_config={'id': 'detail', 'title': 'Zoomed', 'pos': [320, 155], 'size': [130, 200]},
        )
        links = Links(
            links_config=[{
                'id':   'test-link',
                'from': {'view': 'source', 'sections': ['Region B']},
                'to':   {'view': 'detail'},
            }],
            style={'band': {
                'source':  {'width': 30, 'sheight': 'source', 'dheight': 'source'},
                'middle':  {'shape': 'straight', 'sheight': 'source', 'dheight': 'destination'},
                'fill':    'gray',
                'stroke':  'none',
            }},
        )
        result = MapRenderer(
            area_views=[source, detail],
            links=links,
            style=style,
            size=(500, 500),
        ).draw()
        # Should render without error and contain a path
        import xml.etree.ElementTree as ET
        root = ET.fromstring(result)
        ns = 'http://www.w3.org/2000/svg'
        paths = root.findall(f'.//{{{ns}}}path')
        self.assertTrue(len(paths) >= 1)
        # Verify band coordinates span at least MIN_BAND_OPENING_PX apart
        from renderer import MapRenderer as MR
        MIN = MR._MIN_BAND_OPENING_PX
        d_str = paths[0].get('d', '')
        import re
        nums = [float(v) for v in re.findall(r'[+-]?\d+(?:\.\d+)?', d_str)]
        # Path: M lx,ly_t L lx_j,ly_t L rx,ry_t L rx,ry_b L lx_j,ly_b L lx,ly_b Z
        # ly_t is nums[1], ly_b is nums[11]
        ly_t, ly_b = nums[1], nums[11]
        self.assertGreaterEqual(abs(ly_t - ly_b), MIN - 0.01)

    def test_no_link_style_defaults_to_stroke_only(self):
        # Default: fill="none", stroke="black" → 2 open stroke paths
        svg = self._render_two_area({})
        import xml.etree.ElementTree as ET
        root = ET.fromstring(svg)
        ns = 'http://www.w3.org/2000/svg'
        paths = root.findall(f'.//{{{ns}}}path')
        stroked = [p for p in paths if p.get('stroke') not in (None, 'none')]
        self.assertEqual(len(stroked), 2)


if __name__ == '__main__':
    unittest.main()
