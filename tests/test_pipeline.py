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
            {"id": "bad-ref",
             "from": {"view": "overview", "sections": ["typo-section-id"]},
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


def _break_overlap_diagram():
    """A break whose size extends into the next visible section's range — the
    visible section will be silently swallowed → break-overlaps-section ERROR."""
    return {
        "views": [{
            "id": "test-view",
            "sections": [
                {"id": "a",   "address": "0x00000000", "size": "0x00001000", "name": "A"},
                # Break should end at 0x2000 but is sized to end at 0x3000,
                # covering 0x1000 into the next visible section B's range.
                {"id": "brk", "address": "0x00001000", "size": "0x00002000",
                 "name": "···", "flags": ["break"]},
                {"id": "b",   "address": "0x00002000", "size": "0x00001000", "name": "B"},
            ]
        }]
    }


def _visible_overlap_diagram():
    """Two visible sections (e.g. parent block + its child) with overlapping
    address ranges — classic layer-confusion case → section-overlap WARN."""
    return {
        "views": [{
            "id": "test-view",
            "sections": [
                {"id": "apb1",  "address": "0x40000000", "size": "0x10000", "name": "APB1"},
                {"id": "uart0", "address": "0x40000000", "size": "0x00400", "name": "UART0"},
            ]
        }]
    }


def _breaks_only_overlap_diagram():
    """Two break sections that genuinely overlap (a wider reserved range plus an
    inner sub-range flagged as break).  Break-vs-break is an allowed pattern
    used by chained-gap-coverage — no issue should fire."""
    return {
        "views": [{
            "id": "test-view",
            "sections": [
                {"id": "a",    "address": "0x0",     "size": "0x1000", "name": "A"},
                {"id": "outer", "address": "0x1000", "size": "0x4000",
                 "name": "Reserved", "flags": ["break"]},
                {"id": "inner", "address": "0x2000", "size": "0x1000",
                 "name": "···", "flags": ["break"]},
                {"id": "b",    "address": "0x5000", "size": "0x1000", "name": "B"},
            ]
        }]
    }


def _link_address_range_mappable_diagram():
    """A link whose to.sections uses the address-range form but the range
    exactly matches a defined section in the destination view — the author
    should use the section ID instead → link-address-range-mappable WARN."""
    return {
        "views": [
            {"id": "overview", "sections": [
                {"id": "flash", "address": "0x08000000", "size": "0x20000", "name": "Flash"}]},
            {"id": "detail",  "sections": [
                {"id": "code",  "address": "0x08000000", "size": "0x10000", "name": "Code"},
                {"id": "data",  "address": "0x08010000", "size": "0x10000", "name": "Data"}]},
        ],
        "links": [
            {"id": "ovl-detail",
             "from": {"view": "overview", "sections": ["flash"]},
             "to":   {"view": "detail",   "sections": ["0x08000000", "0x08010000"]}}
        ]
    }


def _link_redundant_sections_diagram():
    """A link whose to.sections lists every section of the destination view —
    equivalent to omitting the field → link-redundant-sections WARN."""
    return {
        "views": [
            {"id": "overview", "sections": [
                {"id": "flash", "address": "0x08000000", "size": "0x20000", "name": "Flash"}]},
            {"id": "detail",  "sections": [
                {"id": "code",  "address": "0x08000000", "size": "0x10000", "name": "Code"},
                {"id": "data",  "address": "0x08010000", "size": "0x10000", "name": "Data"}]},
        ],
        "links": [
            {"id": "ovl-detail",
             "from": {"view": "overview", "sections": ["flash"]},
             "to":   {"view": "detail",   "sections": ["code", "data"]}}
        ]
    }


def _link_clean_diagram():
    """A well-formed link that pins from.sections to a proper subset of the
    source view and omits to.sections — no link-form warnings expected."""
    return {
        "views": [
            {"id": "overview", "sections": [
                {"id": "flash", "address": "0x08000000", "size": "0x20000", "name": "Flash"},
                {"id": "sram",  "address": "0x20000000", "size": "0x10000", "name": "SRAM"}]},
            {"id": "detail",  "sections": [
                {"id": "code",  "address": "0x08000000", "size": "0x10000", "name": "Code"},
                {"id": "data",  "address": "0x08010000", "size": "0x10000", "name": "Data"}]},
        ],
        "links": [
            {"id": "ovl-detail",
             "from": {"view": "overview", "sections": ["flash"]},
             "to":   {"view": "detail"}}
        ]
    }


def _link_cross_address_space_diagram():
    """A cross-address-space link where 'to.sections' spans the destination
    view but the source address range lies entirely outside it. Omitting
    'to.sections' would cause the renderer to clamp from_range to the
    destination view, yielding an out-of-bounds anchor — so the spec is
    NOT redundant and link-redundant-sections must NOT fire."""
    return {
        "views": [
            {"id": "gio1", "sections": [
                {"id": "gio1_a", "address": "0x1000000000",
                 "size": "0x800000", "name": "GIO1-A"},
                {"id": "gio1_b", "address": "0x1000800000",
                 "size": "0x800000", "name": "GIO1-B"}]},
            {"id": "fabric", "sections": [
                {"id": "fab_lo", "address": "0x0",
                 "size": "0x8000", "name": "FabricLo"},
                {"id": "fab_hi", "address": "0x8000",
                 "size": "0x8000", "name": "FabricHi"}]},
        ],
        "links": [
            {"id": "gio1-to-fabric",
             "from": {"view": "gio1",   "sections": ["gio1_a"]},
             "to":   {"view": "fabric", "sections": ["fab_lo", "fab_hi"]}}
        ]
    }


def _link_addr_range_not_mappable_diagram():
    """A link whose to.sections address range does not align with any defined
    section boundaries (e.g. virtual→physical mapping).  Legitimate use of
    the address-range form — no link-form warning should fire."""
    return {
        "views": [
            {"id": "overview", "sections": [
                {"id": "flash", "address": "0x08000000", "size": "0x20000", "name": "Flash"}]},
            {"id": "detail",  "sections": [
                {"id": "code",  "address": "0x08000000", "size": "0x10000", "name": "Code"},
                {"id": "data",  "address": "0x08010000", "size": "0x10000", "name": "Data"}]},
        ],
        "links": [
            {"id": "ovl-detail",
             "from": {"view": "overview", "sections": ["flash"]},
             "to":   {"view": "detail",
                      "sections": ["0x08004000", "0x0800C000"]}}  # spans neither Code nor Data cleanly
        ]
    }


def _label_out_of_range_diagram():
    """A label whose address (0x00000000) falls below the view's start
    address (0x08000000) — the label will never be rendered → WARN."""
    return {
        "views": [{
            "id": "test-view",
            "sections": [
                {"id": "flash", "address": "0x08000000", "size": "0x20000", "name": "Flash"}
            ],
            "labels": [
                {"id": "stale", "address": "0x00000000", "text": "Stale",
                 "length": 30, "side": "right"}
            ]
        }]
    }


def _link_inverted_range_diagram():
    """A link whose from.sections address range has lo > hi (inverted) →
    link-address-range-order ERROR."""
    return {
        "views": [
            {"id": "overview", "sections": [
                {"id": "flash", "address": "0x08000000", "size": "0x20000",
                 "name": "Flash"}]},
            {"id": "detail", "sections": [
                {"id": "code", "address": "0x08000000", "size": "0x20000",
                 "name": "Code"}]},
        ],
        "links": [
            {"id": "bad-range",
             "from": {"view": "overview",
                      "sections": ["0x08020000", "0x08000000"]},  # inverted: lo > hi
             "to": {"view": "detail"}}
        ]
    }


def _link_self_diagram():
    """A link whose from.view and to.view are the same view →
    link-self-referential WARN."""
    return {
        "views": [
            {"id": "overview", "sections": [
                {"id": "flash", "address": "0x08000000", "size": "0x20000",
                 "name": "Flash"}]},
        ],
        "links": [
            {"id": "self-link",
             "from": {"view": "overview"},
             "to":   {"view": "overview"}}
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
        area_views, _ = get_area_views(base_style, diagram, theme)
        return area_views

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

    def test_break_overlaps_section_is_error(self):
        """A break whose range overlaps a visible section fires
        break-overlaps-section ERROR (the visible section would be
        silently swallowed by the layout engine)."""
        from check import run_checks, ALL_RULES
        diagram = _break_overlap_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        hits = [i for i in issues if i.rule == 'break-overlaps-section']
        self.assertTrue(hits, "Expected break-overlaps-section issue")
        self.assertTrue(all(i.level == 'ERROR' for i in hits))
        # The message must carry the corrected break size so the fix is mechanical.
        self.assertIn('0x1000', str(hits[0]))

    def test_section_overlap_visible_is_warn(self):
        """Two visible sections with overlapping ranges still fire
        section-overlap WARN after the overlap-check consolidation."""
        from check import run_checks, ALL_RULES
        diagram = _visible_overlap_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        hits = [i for i in issues if i.rule == 'section-overlap']
        self.assertTrue(hits, "Expected section-overlap issue")
        self.assertTrue(all(i.level == 'WARN' for i in hits))
        # break-overlaps-section must NOT fire for visible-vs-visible.
        self.assertFalse(
            [i for i in issues if i.rule == 'break-overlaps-section'],
            "visible-vs-visible must not emit break-overlaps-section",
        )

    def test_break_vs_break_overlap_is_warn(self):
        """Break-vs-break overlap is now flagged as section-overlap WARN
        (overlapping breaks are redundant).  break-overlaps-section must
        NOT fire — that rule is reserved for break eating a visible section."""
        from check import run_checks, ALL_RULES
        diagram = _breaks_only_overlap_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        overlap_hits = [i for i in issues if i.rule == 'section-overlap']
        self.assertTrue(
            overlap_hits,
            "Break-vs-break overlap must fire section-overlap WARN",
        )
        self.assertTrue(all(i.level == 'WARN' for i in overlap_hits))
        # break-overlaps-section must NOT fire for break-vs-break.
        self.assertFalse(
            [i for i in issues if i.rule == 'break-overlaps-section'],
            "Break-vs-break must not emit break-overlaps-section",
        )

    def test_link_address_range_mappable_is_warn(self):
        """An address-range link that resolves exactly to defined section(s)
        should warn so the author can switch to section IDs."""
        from check import run_checks, ALL_RULES
        diagram = _link_address_range_mappable_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        hits = [i for i in issues if i.rule == 'link-address-range-mappable']
        self.assertTrue(hits, "Expected link-address-range-mappable issue")
        self.assertTrue(all(i.level == 'WARN' for i in hits))

    def test_link_redundant_sections_is_warn_id_list(self):
        """A sections list enumerating every section of the destination view
        is equivalent to omitting the field → link-redundant-sections WARN."""
        from check import run_checks, ALL_RULES
        diagram = _link_redundant_sections_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        hits = [i for i in issues if i.rule == 'link-redundant-sections']
        self.assertTrue(hits, "Expected link-redundant-sections issue")
        self.assertTrue(all(i.level == 'WARN' for i in hits))

    def test_link_clean_form_no_link_warnings(self):
        """A link with a single source section ID and omitted to.sections
        should produce no link-form warnings."""
        from check import run_checks, ALL_RULES
        diagram = _link_clean_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        self.assertFalse(
            [i for i in issues
             if i.rule in ('link-address-range-mappable', 'link-redundant-sections')],
            "Clean link must not fire link-form warnings",
        )

    def test_link_redundant_sections_skips_cross_address_space(self):
        """When 'from' and 'to' live in different address spaces, omitting
        'to.sections' makes the renderer clamp from_range into the
        destination view — NOT the whole-view default. The spec is load-
        bearing, so link-redundant-sections must not fire."""
        from check import run_checks, ALL_RULES
        diagram = _link_cross_address_space_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        self.assertFalse(
            [i for i in issues if i.rule == 'link-redundant-sections'],
            "Cross-address-space link spec is load-bearing, not redundant",
        )

    def test_link_address_range_legitimate_no_warning(self):
        """An address-range link that doesn't align with any defined section
        (e.g. virtual→physical mapping) must not fire
        link-address-range-mappable."""
        from check import run_checks, ALL_RULES
        diagram = _link_addr_range_not_mappable_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        self.assertFalse(
            [i for i in issues if i.rule == 'link-address-range-mappable'],
            "Address-range that doesn't map to section(s) must not warn",
        )

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

    def test_label_out_of_range_is_warn(self):
        """A label whose address is outside the view's [Lo, Hi] range must
        fire label-out-of-range WARN."""
        from check import run_checks, ALL_RULES
        diagram = _label_out_of_range_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        hits = [i for i in issues if i.rule == 'label-out-of-range']
        self.assertTrue(hits, "Expected label-out-of-range issue")
        self.assertTrue(all(i.level == 'WARN' for i in hits))

    def test_link_address_range_order_is_error(self):
        """A link address range with lo > hi must fire link-address-range-order
        ERROR."""
        from check import run_checks, ALL_RULES
        diagram = _link_inverted_range_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        hits = [i for i in issues if i.rule == 'link-address-range-order']
        self.assertTrue(hits, "Expected link-address-range-order issue")
        self.assertTrue(all(i.level == 'ERROR' for i in hits))

    def test_link_self_referential_is_warn(self):
        """A link whose from.view == to.view must fire link-self-referential
        WARN."""
        from check import run_checks, ALL_RULES
        diagram = _link_self_diagram()
        area_views = self._build_area_views(diagram)
        issues = run_checks(diagram, area_views, ALL_RULES)
        hits = [i for i in issues if i.rule == 'link-self-referential']
        self.assertTrue(hits, "Expected link-self-referential issue")
        self.assertTrue(all(i.level == 'WARN' for i in hits))


# ---------------------------------------------------------------------------
# Unit tests: uncovered-gap (chained breaks + partial break)
# ---------------------------------------------------------------------------

class TestUncoveredGap(unittest.TestCase):

    def _build_area_views(self, diagram):
        from theme import Theme
        from mmpviz import get_area_views
        theme = Theme(None)
        base_style = theme.resolve('')
        area_views, _ = get_area_views(base_style, diagram, theme)
        return area_views

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
        # Message must mention the uncovered address range.
        self.assertTrue(any('has no section defined' in i.message for i in gaps))


# ---------------------------------------------------------------------------
# Unit tests: link-anchor-out-of-bounds
# ---------------------------------------------------------------------------

class TestLinkAnchorOutOfBounds(unittest.TestCase):

    def _build_area_views(self, diagram):
        from theme import Theme
        from mmpviz import get_area_views
        theme = Theme(None)
        base_style = theme.resolve('')
        area_views, _ = get_area_views(base_style, diagram, theme)
        return area_views

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


# ---------------------------------------------------------------------------
# Unit tests: min-height-below-global and min-height-violated label floor
# ---------------------------------------------------------------------------

class TestMinHeightChecks(unittest.TestCase):
    """Tests for _check_min_height_below_global and the label-floor extension
    of _check_min_height_violated."""

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
        from check import (
            _check_min_height_below_global,
            _check_min_height_violated,
            run_checks,
            ALL_RULES,
        )
        from section import Section
        self._check_min_height_below_global = _check_min_height_below_global
        self._check_min_height_violated = _check_min_height_violated
        self.run_checks = run_checks
        self.ALL_RULES = ALL_RULES
        self.Section = Section

    # -- helpers --

    def _make_sub(self, font_size=12, min_section_height=None, size_x=200.0):
        """Minimal sub-area stub with only the attributes the check functions use."""
        import types
        sub = types.SimpleNamespace()
        style = {'font_size': font_size}
        if min_section_height is not None:
            style['min_section_height'] = min_section_height
        sub.style = style
        sub.size_x = size_x
        return sub

    def _make_section(self, min_height=None, name='s', size=0x1000, address=0x0):
        s = self.Section(size=size, address=address, id=name, name=name,
                         min_height=min_height)
        s.size_y = 0  # will be overridden per test
        return s

    # -- min-height-below-global --

    def test_min_height_below_global_fires(self):
        sub = self._make_sub(min_section_height=40)
        sec = self._make_section(min_height=10)
        issues = self._check_min_height_below_global('v', sec, sub)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule, 'min-height-below-global')
        self.assertEqual(issues[0].level, 'WARN')

    def test_min_height_below_global_no_fire_when_equal(self):
        sub = self._make_sub(min_section_height=40)
        sec = self._make_section(min_height=40)
        issues = self._check_min_height_below_global('v', sec, sub)
        self.assertEqual(issues, [])

    def test_min_height_below_global_no_fire_when_above(self):
        sub = self._make_sub(min_section_height=40)
        sec = self._make_section(min_height=60)
        issues = self._check_min_height_below_global('v', sec, sub)
        self.assertEqual(issues, [])

    def test_min_height_below_global_no_fire_when_no_per_section(self):
        sub = self._make_sub(min_section_height=40)
        sec = self._make_section(min_height=None)
        issues = self._check_min_height_below_global('v', sec, sub)
        self.assertEqual(issues, [])

    def test_min_height_below_global_no_fire_when_no_global(self):
        sub = self._make_sub(min_section_height=None)
        sec = self._make_section(min_height=10)
        issues = self._check_min_height_below_global('v', sec, sub)
        self.assertEqual(issues, [])

    def test_min_height_below_global_skips_break(self):
        from section import Section
        brk = Section(size=0x100, address=0x0, id='brk', flags=['break'],
                      min_height=5)
        sub = self._make_sub(min_section_height=40)
        issues = self._check_min_height_below_global('v', brk, sub)
        self.assertEqual(issues, [])

    def test_min_height_below_global_in_all_rules(self):
        self.assertIn('min-height-below-global', self.ALL_RULES)

    # -- min-height-violated: label-floor included --

    def test_min_height_violated_fires_on_label_floor(self):
        """Section height below 30+font_size triggers violation even when
        no global or per-section min_height is configured."""
        # font_size=12 → label floor = 42 px when labels conflict.
        # Use a wide name on a narrow panel so labels conflict.
        # size_x=200, name='long_section_name_here' (22 chars):
        #   size_label_right = 2 + 5*0.6*12 = 38
        #   name_left = 100 - 22*0.6*12/2 = 100 - 79.2 = 20.8 → conflict → floor=42
        sub = self._make_sub(font_size=12, min_section_height=None, size_x=200.0)
        sec = self._make_section(min_height=None, name='long_section_name_here',
                                 size=0x1000)
        sec.size_y = 30.0  # below label floor of 42 px
        issues = self._check_min_height_violated('v', sec, sub)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule, 'min-height-violated')

    def test_min_height_violated_no_fire_above_label_floor(self):
        """Section height above the label floor must not fire the check."""
        sub = self._make_sub(font_size=12, min_section_height=None, size_x=200.0)
        sec = self._make_section(min_height=None, name='long_section_name_here',
                                 size=0x1000)
        sec.size_y = 50.0  # above label floor of 42 px
        issues = self._check_min_height_violated('v', sec, sub)
        self.assertEqual(issues, [])

    def test_min_height_violated_no_fire_when_no_conflict(self):
        """Short name with no label conflict and no configured floor must not fire."""
        sub = self._make_sub(font_size=12, min_section_height=None, size_x=200.0)
        sec = self._make_section(min_height=None, name='Hi', size=0x1000)
        sec.size_y = 5.0
        issues = self._check_min_height_violated('v', sec, sub)
        self.assertEqual(issues, [])

    # -- min-height-on-break --

    def test_min_height_on_break_fires(self):
        from check import _check_min_height_on_break
        sub = self._make_sub(font_size=12)
        sub.style['break_height'] = 20
        brk = self.Section(size=0x100, address=0x0, id='gap', flags=['break'],
                           min_height=40)
        issues = _check_min_height_on_break('v', brk, sub)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule, 'min-height-on-break')
        self.assertEqual(issues[0].level, 'WARN')

    def test_min_height_on_break_no_fire_without_min_height(self):
        from check import _check_min_height_on_break
        sub = self._make_sub()
        brk = self.Section(size=0x100, address=0x0, id='gap', flags=['break'])
        issues = _check_min_height_on_break('v', brk, sub)
        self.assertEqual(issues, [])

    def test_min_height_on_break_no_fire_for_non_break(self):
        from check import _check_min_height_on_break
        sub = self._make_sub()
        sec = self._make_section(min_height=40)
        issues = _check_min_height_on_break('v', sec, sub)
        self.assertEqual(issues, [])

    def test_min_height_on_break_message_includes_break_height(self):
        from check import _check_min_height_on_break
        sub = self._make_sub()
        sub.style['break_height'] = 20
        brk = self.Section(size=0x100, address=0x0, id='gap', flags=['break'],
                           min_height=50)
        issues = _check_min_height_on_break('v', brk, sub)
        self.assertIn('break_height=20', issues[0].message)

    def test_min_height_on_break_in_all_rules(self):
        self.assertIn('min-height-on-break', self.ALL_RULES)

    def test_min_height_violated_message_includes_label_floor(self):
        """Issue message reports the label floor so the user knows why it fired."""
        sub = self._make_sub(font_size=12, min_section_height=None, size_x=200.0)
        sec = self._make_section(min_height=None, name='long_section_name_here',
                                 size=0x1000)
        sec.size_y = 10.0
        issues = self._check_min_height_violated('v', sec, sub)
        self.assertTrue(issues)
        self.assertIn('label floor', issues[0].message)


