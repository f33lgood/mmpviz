import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import unittest
from theme import Theme

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


class TestThemeDefaults(unittest.TestCase):

    def test_no_path_uses_built_in_defaults(self):
        t = Theme()
        style = t.resolve('nonexistent-area')
        self.assertEqual(style['fill'], 'lightgrey')
        self.assertEqual(style['stroke'], 'black')
        self.assertEqual(style['break_size'], 20)

    def test_all_required_keys_present(self):
        t = Theme()
        style = t.resolve('x')
        for key in ('background', 'fill', 'stroke', 'stroke_width', 'font_size',
                    'font_family', 'text_fill', 'break_size',
                    'growth_arrow_size', 'hide_size', 'hide_name', 'hide_address'):
            self.assertIn(key, style, f"Missing key: {key}")


class TestThemeFromFile(unittest.TestCase):

    def setUp(self):
        self.theme = Theme(os.path.join(FIXTURES, 'sample_theme.json'))

    def test_defaults_override_built_in(self):
        style = self.theme.resolve('nonexistent')
        # sample_theme.json sets background to #1a1a2e in defaults
        self.assertEqual(style['background'], '#1a1a2e')

    def test_area_override_applied(self):
        style = self.theme.resolve('flash-view')
        self.assertEqual(style['fill'], '#08c6ab')
        self.assertEqual(style['background'], '#212b38')

    def test_section_override_applied(self):
        style = self.theme.resolve('flash-view', 'text')
        self.assertEqual(style['fill'], '#99B898')

    def test_area_without_section_override(self):
        # 'sram-view' not defined in sample theme; should get defaults
        style = self.theme.resolve('sram-view')
        self.assertEqual(style['background'], '#1a1a2e')  # from defaults block

    def test_unknown_section_falls_back_to_area(self):
        style = self.theme.resolve('flash-view', 'nonexistent-section')
        # Should get area style (fill from flash-view area override)
        self.assertEqual(style['fill'], '#08c6ab')

    def test_unknown_keys_dont_raise(self):
        try:
            style = self.theme.resolve('flash-view', 'text')
            _ = style.get('nonexistent_key')
        except Exception as e:
            self.fail(f"Unexpected exception: {e}")

    def test_resolve_links(self):
        style = self.theme.resolve_links()
        self.assertEqual(style['fill'], 'gray')
        self.assertAlmostEqual(style['opacity'], 0.4)

    def test_resolve_labels(self):
        style = self.theme.resolve_labels()
        self.assertEqual(style['stroke'], 'white')

    def test_section_key_not_in_area_style(self):
        # The 'sections' sub-dict should not appear in the resolved area style
        style = self.theme.resolve('flash-view')
        self.assertNotIn('sections', style)


class TestThemePalette(unittest.TestCase):

    def setUp(self):
        self.theme = Theme(os.path.join(FIXTURES, 'palette_theme.json'))

    def test_palette_applied_when_no_explicit_fill(self):
        # No area or section fill → palette kicks in
        style = self.theme.resolve('any-area', 'any-section', palette_index=0)
        self.assertEqual(style['fill'], '#aabbcc')

    def test_palette_cycles(self):
        style = self.theme.resolve('any-area', 'any-section', palette_index=3)
        self.assertEqual(style['fill'], '#aabbcc')  # 3 % 3 == 0

    def test_palette_index_1(self):
        style = self.theme.resolve('any-area', 'any-section', palette_index=1)
        self.assertEqual(style['fill'], '#bbccaa')

    def test_area_fill_overrides_palette(self):
        # Area has explicit fill → palette should NOT apply
        style = self.theme.resolve('with-area-fill', 'any-section', palette_index=0)
        self.assertEqual(style['fill'], '#explicit-area')

    def test_section_fill_overrides_palette(self):
        # Section has explicit fill → palette should NOT apply
        style = self.theme.resolve('with-section-fill', 'sec-a', palette_index=0)
        self.assertEqual(style['fill'], '#explicit-section')

    def test_no_palette_index_ignores_palette(self):
        # palette_index not supplied → falls through to defaults fill
        style = self.theme.resolve('any-area', 'any-section')
        self.assertEqual(style['fill'], 'lightgrey')

    def test_no_palette_in_theme_ignores_index(self):
        # Theme without palette → palette_index has no effect
        theme = Theme(os.path.join(FIXTURES, 'sample_theme.json'))
        style = theme.resolve('nonexistent', 'nonexistent', palette_index=0)
        self.assertEqual(style['fill'], '#16213e')  # from sample defaults


if __name__ == '__main__':
    unittest.main()
