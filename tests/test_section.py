import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import unittest
from section import Section


class TestSectionFlags(unittest.TestCase):

    def _make(self, flags=None):
        return Section(size=0x1000, address=0x08000000, id='test', flags=flags)

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


class TestSectionProperties(unittest.TestCase):

    def test_addr_label_pos_x(self):
        s = Section(size=0, address=0, id='x')
        s.size_x = 200
        self.assertEqual(s.addr_label_pos_x, 210)  # size_x + label_offset(10)

    def test_name_label_pos_x(self):
        s = Section(size=0, address=0, id='x')
        s.size_x = 200
        self.assertEqual(s.name_label_pos_x, 100)

    def test_name_label_pos_y(self):
        s = Section(size=0, address=0, id='x')
        s.pos_y = 100
        s.size_y = 40
        self.assertEqual(s.name_label_pos_y, 120)


if __name__ == '__main__':
    unittest.main()
