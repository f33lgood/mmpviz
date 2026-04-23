"""
tests/test_embedded_theme.py — Embedded-theme support in diagram.json.

Covers the three layers of the feature:

  1. Diagram schema / loader — the new top-level ``"theme"`` key is permitted
     and type-checked (must be string or object).
  2. Theme constructor — ``Theme(dict)`` behaves identically to loading the
     same object as a sidecar ``theme.json`` file. ``extends`` restricted to
     built-in names when the source is an embedded dict.
  3. CLI integration — resolution order (``-t`` > embedded > sibling > default)
     and the warning emitted when ``-t`` overrides an embedded theme.
"""
import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest

# conftest.py adds scripts/ to sys.path for direct imports.
from loader import validate
from theme import Theme, ThemeError

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))
MMPVIZ = os.path.join(SCRIPTS_DIR, 'mmpviz.py')


def _clean_diagram():
    return {
        "views": [{
            "id": "view-a",
            "sections": [
                {"id": "code",  "address": "0x08000000", "size": "0x9000",  "name": "Code"},
                {"id": "const", "address": "0x08009000", "size": "0x2000",  "name": "Constants"},
            ]
        }]
    }


# ---------------------------------------------------------------------------
# Layer 1: diagram schema / loader accepts the new key
# ---------------------------------------------------------------------------

class TestLoaderAcceptsEmbeddedTheme(unittest.TestCase):

    def _write(self, tmpdir, data):
        path = os.path.join(tmpdir, 'diagram.json')
        with open(path, 'w') as f:
            json.dump(data, f)
        return path

    def test_string_alias_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _clean_diagram()
            d["theme"] = "plantuml"
            errors = validate(self._write(tmp, d))
            self.assertEqual(errors, [])

    def test_inline_object_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _clean_diagram()
            d["theme"] = {"base": {"fill": "#123456"}}
            errors = validate(self._write(tmp, d))
            self.assertEqual(errors, [])

    def test_wrong_type_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _clean_diagram()
            d["theme"] = 42
            errors = validate(self._write(tmp, d))
            self.assertTrue(any("theme" in e for e in errors),
                            f"Expected a 'theme' error, got: {errors}")

    def test_sidecar_theme_pasted_verbatim_validates(self):
        """The 'copy your sidecar theme.json inline' workflow must work —
        the embedded block accepts ``schema_version`` and every other
        top-level theme key exactly as a sidecar file would."""
        with tempfile.TemporaryDirectory() as tmp:
            d = _clean_diagram()
            d["theme"] = {
                "schema_version": 1,
                "extends": "default",
                "base": {"fill": "#aabbcc"},
                "views": {"view-a": {"sections": {"code": {"fill": "#112233"}}}},
            }
            errors = validate(self._write(tmp, d))
            self.assertEqual(errors, [])

    def test_schema_version_at_diagram_top_level_is_accepted(self):
        """``schema_version`` is now a recognised optional top-level key in
        diagram.json. Declaring the current supported version is silent and
        the diagram validates cleanly. Absent (pre-1.1.1 style) remains
        fully valid and is covered by every other test that omits the
        field."""
        with tempfile.TemporaryDirectory() as tmp:
            d = _clean_diagram()
            d["schema_version"] = 1
            errors = validate(self._write(tmp, d))
            self.assertEqual(errors, [])

    def test_schema_version_older_warns(self):
        """A diagram declaring a version below the reader's supported version
        renders with a warning — per-feature backfills (none today) would
        apply here when they land."""
        with tempfile.TemporaryDirectory() as tmp:
            d = _clean_diagram()
            d["schema_version"] = 0  # any value < DIAGRAM_SUPPORTED_VERSION
            with self.assertLogs(level=logging.WARNING) as cm:
                errors = validate(self._write(tmp, d))
            self.assertEqual(errors, [])
            self.assertTrue(
                any("schema_version" in msg for msg in cm.output),
                f"Expected schema_version warning, got: {cm.output}",
            )

    def test_schema_version_newer_is_fatal(self):
        """A diagram declaring a version above the reader's supported version
        is a hard validation error — the reader is too old to interpret
        future semantics safely."""
        with tempfile.TemporaryDirectory() as tmp:
            d = _clean_diagram()
            d["schema_version"] = 9999
            errors = validate(self._write(tmp, d))
            self.assertTrue(
                any("schema_version" in e and "9999" in e for e in errors),
                f"Expected schema_version upgrade error, got: {errors}",
            )

    def test_schema_version_wrong_type_is_rejected(self):
        """schema_version must be an integer — a boolean (which is an int
        subclass in Python) or a string must be rejected so typos surface."""
        with tempfile.TemporaryDirectory() as tmp:
            d = _clean_diagram()
            d["schema_version"] = "1"
            errors = validate(self._write(tmp, d))
            self.assertTrue(
                any("schema_version" in e for e in errors),
                f"Expected schema_version type error, got: {errors}",
            )


