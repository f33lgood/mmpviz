#!/usr/bin/env python3
"""
check.py — Post-generation rule checker for mmpviz diagrams.

Validates diagram.json + theme.json against layout and display rules without
producing SVG output.  Designed to catch issues that only become visible after
rendering, such as section text overflow, forced labels on sections that are too
small to show them, proportional-fallback violations, out-of-canvas panels, and
over-wide link bands.

Exit codes:
  0  — no issues found
  1  — one or more ERRORs (diagram is broken)
  2  — warnings only (diagram renders, but quality problems detected)

Usage:
  python3 scripts/check.py -d diagram.json -t theme.json
  python3 scripts/check.py -d diagram.json -t theme.json --format json
  python3 scripts/check.py -d diagram.json -t theme.json --rules text-overflow,band-too-wide
"""

import argparse
import copy
import json
import os
import sys

# Allow importing sibling modules when invoked as a script.
sys.path.insert(0, os.path.dirname(__file__))

from area_view import AreaView
from helpers import DefaultAppValues
from loader import load, parse_int
from sections import Sections
from theme import Theme

# Re-use the get_area_views helper from mmpviz without importing main().
from mmpviz import get_area_views, _auto_layout


# ---------------------------------------------------------------------------
# Issue dataclass
# ---------------------------------------------------------------------------

class Issue:
    """A single check finding."""

    def __init__(self, level: str, rule: str, area_id: str,
                 section_id: str | None, message: str):
        self.level = level          # 'ERROR' or 'WARN'
        self.rule = rule
        self.area_id = area_id
        self.section_id = section_id
        self.message = message

    def __str__(self) -> str:
        loc = f"{self.area_id}/{self.section_id}" if self.section_id else self.area_id
        return f"[{self.level}] {self.rule} in {loc}: {self.message}"

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "rule": self.rule,
            "area": self.area_id,
            "section": self.section_id,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Height computation helper
# ---------------------------------------------------------------------------

def _populate_section_heights(area_views: list) -> list:
    """
    Compute size_y / pos_y / size_x for every visible section in every subarea.

    Returns a flat list of (area_id, section, subarea) triples with those
    attributes set on the section object so that is_name_hidden() etc. work.
    """
    result = []
    for area in area_views:
        for sub in area.get_split_area_views():
            for section in sub.sections.get_sections():
                if section.is_hidden():
                    continue
                section.size_x = sub.size_x
                section.size_y = sub.to_pixels(section.size)
                section.pos_y = sub.to_pixels(
                    sub.end_address - section.size - section.address)
                section.pos_x = 0
                result.append((area.area_id, section, sub))
    return result


# ---------------------------------------------------------------------------
# Individual rule checkers
# ---------------------------------------------------------------------------

def _check_text_overflow(area_id: str, section, _sub) -> list[Issue]:
    """
    Name is visible but section height is smaller than the font size, so the
    label overflows the section box.

    Triggered when:
      - hide_name resolves to False (forced or auto-show), AND
      - size_y < font_size
    """
    if section.is_break():
        return []
    if section.is_name_hidden():
        return []
    font_size = section.style.get('font_size', 16)
    try:
        font_size = float(font_size)
    except (TypeError, ValueError):
        return []
    if section.size_y < font_size:
        return [Issue(
            'WARN', 'text-overflow', area_id, section.id,
            f"height {section.size_y:.1f} px < font_size {font_size:.0f} px "
            f"— name label will overflow the section box",
        )]
    return []


def _check_addr_auto_hidden(area_id: str, section, _sub) -> list[Issue]:
    """
    The name is forced visible (hide_name: false) but the address or end-address
    visibility is left on 'auto'.  Because size_y < 20 px, the auto-hide threshold
    suppresses the address labels even though a forced name implies the designer
    intended the section to be fully labelled.

    Suggests adding  hide_address: false  and/or  hide_end_address: false.
    """
    if section.is_break():
        return []
    AUTO_THRESHOLD = 20
    hide_name_val = str(section.style.get('hide_name', 'auto')).lower()
    if hide_name_val not in ('false', 'no'):
        return []
    if section.size_y >= AUTO_THRESHOLD:
        return []  # auto-hide won't trigger; no inconsistency

    issues = []
    hide_addr_val = str(section.style.get('hide_address', 'auto')).lower()
    if hide_addr_val == 'auto':
        issues.append(Issue(
            'WARN', 'addr-auto-hidden', area_id, section.id,
            f"hide_name=false but hide_address=auto and height {section.size_y:.1f} px < {AUTO_THRESHOLD} px "
            f"— start address will be suppressed; set hide_address: false to match",
        ))
    hide_end_val = str(section.style.get('hide_end_address', 'auto')).lower()
    if hide_end_val == 'auto':
        issues.append(Issue(
            'WARN', 'addr-auto-hidden', area_id, section.id,
            f"hide_name=false but hide_end_address=auto and height {section.size_y:.1f} px < {AUTO_THRESHOLD} px "
            f"— end address will be suppressed; set hide_end_address: false to match",
        ))
    return issues