# ---------------------------------------------------------------------------
# Unit tests: section-name-overflow
# ---------------------------------------------------------------------------

class TestSectionNameOverflow(unittest.TestCase):
    """Tests for _check_section_name_overflow."""

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
        from check import _check_section_name_overflow, ALL_RULES
        from section import Section
        self._check = _check_section_name_overflow
        self.ALL_RULES = ALL_RULES
        self.Section = Section

    def _make_sub(self, font_size=12, size_x=230.0):
        import types
        sub = types.SimpleNamespace()
        sub.style = {'font_size': font_size}
        sub.size_x = size_x
        return sub

    def _make_section(self, name, size=0x1000, address=0x0, flags=None):
        s = self.Section(size=size, address=address, id=name, name=name,
                         flags=flags or [])
        s.size_y = 42
        return s

    def test_fires_when_name_too_wide(self):
        # 40 chars × 0.6 × 12 = 288 px > 230 - 8 = 222 px
        sub = self._make_sub(font_size=12, size_x=230.0)
        sec = self._make_section('a' * 40)
        issues = self._check('v', sec, sub)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule, 'section-name-overflow')
        self.assertEqual(issues[0].level, 'WARN')

    def test_no_fire_when_name_fits(self):
        # 10 chars × 0.6 × 12 = 72 px < 222 px
        sub = self._make_sub(font_size=12, size_x=230.0)
        sec = self._make_section('Short Name')
        issues = self._check('v', sec, sub)
        self.assertEqual(issues, [])

    def test_no_fire_at_exact_limit(self):
        # max_width = 230 - 8 = 222; chars = floor(222 / (0.6*12)) = floor(30.8) = 30
        # 30 chars × 7.2 = 216 px ≤ 222 px
        sub = self._make_sub(font_size=12, size_x=230.0)
        sec = self._make_section('a' * 30)
        issues = self._check('v', sec, sub)
        self.assertEqual(issues, [])

    def test_skips_break_section(self):
        sub = self._make_sub(font_size=12, size_x=230.0)
        brk = self._make_section('a' * 40, flags=['break'])
        issues = self._check('v', brk, sub)
        self.assertEqual(issues, [])

    def test_uses_font_size_from_style(self):
        # font_size=20: max_width=222 px; overflow at ceil(222/(0.6*20))+1 = 19 chars
        # 19 chars × 0.6 × 20 = 228 px > 222 px → fires
        sub = self._make_sub(font_size=20, size_x=230.0)
        sec = self._make_section('a' * 19)
        issues = self._check('v', sec, sub)
        self.assertEqual(len(issues), 1)

    def test_message_includes_char_count_and_panel_width(self):
        sub = self._make_sub(font_size=12, size_x=230.0)
        sec = self._make_section('a' * 40)
        issues = self._check('v', sec, sub)
        self.assertIn('40 chars', issues[0].message)
        self.assertIn('230', issues[0].message)

    def test_in_all_rules(self):
        self.assertIn('section-name-overflow', self.ALL_RULES)


if __name__ == '__main__':
    unittest.main()
