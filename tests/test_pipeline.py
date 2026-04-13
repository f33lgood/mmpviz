"""
tests/test_pipeline.py — Integration tests for the mmpviz.py render pipeline.

Covers:
  - Issue.level field is set correctly (ERROR vs WARN) by check.py rule checkers
  - format_diagram() round-trips correctly
  - run_checks() returns issues with correct levels for known-bad diagrams
  - uncovered-gap: chained consecutive breaks that together cover a gap produce no issue;
    a partial break still fires
  - link-anchor-out-of-bounds: address-range link that extends outside the source view
    produces an ERROR; a normal full-view link produces no issue
  - CLI pipeline: --fmt only, --fmt + render, check ERRORs abort, WARNINGs continue
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

# conftest.py already adds scripts/ to sys.path for direct imports.

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))
MMPVIZ = os.path.join(SCRIPTS_DIR, 'mmpviz.py')


# ---------------------------------------------------------------------------
# Minimal diagram fixtures
# ---------------------------------------------------------------------------

def _section_conflict_diagram():
    """A diagram whose only section has min_height > max_height → ERROR.
    Note: the JSON Schema also validates this constraint, so it may be caught
    at schema-validation time before run_checks() is called."""
    return {
        "views": [{
            "id": "test-view",
            "sections": [
                {"id": "code", "address": "0x08000000", "size": "0x9000",
                 "name": "Code", "min_height": 100, "max_height": 50}
            ]
        }]
    }


def _unresolved_link_diagram():
    """A diagram with a link referencing a non-existent section → unresolved-section ERROR.
    This passes JSON Schema (schema cannot validate section ID references) so
    the error is caught only by run_checks()."""
    return {
        "views": [
            {"id": "overview", "sections": [
                {"id": "flash", "address": "0x08000000", "size": "0x20000", "name": "Flash"}]},
            {"id": "detail", "sections": [
                {"id": "code", "address": "0x08000000", "size": "0x20000", "name": "Code"}]},
        ],
        "links": [
            {"from": {"view": "overview", "sections": ["typo-section-id"]},
             "to":   {"view": "detail"}}
        ]
    }


def _uncovered_gap_diagram():
    """A diagram with Flash at 0x0 and SRAM at 0x20000000 — large uncovered gap → WARN."""
    return {
        "views": [{
            "id": "test-view",
            "sections": [
                {"id": "flash", "address": "0x00000000", "size": "0x10000", "name": "Flash"},
                {"id": "sram",  "address": "0x20000000", "size": "0x10000", "name": "SRAM"},
            ]
        }]
    }


def _clean_diagram():
    """A minimal diagram with no issues."""
    return {
        "views": [{
            "id": "test-view",
            "sections": [
                {"id": "code",  "address": "0x08000000", "size": "0x9000",  "name": "Code"},
                {"id": "const", "address": "0x08009000", "size": "0x2000",  "name": "Constants"},
            ]
        }]
    }


def _chained_breaks_diagram():
    """Three consecutive break sections that together span the full gap between two visible
    sections — the union fully covers the gap, so uncovered-gap must NOT fire."""
    return {
        "views": [{
            "id": "test-view",
            "sections": [
                {"id": "trustedsram", "address": "0x00000000", "size": "0x00090000",
                 "name": "TrustedSRAM"},
                {"id": "brk1", "address": "0x00090000", "size": "0x1FF70000",
                 "name": "···", "flags": ["break"]},
                {"id": "brk2", "address": "0x20000000", "size": "0x00110000",
                 "name": "···", "flags": ["break"]},
                {"id": "brk3", "address": "0x20110000", "size": "0x0BEF0000",
                 "name": "···", "flags": ["break"]},
                {"id": "sysperiph", "address": "0x2C000000", "size": "0x04000000",
                 "name": "SysPeriph"},
            ]
        }]
    }


def _partial_break_diagram():
    """One break that covers only part of a large gap — uncovered-gap WARN expected."""
    return {
        "views": [{
            "id": "test-view",
            "sections": [
                {"id": "flash", "address": "0x00000000", "size": "0x00010000", "name": "Flash"},
                {"id": "brk",   "address": "0x00010000", "size": "0x00010000",
                 "name": "···", "flags": ["break"]},
                {"id": "sram",  "address": "0x20000000", "size": "0x00010000", "name": "SRAM"},
            ]
        }]
    }


def _out_of_bounds_anchor_diagram():
    """A link whose from.sections address range extends below the source view's start
    address — the source band bottom anchor falls outside the panel → ERROR."""
    return {
        "views": [
            {"id": "source-view", "sections": [
                {"id": "flash", "address": "0x08000000", "size": "0x20000", "name": "Flash"}]},
            {"id": "detail-view", "sections": [
                {"id": "code",  "address": "0x08000000", "size": "0x20000", "name": "Code"}]},
        ],
        "links": [
            {"from": {"view": "source-view",
                      "sections": ["0x07000000", "0x08020000"]},
             "to":   {"view": "detail-view"}}
        ]
    }


def _unformatted_json(data: dict) -> str:
    """Dump dict as compact single-line JSON (opposite of canonical format)."""
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Unit tests: Issue.level
# ---------------------------------------------------------------------------

class TestIssueLevel(unittest.TestCase):

    def setUp(self):
        from check import (
            Issue,
            _check_section_height_conflict,
            _check_min_height_violated,
            _check_panel_overlap,
            _check_unresolved_link_sections,
        )
        self.Issue = Issue
        self._check_section_height_conflict = _check_section_height_conflict
        self._check_min_height_violated = _check_min_height_violated
        self._check_panel_overlap = _check_panel_overlap
        self._check_unresolved_link_sections = _check_unresolved_link_sections

    def test_issue_default_level_is_warn(self):
        i = self.Issue('some-rule', 'view1', None, 'msg')
        self.assertEqual(i.level, 'WARN')

    def test_issue_explicit_error(self):
        i = self.Issue('some-rule', 'view1', None, 'msg', level='ERROR')
        self.assertEqual(i.level, 'ERROR')

    def test_issue_str_warn_prefix(self):
        i = self.Issue('uncovered-gap', 'view1', None, 'some msg')
        self.assertIn('[WARNING]', str(i))
        self.assertNotIn('[ERROR]', str(i))

    def test_issue_str_error_prefix(self):
        i = self.Issue('panel-overlap', 'view1', None, 'some msg', level='ERROR')
        self.assertIn('[ERROR]', str(i))

    def test_issue_to_dict_includes_level(self):
        i = self.Issue('panel-overlap', 'view1', None, 'msg', level='ERROR')
        d = i.to_dict()
        self.assertEqual(d['level'], 'ERROR')
        self.assertIn('rule', d)
        self.assertIn('message', d)


# ---------------------------------------------------------------------------
# Unit tests: run_checks() issue levels
# ---------------------------------------------------------------------------

class TestRunChecksLevels(unittest.TestCase):

    def _build_area_views(self, diagram):
        from theme import Theme
        from mmpviz import get_area_views
        theme = Theme(None)
        base_style = theme.resolve('')
        return get_area_views(base_style, diagram, theme)

    def test_section_height_conflict_is_error(self):
        from check import run_checks, ALL_RULES
        diagram = _section_conflict_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        conflict = [i for i in issues if i.rule == 'section-height-conflict']
        self.assertTrue(conflict, "Expected section-height-conflict issue")
        self.assertTrue(all(i.level == 'ERROR' for i in conflict))

    def test_uncovered_gap_is_warn(self):
        from check import run_checks, ALL_RULES
        diagram = _uncovered_gap_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        gaps = [i for i in issues if i.rule == 'uncovered-gap']
        self.assertTrue(gaps, "Expected uncovered-gap issue")
        self.assertTrue(all(i.level == 'WARN' for i in gaps))

    def test_clean_diagram_no_issues(self):
        from check import run_checks, ALL_RULES
        diagram = _clean_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        self.assertEqual(issues, [])

    def test_panel_overlap_is_error(self):
        """Manually crafted area_views with two overlapping panels."""
        from check import run_checks, ALL_RULES
        from area_view import AreaView
        from sections import Sections
        from theme import Theme
        from loader import resolve_view_sections
        import copy

        diagram = {
            "views": [
                {"id": "v1", "sections": [
                    {"id": "s1", "address": "0x0", "size": "0x1000", "name": "S1"}]},
                {"id": "v2", "sections": [
                    {"id": "s2", "address": "0x0", "size": "0x1000", "name": "S2"}]},
            ]
        }
        theme = Theme(None)
        area_views = []
        for cfg in diagram['views']:
            cfg = dict(cfg)
            cfg['pos'] = [50.0, 60.0]   # identical position — guaranteed overlap
            cfg['size'] = [230.0, 400.0]
            secs = copy.deepcopy(resolve_view_sections(cfg))
            av = AreaView(sections=Sections(sections=secs),
                          style=theme.resolve(cfg['id']),
                          area_config=cfg, theme=theme)
            area_views.append(av)

        issues = run_checks(diagram, area_views, ALL_RULES)
        overlaps = [i for i in issues if i.rule == 'panel-overlap']
        self.assertTrue(overlaps, "Expected panel-overlap issue")
        self.assertTrue(all(i.level == 'ERROR' for i in overlaps))


# ---------------------------------------------------------------------------
# Unit tests: uncovered-gap (chained breaks + partial break)
# ---------------------------------------------------------------------------

class TestUncoveredGap(unittest.TestCase):

    def _build_area_views(self, diagram):
        from theme import Theme
        from mmpviz import get_area_views
        theme = Theme(None)
        base_style = theme.resolve('')
        return get_area_views(base_style, diagram, theme)

    def test_chained_breaks_no_issue(self):
        """Three consecutive break sections that together cover the full gap
        must NOT produce an uncovered-gap warning."""
        from check import run_checks, ALL_RULES
        diagram = _chained_breaks_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        gaps = [i for i in issues if i.rule == 'uncovered-gap']
        self.assertEqual(gaps, [],
                         "Chained breaks that fully cover the gap should not "
                         "produce uncovered-gap issues")

    def test_partial_break_fires_warning(self):
        """A single break that covers only part of a large gap must still
        produce an uncovered-gap warning."""
        from check import run_checks, ALL_RULES
        diagram = _partial_break_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        gaps = [i for i in issues if i.rule == 'uncovered-gap']
        self.assertTrue(gaps, "Partial break coverage should still fire uncovered-gap")
        self.assertTrue(all(i.level == 'WARN' for i in gaps))
        # Message should mention partial coverage, not the old single-break phrasing.
        self.assertTrue(any('partially cover' in i.message for i in gaps))


# ---------------------------------------------------------------------------
# Unit tests: link-anchor-out-of-bounds
# ---------------------------------------------------------------------------

class TestLinkAnchorOutOfBounds(unittest.TestCase):

    def _build_area_views(self, diagram):
        from theme import Theme
        from mmpviz import get_area_views
        theme = Theme(None)
        base_style = theme.resolve('')
        return get_area_views(base_style, diagram, theme)

    def test_out_of_bounds_anchor_is_error(self):
        """A link whose from.sections address range extends outside the source
        view's address range must produce a link-anchor-out-of-bounds ERROR."""
        from check import run_checks, ALL_RULES
        diagram = _out_of_bounds_anchor_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        anchors = [i for i in issues if i.rule == 'link-anchor-out-of-bounds']
        self.assertTrue(anchors,
                        "Address range extending outside the view should trigger "
                        "link-anchor-out-of-bounds")
        self.assertTrue(all(i.level == 'ERROR' for i in anchors))

    def test_valid_link_no_anchor_issue(self):
        """A diagram with a normal full-view link must not produce any
        link-anchor-out-of-bounds issues."""
        from check import run_checks, ALL_RULES
        diagram = {
            "views": [
                {"id": "overview", "sections": [
                    {"id": "flash", "address": "0x08000000", "size": "0x20000",
                     "name": "Flash"}]},
                {"id": "detail", "sections": [
                    {"id": "code",  "address": "0x08000000", "size": "0x20000",
                     "name": "Code"}]},
            ],
            "links": [
                {"from": {"view": "overview"}, "to": {"view": "detail"}}
            ]
        }
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        anchors = [i for i in issues if i.rule == 'link-anchor-out-of-bounds']
        self.assertEqual(anchors, [],
                         "A valid full-view link should not trigger "
                         "link-anchor-out-of-bounds")


