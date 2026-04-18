"""
Regression tests for the issues surfaced in the April 2026 validator review.

Each test covers one user-facing silent-failure mode or internal functional bug
so a future regression will trip immediately.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import json
import logging
import tempfile
import unittest

from loader import (
    validate, resolve_view_sections, _is_hex_or_int,
)
from theme import Theme, ThemeError, validate_theme


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_dir, data, name='diagram.json'):
    p = os.path.join(tmp_dir, name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return p


def _minimal_diagram(**overrides):
    d = {
        "views": [{
            "id": "v1",
            "sections": [
                {"id": "s1", "address": "0x0", "size": "0x1000", "name": "S1"},
            ],
        }]
    }
    d.update(overrides)
    return d


# ---------------------------------------------------------------------------
# diagram.json — structural typos must surface as hard errors
# ---------------------------------------------------------------------------

class TestDiagramAdditionalProperties(unittest.TestCase):
    """Typos in diagram.json keys must NOT be silently ignored."""

    def test_top_level_typo_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"views": [], "tittle": "typo"})
            errors = validate(path)
            self.assertTrue(any("tittle" in e for e in errors),
                            f"Top-level typo was accepted: {errors}")

    def test_view_key_typo_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"views": [{"id": "v", "titl": "oops",
                                           "sections": []}]})
            errors = validate(path)
            self.assertTrue(any("titl" in e for e in errors), errors)

    def test_section_key_typo_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"views": [{"id": "v", "sections": [
                {"id": "s", "adress": "0x0", "size": "0x100", "name": "S"}
            ]}]})
            errors = validate(path)
            self.assertTrue(any("adress" in e for e in errors), errors)
            # and still complains about the missing required address
            self.assertTrue(any("address" in e and "adress" not in e
                                for e in errors), errors)

    def test_label_key_typo_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"views": [{"id": "v", "sections": [
                {"id": "s", "address": "0x0", "size": "0x100", "name": "S"}
            ], "labels": [
                {"id": "l", "address": "0x10", "txt": "oops"}
            ]}]})
            errors = validate(path)
            self.assertTrue(any("txt" in e for e in errors), errors)

    def test_link_key_typo_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {
                "views": [
                    {"id": "a", "sections": [
                        {"id": "s", "address": "0x0", "size": "0x100", "name": "S"}]},
                    {"id": "b", "sections": [
                        {"id": "s", "address": "0x0", "size": "0x100", "name": "S"}]},
                ],
                "links": [{"id": "lk", "from": {"view": "a", "sektions": ["s"]},
                           "to": {"view": "b"}}],
            })
            errors = validate(path)
            self.assertTrue(any("sektions" in e for e in errors), errors)


class TestDiagramTypeEnforcement(unittest.TestCase):
    """Malformed values must surface at validate(), not crash later."""

    def test_malformed_address_string_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"views": [{"id": "v", "sections": [
                {"id": "s", "address": "0x1000MB", "size": "0x100", "name": "S"}
            ]}]})
            errors = validate(path)
            self.assertTrue(any("address" in e and "0x1000MB" in e
                                for e in errors), errors)

    def test_boolean_address_is_error(self):
        # Without an explicit bool-rejection, True would coerce to 1.
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"views": [{"id": "v", "sections": [
                {"id": "s", "address": True, "size": "0x100", "name": "S"}
            ]}]})
            errors = validate(path)
            self.assertTrue(any("address" in e for e in errors), errors)

    def test_negative_address_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"views": [{"id": "v", "sections": [
                {"id": "s", "address": -1, "size": "0x100", "name": "S"}
            ]}]})
            errors = validate(path)
            self.assertTrue(any("address" in e for e in errors), errors)

    def test_string_min_height_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"views": [{"id": "v", "sections": [
                {"id": "s", "address": "0x0", "size": "0x100", "name": "S",
                 "min_height": "tall"}
            ]}]})
            errors = validate(path)
            self.assertTrue(any("min_height" in e for e in errors), errors)

    def test_bad_section_flag_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"views": [{"id": "v", "sections": [
                {"id": "s", "address": "0x0", "size": "0x100", "name": "S",
                 "flags": ["grows-diagonally"]}
            ]}]})
            errors = validate(path)
            self.assertTrue(any("grows-diagonally" in e for e in errors), errors)


class TestDiagramLinkValidation(unittest.TestCase):
    """Links must be fully validated, including cross-references."""

    def test_link_missing_id_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {
                "views": [{"id": "v", "sections": [
                    {"id": "s", "address": "0x0", "size": "0x100", "name": "S"}]}],
                "links": [{"from": {"view": "v"}, "to": {"view": "v"}}],
            })
            errors = validate(path)
            self.assertTrue(any("missing 'id'" in e and "links[0]" in e
                                for e in errors), errors)

    def test_link_missing_from_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {
                "views": [{"id": "v", "sections": [
                    {"id": "s", "address": "0x0", "size": "0x100", "name": "S"}]}],
                "links": [{"id": "lk", "to": {"view": "v"}}],
            })
            errors = validate(path)
            self.assertTrue(any("missing 'from'" in e for e in errors), errors)

    def test_link_unknown_view_ref_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {
                "views": [{"id": "real", "sections": [
                    {"id": "s", "address": "0x0", "size": "0x100", "name": "S"}]}],
                "links": [{"id": "lk",
                           "from": {"view": "real"},
                           "to":   {"view": "typo"}}],
            })
            errors = validate(path)
            self.assertTrue(any("unknown view" in e and "typo" in e
                                for e in errors), errors)

    def test_duplicate_link_id_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {
                "views": [
                    {"id": "a", "sections": [
                        {"id": "s", "address": "0x0", "size": "0x100", "name": "S"}]},
                    {"id": "b", "sections": [
                        {"id": "s", "address": "0x0", "size": "0x100", "name": "S"}]}],
                "links": [
                    {"id": "dup", "from": {"view": "a"}, "to": {"view": "b"}},
                    {"id": "dup", "from": {"view": "a"}, "to": {"view": "b"}},
                ],
            })
            errors = validate(path)
            self.assertTrue(any("duplicate" in e and "dup" in e
                                for e in errors), errors)


# ---------------------------------------------------------------------------
# Legacy auto-layout fields — diagram-level `size`, view-level `pos`/`size` —
# were removed when auto-layout became the only layout engine.  They now
# surface as hard "unknown key" errors from the structural check.
# ---------------------------------------------------------------------------

class TestLegacyLayoutFields(unittest.TestCase):

    def test_diagram_size_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"size": [500, 500],
                                "views": [{"id": "v", "sections": [
                                    {"id": "s", "address": "0x0",
                                     "size": "0x100", "name": "S"}]}]})
            errors = validate(path)
            self.assertTrue(any("size" in e for e in errors),
                            f"Legacy 'size' was accepted: {errors}")

    def test_view_pos_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"views": [{
                "id": "v",
                "pos": [0, 0],
                "sections": [{"id": "s", "address": "0x0",
                              "size": "0x100", "name": "S"}],
            }]})
            errors = validate(path)
            self.assertTrue(any("pos" in e for e in errors),
                            f"Legacy view 'pos' was accepted: {errors}")

    def test_view_size_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"views": [{
                "id": "v",
                "size": [100, 200],
                "sections": [{"id": "s", "address": "0x0",
                              "size": "0x100", "name": "S"}],
            }]})
            errors = validate(path)
            self.assertTrue(any("size" in e for e in errors),
                            f"Legacy view 'size' was accepted: {errors}")


# ---------------------------------------------------------------------------
# theme.json — typos in nested blocks must surface as errors
# ---------------------------------------------------------------------------

class TestThemeValidation(unittest.TestCase):
    """validate_theme() is the stdlib-only authoritative theme validator."""

    def test_base_key_typo_is_error(self):
        errors = validate_theme({"base": {"font_siz": 12}})
        self.assertTrue(any("font_siz" in e for e in errors), errors)

    def test_view_override_key_typo_is_error(self):
        errors = validate_theme({"views": {"v1": {"fil": "red"}}})
        self.assertTrue(any("fil" in e for e in errors), errors)

    def test_section_override_key_typo_is_error(self):
        errors = validate_theme({
            "views": {"v1": {"sections": {"s1": {"fil": "red"}}}}
        })
        self.assertTrue(any("fil" in e for e in errors), errors)

    def test_bad_opacity_range_is_error(self):
        errors = validate_theme({"base": {"opacity": 1.5}})
        self.assertTrue(any("opacity" in e for e in errors), errors)

    def test_bad_connector_shape_is_error(self):
        errors = validate_theme({
            "links": {"connector": {"middle": {"shape": "zigzag"}}}
        })
        self.assertTrue(any("shape" in e for e in errors), errors)

    def test_growth_arrow_typo_is_error(self):
        errors = validate_theme({"growth_arrow": {"sizee": 2}})
        self.assertTrue(any("sizee" in e for e in errors), errors)

    def test_valid_theme_produces_no_errors(self):
        errors = validate_theme({
            "schema_version": 1,
            "base": {"fill": "red", "opacity": 0.5},
            "views": {"v1": {"fill": "blue",
                             "sections": {"s1": {"stroke": "black"}}}},
            "links": {"connector": {"fill": "gray",
                                    "middle": {"shape": "curve", "width": 2}}},
            "labels": {"stroke": "white"},
            "growth_arrow": {"size": 2, "fill": "red"},
        })
        self.assertEqual(errors, [])

    def test_theme_init_raises_on_deep_error(self):
        """A typo inside theme.base should block Theme(path) construction."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'theme.json')
            with open(path, 'w') as f:
                json.dump({"schema_version": 1,
                           "base": {"font_siz": 12}}, f)
            with self.assertRaises(ThemeError) as ctx:
                Theme(path)
            self.assertIn("font_siz", str(ctx.exception))

    def test_builtin_default_theme_is_valid(self):
        """The shipped default theme must validate cleanly."""
        # If this ever fails, our schema accepted something the validator
        # doesn't — one of the two is out of date.
        Theme()  # no raise


