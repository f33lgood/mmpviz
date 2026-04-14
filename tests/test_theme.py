import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import json
import tempfile
import unittest
from theme import Theme, ThemeError

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


class TestThemeDefaults(unittest.TestCase):

    def test_no_path_loads_default_theme(self):
        # When no path is given, themes/default.json is loaded automatically.
        t = Theme()
        style = t.resolve('nonexistent-area')
        # default.json style overrides Theme.DEFAULT
        self.assertEqual(style['fill'], '#e8e8e8')
        self.assertEqual(style['stroke'], '#555555')
        self.assertEqual(style['break_height'], 20)

    def test_all_required_keys_present(self):
        t = Theme()
        style = t.resolve('x')
        for key in ('background', 'fill', 'stroke', 'stroke_width', 'font_size',
                    'font_family', 'text_fill', 'break_height'):
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
        connector = style.get('connector', {})
        self.assertEqual(connector['fill'], 'gray')
        self.assertAlmostEqual(connector['opacity'], 0.4)

    def test_resolve_labels(self):
        style = self.theme.resolve_labels()
        self.assertEqual(style['stroke'], 'white')

    def test_resolve_growth_arrow(self):
        t = Theme()
        ga = t.resolve_growth_arrow()
        self.assertIn('size',   ga)
        self.assertIn('fill',   ga)
        self.assertIn('stroke', ga)

    def test_section_key_not_in_area_style(self):
        # The 'sections' sub-dict should not appear in the resolved area style
        style = self.theme.resolve('flash-view')
        self.assertNotIn('sections', style)

    def test_labels_key_not_in_area_style(self):
        # The 'labels' sub-dict should not appear in the resolved area style
        style = self.theme.resolve('flash-view')
        self.assertNotIn('labels', style)

    def test_resolve_label_overrides_returns_empty_for_unknown_view(self):
        overrides = self.theme.resolve_label_overrides('nonexistent-view')
        self.assertEqual(overrides, {})


class TestThemeInheritance(unittest.TestCase):

    def _write_tmp(self, d, data):
        """Write JSON to a temp file inside directory d and return its path."""
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', dir=d, delete=False) as f:
            json.dump(data, f)
            return f.name

    def test_extends_builtin_name(self):
        # A child that extends "plantuml" by name inherits plantuml's fill.
        with tempfile.TemporaryDirectory() as d:
            child_path = self._write_tmp(d, {
                "schema_version": 1,
                "extends": "plantuml",
                "base": {"stroke": "red"}
            })
            t = Theme(child_path)
            style = t.resolve('x')
            self.assertEqual(style['stroke'], 'red')       # child override
            self.assertEqual(style['fill'], '#FEFECE')     # inherited from plantuml

    def test_extends_relative_path(self):
        # extends with a relative path resolves relative to the child theme file.
        with tempfile.TemporaryDirectory() as d:
            parent_path = self._write_tmp(d, {
                "schema_version": 1,
                "base": {"fill": "#parent"}
            })
            parent_name = os.path.basename(parent_path)
            child_path = self._write_tmp(d, {
                "schema_version": 1,
                "extends": f"./{parent_name}",
                "base": {"stroke": "#child"}
            })
            t = Theme(child_path)
            style = t.resolve('x')
            self.assertEqual(style['fill'], '#parent')
            self.assertEqual(style['stroke'], '#child')

    def test_extends_chain(self):
        # Three-level chain: grandparent → parent → child. Deepest child wins.
        with tempfile.TemporaryDirectory() as d:
            gp_path = self._write_tmp(d, {
                "schema_version": 1,
                "base": {"fill": "#gp", "stroke": "#gp", "background": "#gp"}
            })
            p_path = self._write_tmp(d, {
                "schema_version": 1,
                "extends": f"./{os.path.basename(gp_path)}",
                "base": {"stroke": "#parent"}
            })
            c_path = self._write_tmp(d, {
                "schema_version": 1,
                "extends": f"./{os.path.basename(p_path)}",
                "base": {"fill": "#child"}
            })
            t = Theme(c_path)
            style = t.resolve('x')
            self.assertEqual(style['fill'], '#child')         # child wins
            self.assertEqual(style['stroke'], '#parent')      # parent wins over gp
            self.assertEqual(style['background'], '#gp')      # inherited from gp

    def test_circular_extends_raises(self):
        # A → B → A should raise ThemeError.
        with tempfile.TemporaryDirectory() as d:
            # Write placeholder files so we can get their names before content
            a_fd, a_path = tempfile.mkstemp(suffix='.json', dir=d)
            b_fd, b_path = tempfile.mkstemp(suffix='.json', dir=d)
            os.close(a_fd); os.close(b_fd)
            with open(a_path, 'w') as f:
                json.dump({"schema_version": 1,
                           "extends": f"./{os.path.basename(b_path)}"}, f)
            with open(b_path, 'w') as f:
                json.dump({"schema_version": 1,
                           "extends": f"./{os.path.basename(a_path)}"}, f)
            with self.assertRaises(ThemeError):
                Theme(a_path)

    def test_extends_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as d:
            child_path = self._write_tmp(d, {
                "schema_version": 1,
                "extends": "./does_not_exist.json"
            })
            with self.assertRaises(ThemeError):
                Theme(child_path)

    def test_areas_merged_two_levels(self):
        # Parent defines area with section; child overrides one property.
        with tempfile.TemporaryDirectory() as d:
            parent_path = self._write_tmp(d, {
                "schema_version": 1,
                "views": {
                    "flash": {
                        "fill": "#parent-flash",
                        "sections": {
                            "text": {"fill": "#parent-text"},
                            "rodata": {"fill": "#parent-rodata"}
                        }
                    }
                }
            })
            child_path = self._write_tmp(d, {
                "schema_version": 1,
                "extends": f"./{os.path.basename(parent_path)}",
                "views": {
                    "flash": {
                        "sections": {
                            "text": {"fill": "#child-text"}
                        }
                    }
                }
            })
            t = Theme(child_path)
            style_text = t.resolve('flash', 'text')
            style_rodata = t.resolve('flash', 'rodata')
            style_area = t.resolve('flash')
            self.assertEqual(style_text['fill'], '#child-text')    # child wins
            self.assertEqual(style_rodata['fill'], '#parent-rodata')  # inherited
            self.assertEqual(style_area['fill'], '#parent-flash')  # area prop inherited


