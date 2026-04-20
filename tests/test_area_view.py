import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import unittest
from section import Section
from sections import Sections
from area_view import AreaView, section_label_min_h
from mmpviz import _estimate_area_height
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


class TestAreaViewDegenerateInputs(unittest.TestCase):
    """Zero-range / zero-height views must fail loudly, not divide by zero."""

    def _construct(self, area_config):
        s = make_section(0x0, 0x1000)
        return AreaView(
            sections=Sections([s]),
            style=default_style(),
            area_config=area_config,
            is_subarea=True,
        )

    def test_zero_size_y_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self._construct({'id': 'v', 'pos': [0, 0], 'size': [200, 0],
                             'start': 0x0, 'end': 0x1000})
        self.assertIn('size_y', str(ctx.exception))

    def test_negative_size_y_raises(self):
        with self.assertRaises(ValueError):
            self._construct({'id': 'v', 'pos': [0, 0], 'size': [200, -10],
                             'start': 0x0, 'end': 0x1000})

    def test_equal_start_end_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self._construct({'id': 'v', 'pos': [0, 0], 'size': [200, 500],
                             'start': 0x1000, 'end': 0x1000})
        self.assertIn('end_address', str(ctx.exception))

    def test_end_less_than_start_raises(self):
        with self.assertRaises(ValueError):
            self._construct({'id': 'v', 'pos': [0, 0], 'size': [200, 500],
                             'start': 0x2000, 'end': 0x1000})


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

    def test_break_section_stacked_in_single_area(self):
        # Breaks no longer split the view into subareas; everything stays in one
        # AreaView and every section gets size_y_override set by _process().
        s1 = make_section(0x0, 0x400, 's1')
        brk = make_section(0x400, 0x200, 'brk', flags=['break'])
        s2 = make_section(0x600, 0x400, 's2')
        av = AreaView(
            sections=Sections([s1, brk, s2]),
            style=default_style(),
            area_config={'id': 'av', 'title': 'Test', 'pos': [0, 500], 'size': [200, 500]},
        )
        views = av.get_split_area_views()
        self.assertEqual(len(views), 1)
        self.assertIs(views[0], av)
        # Break section gets break_height; non-breaks get their floor height.
        for s in av.sections.get_sections():
            if s.size > 0:
                self.assertIsNotNone(s.size_y_override)
                self.assertGreater(s.size_y_override, 0)
        # Break section gets exactly break_height from style.
        self.assertAlmostEqual(brk.size_y_override, 20.0)

    def test_sections_stacked_contiguously(self):
        # Sections must be stacked without gaps.
        s1 = make_section(0x0, 0x500, 's1')
        s2 = make_section(0x500, 0x500, 's2')
        av = AreaView(
            sections=Sections([s1, s2]),
            style=default_style(),
            area_config={'id': 'av', 'title': 'Test', 'pos': [0, 500], 'size': [200, 500]},
        )
        secs = [s for s in av.sections.get_sections() if s.size > 0]
        # Sort by pos_y_in_subarea
        secs.sort(key=lambda s: s.pos_y_in_subarea)
        for i in range(len(secs) - 1):
            end_of_this = secs[i].pos_y_in_subarea + secs[i].size_y_override
            self.assertAlmostEqual(end_of_this, secs[i + 1].pos_y_in_subarea, places=6)

    def test_view_height_equals_stack_height(self):
        # View size_y must equal the sum of section heights exactly.
        s1 = make_section(0x0, 0x500, 's1')
        s2 = make_section(0x500, 0x500, 's2')
        av = AreaView(
            sections=Sections([s1, s2]),
            style=default_style(),
            area_config={'id': 'av', 'title': 'Test', 'pos': [0, 500], 'size': [200, 500]},
        )
        total_sections = sum(s.size_y_override for s in av.sections.get_sections()
                             if s.size > 0)
        self.assertAlmostEqual(av.size_y, total_sections, places=6)


class TestAreaViewStyleOverride(unittest.TestCase):

    def test_section_flag_applied_before_area_view_created(self):
        # Flags are applied during resolve_view_sections(), before AreaView is created.
        # AreaView receives sections with flags already set.
        s = make_section(0x0, 0x400, 's1', flags=['break'])
        av = AreaView(
            sections=Sections([s]),
            style=default_style(),
            area_config={'id': 'av', 'title': 'T', 'pos': [0, 500], 'size': [200, 500]},
        )
        # s1 already has the 'break' flag from pre-resolution
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


