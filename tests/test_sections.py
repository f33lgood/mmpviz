import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import unittest
from section import Section
from sections import Sections


def make_section(address, size, id='s', flags=None):
    return Section(size=size, address=address, id=id,
                   _type='section', parent='none', flags=flags)


class TestSectionsFilters(unittest.TestCase):

    def setUp(self):
        self.s1 = make_section(0x1000, 0x100, 's1')
        self.s2 = make_section(0x2000, 0x200, 's2')
        self.s3 = make_section(0x3000, 0x50,  's3')
        self.sections = Sections([self.s1, self.s2, self.s3])

    def test_filter_size_min(self):
        result = self.sections.filter_size_min(0x100)
        ids = [s.id for s in result.get_sections()]
        self.assertIn('s2', ids)
        self.assertNotIn('s1', ids)
        self.assertNotIn('s3', ids)

    def test_filter_size_max(self):
        result = self.sections.filter_size_max(0x100)
        ids = [s.id for s in result.get_sections()]
        self.assertIn('s3', ids)
        self.assertNotIn('s1', ids)
        self.assertNotIn('s2', ids)

    def test_filter_address_min(self):
        result = self.sections.filter_address_min(0x2000)
        ids = [s.id for s in result.get_sections()]
        self.assertIn('s2', ids)
        self.assertIn('s3', ids)
        self.assertNotIn('s1', ids)

    def test_filter_address_max(self):
        # filter_address_max keeps sections where (address + size) <= max
        result = self.sections.filter_address_max(0x1100)
        ids = [s.id for s in result.get_sections()]
        self.assertIn('s1', ids)  # 0x1000 + 0x100 = 0x1100 ≤ 0x1100
        self.assertNotIn('s2', ids)

    def test_filter_none_returns_all(self):
        self.assertEqual(len(self.sections.filter_size_min(None).get_sections()), 3)
        self.assertEqual(len(self.sections.filter_size_max(None).get_sections()), 3)

    def test_has_address_true(self):
        self.assertTrue(self.sections.has_address(0x1050))

    def test_has_address_false(self):
        self.assertFalse(self.sections.has_address(0x5000))

    def test_highest_memory(self):
        # s3: 0x3000 + 0x50 = 0x3050
        self.assertEqual(self.sections.highest_memory, 0x3050)

    def test_lowest_memory(self):
        self.assertEqual(self.sections.lowest_memory, 0x1000)


class TestSplitAroundBreaks(unittest.TestCase):

    def test_no_breaks_returns_one_group(self):
        s1 = make_section(0x1000, 0x100, 's1')
        s2 = make_section(0x1100, 0x100, 's2')
        secs = Sections([s1, s2])
        groups = secs.split_sections_around_breaks()
        self.assertEqual(len(groups), 1)

    def test_one_break_splits_into_three(self):
        s1 = make_section(0x1000, 0x100, 's1')
        brk = make_section(0x1100, 0x100, 'brk', flags=['break'])
        s2 = make_section(0x1200, 0x100, 's2')
        secs = Sections([s1, brk, s2])
        groups = secs.split_sections_around_breaks()
        # [before-break, break, after-break]
        self.assertEqual(len(groups), 3)
        self.assertTrue(groups[1].is_break_section_group())

    def test_break_at_start(self):
        brk = make_section(0x1000, 0x100, 'brk', flags=['break'])
        s1 = make_section(0x1100, 0x100, 's1')
        secs = Sections([brk, s1])
        groups = secs.split_sections_around_breaks()
        # [break, after-break]  (no before-break group because empty)
        self.assertGreaterEqual(len(groups), 1)
        self.assertTrue(any(g.is_break_section_group() for g in groups))


if __name__ == '__main__':
    unittest.main()