class TestThemeValidation(unittest.TestCase):

    def _write_tmp(self, d, data):
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', dir=d, delete=False) as f:
            json.dump(data, f)
            return f.name

    def test_future_schema_version_raises(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_tmp(d, {"schema_version": 9999})
            with self.assertRaises(ThemeError):
                Theme(path)

    def test_old_schema_version_warns(self):
        import logging
        with tempfile.TemporaryDirectory() as d:
            path = self._write_tmp(d, {"schema_version": 0, "base": {"fill": "red"}})
            with self.assertLogs(level=logging.WARNING) as cm:
                t = Theme(path)
            self.assertTrue(any("schema_version" in msg for msg in cm.output))
            self.assertEqual(t.resolve('x')['fill'], 'red')

    def test_unknown_top_level_key_warns(self):
        import logging
        with tempfile.TemporaryDirectory() as d:
            path = self._write_tmp(d, {
                "schema_version": 1,
                "unknown_future_key": "ignored",
                "base": {"fill": "blue"}
            })
            with self.assertLogs(level=logging.WARNING) as cm:
                t = Theme(path)
            self.assertTrue(any("unknown_future_key" in msg for msg in cm.output))
            self.assertEqual(t.resolve('x')['fill'], 'blue')

    def test_style_wrong_type_raises(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_tmp(d, {"schema_version": 1, "base": ["oops"]})
            with self.assertRaises(ThemeError):
                Theme(path)

    def test_schema_version_absent_is_silent(self):
        # Legacy files with no schema_version load cleanly with no warning.
        with tempfile.TemporaryDirectory() as d:
            path = self._write_tmp(d, {"base": {"fill": "#legacy"}})
            t = Theme(path)
            self.assertEqual(t.resolve('x')['fill'], '#legacy')


class TestThemeBuiltinNameResolution(unittest.TestCase):

    def test_builtin_name_plantuml(self):
        t = Theme("plantuml")
        style = t.resolve('x')
        self.assertEqual(style['fill'], '#FEFECE')

    def test_builtin_name_default(self):
        t = Theme("default")
        style = t.resolve('x')
        self.assertEqual(style['fill'], '#e8e8e8')

    def test_default_theme_is_default_json(self):
        t_implicit = Theme()
        t_explicit = Theme("default")
        self.assertEqual(t_implicit.resolve('x')['fill'],
                         t_explicit.resolve('x')['fill'])


if __name__ == '__main__':
    unittest.main()