class TestFloorStackLayout(unittest.TestCase):
    """Verify floor-stack layout: each section gets its effective floor height."""

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

    def test_all_sections_get_at_least_min_h(self):
        av = self._make_area(min_h=20)
        for sv in av.get_split_area_views():
            for s in sv.sections.get_sections():
                if not s.is_break() and s.size > 0:
                    self.assertIsNotNone(s.size_y_override)
                    self.assertGreaterEqual(s.size_y_override, 20.0)

    def test_small_section_gets_min_h_floor(self):
        av = self._make_area(min_h=20)
        small = self._find_section(av, 'small')
        self.assertIsNotNone(small)
        self.assertIsNotNone(small.size_y_override)
        self.assertGreaterEqual(small.size_y_override, 20.0)

    def test_big_section_gets_min_h_floor(self):
        # In the floor-stack model, byte size no longer determines height;
        # every section gets its floor.  big and small have the same short name
        # and no label conflict, so both get exactly min_h.
        av = self._make_area(min_h=20)
        big = self._find_section(av, 'big')
        small = self._find_section(av, 'small')
        self.assertIsNotNone(big.size_y_override)
        self.assertIsNotNone(small.size_y_override)
        self.assertGreaterEqual(big.size_y_override, 20.0)
        self.assertGreaterEqual(small.size_y_override, 20.0)

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

        # Non-conflicting section gets a height override, but NOT forced to label_min
        self.assertIsNotNone(found_ok)
        self.assertIsNotNone(found_ok.size_y_override)

    def test_no_breaks_label_floor_applied(self):
        """No-break path applies the label-conflict floor like the breaks path.

        With font_size=16 and size_x=200, a 17-char section name causes a label
        conflict (size_label_right > name_label_left), so the height floor must be
        at least 30 + 16 = 46 px even when there are no break sections.
        """
        style = default_style()  # font_size=16, no min_section_height
        # Two sections, no breaks — exercises the no-breaks code path.
        s_conflict = make_section(0x0, 0x1000, 'long_section_name_x')  # 20-char → conflict
        s_other = make_section(0x1000, 0x8000, 'short')
        av = AreaView(
            sections=Sections([s_conflict, s_other]),
            style=style,
            area_config={'id': 't', 'title': 'T', 'pos': [0, 0], 'size': [200, 400]},
        )
        font_size = float(style.get('font_size', 16))
        label_min = 30.0 + font_size  # 46 px

        found = None
        for sv in av.get_split_area_views():
            for sec in sv.sections.get_sections():
                if sec.id == 'long_section_name_x':
                    found = sec
        self.assertIsNotNone(found)
        self.assertIsNotNone(found.size_y_override)
        self.assertGreaterEqual(found.size_y_override, label_min)

    def test_cumulative_positions_non_overlapping(self):
        """Sections have non-overlapping cumulative positions."""
        av = self._make_area(min_h=20, big_size=0x1000, small_size=0x100)
        all_secs = [s for s in av.sections.get_sections() if s.size > 0]
        self.assertTrue(all(s.size_y_override is not None for s in all_secs))
        secs_sorted = sorted(all_secs, key=lambda s: s.pos_y_in_subarea)
        for i in range(len(secs_sorted) - 1):
            end = secs_sorted[i].pos_y_in_subarea + secs_sorted[i].size_y_override
            self.assertLessEqual(end, secs_sorted[i + 1].pos_y_in_subarea + 1e-9)