# ---------------------------------------------------------------------------
# Unit tests: format_diagram()
# ---------------------------------------------------------------------------

class TestFormatDiagram(unittest.TestCase):

    def test_round_trip(self):
        from fmt_diagram import format_diagram
        original = _clean_diagram()
        formatted_str = format_diagram(original)
        # The formatted output must be valid JSON that round-trips to the same data
        parsed = json.loads(formatted_str)
        self.assertEqual(parsed, original)

    def test_idempotent(self):
        from fmt_diagram import format_diagram
        original = _clean_diagram()
        first  = format_diagram(original)
        second = format_diagram(json.loads(first))
        self.assertEqual(first, second)


# ---------------------------------------------------------------------------
# CLI integration tests (subprocess)
# ---------------------------------------------------------------------------

class TestCLIPipeline(unittest.TestCase):
    """End-to-end tests via subprocess."""

    def _run(self, *args, input_data=None):
        """Run mmpviz.py with given args; return (returncode, stdout+stderr)."""
        cmd = [sys.executable, MMPVIZ] + list(args)
        result = subprocess.run(
            cmd, capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr

    def test_fmt_only_formats_file(self):
        """--fmt without -o: formats diagram.json in-place, exits 0."""
        with tempfile.TemporaryDirectory() as tmp:
            diag_path = os.path.join(tmp, 'diagram.json')
            with open(diag_path, 'w') as f:
                f.write(_unformatted_json(_clean_diagram()))

            rc, out = self._run('-d', diag_path, '--fmt')
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}. Output: {out}")
            self.assertIn('Formatted', out)

            # Verify file was rewritten as valid JSON
            with open(diag_path) as f:
                content = f.read()
            parsed = json.loads(content)
            self.assertEqual(parsed, _clean_diagram())

    def test_render_clean_diagram(self):
        """Clean diagram renders to SVG with exit 0."""
        with tempfile.TemporaryDirectory() as tmp:
            diag_path = os.path.join(tmp, 'diagram.json')
            svg_path  = os.path.join(tmp, 'out.svg')
            with open(diag_path, 'w') as f:
                json.dump(_clean_diagram(), f)

            rc, out = self._run('-d', diag_path, '-o', svg_path)
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}. Output: {out}")
            self.assertTrue(os.path.isfile(svg_path), "SVG file should have been written")
            with open(svg_path) as f:
                svg = f.read()
            self.assertIn('<svg', svg)

    def test_render_with_fmt(self):
        """--fmt + -o: formats file then renders SVG."""
        with tempfile.TemporaryDirectory() as tmp:
            diag_path = os.path.join(tmp, 'diagram.json')
            svg_path  = os.path.join(tmp, 'out.svg')
            with open(diag_path, 'w') as f:
                f.write(_unformatted_json(_clean_diagram()))

            rc, out = self._run('-d', diag_path, '-o', svg_path, '--fmt')
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}. Output: {out}")
            self.assertIn('Formatted', out)
            self.assertTrue(os.path.isfile(svg_path))

    def test_check_error_aborts_render(self):
        """unresolved-section (ERROR from run_checks) aborts before SVG is written.
        Uses a link referencing a non-existent section ID — this passes JSON Schema
        but is caught by run_checks() as an unresolved-section ERROR."""
        with tempfile.TemporaryDirectory() as tmp:
            diag_path = os.path.join(tmp, 'diagram.json')
            svg_path  = os.path.join(tmp, 'out.svg')
            with open(diag_path, 'w') as f:
                json.dump(_unresolved_link_diagram(), f)

            rc, out = self._run('-d', diag_path, '-o', svg_path)
            self.assertEqual(rc, 1, f"Expected exit 1, got {rc}. Output: {out}")
            self.assertFalse(os.path.isfile(svg_path),
                             "SVG must not be written when an ERROR is found")
            self.assertIn('ERROR', out)

    def test_check_warning_continues_render(self):
        """uncovered-gap (WARN) prints warning but still writes SVG."""
        with tempfile.TemporaryDirectory() as tmp:
            diag_path = os.path.join(tmp, 'diagram.json')
            svg_path  = os.path.join(tmp, 'out.svg')
            with open(diag_path, 'w') as f:
                json.dump(_uncovered_gap_diagram(), f)

            rc, out = self._run('-d', diag_path, '-o', svg_path)
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}. Output: {out}")
            self.assertTrue(os.path.isfile(svg_path),
                            "SVG must still be written when only WARNINGs exist")
            self.assertIn('WARNING', out)

    def test_no_output_no_fmt_errors(self):
        """Providing only -d with no -o and no --fmt should print an error."""
        with tempfile.TemporaryDirectory() as tmp:
            diag_path = os.path.join(tmp, 'diagram.json')
            with open(diag_path, 'w') as f:
                json.dump(_clean_diagram(), f)

            rc, out = self._run('-d', diag_path)
            self.assertNotEqual(rc, 0)
            self.assertIn('Error', out)


if __name__ == '__main__':
    unittest.main()