# ---------------------------------------------------------------------------
# resolve_view_sections — should not crash on malformed inputs post-validate,
# but must also not crash if the caller bypasses validate().
# ---------------------------------------------------------------------------

class TestResolveViewSectionsDefensive(unittest.TestCase):

    def test_malformed_address_no_traceback(self):
        result = resolve_view_sections({
            'id': 'v', 'sections': [
                {'id': 's', 'address': '0xbogus', 'size': '0x100', 'name': 'S'}]})
        self.assertEqual(result, [], "malformed address should be skipped, not crash")

    def test_malformed_min_height_no_traceback(self):
        result = resolve_view_sections({
            'id': 'v', 'sections': [
                {'id': 's', 'address': '0x0', 'size': '0x100', 'name': 'S',
                 'min_height': [1, 2, 3]}]})
        self.assertEqual(result, [], "malformed min_height should be skipped, not crash")


# ---------------------------------------------------------------------------
# Quick sanity check on _is_hex_or_int helper — used by the schema walker
# ---------------------------------------------------------------------------

class TestIsHexOrInt(unittest.TestCase):

    def test_accepts_hex(self):
        self.assertTrue(_is_hex_or_int("0x1000"))
        self.assertTrue(_is_hex_or_int("0XABCDEF"))
        self.assertTrue(_is_hex_or_int("123"))

    def test_accepts_non_negative_int(self):
        self.assertTrue(_is_hex_or_int(0))
        self.assertTrue(_is_hex_or_int(1024))

    def test_rejects_negative(self):
        self.assertFalse(_is_hex_or_int(-1))

    def test_rejects_float(self):
        self.assertFalse(_is_hex_or_int(1.5))

    def test_rejects_bool(self):
        self.assertFalse(_is_hex_or_int(True))
        self.assertFalse(_is_hex_or_int(False))

    def test_rejects_garbage_string(self):
        self.assertFalse(_is_hex_or_int("0xBAD!"))
        self.assertFalse(_is_hex_or_int("not_a_number"))
        self.assertFalse(_is_hex_or_int(""))


if __name__ == '__main__':
    unittest.main()
