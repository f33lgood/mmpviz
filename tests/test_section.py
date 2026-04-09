import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import unittest
from section import Section


class TestSectionFlags(unittest.TestCase):

    def _make(self, flags=None):
        return Section(size=0x1000, address=0x08000000, id='test',
                       _type='section', parent='none', flags=flags)

    def test_default_flags_empty(self):
        s = self._make()
        self.assertFalse(s.is_grow_up())
        self.assertFalse(s.is_grow_down())
        self.assertFalse(s.is_break())
        self.assertFalse(s.is_hidden())

    def test_grows_up(self):
        s = self._make(['grows-up'])
        self.assertTrue(s.is_grow_up())
        self.assertFalse(s.is_grow_down())

    def test_grows_down(self):
        s = self._make(['grows-down'])
        self.assertTrue(s.is_grow_down())
        self.assertFalse(s.is_grow_up())

    def test_break_flag(self):
        s = self._make(['break'])
        self.assertTrue(s.is_break())

    def test_hidden_flag(self):
        s = self._make(['hidden'])
        self.assertTrue(s.is_hidden())

    def test_multiple_flags(self):
        s = self._make(['grows-up', 'break'])
        self.assertTrue(s.is_grow_up())
        self.assertTrue(s.is_break())
        self.assertFalse(s.is_hidden())


class TestSectionVisibility(unittest.TestCase):

    def _make(self, size_y=30, style=None):
        s = Section(size=0x1000, address=0, id='x', _type='section', parent='none')
        s.size_y = size_y
        s.style = style or {}
        return s

    # --- explicit style overrides ---

    def test_explicit_true_hides(self):
        s = self._make(size_y=100, style={'hide_address': 'True'})
        self.assertTrue(s.is_address_hidden())

    def test_explicit_yes_hides(self):
        s = self._make(size_y=100, style={'hide_name': 'yes'})
        self.assertTrue(s.is_name_hidden())

    def test_explicit_false_shows_when_large(self):
        # Large section: geometry is fine, explicit false → shown
        s = self._make(size_y=100, style={'hide_size': 'False'})
        self.assertFalse(s.is_size_hidden())

    def test_explicit_no_shows_when_large(self):
        s = self._make(size_y=100, style={'hide_size': 'no'})
        self.assertFalse(s.is_size_hidden())

    def test_end_address_shown_by_default(self):
        s = self._make(size_y=40)
        self.assertFalse(s.is_end_address_hidden())

    def test_end_address_explicit_hide(self):
        s = self._make(size_y=40, style={'hide_end_address': 'true'})
        self.assertTrue(s.is_end_address_hidden())

    def test_auto_treated_as_shown_for_large_section(self):
        # 'auto' is not a special value; treated as False (shown) when geometry allows
        s = self._make(size_y=100, style={'hide_name': 'auto'})
        self.assertFalse(s.is_name_hidden())

    # --- geometry auto-fix: name ---

    def test_name_auto_hidden_when_overflows(self):
        # size_y < font_size → name would visually overflow
        s = self._make(size_y=10, style={'font_size': 16})
        self.assertTrue(s.is_name_hidden())

    def test_name_shown_when_fits(self):
        s = self._make(size_y=20, style={'font_size': 16})
        self.assertFalse(s.is_name_hidden())

    def test_name_size_y_zero_not_auto_hidden(self):
        # size_y == 0 means geometry not yet computed; should not auto-hide
        s = self._make(size_y=0, style={'font_size': 16})
        self.assertFalse(s.is_name_hidden())

    # --- geometry auto-fix: size label ---

    def test_size_auto_hidden_when_section_too_short(self):
        # size_y < 12 (size label font) → size label cannot fit
        s = self._make(size_y=8, style={'font_size': 16})
        self.assertTrue(s.is_size_hidden())

    def test_size_auto_hidden_when_overlaps_name(self):
        # size_y < font_size + 28 triggers overlap; name is shown (size_y >= font_size)
        # font_size=12 → threshold = 12 + 28 = 40
        s = self._make(size_y=30, style={'font_size': 12})
        self.assertFalse(s.is_name_hidden())   # 30 >= 12, name shown
        self.assertTrue(s.is_size_hidden())    # name_top=9 < 14 → size hidden

    def test_size_shown_when_sufficient_height(self):
        # size_y >= font_size + 28 → no overlap
        # font_size=12 → need size_y >= 40
        s = self._make(size_y=42, style={'font_size': 12})
        self.assertFalse(s.is_name_hidden())
        self.assertFalse(s.is_size_hidden())

    def test_size_not_auto_hidden_if_name_hidden(self):
        # If name is explicitly hidden, size-name overlap check is skipped;
        # size label can show as long as section is tall enough for it.
        s = self._make(size_y=20, style={'hide_name': 'true', 'font_size': 12})
        self.assertTrue(s.is_name_hidden())
        self.assertFalse(s.is_size_hidden())  # no overlap concern; 20 >= 12

    def test_address_not_auto_hidden_by_geometry(self):
        # Address / end-address labels have no geometry auto-fix
        s = self._make(size_y=1, style={})
        self.assertFalse(s.is_address_hidden())
        self.assertFalse(s.is_end_address_hidden())


class TestSectionProperties(unittest.TestCase):

    def test_addr_label_pos_x(self):
        s = Section(size=0, address=0, id='x', _type='section', parent='none')
        s.size_x = 200
        self.assertEqual(s.addr_label_pos_x, 210)  # size_x + label_offset(10)

    def test_name_label_pos_x(self):
        s = Section(size=0, address=0, id='x', _type='section', parent='none')
        s.size_x = 200
        self.assertEqual(s.name_label_pos_x, 100)

    def test_name_label_pos_y(self):
        s = Section(size=0, address=0, id='x', _type='section', parent='none')
        s.pos_y = 100
        s.size_y = 40
        self.assertEqual(s.name_label_pos_y, 120)


if __name__ == '__main__':
    unittest.main()
