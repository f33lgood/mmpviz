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
    return Section(size=size, address=address, id=id,
                   _type='section', parent='none', flags=flags, name=name)


def default_style():
    return {
        'background': 'white', 'fill': 'lightgrey', 'stroke': 'black',
        'stroke_width': 1, 'font_size': 16, 'font_family': 'Helvetica',
        'text_fill': 'black', 'text_stroke': 'black', 'text_stroke_width': 0,
        'break_size': 20, 'break_type': '≈', 'opacity': 1,
        'hide_name': 'auto', 'hide_address': 'auto', 'hide_size': 'auto',
        'growth_arrow_size': 1, 'growth_arrow_fill': 'white', 'growth_arrow_stroke': 'black',
        'weight': 2, 'stroke_dasharray': '3,2',
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
        self.assertIn('0x1000', result)


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
        sections, diagram = load(os.path.join(FIXTURES, 'sample_diagram.json'))
        theme = Theme(os.path.join(FIXTURES, 'sample_theme.json'))

        import copy
        from loader import parse_int
        area_views = []
        for area_config in diagram.get('areas', []):
            area_id = area_config.get('id', '')
            memory_range = area_config.get('range', [])
            rmin = parse_int(memory_range[0]) if len(memory_range) > 0 else None
            rmax = parse_int(memory_range[1]) if len(memory_range) > 1 else None
            filtered = (Sections(sections=copy.deepcopy(sections))
                        .filter_address_min(rmin)
                        .filter_address_max(rmax))
            if not filtered.get_sections():
                continue
            area_views.append(AreaView(
                sections=filtered,
                style=theme.resolve(area_id),
                area_config=area_config,
                theme=theme,
            ))

        links = Links(
            links_config=diagram.get('links', {}),
            style=theme.resolve_links()
        )

        result = MapRenderer(
            area_views=area_views,
            links=links,
            style=theme.resolve(''),
            size=tuple(diagram.get('size', [400, 600])),
        ).draw()

        self.assertIn('<svg', result)
        self.assertNotIn('ns0:', result)


if __name__ == '__main__':
    unittest.main()