def _check_min_height_violated(area_id: str, section, sub) -> list[Issue]:
    """
    Section height is below min_section_height.

    This indicates the proportional-fallback was triggered: the algorithm
    could not satisfy all minimum-height constraints simultaneously and fell
    back to pure proportional rendering, allowing sections to be shorter than
    the configured floor.
    """
    if section.is_break():
        return []
    min_h = sub.style.get('min_section_height')
    if min_h is None:
        return []
    try:
        min_h = float(min_h)
    except (TypeError, ValueError):
        return []
    if section.size_y < min_h - 1e-6:
        return [Issue(
            'WARN', 'min-height-violated', area_id, section.id,
            f"height {section.size_y:.1f} px < min_section_height {min_h:.0f} px "
            f"— proportional fallback likely triggered; increase panel height or "
            f"raise max_section_height in the area theme",
        )]
    return []


def _check_out_of_canvas(area_views: list, canvas_w: float, canvas_h: float) -> list[Issue]:
    """Panel (pos + size) extends beyond the canvas boundary."""
    issues = []
    for area in area_views:
        right = area.pos_x + area.size_x
        bottom = area.pos_y + area.size_y
        if right > canvas_w:
            issues.append(Issue(
                'ERROR', 'out-of-canvas', area.area_id, None,
                f"right edge {right:.0f} px exceeds canvas width {canvas_w:.0f} px",
            ))
        if bottom > canvas_h:
            issues.append(Issue(
                'ERROR', 'out-of-canvas', area.area_id, None,
                f"bottom edge {bottom:.0f} px exceeds canvas height {canvas_h:.0f} px",
            ))
    return issues


def _check_band_too_wide(area_views: list, raw_sections: list,
                         links_config: dict) -> list[Issue]:
    """
    Horizontal span of a link band exceeds the readability guideline.

    Guidelines (from references/layout-guide.md):
      - ≤ 200 px  for the band connecting to the nearest detail panel
      - ≤ 600 px  for secondary bands; beyond this, use opacity ≤ 0.4
    """
    if not area_views:
        return []

    source = area_views[0]
    source_right = source.pos_x + source.size_x

    # Build section-id → (start, end) map from raw sections
    sec_map = {s.id: (s.address, s.address + s.size) for s in raw_sections}

    linked = links_config.get('sections', [])
    issues = []
    for entry in linked:
        section_id = entry if isinstance(entry, str) else entry[0]
        if section_id not in sec_map:
            continue  # reported separately by _check_unresolved_link_sections

        start_addr, end_addr = sec_map[section_id]
        for area in area_views[1:]:
            lo = area.sections.lowest_memory
            hi = area.sections.highest_memory
            if start_addr >= lo and end_addr <= hi:
                span = area.pos_x - source_right
                if span > 600:
                    issues.append(Issue(
                        'WARN', 'band-too-wide', area.area_id, section_id,
                        f"link band span {span:.0f} px > 600 px guideline "
                        f"— consider increasing link opacity to 0.3–0.4",
                    ))
                elif span > 200:
                    # Only warn for nearest-column violations (first non-source area)
                    if area is area_views[1]:
                        issues.append(Issue(
                            'WARN', 'band-too-wide', area.area_id, section_id,
                            f"nearest-column link band span {span:.0f} px > 200 px "
                            f"— ideal is ≤ 200 px for the closest panel",
                        ))
                break

    return issues


# ---------------------------------------------------------------------------
# Panel-layout geometry constants
# ---------------------------------------------------------------------------

# Title text is rendered at (size_x/2, -20) relative to (pos_x, pos_y) in
# renderer.py _make_title.  Allow this much clearance above the panel top.
_TITLE_CLEARANCE_PX = 25

