import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import unittest
from mmpviz import _auto_layout
from auto_layout import build_link_graph, assign_columns
from section import Section


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


def _sec(address, size, sid='s'):
    return Section(size=size, address=address, id=sid)


class TestBuildLinkGraph(unittest.TestCase):

    def test_empty_areas_returns_empty_graph(self):
        g = build_link_graph([], [])
        self.assertEqual(g, {})

    def test_no_sections_no_edges(self):
        areas = [
            {'id': 'a', 'range': ['0x0', '0x1000']},
            {'id': 'b', 'range': ['0x0', '0x800']},
        ]
        g = build_link_graph(areas, [])
        self.assertEqual(g['a'], [])
        self.assertEqual(g['b'], [])

    def test_section_in_a_contains_b_adds_edge(self):
        # Section L covers 0x0–0x1000, area B's range is 0x0–0x1000 (same)
        areas = [
            {'id': 'a', 'range': ['0x0', '0x2000']},
            {'id': 'b', 'range': ['0x0', '0x1000']},
        ]
        secs = [_sec(0x0, 0x1000)]
        g = build_link_graph(areas, secs)
        self.assertIn('b', g['a'])
        self.assertEqual(g['b'], [])

    def test_no_self_loop(self):
        areas = [{'id': 'a', 'range': ['0x0', '0x1000']}]
        secs = [_sec(0x0, 0x1000)]
        g = build_link_graph(areas, secs)
        self.assertNotIn('a', g['a'])

    def test_section_too_small_for_area_b_no_edge(self):
        # Section L covers 0x100–0x200, area B's range 0x0–0x1000 is NOT ⊆ L
        areas = [
            {'id': 'a', 'range': ['0x0', '0x2000']},
            {'id': 'b', 'range': ['0x0', '0x1000']},
        ]
        secs = [_sec(0x100, 0x100)]
        g = build_link_graph(areas, secs)
        self.assertEqual(g['a'], [])

    def test_area_without_range_derives_from_global_sections(self):
        # A rangeless view acts as an overview spanning all sections.
        # Edge a→b should be created because a's derived range covers the
        # section, which in turn contains b's explicit range.
        areas = [
            {'id': 'a'},   # no range — derives [0x0, 0x2000) from sections
            {'id': 'b', 'range': ['0x0', '0x1000']},
        ]
        secs = [_sec(0x0, 0x2000)]
        g = build_link_graph(areas, secs)
        self.assertIn('b', g.get('a', []))

    def test_no_duplicate_edges(self):
        # Two sections both containing area B → still only one edge A→B
        areas = [
            {'id': 'a', 'range': ['0x0', '0x4000']},
            {'id': 'b', 'range': ['0x0', '0x1000']},
        ]
        secs = [_sec(0x0, 0x2000), _sec(0x0, 0x3000)]
        g = build_link_graph(areas, secs)
        self.assertEqual(g['a'].count('b'), 1)

    def test_stm32f103_like_graph(self):
        # Simplified stm32f103: overview contains all; detail areas zoom in
        areas = [
            {'id': 'overview',  'range': ['0x00000000', '0x100000000']},
            {'id': 'm3-periph', 'range': ['0xE0000000', '0xE1000000']},
            {'id': 'apb',       'range': ['0x40000000', '0x60000000']},
            {'id': 'flash',     'range': ['0x08000000', '0x08020000']},
        ]
        secs = [
            _sec(0xE0000000, 0x01000000, 'M3'),          # M3 → m3-periph
            _sec(0x40000000, 0x20000000, 'Peripherals'),  # Peripherals → apb
            _sec(0x08000000, 0x00020000, 'Flash'),        # Flash → flash
        ]
        g = build_link_graph(areas, secs)
        self.assertIn('m3-periph', g['overview'])
        self.assertIn('apb',       g['overview'])
        self.assertIn('flash',     g['overview'])
        # Detail areas have no outgoing edges (no section contains another area)
        self.assertEqual(g['m3-periph'], [])
        self.assertEqual(g['apb'],       [])
        self.assertEqual(g['flash'],     [])

    def test_all_area_ids_present_in_result(self):
        areas = [
            {'id': 'x', 'range': ['0x0', '0x1000']},
            {'id': 'y', 'range': ['0x2000', '0x3000']},
        ]
        g = build_link_graph(areas, [])
        self.assertIn('x', g)
        self.assertIn('y', g)


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
        """Load raw sections and area configs from a chip example."""
        # Import here to avoid circular import issues at module level
        from loader import load
        chip_dir = os.path.join(self.REPO, 'examples', 'chips', chip_name)
        diagram_path = os.path.join(chip_dir, 'diagram.json')
        if not os.path.isfile(diagram_path):
            return None, None
        raw_sections, diagram = load(diagram_path)
        area_configs = diagram.get('views', []) or []
        return raw_sections, area_configs

    def test_stm32f103_overview_is_root(self):
        raw_sections, area_configs = self._load_chip('stm32f103')
        if area_configs is None:
            self.skipTest('stm32f103 example not found')
        g = build_link_graph(area_configs, raw_sections)
        cols = assign_columns(g, [c['id'] for c in area_configs])
        # overview-view has no incoming edges → column 0
        self.assertEqual(cols.get('overview-view'), 0)
        # detail areas are in column 1 (or deeper)
        for detail in ('m3-periph-view', 'flash-zoom-view', 'sysmem-zoom-view', 'apb-view'):
            self.assertGreaterEqual(cols.get(detail, 0), 1,
                                    f"{detail} should be in column >= 1")

    def test_stm32f103_overview_has_outgoing_edges(self):
        raw_sections, area_configs = self._load_chip('stm32f103')
        if area_configs is None:
            self.skipTest('stm32f103 example not found')
        g = build_link_graph(area_configs, raw_sections)
        self.assertGreater(len(g.get('overview-view', [])), 0)

    def test_all_chips_produce_valid_graphs(self):
        """For each chip, the graph must contain all area ids exactly once."""
        chips_dir = os.path.join(self.REPO, 'examples', 'chips')
        for chip_name in os.listdir(chips_dir):
            chip_path = os.path.join(chips_dir, chip_name)
            if not os.path.isdir(chip_path):
                continue
            raw_sections, area_configs = self._load_chip(chip_name)
            if not area_configs:
                continue
            view_ids = [c['id'] for c in area_configs if 'id' in c]
            g = build_link_graph(area_configs, raw_sections)
            # Every view id should be a key in the graph
            for vid in view_ids:
                self.assertIn(vid, g, f"[{chip_name}] {vid!r} missing from graph")
            # No self-loops
            for src, targets in g.items():
                self.assertNotIn(src, targets, f"[{chip_name}] self-loop on {src!r}")


if __name__ == '__main__':
    unittest.main()