# ---------------------------------------------------------------------------
# Layer 2: Theme(dict) parity with sidecar theme.json
# ---------------------------------------------------------------------------

class TestThemeAcceptsDict(unittest.TestCase):

    def test_dict_equivalent_to_sidecar_file(self):
        """Loading a dict gives the same resolved style as loading that dict
        written to a file — embedded mode is truly "file contents inlined"."""
        body = {
            "schema_version": 1,
            "base": {"fill": "#abcdef", "stroke": "#111111"},
        }
        t_inline = Theme(body)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                         delete=False, encoding='utf-8') as f:
            json.dump(body, f)
            sidecar_path = f.name
        try:
            t_sidecar = Theme(sidecar_path)
            self.assertEqual(
                t_inline.resolve('x'),
                t_sidecar.resolve('x'),
                "Inline dict theme must resolve identically to sidecar file",
            )
        finally:
            os.unlink(sidecar_path)

    def test_dict_extends_builtin_name(self):
        """An embedded dict can extend a built-in by name."""
        t = Theme({
            "schema_version": 1,
            "extends": "plantuml",
            "base": {"stroke": "red"},
        })
        style = t.resolve('x')
        self.assertEqual(style['stroke'], 'red')           # child override
        self.assertEqual(style['fill'], '#FEFECE')         # inherited from plantuml

    def test_dict_fully_inline_no_extends(self):
        """A fully inline dict without ``extends`` works — no built-in
        inheritance, just the user's values layered on Theme.DEFAULT.

        ``schema_version`` is intentionally omitted here: the minimal
        embedded-theme shape is a plain ``base``/``views``/... object,
        matching the same "legacy, no declared version" contract that
        sidecar theme.json files have always supported.
        """
        t = Theme({
            "base": {"fill": "#deadbe", "stroke": "#ef0123"},
        })
        style = t.resolve('x')
        self.assertEqual(style['fill'], '#deadbe')
        self.assertEqual(style['stroke'], '#ef0123')

    def test_dict_relative_extends_rejected(self):
        """Embedded themes have no on-disk anchor so relative paths in
        ``extends`` must error with a clear, actionable message."""
        with self.assertRaises(ThemeError) as ctx:
            Theme({"schema_version": 1, "extends": "./parent.json"})
        msg = str(ctx.exception)
        self.assertIn("embedded", msg)
        self.assertIn("built-in", msg)

    def test_dict_absolute_extends_rejected(self):
        """Absolute-path extends is likewise not portable across machines
        and so is rejected for embedded themes."""
        with self.assertRaises(ThemeError):
            Theme({"schema_version": 1, "extends": "/etc/theme.json"})

    def test_dict_invalid_structure_raises(self):
        """Deep validation still runs on embedded themes."""
        with self.assertRaises(ThemeError):
            Theme({"schema_version": 1, "base": "not-an-object"})


# ---------------------------------------------------------------------------
# Layer 3: CLI integration — resolution order and override warning
# ---------------------------------------------------------------------------