# Address labels ("0x00000000") are placed at panel_right + label_offset
# (section.py label_offset = 10) with anchor 'start'.
# Width estimate: 10 chars × font_size × Helvetica width ratio 0.6.
_ADDR_LABEL_H_OFFSET = 10     # section.py label_offset
_ADDR_LABEL_CHARS    = 10     # len("0x00000000")
_HELVETICA_W_RATIO   = 0.6    # character width / font-size for Helvetica


def _addr_label_width(font_size: float) -> float:
    return _ADDR_LABEL_CHARS * font_size * _HELVETICA_W_RATIO


# ---------------------------------------------------------------------------
# Panel-layout rule checkers
# ---------------------------------------------------------------------------

def _check_panel_overlap(area_views: list) -> list[Issue]:
    """
    Two panels' bounding rectangles physically intersect.

    Overlapping panel bodies guarantee that sections, borders, and labels
    from one panel will bleed into the other.  All panel pairs are checked.
    """
    issues = []
    for i, a in enumerate(area_views):
        for b in area_views[i + 1:]:
            h = a.pos_x < b.pos_x + b.size_x and a.pos_x + a.size_x > b.pos_x
            v = a.pos_y < b.pos_y + b.size_y and a.pos_y + a.size_y > b.pos_y
            if h and v:
                issues.append(Issue(
                    'ERROR', 'panel-overlap', a.area_id, None,
                    f"panel [{a.pos_x},{a.pos_y} {a.size_x}×{a.size_y}] physically overlaps "
                    f"'{b.area_id}' [{b.pos_x},{b.pos_y} {b.size_x}×{b.size_y}]"
                    f" — adjust pos or size in diagram.json",
                ))
    return issues


def _check_title_overlap(area_views: list) -> list[Issue]:
    """
    A panel's title intrudes into the body of the panel directly above it.

    Titles are rendered _TITLE_CLEARANCE_PX above the panel's top edge.
    When the gap between two vertically adjacent, horizontally overlapping
    panels is smaller than _TITLE_CLEARANCE_PX, the lower panel's title
    overlaps the upper panel's body.
    """
    issues = []
    for a in area_views:
        a_title_top = a.pos_y - _TITLE_CLEARANCE_PX
        for b in area_views:
            if b is a:
                continue
            b_bottom = b.pos_y + b.size_y
            # b must be directly above a: its bottom falls inside a's title zone
            if not (a_title_top < b_bottom <= a.pos_y):
                continue
            # Must share horizontal extent
            if a.pos_x >= b.pos_x + b.size_x or a.pos_x + a.size_x <= b.pos_x:
                continue
            overlap = b_bottom - a_title_top
            issues.append(Issue(
                'WARN', 'title-overlap', a.area_id, None,
                f"title of '{a.area_id}' (needs y≥{a_title_top:.0f}) overlaps bottom of "
                f"'{b.area_id}' (y={b_bottom:.0f}) by {overlap:.0f} px "
                f"— increase vertical gap to at least {_TITLE_CLEARANCE_PX} px",
            ))
    return issues


def _check_label_overlap(area_views: list) -> list[Issue]:
    """
    Estimated address-label right extent of one panel overlaps the left edge
    of the panel to its right.

    Address labels are drawn starting at panel_right + _ADDR_LABEL_H_OFFSET
    with text-anchor 'start'.  Width is estimated from font_size and character
    count.  Only checked when the two panels share a vertical range so that
    a label at that height could actually reach the neighbouring panel.
    """
    issues = []
    for a in area_views:
        font_size   = float(a.style.get('font_size', 12))
        label_w     = _addr_label_width(font_size)
        a_right     = a.pos_x + a.size_x
        a_label_ext = a_right + _ADDR_LABEL_H_OFFSET + label_w

        for b in area_views:
            if b is a or b.pos_x <= a_right:
                continue
            # Vertical overlap — label only matters where the panels coexist
            if a.pos_y >= b.pos_y + b.size_y or a.pos_y + a.size_y <= b.pos_y:
                continue
            if a_label_ext > b.pos_x:
                gap    = b.pos_x - a_right
                needed = int(_ADDR_LABEL_H_OFFSET + label_w)
                issues.append(Issue(
                    'WARN', 'label-overlap', a.area_id, None,
                    f"address labels of '{a.area_id}' extend to ~{a_label_ext:.0f} px but "
                    f"'{b.area_id}' starts at {b.pos_x} px "
                    f"(gap {gap:.0f} px < {needed} px needed at font_size={font_size:.0f})"
                    f" — widen horizontal gap or move panels apart",
                ))
    return issues


