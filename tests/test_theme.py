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
        self.assertEqual(style['break_type'], '≈')

    def test_all_required_keys_present(self):
        t = Theme()
        style = t.resolve('x')
        for key in ('background', 'fill', 'stroke', 'stroke_width', 'font_size',
                    'font_family', 'text_fill', 'break_type', 'break_size',
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


if __name__ == '__main__':
    unittest.main()
