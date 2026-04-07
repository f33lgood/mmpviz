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

    def test_auto_shows_when_large(self):
        s = self._make(size_y=30, style={'hide_name': 'auto'})
        self.assertFalse(s.is_name_hidden())

    def test_auto_hides_when_small(self):
        s = self._make(size_y=10, style={'hide_name': 'auto'})
        self.assertTrue(s.is_name_hidden())

    def test_boundary_exactly_20_hides(self):
        # size_y < 20 hides; exactly 20 does not hide
        s = self._make(size_y=19)
        self.assertTrue(s.is_name_hidden())
        s2 = self._make(size_y=20)
        self.assertFalse(s2.is_name_hidden())

    def test_explicit_true_hides(self):
        s = self._make(size_y=100, style={'hide_address': 'True'})
        self.assertTrue(s.is_address_hidden())

    def test_explicit_false_shows(self):
        s = self._make(size_y=5, style={'hide_size': 'False'})
        self.assertFalse(s.is_size_hidden())

    def test_missing_style_key_defaults_auto(self):
        s = self._make(size_y=30, style={})
        self.assertFalse(s.is_name_hidden())  # 30 >= 20 → shown


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