def _check_unresolved_link_sections(area_views: list, raw_sections: list,
                                    links_config: dict) -> list[Issue]:
    """Section listed in links.sections does not appear in any area's filtered sections."""
    # Collect all section IDs that appear in any area after filtering/flag application
    area_section_ids = set()
    for area in area_views:
        for sub in area.get_split_area_views():
            for s in sub.sections.get_sections():
                area_section_ids.add(s.id)

    linked = links_config.get('sections', [])
    issues = []
    for entry in linked:
        section_id = entry if isinstance(entry, str) else entry[0]
        if section_id not in area_section_ids:
            issues.append(Issue(
                'ERROR', 'unresolved-section', 'links', section_id,
                f"'{section_id}' not found in any area after filtering",
            ))
    return issues


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_RULES = {
    'text-overflow',
    'addr-auto-hidden',
    'min-height-violated',
    'out-of-canvas',
    'band-too-wide',
    'unresolved-section',
    'panel-overlap',
    'title-overlap',
    'label-overlap',
}

PER_SECTION_RULES = [
    _check_text_overflow,
    _check_addr_auto_hidden,
    _check_min_height_violated,
]


def run_checks(diagram: dict, raw_sections: list, area_views: list,
               enabled_rules: set) -> list[Issue]:
    canvas = diagram.get('size', list(DefaultAppValues.DOCUMENT_SIZE))
    canvas_w, canvas_h = float(canvas[0]), float(canvas[1])
    links_config = diagram.get('links', {})

    issues = []

    # Per-section rules (run all; filter by enabled_rules at the end)
    section_data = _populate_section_heights(area_views)
    for area_id, section, sub in section_data:
        for rule_fn in PER_SECTION_RULES:
            issues.extend(rule_fn(area_id, section, sub))

    # Area-level rules
    issues.extend(_check_out_of_canvas(area_views, canvas_w, canvas_h))
    issues.extend(_check_panel_overlap(area_views))
    issues.extend(_check_title_overlap(area_views))
    issues.extend(_check_label_overlap(area_views))

    # Link rules
    issues.extend(_check_band_too_wide(area_views, raw_sections, links_config))
    issues.extend(_check_unresolved_link_sections(area_views, raw_sections, links_config))

    # Filter to only enabled rules
    return [i for i in issues if i.rule in enabled_rules]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description='Check a mmpviz diagram.json for layout and display rule violations.')
    parser.add_argument('--diagram', '-d', required=True,
                        help='Path to diagram.json')
    parser.add_argument('--theme', '-t', default=None,
                        help='Path to theme.json (uses built-in defaults if omitted)')
    parser.add_argument('--format', choices=['text', 'json'], default='text',
                        help='Output format (default: text)')
    parser.add_argument('--rules', default=None,
                        help=f'Comma-separated list of rules to run '
                             f'(default: all). Available: {", ".join(sorted(ALL_RULES))}')
    return parser.parse_args()


def main():
    args = parse_args()

    enabled_rules = ALL_RULES
    if args.rules:
        requested = {r.strip() for r in args.rules.split(',')}
        unknown = requested - ALL_RULES
        if unknown:
            print(f"Unknown rules: {', '.join(sorted(unknown))}", file=sys.stderr)
            print(f"Available: {', '.join(sorted(ALL_RULES))}", file=sys.stderr)
            sys.exit(1)
        enabled_rules = requested

    try:
        raw_sections, diagram = load(args.diagram)
    except (ValueError, OSError) as e:
        print(f"Error loading diagram: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        theme = Theme(args.theme)
    except (OSError, Exception) as e:
        print(f"Error loading theme: {e}", file=sys.stderr)
        sys.exit(1)

    base_style = theme.resolve('')
    area_views = get_area_views(raw_sections, base_style, diagram, theme)
    if not area_views:
        print("Error: no area views could be created.", file=sys.stderr)
        sys.exit(1)

    issues = run_checks(diagram, raw_sections, area_views, enabled_rules)

    if args.format == 'json':
        print(json.dumps([i.to_dict() for i in issues], indent=2))
    else:
        if not issues:
            print("OK — no issues found")
        else:
            for issue in issues:
                print(issue)

    has_errors = any(i.level == 'ERROR' for i in issues)
    has_warnings = any(i.level == 'WARN' for i in issues)

    if has_errors:
        sys.exit(1)
    elif has_warnings:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
