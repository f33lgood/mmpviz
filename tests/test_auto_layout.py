import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import unittest
from mmpviz import _auto_layout


class TestAutoLayout(unittest.TestCase):

    def test_no_areas_returns_empty(self):
        self.assertEqual(_auto_layout([], (500, 900)), [])

    def test_single_area_no_pos_no_size(self):
        result = _auto_layout([{'id': 'a'}], (500, 900))
        self.assertEqual(len(result), 1)
        pos = result[0]['pos']
        size = result[0]['size']
        # x = PADDING = 50, y = TITLE_SPACE = 60
        self.assertAlmostEqual(pos[0], 50.0, places=1)
        self.assertEqual(pos[1], 60)
        # auto_width = (500 - 50*(1+1)) / 1 = 400
        self.assertAlmostEqual(size[0], 400.0, places=1)
        # auto_height = 900 - 60 - 30 = 810
        self.assertAlmostEqual(size[1], 810.0, places=1)

    def test_two_areas_even_distribution(self):
        configs = [{'id': 'a'}, {'id': 'b'}]
        result = _auto_layout(configs, (500, 900))
        # auto_width = (500 - 50*3) / 2 = 175
        self.assertAlmostEqual(result[0]['pos'][0], 50.0, places=1)
        self.assertAlmostEqual(result[1]['pos'][0], 50.0 + 175.0 + 50.0, places=1)
        self.assertAlmostEqual(result[0]['size'][0], 175.0, places=1)
        self.assertAlmostEqual(result[1]['size'][0], 175.0, places=1)
        # Both areas share the same auto height
        self.assertEqual(result[0]['size'][1], result[1]['size'][1])

    def test_three_areas_x_positions(self):
        configs = [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}]
        # canvas 650×700
        # auto_width = (650 - 50*4) / 3 = 450/3 = 150
        result = _auto_layout(configs, (650, 700))
        xs = [r['pos'][0] for r in result]
        self.assertAlmostEqual(xs[0], 50.0, places=1)
        self.assertAlmostEqual(xs[1], 250.0, places=1)   # 50 + 150 + 50
        self.assertAlmostEqual(xs[2], 450.0, places=1)   # 250 + 150 + 50

    def test_explicit_pos_preserved(self):
        configs = [{'id': 'a', 'pos': [10, 20]}, {'id': 'b'}]
        result = _auto_layout(configs, (500, 900))
        # First area keeps its explicit pos
        self.assertEqual(result[0]['pos'], [10, 20])
        # Second area still gets auto pos
        self.assertIsNotNone(result[1].get('pos'))

    def test_explicit_size_preserved(self):
        configs = [{'id': 'a', 'size': [100, 400]}]
        result = _auto_layout(configs, (500, 900))
        self.assertEqual(result[0]['size'], [100, 400])

    def test_partial_explicit_pos_and_size(self):
        """An area with only 'pos' still gets auto 'size' and vice versa."""
        cfg_pos_only = [{'id': 'a', 'pos': [5, 5]}]
        r = _auto_layout(cfg_pos_only, (500, 900))
        self.assertEqual(r[0]['pos'], [5, 5])     # explicit kept
        self.assertIn('size', r[0])               # auto size added

        cfg_size_only = [{'id': 'b', 'size': [80, 300]}]
        r2 = _auto_layout(cfg_size_only, (500, 900))
        self.assertEqual(r2[0]['size'], [80, 300])  # explicit kept
        self.assertIn('pos', r2[0])                 # auto pos added

    def test_original_config_not_mutated(self):
        orig = [{'id': 'a'}, {'id': 'b'}]
        _auto_layout(orig, (500, 900))
        # originals should be untouched
        self.assertNotIn('pos', orig[0])
        self.assertNotIn('size', orig[0])

    def test_minimum_width_floor(self):
        """With many areas on a narrow canvas the width floor (50px) kicks in."""
        configs = [{'id': str(i)} for i in range(20)]
        result = _auto_layout(configs, (200, 700))
        for r in result:
            self.assertGreaterEqual(r['size'][0], 50.0)


if __name__ == '__main__':
    unittest.main()