class TestEstimateAreaHeight(unittest.TestCase):
    """_estimate_area_height() uses the same effective floor as AreaView._process()."""

    def _style(self, min_h=0, font_size=12, break_h=20):
        return {'min_section_height': min_h, 'font_size': font_size, 'break_height': break_h}

    def test_single_section_no_conflict(self):
        # Short name, wide view — no label conflict, floor = global_min.
        s = make_section(0x0, 0x1000, 'ROM')
        style = self._style(min_h=20)
        h = _estimate_area_height([s], style, size_x=230.0)
        # floor = 20, no padding → total = 20
        self.assertAlmostEqual(h, 20.0, places=6)

    def test_long_name_triggers_label_floor(self):
        # With font_size=12, size_x=100:
        #   name_left(18 chars) = 50 - 18*0.6*12/2 = 50 - 64.8 = negative → CONFLICT
        #   label_floor = 30 + 12 = 42
        # Use 6 sections so total floors push above the 200px minimum:
        #   wide: 6 * 20 + 20 = 140 < 200 → 200  (no label conflict)
        #   narrow: 6 * 42 + 20 = 272 > 200      (label conflict adds floor)
        s_name = 'VERY_LONG_NAME_XX'  # 18 chars
        sections = [make_section(i * 0x1000, 0x1000, s_name) for i in range(6)]
        style = self._style(min_h=20, font_size=12)
        h_wide = _estimate_area_height(sections, style, size_x=230.0)
        h_narrow = _estimate_area_height(sections, style, size_x=100.0)
        # Narrow view has label conflict → each section gets floor 42 > 20 → taller estimate
        self.assertGreater(h_narrow, h_wide)

    def test_label_floor_matches_layout_floor(self):
        # Verify estimate uses the SAME formula as AreaView._process().
        s = make_section(0x0, 0x1000, 'VERY_LONG_SECTION_NAME')  # 22 chars
        font_size = 12.0
        size_x = 100.0
        style = self._style(min_h=20, font_size=font_size)
        expected_floor = max(20.0, section_label_min_h(s, font_size, size_x))
        h = _estimate_area_height([s], style, size_x=size_x)
        # estimate = expected_floor + pad(20) ≥ 200
        self.assertGreaterEqual(h, expected_floor)

    def test_break_sections_contribute_break_height(self):
        sections = [make_section(i * 0x1000, 0x1000, f's{i}') for i in range(8)]
        brk = Section(size=0x100, address=0x8000, id='brk', flags=['break'])
        style = self._style(min_h=30, break_h=40)
        h_with_break = _estimate_area_height(sections + [brk], style, size_x=230.0)
        h_without = _estimate_area_height(sections, style, size_x=230.0)
        # With break: 8*30 + 40 = 280; without: 8*30 = 240
        self.assertAlmostEqual(h_with_break, 280.0, places=6)
        self.assertAlmostEqual(h_without, 240.0, places=6)
        self.assertGreater(h_with_break, h_without)

    def test_multiple_sections_sum_floors(self):
        sections = [make_section(i * 0x1000, 0x1000, f's{i}') for i in range(5)]
        style = self._style(min_h=30)
        h = _estimate_area_height(sections, style, size_x=230.0)
        # 5 sections × 30px = 150
        self.assertAlmostEqual(h, 150.0, places=6)
        # With 10 sections × 30px = 300
        sections10 = [make_section(i * 0x1000, 0x1000, f's{i}') for i in range(10)]
        h10 = _estimate_area_height(sections10, style, size_x=230.0)
        self.assertAlmostEqual(h10, 300.0, places=6)

    def test_estimate_matches_process_result(self):
        # The estimate must equal the view's final size_y after _process().
        # 4 sections × 25px = 100px exactly.
        sections = [make_section(i * 0x1000, 0x1000, f's{i}') for i in range(4)]
        style = dict(default_style())
        style['min_section_height'] = 25
        size_x = 230.0
        estimated = _estimate_area_height(sections, style, size_x=size_x)
        self.assertAlmostEqual(estimated, 100.0, places=6)
        total_addr = 4 * 0x1000
        av = AreaView(
            sections=Sections(sections),
            style=style,
            area_config={'id': 'v', 'title': 'V', 'pos': [0, estimated],
                         'size': [size_x, estimated], 'start': 0x0, 'end': total_addr},
        )
        self.assertAlmostEqual(av.size_y, estimated, places=6)


class TestFloorSectionMinHeight(unittest.TestCase):
    """Sections always receive at least their floor regardless of byte size."""

    def test_tiny_section_gets_min_h(self):
        # Very large address range, tiny section — in the floor model it still gets min_h.
        tiny = make_section(0x0, 0x1, 'tiny')
        style = {'min_section_height': 20, 'font_size': 12, 'break_height': 20,
                 'background': 'white', 'fill': 'grey', 'stroke': 'black',
                 'stroke_width': 1, 'font_family': 'Helvetica', 'text_fill': 'black'}
        av = AreaView(
            sections=Sections([tiny]),
            style=style,
            area_config={'id': 'v', 'title': 'V', 'pos': [0, 200], 'size': [230, 200],
                         'start': 0x0, 'end': 0x10000},
        )
        found = None
        for sv in av.get_split_area_views():
            for sec in sv.sections.get_sections():
                if sec.id == 'tiny':
                    found = sec
        self.assertIsNotNone(found)
        self.assertIsNotNone(found.size_y_override)
        self.assertGreaterEqual(found.size_y_override, 20.0)

    def test_sections_with_break_all_get_min_h(self):
        # Mix of sections and a break; all non-break sections must reach min_h.
        sections = [make_section(i * 0x10, 0x10, f's{i}') for i in range(10)]
        brk = Section(size=0x10000, address=0xa0, id='brk', flags=['break'])
        style = {'min_section_height': 20, 'font_size': 12, 'break_height': 10,
                 'background': 'white', 'fill': 'grey', 'stroke': 'black',
                 'stroke_width': 1, 'font_family': 'Helvetica', 'text_fill': 'black'}
        av = AreaView(
            sections=Sections(sections + [brk]),
            style=style,
            area_config={'id': 'v', 'title': 'V', 'pos': [0, 400], 'size': [230, 400]},
        )
        for sv in av.get_split_area_views():
            for sec in sv.sections.get_sections():
                if not sec.is_break() and sec.size > 0:
                    self.assertIsNotNone(sec.size_y_override,
                        msg=f'section {sec.id} missing size_y_override')
                    self.assertGreaterEqual(sec.size_y_override, 20.0,
                        msg=f'section {sec.id} override {sec.size_y_override:.1f} < 20px')