class TestCLIEmbeddedTheme(unittest.TestCase):

    def _run(self, *args):
        cmd = [sys.executable, MMPVIZ] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr

    def _write_diagram(self, tmp, data, name='diagram.json'):
        path = os.path.join(tmp, name)
        with open(path, 'w') as f:
            json.dump(data, f)
        return path

    def test_embedded_string_alias_renders(self):
        """A diagram with ``"theme": "plantuml"`` renders successfully
        without any sidecar file or -t argument."""
        with tempfile.TemporaryDirectory() as tmp:
            d = _clean_diagram()
            d["theme"] = "plantuml"
            diag = self._write_diagram(tmp, d)
            svg = os.path.join(tmp, 'out.svg')

            rc, out = self._run('-d', diag, '-o', svg)
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}. Output: {out}")
            self.assertTrue(os.path.isfile(svg))
            with open(svg) as f:
                content = f.read()
            # PlantUML theme uses fill=#FEFECE — should appear in the SVG.
            self.assertIn('#FEFECE', content)

    def test_embedded_inline_object_renders(self):
        """A fully inline theme object renders without sidecar or -t."""
        with tempfile.TemporaryDirectory() as tmp:
            d = _clean_diagram()
            d["theme"] = {
                "schema_version": 1,
                "base": {"fill": "#ABCABC", "stroke": "#222222"},
            }
            diag = self._write_diagram(tmp, d)
            svg = os.path.join(tmp, 'out.svg')

            rc, out = self._run('-d', diag, '-o', svg)
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}. Output: {out}")
            with open(svg) as f:
                content = f.read()
            self.assertIn('#ABCABC', content)

    def test_cli_theme_overrides_embedded_with_warning(self):
        """Explicit -t wins over an embedded theme, and a warning is emitted
        so the operator knows their flag took precedence."""
        with tempfile.TemporaryDirectory() as tmp:
            d = _clean_diagram()
            # Embedded says fill=#ABCABC, but we pass -t plantuml (#FEFECE)
            d["theme"] = {
                "schema_version": 1,
                "base": {"fill": "#ABCABC"},
            }
            diag = self._write_diagram(tmp, d)
            svg = os.path.join(tmp, 'out.svg')

            rc, out = self._run('-d', diag, '-o', svg, '-t', 'plantuml')
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}. Output: {out}")
            self.assertIn("Ignoring embedded 'theme'", out)
            with open(svg) as f:
                content = f.read()
            self.assertIn('#FEFECE', content)     # -t plantuml won
            self.assertNotIn('#ABCABC', content)  # embedded lost

    def test_embedded_beats_sibling(self):
        """When both an embedded theme and a sibling theme.json are present,
        the embedded theme wins — it is a more explicit declaration than
        the auto-discovered sidecar."""
        with tempfile.TemporaryDirectory() as tmp:
            # Sibling theme.json with a distinctive fill...
            sidecar = os.path.join(tmp, 'theme.json')
            with open(sidecar, 'w') as f:
                json.dump({"schema_version": 1,
                           "base": {"fill": "#111111"}}, f)
            # ...and an embedded theme with a different one.
            d = _clean_diagram()
            d["theme"] = {"schema_version": 1, "base": {"fill": "#999999"}}
            diag = self._write_diagram(tmp, d)
            svg = os.path.join(tmp, 'out.svg')

            rc, out = self._run('-d', diag, '-o', svg)
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}. Output: {out}")
            with open(svg) as f:
                content = f.read()
            self.assertIn('#999999', content)
            self.assertNotIn('#111111', content)

    def test_no_theme_still_renders_with_default(self):
        """Regression: a diagram with no theme declaration at all still
        renders via the built-in default — the whole point of keeping the
        sidecar/default path unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            diag = self._write_diagram(tmp, _clean_diagram())
            svg = os.path.join(tmp, 'out.svg')

            rc, out = self._run('-d', diag, '-o', svg)
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}. Output: {out}")
            self.assertTrue(os.path.isfile(svg))


if __name__ == '__main__':
    unittest.main()
