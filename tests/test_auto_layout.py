import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import unittest
from mmpviz import _auto_layout
from auto_layout import build_link_graph_from_links, assign_columns


class TestAutoLayout(unittest.TestCase):

    def test_no_areas_returns_empty(self):
        self.assertEqual(_auto_layout([]), [])

    def test_single_area_gets_pos_and_size(self):
        result = _auto_layout([{'id': 'a'}])
        self.assertEqual(len(result), 1)
        pos = result[0]['pos']
        size = result[0]['size']
        # x = PADDING = 50, y = TITLE_SPACE = 60
        self.assertAlmostEqual(pos[0], 50.0, places=1)
        self.assertAlmostEqual(pos[1], 60.0, places=1)
        # width = MAX_COL_WIDTH = 230
        self.assertAlmostEqual(size[0], 230.0, places=1)
        # height >= 200 (minimum floor)
        self.assertGreaterEqual(size[1], 200.0)

    def test_two_areas_no_columns_stacked_vertically(self):
        configs = [{'id': 'a'}, {'id': 'b'}]
        result = _auto_layout(configs)
        # Both in same single column, x = PADDING
        self.assertAlmostEqual(result[0]['pos'][0], 50.0, places=1)
        self.assertAlmostEqual(result[1]['pos'][0], 50.0, places=1)
        # Second area is below first
        self.assertGreater(result[1]['pos'][1], result[0]['pos'][1])

    def test_two_columns_side_by_side(self):
        columns = {'a': 0, 'b': 1}
        configs = [{'id': 'a'}, {'id': 'b'}]
        result = _auto_layout(configs, columns=columns)
        # Column 0 starts at x=PADDING=50
        # Column 1 starts at x=PADDING + MAX_COL_WIDTH + INTER_COL_GAP = 50+230+120=400
        self.assertAlmostEqual(result[0]['pos'][0], 50.0, places=1)
        self.assertAlmostEqual(result[1]['pos'][0], 400.0, places=1)

    def test_original_config_not_mutated(self):
        orig = [{'id': 'a'}, {'id': 'b'}]
        _auto_layout(orig)
        self.assertNotIn('pos', orig[0])
        self.assertNotIn('size', orig[0])

    def test_area_heights_used(self):
        configs = [{'id': 'a'}]
        result = _auto_layout(configs, area_heights={'a': 350.0})
        self.assertAlmostEqual(result[0]['size'][1], 350.0, places=1)

    def test_height_floor_applied(self):
        configs = [{'id': 'a'}]
        result = _auto_layout(configs, area_heights={'a': 50.0})
        # Floor is 100.0
        self.assertGreaterEqual(result[0]['size'][1], 100.0)

    def test_column_width_is_230(self):
        """Column width is always MAX_COL_WIDTH regardless of number of areas."""
        configs = [{'id': str(i)} for i in range(5)]
        cols = {str(i): 0 for i in range(5)}
        result = _auto_layout(configs, columns=cols)
        for r in result:
            self.assertAlmostEqual(r['size'][0], 230.0, places=1)