class TestGrowArrowNeighborFloor(unittest.TestCase):
    """Grows-up/down arrows automatically raise the adjacent neighbor's floor."""

    def _arrow_floor(self, font_size=16.0, growth_arrow_size=1.0):
        return 2.0 * 20.0 * growth_arrow_size + font_size

    def _make_av(self, sections, growth_arrow_size=1.0, style=None):
        if style is None:
            style = default_style()
        return AreaView(
            sections=Sections(sections),
            style=style,
            area_config={'id': 'v', 'title': 'V', 'pos': [0, 200], 'size': [230, 200]},
            growth_arrow_size=growth_arrow_size,
        )

    def test_grows_up_raises_higher_address_neighbor(self):
        # grows-up on heap_used → its higher-address neighbor (heap_free) is raised.
        heap_used = Section(size=0x800, address=0x1000, id='heap_used', flags=['grows-up'])
        heap_free = Section(size=0x1000, address=0x1800, id='heap_free')
        av = self._make_av([heap_used, heap_free])
        found = next(s for s in av.sections.get_sections() if s.id == 'heap_free')
        self.assertGreaterEqual(found.size_y_override, self._arrow_floor())

    def test_grows_down_raises_lower_address_neighbor(self):
        # grows-down on stack_used → its lower-address neighbor (stack_free) is raised.
        stack_free = Section(size=0x1000, address=0x2800, id='stack_free')
        stack_used = Section(size=0x800, address=0x3800, id='stack_used', flags=['grows-down'])
        av = self._make_av([stack_free, stack_used])
        found = next(s for s in av.sections.get_sections() if s.id == 'stack_free')
        self.assertGreaterEqual(found.size_y_override, self._arrow_floor())

    def test_neighbor_already_taller_not_shrunk(self):
        # A neighbor with min_height > arrow_neighbor_floor keeps its taller floor.
        heap_used = Section(size=0x800, address=0x1000, id='heap_used', flags=['grows-up'])
        heap_free = Section(size=0x1000, address=0x1800, id='heap_free', min_height=100)
        av = self._make_av([heap_used, heap_free])
        found = next(s for s in av.sections.get_sections() if s.id == 'heap_free')
        self.assertGreaterEqual(found.size_y_override, 100.0)

    def test_break_neighbor_not_raised(self):
        # A break section adjacent to a grows-up section keeps its break_height.
        data = Section(size=0x800, address=0x0, id='data')
        brk = Section(size=0x800, address=0x800, id='brk', flags=['break'])
        heap_used = Section(size=0x800, address=0x1000, id='heap_used', flags=['grows-up'])
        style = default_style()
        style['break_height'] = 20
        av = self._make_av([data, brk, heap_used], style=style)
        found_brk = next(s for s in av.sections.get_sections() if s.id == 'brk')
        self.assertAlmostEqual(found_brk.size_y_override, 20.0, places=6)

    def test_growth_arrow_size_scales_neighbor_floor(self):
        # growth_arrow_size=2 doubles the arrow height component of the floor.
        heap_used = Section(size=0x800, address=0x1000, id='heap_used', flags=['grows-up'])
        heap_free = Section(size=0x1000, address=0x1800, id='heap_free')
        av = self._make_av([heap_used, heap_free], growth_arrow_size=2.0)
        found = next(s for s in av.sections.get_sections() if s.id == 'heap_free')
        # arrow_neighbor_floor = 20*2 + 16 = 56
        self.assertGreaterEqual(found.size_y_override, self._arrow_floor(growth_arrow_size=2.0))

    def test_estimate_matches_process_with_grows(self):
        # _estimate_area_height and _process() must agree when grows flags are present.
        heap_used = Section(size=0x800, address=0x1000, id='heap_used', flags=['grows-up'])
        heap_free = Section(size=0x1000, address=0x1800, id='heap_free')
        style = dict(default_style())
        style['min_section_height'] = 20
        size_x = 230.0
        growth_arrow_size = 1.0
        estimated = _estimate_area_height([heap_used, heap_free], style,
                                           size_x=size_x, growth_arrow_size=growth_arrow_size)
        av = AreaView(
            sections=Sections([heap_used, heap_free]),
            style=style,
            area_config={'id': 'v', 'title': 'V', 'pos': [0, estimated],
                         'size': [size_x, estimated], 'start': 0x1000, 'end': 0x2800},
            growth_arrow_size=growth_arrow_size,
        )
        self.assertAlmostEqual(av.size_y, estimated, places=6)


if __name__ == '__main__':
    unittest.main()
