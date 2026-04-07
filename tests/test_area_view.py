import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import unittest
from section import Section
from sections import Sections
from area_view import AreaView
from theme import Theme

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def make_section(address, size, id='s', flags=None):
    return Section(size=size, address=address, id=id,
                   _type='section', parent='none', flags=flags)


def default_style():
    return {
        'background': 'white', 'fill': 'lightgrey', 'stroke': 'black',
        'stroke_width': 1, 'font_size': 16, 'font_family': 'Helvetica',
        'text_fill': 'black', 'break_size': 20, 'break_type': '≈',
        'hide_name': 'auto', 'hide_address': 'auto', 'hide_size': 'auto',
    }


class TestAreaViewPixelConversion(unittest.TestCase):

    def setUp(self):
        s = make_section(0x0, 0x1000)
        self.av = AreaView(
            sections=Sections([s]),
            style=default_style(),
            area_config={
                'id': 'test', 'title': 'Test',
                'pos': [0, 500], 'size': [200, 500],
                'start': 0x0, 'end': 0x1000,
            },
            is_subarea=True,  # don't call _process
        )

    def test_to_pixels(self):
        # address_to_pxl = 0x1000 / 500 = 8.192
        # to_pixels(0x1000) = 0x1000 / ratio = 500
        self.assertAlmostEqual(self.av.to_pixels(0x1000), 500.0, places=2)

    def test_to_pixels_relative_bottom(self):
        # to_pixels_relative(0x0) = size_y - 0 = 500
        self.assertAlmostEqual(self.av.to_pixels_relative(0x0), 500.0, places=2)

    def test_to_pixels_relative_top(self):
        # to_pixels_relative(0x1000) = size_y - size_y = 0
        self.assertAlmostEqual(self.av.to_pixels_relative(0x1000), 0.0, places=2)

    def test_to_pixels_relative_midpoint(self):
        # mid address → mid pixels
        mid_addr = 0x800
        result = self.av.to_pixels_relative(mid_addr)
        self.assertAlmostEqual(result, 250.0, places=2)


class TestAreaViewProcess(unittest.TestCase):

    def test_no_breaks_produces_self(self):
        s1 = make_section(0x0, 0x500)
        s2 = make_section(0x500, 0x500)
        av = AreaView(
            sections=Sections([s1, s2]),
            style=default_style(),
            area_config={'id': 'av', 'title': 'Test', 'pos': [0, 500], 'size': [200, 500]},
        )
        views = av.get_split_area_views()
        self.assertEqual(len(views), 1)
        self.assertIs(views[0], av)

    def test_break_section_creates_subareas(self):
        s1 = make_section(0x0, 0x400, 's1')
        brk = make_section(0x400, 0x200, 'brk', flags=['break'])
        s2 = make_section(0x600, 0x400, 's2')
        av = AreaView(
            sections=Sections([s1, brk, s2]),
            style=default_style(),
            area_config={'id': 'av', 'title': 'Test', 'pos': [0, 500], 'size': [200, 500]},
        )
        views = av.get_split_area_views()
        self.assertGreater(len(views), 1)


class TestAreaViewStyleOverride(unittest.TestCase):

    def test_section_flag_override_appended(self):
        s = make_section(0x0, 0x400, 's1')
        area_config = {
            'id': 'av', 'title': 'T', 'pos': [0, 500], 'size': [200, 500],
            'sections': [{'names': ['s1'], 'flags': ['break']}]
        }
        av = AreaView(
            sections=Sections([s]),
            style=default_style(),
            area_config=area_config,
        )
        # s1 should now have the 'break' flag appended
        section = av.sections.get_sections()[0]
        self.assertIn('break', section.flags)

    def test_style_from_theme_applied(self):
        s = make_section(0x0, 0x400, 'text')
        theme = Theme(os.path.join(FIXTURES, 'sample_theme.json'))
        area_config = {'id': 'flash-view', 'title': 'Flash', 'pos': [0, 500], 'size': [200, 500]}
        av = AreaView(
            sections=Sections([s]),
            style=theme.resolve('flash-view'),
            area_config=area_config,
            theme=theme,
        )
        # 'text' section should get section-specific fill from theme
        section = av.sections.get_sections()[0]
        self.assertEqual(section.style.get('fill'), '#99B898')


if __name__ == '__main__':
    unittest.main()