class TestAssignColumns(unittest.TestCase):

    def test_single_node_is_column_zero(self):
        g = {'a': []}
        c = assign_columns(g, ['a'])
        self.assertEqual(c['a'], 0)

    def test_root_and_leaf(self):
        g = {'a': ['b'], 'b': []}
        c = assign_columns(g, ['a', 'b'])
        self.assertEqual(c['a'], 0)
        self.assertEqual(c['b'], 1)

    def test_linear_chain(self):
        g = {'a': ['b'], 'b': ['c'], 'c': []}
        c = assign_columns(g, ['a', 'b', 'c'])
        self.assertEqual(c['a'], 0)
        self.assertEqual(c['b'], 1)
        self.assertEqual(c['c'], 2)

    def test_diamond_uses_max_depth(self):
        # a→b, a→c, b→d, c→d
        g = {'a': ['b', 'c'], 'b': ['d'], 'c': ['d'], 'd': []}
        c = assign_columns(g, ['a', 'b', 'c', 'd'])
        self.assertEqual(c['a'], 0)
        self.assertEqual(c['b'], 1)
        self.assertEqual(c['c'], 1)
        self.assertEqual(c['d'], 2)

    def test_stm32f103_like_columns(self):
        # overview → m3-periph, apb, flash, sysmem
        g = {
            'overview':  ['m3-periph', 'apb', 'flash', 'sysmem'],
            'm3-periph': [],
            'apb':       [],
            'flash':     [],
            'sysmem':    [],
        }
        ids = list(g.keys())
        c = assign_columns(g, ids)
        self.assertEqual(c['overview'], 0)
        for detail in ('m3-periph', 'apb', 'flash', 'sysmem'):
            self.assertEqual(c[detail], 1)

    def test_disconnected_nodes_get_column_zero(self):
        g = {'a': [], 'b': [], 'c': []}
        c = assign_columns(g, ['a', 'b', 'c'])
        for aid in ('a', 'b', 'c'):
            self.assertEqual(c[aid], 0)

    def test_multiple_roots(self):
        # Two separate chains: a→c, b→d
        g = {'a': ['c'], 'b': ['d'], 'c': [], 'd': []}
        c = assign_columns(g, ['a', 'b', 'c', 'd'])
        self.assertEqual(c['a'], 0)
        self.assertEqual(c['b'], 0)
        self.assertEqual(c['c'], 1)
        self.assertEqual(c['d'], 1)

    def test_deeper_chain_with_shortcut(self):
        # a→b→c, a→c  — c should be at column 2, not 1
        g = {'a': ['b', 'c'], 'b': ['c'], 'c': []}
        c = assign_columns(g, ['a', 'b', 'c'])
        self.assertEqual(c['a'], 0)
        self.assertEqual(c['b'], 1)
        self.assertEqual(c['c'], 2)


class TestBuildLinkGraphChipExamples(unittest.TestCase):
    """End-to-end: build_link_graph against actual chip examples."""

    REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    def _load_chip(self, chip_name):
        """Load area configs and diagram from a chip example."""
        from loader import load
        chip_dir = os.path.join(self.REPO, 'examples', 'chips', chip_name)
        diagram_path = os.path.join(chip_dir, 'diagram.json')
        if not os.path.isfile(diagram_path):
            return None, None
        diagram = load(diagram_path)
        area_configs = diagram.get('views', []) or []
        return area_configs, diagram

    def test_stm32f103_overview_is_root(self):
        from links import Links
        area_configs, diagram = self._load_chip('stm32f103')
        if area_configs is None:
            self.skipTest('stm32f103 example not found')
        view_ids = [c['id'] for c in area_configs]
        links = Links(links_config=diagram.get('links', []))
        g = build_link_graph_from_links(links.entries, view_ids)
        cols = assign_columns(g, view_ids)
        self.assertEqual(cols.get('overview-view'), 0)
        for detail in ('m3-periph-view', 'flash-zoom-view', 'sysmem-zoom-view', 'apb-view'):
            self.assertGreaterEqual(cols.get(detail, 0), 1,
                                    f"{detail} should be in column >= 1")

    def test_stm32f103_overview_has_outgoing_edges(self):
        from links import Links
        area_configs, diagram = self._load_chip('stm32f103')
        if area_configs is None:
            self.skipTest('stm32f103 example not found')
        view_ids = [c['id'] for c in area_configs]
        links = Links(links_config=diagram.get('links', []))
        g = build_link_graph_from_links(links.entries, view_ids)
        self.assertGreater(len(g.get('overview-view', [])), 0)

    def test_all_chips_produce_valid_graphs(self):
        """For each chip, the graph must contain all area ids exactly once."""
        from links import Links
        chips_dir = os.path.join(self.REPO, 'examples', 'chips')
        for chip_name in os.listdir(chips_dir):
            chip_path = os.path.join(chips_dir, chip_name)
            if not os.path.isdir(chip_path):
                continue
            area_configs, diagram = self._load_chip(chip_name)
            if not area_configs:
                continue
            view_ids = [c['id'] for c in area_configs if 'id' in c]
            links = Links(links_config=diagram.get('links', []))
            g = build_link_graph_from_links(links.entries, view_ids)
            for vid in view_ids:
                self.assertIn(vid, g, f"[{chip_name}] {vid!r} missing from graph")
            for src, targets in g.items():
                self.assertNotIn(src, targets, f"[{chip_name}] self-loop on {src!r}")


if __name__ == '__main__':
    unittest.main()
