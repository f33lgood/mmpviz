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
                    'font_family', 'text_fill', 'break_height',
                    'growth_arrow_size'):
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


class TestThemeInheritance(unittest.TestCase):

    def _write_tmp(self, d, data):
        """Write JSON to a temp file inside directory d and return its path."""
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', dir=d, delete=False) as f:
            json.dump(data, f)
            return f.name

    def test_extends_builtin_name(self):
        # A child that extends "light" by name inherits light's background and palette.
        with tempfile.TemporaryDirectory() as d:
            child_path = self._write_tmp(d, {
                "schema_version": 1,
                "extends": "light",
                "style": {"stroke": "red"}
            })
            t = Theme(child_path)
            style = t.resolve('x')
            self.assertEqual(style['stroke'], 'red')         # child override
            self.assertEqual(style['background'], '#ffffff')  # inherited from light
            # palette from light is inherited
            self.assertIn('palette', t._data)

    def test_extends_relative_path(self):
        # extends with a relative path resolves relative to the child theme file.
        with tempfile.TemporaryDirectory() as d:
            parent_path = self._write_tmp(d, {
                "schema_version": 1,
                "style": {"fill": "#parent"}
            })
            parent_name = os.path.basename(parent_path)
            child_path = self._write_tmp(d, {
                "schema_version": 1,
                "extends": f"./{parent_name}",
                "style": {"stroke": "#child"}
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
                "style": {"fill": "#gp", "stroke": "#gp", "background": "#gp"}
            })
            p_path = self._write_tmp(d, {
                "schema_version": 1,
                "extends": f"./{os.path.basename(gp_path)}",
                "style": {"stroke": "#parent"}
            })
            c_path = self._write_tmp(d, {
                "schema_version": 1,
                "extends": f"./{os.path.basename(p_path)}",
                "style": {"fill": "#child"}
            })
            t = Theme(c_path)
            style = t.resolve('x')
            self.assertEqual(style['fill'], '#child')         # child wins
            self.assertEqual(style['stroke'], '#parent')      # parent wins over gp
            self.assertEqual(style['background'], '#gp')      # inherited from gp

    def test_palette_replaced_not_merged(self):
        # Child palette fully replaces parent's — no index merging.
        with tempfile.TemporaryDirectory() as d:
            parent_path = self._write_tmp(d, {
                "schema_version": 1,
                "palette": ["#aaa", "#bbb", "#ccc"]
            })
            child_path = self._write_tmp(d, {
                "schema_version": 1,
                "extends": f"./{os.path.basename(parent_path)}",
                "palette": ["#111", "#222"]
            })
            t = Theme(child_path)
            self.assertEqual(t._data['palette'], ["#111", "#222"])

    def test_palette_inherited_when_absent_in_child(self):
        # If child doesn't specify palette, parent's is inherited.
        with tempfile.TemporaryDirectory() as d:
            parent_path = self._write_tmp(d, {
                "schema_version": 1,
                "palette": ["#aaa", "#bbb"]
            })
            child_path = self._write_tmp(d, {
                "schema_version": 1,
                "extends": f"./{os.path.basename(parent_path)}",
                "style": {"stroke": "red"}
            })
            t = Theme(child_path)
            self.assertEqual(t._data['palette'], ["#aaa", "#bbb"])

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
            path = self._write_tmp(d, {"schema_version": 0, "style": {"fill": "red"}})
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
                "style": {"fill": "blue"}
            })
            with self.assertLogs(level=logging.WARNING) as cm:
                t = Theme(path)
            self.assertTrue(any("unknown_future_key" in msg for msg in cm.output))
            self.assertEqual(t.resolve('x')['fill'], 'blue')

    def test_style_wrong_type_raises(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_tmp(d, {"schema_version": 1, "style": ["oops"]})
            with self.assertRaises(ThemeError):
                Theme(path)

    def test_schema_version_absent_is_silent(self):
        # Legacy files with no schema_version load cleanly with no warning.
        with tempfile.TemporaryDirectory() as d:
            path = self._write_tmp(d, {"style": {"fill": "#legacy"}})
            t = Theme(path)
            self.assertEqual(t.resolve('x')['fill'], '#legacy')


class TestThemeBuiltinNameResolution(unittest.TestCase):

    def test_builtin_name_light(self):
        t = Theme("light")
        style = t.resolve('x')
        self.assertEqual(style['fill'], '#dce8f0')

    def test_builtin_name_monochrome(self):
        t = Theme("monochrome")
        style = t.resolve('x')
        self.assertEqual(style['fill'], '#ebebeb')

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
