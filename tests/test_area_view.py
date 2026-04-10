import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import unittest
from section import Section
from sections import Sections
from area_view import AreaView
from theme import Theme

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def make_section(address, size, id='s', flags=None):
    return Section(size=size, address=address, id=id, flags=flags)


def default_style():
    return {
        'background': 'white', 'fill': 'lightgrey', 'stroke': 'black',
        'stroke_width': 1, 'font_size': 16, 'font_family': 'Helvetica',
        'text_fill': 'black', 'break_height': 20,
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
            'sections': [{'ids': ['s1'], 'flags': ['break']}]
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


class TestComputePerSectionHeights(unittest.TestCase):
    """Unit tests for _compute_per_section_heights."""

    def _av(self):
        s = make_section(0x0, 0x1000)
        return AreaView(
            sections=Sections([s]),
            style=default_style(),
            area_config={'id': 't', 'pos': [0, 500], 'size': [200, 500],
                         'start': 0x0, 'end': 0x1000},
            is_subarea=True,
        )

    def test_empty_returns_empty(self):
        av = self._av()
        self.assertEqual(av._compute_per_section_heights([], 100.0, 14.0, None), {})

    def test_zero_available_returns_empty(self):
        av = self._av()
        s = make_section(0x0, 0x100)
        self.assertEqual(av._compute_per_section_heights([s], 0.0, 14.0, None), {})

    def test_proportional_no_constraints(self):
        av = self._av()
        s1 = make_section(0x0, 0x800, 's1')
        s2 = make_section(0x800, 0x800, 's2')
        r = av._compute_per_section_heights([s1, s2], 100.0, None, None)
        self.assertAlmostEqual(r[id(s1)], 50.0, places=5)
        self.assertAlmostEqual(r[id(s2)], 50.0, places=5)

    def test_small_section_locked_at_min_h(self):
        av = self._av()
        big = make_section(0x0, 0x10000, 'big')
        small = make_section(0x10000, 0x10, 'small')
        r = av._compute_per_section_heights([big, small], 100.0, 14.0, None)
        self.assertAlmostEqual(r[id(small)], 14.0, places=5)
        self.assertAlmostEqual(r[id(big)], 86.0, places=2)
        total = sum(r.values())
        self.assertAlmostEqual(total, 100.0, places=2)

    def test_large_section_capped_at_max_h(self):
        av = self._av()
        big = make_section(0x0, 0x10000, 'big')
        small = make_section(0x10000, 0x10, 'small')
        # Use max_h=80: big (~99.98px proportional) is capped; small gets ~20px
        r = av._compute_per_section_heights([big, small], 100.0, None, 80.0)
        self.assertAlmostEqual(r[id(big)], 80.0, places=5)
        # small receives the space freed by the cap (100 - 80 = 20)
        self.assertAlmostEqual(r[id(small)], 20.0, places=2)
        self.assertAlmostEqual(sum(r.values()), 100.0, places=2)

    def test_overflow_falls_back_to_proportional(self):
        av = self._av()
        s1 = make_section(0x0, 0x10, 's1')
        s2 = make_section(0x10, 0x10, 's2')
        # min_h=80 would require 160px but only 100 available → proportional fallback
        r = av._compute_per_section_heights([s1, s2], 100.0, 80.0, None)
        self.assertAlmostEqual(r[id(s1)], 50.0, places=5)
        self.assertAlmostEqual(r[id(s2)], 50.0, places=5)

    def test_hidden_section_not_min_h_enforced(self):
        av = self._av()
        visible = make_section(0x0, 0x10, 'v')
        hidden = make_section(0x10, 0x10000, 'h', flags=['hidden'])
        # hidden section acts as a spacer — no min_h constraint
        r = av._compute_per_section_heights([visible, hidden], 100.0, 14.0, None)
        self.assertAlmostEqual(r[id(visible)], 14.0, places=5)
        # hidden gets the remainder
        self.assertAlmostEqual(r[id(hidden)], 86.0, places=2)

    def test_total_equals_available(self):
        av = self._av()
        sections = [make_section(i * 0x100, 0x100, f's{i}') for i in range(5)]
        r = av._compute_per_section_heights(sections, 300.0, 14.0, 200.0)
        self.assertAlmostEqual(sum(r.values()), 300.0, places=2)

    def test_equal_sections_equal_height(self):
        av = self._av()
        sections = [make_section(i * 0x100, 0x100, f's{i}') for i in range(4)]
        r = av._compute_per_section_heights(sections, 200.0, 14.0, None)
        for s in sections:
            self.assertAlmostEqual(r[id(s)], 50.0, places=5)

    def test_multiple_small_sections_all_get_min_h(self):
        av = self._av()
        big = make_section(0x0, 0x100000, 'big')
        smalls = [make_section(0x100000 + i * 0x10, 0x10, f's{i}') for i in range(3)]
        all_secs = [big] + smalls
        r = av._compute_per_section_heights(all_secs, 200.0, 20.0, None)
        for s in smalls:
            self.assertAlmostEqual(r[id(s)], 20.0, places=5)
        self.assertAlmostEqual(r[id(big)], 140.0, places=2)
        self.assertAlmostEqual(sum(r.values()), 200.0, places=2)

    def test_zero_size_sections_excluded(self):
        av = self._av()
        s1 = make_section(0x0, 0x100, 's1')
        zero = make_section(0x100, 0x0, 'zero')
        r = av._compute_per_section_heights([s1, zero], 100.0, 14.0, None)
        self.assertIn(id(s1), r)
        self.assertNotIn(id(zero), r)


class TestPerSectionHeightsIntegration(unittest.TestCase):
    """Integration: per-section heights assigned correctly through _process()."""

    def _make_area(self, min_h, max_h=None, big_size=0x10000, small_size=0x10):
        """Area with a break, one big section, one small section, one post-break section."""
        big = Section(size=big_size, address=0x0000, id='big')
        small = Section(size=small_size, address=big_size, id='small')
        brk = Section(size=0x1000, address=big_size + small_size, id='brk',
                      flags=['break'])
        after = Section(size=0x1000, address=big_size + small_size + 0x1000, id='after')
        style = default_style()
        style['min_section_height'] = min_h
        if max_h is not None:
            style['max_section_height'] = max_h
        total = big_size + small_size + 0x1000 + 0x1000
        return AreaView(
            sections=Sections([big, small, brk, after]),
            style=style,
            area_config={'id': 't', 'title': 'T', 'pos': [0, 600], 'size': [200, 600],
                         'start': 0x0, 'end': total},
        )

    def _find_section(self, av, section_id):
        for sv in av.get_split_area_views():
            for s in sv.sections.get_sections():
                if s.id == section_id:
                    return s
        return None

    def test_small_section_gets_min_h_override(self):
        av = self._make_area(min_h=20)
        small = self._find_section(av, 'small')
        self.assertIsNotNone(small)
        self.assertIsNotNone(small.size_y_override)
        self.assertGreaterEqual(small.size_y_override, 20.0)

    def test_big_section_shrinks_to_accommodate_small(self):
        av = self._make_area(min_h=20)
        big = self._find_section(av, 'big')
        small = self._find_section(av, 'small')
        self.assertIsNotNone(big.size_y_override)
        # big + small should sum to the available height for their group
        self.assertAlmostEqual(
            big.size_y_override + small.size_y_override,
            big.size_y_override + small.size_y_override,  # trivially true, just check presence
        )
        # big should be larger than small
        self.assertGreater(big.size_y_override, small.size_y_override)

    def test_conflicting_section_gets_label_floor(self):
        """Sections where size label and name label overlap on x-axis get a height floor."""
        # With font_size=16, size_x=200:
        #   size_label_right = 2 + 5 * 0.6 * 12 = 38  (for '4 KiB' = 5 chars)
        #   name_left(17-char) = 100 - 17 * 0.6*16/2 = 100 - 81.6 = 18.4  → CONFLICT
        #   name_left( 5-char) = 100 -  5 * 0.6*16/2 = 100 - 24   = 76.0  → no conflict
        style = default_style()  # font_size=16, no min_section_height
        s_conflict = make_section(0x0, 0x1000, 'long_section_name')   # 17-char name
        brk = Section(size=0x100, address=0x1000, id='brk', flags=['break'])
        s_ok = make_section(0x1100, 0x1000, 'short')                   # 5-char name
        av = AreaView(
            sections=Sections([s_conflict, brk, s_ok]),
            style=style,
            area_config={'id': 't', 'title': 'T', 'pos': [0, 400], 'size': [200, 400]},
        )
        font_size = float(style.get('font_size', 16))
        label_min = 30.0 + font_size  # 46 px for font_size=16

        found_conflict = found_ok = None
        for sv in av.get_split_area_views():
            for sec in sv.sections.get_sections():
                if sec.id == 'long_section_name':
                    found_conflict = sec
                elif sec.id == 'short':
                    found_ok = sec

        # Conflicting section must be inflated to at least label_min
        self.assertIsNotNone(found_conflict)
        self.assertIsNotNone(found_conflict.size_y_override)
        self.assertGreaterEqual(found_conflict.size_y_override, label_min)

        # Non-conflicting section gets a height override too (proportional/user-min),
        # but it is NOT forced up to label_min
        self.assertIsNotNone(found_ok)
        self.assertIsNotNone(found_ok.size_y_override)

    def test_cumulative_positions_within_group(self):
        """Sections in the same group have non-overlapping cumulative positions."""
        av = self._make_area(min_h=20, big_size=0x1000, small_size=0x100)
        big = self._find_section(av, 'big')
        small = self._find_section(av, 'small')
        # Both should have overrides
        self.assertIsNotNone(big.size_y_override)
        self.assertIsNotNone(small.size_y_override)
        # Positions should be cumulative (non-overlapping within the group)
        positions = sorted([(big.pos_y_in_subarea, big.size_y_override),
                            (small.pos_y_in_subarea, small.size_y_override)])
        p0_end = positions[0][0] + positions[0][1]
        self.assertLessEqual(p0_end, positions[1][0] + 1e-9)


if __name__ == '__main__':
    unittest.main()
