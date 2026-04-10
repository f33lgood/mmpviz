#!/usr/bin/env python3
"""
check.py — Post-generation rule checker for mmpviz diagrams.

Validates diagram.json + theme.json against layout rules without producing SVG
output.  Catches issues that only become visible after rendering: proportional-
fallback violations, out-of-canvas panels, panel or label collisions, and
over-wide link bands.

Note: name/size label geometry issues (text overflow, size-name overlap) are
handled automatically by the renderer and are not reported here.

Exit codes:
  0  — no issues found
  1  — one or more issues detected

Usage:
  python3 scripts/check.py -d diagram.json -t theme.json
  python3 scripts/check.py -d diagram.json -t theme.json --format json
  python3 scripts/check.py -d diagram.json -t theme.json --rules band-too-wide,label-overlap
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

    def __init__(self, rule: str, area_id: str,
                 section_id: str | None, message: str):
        self.rule = rule
        self.area_id = area_id
        self.section_id = section_id
        self.message = message

    def __str__(self) -> str:
        loc = f"{self.area_id}/{self.section_id}" if self.section_id else self.area_id
        return f"{self.rule} in {loc}: {self.message}"

    def to_dict(self) -> dict:
        return {
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

    Returns a flat list of (area_id, section, subarea) triples.
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
            'min-height-violated', area_id, section.id,
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
                'out-of-canvas', area.area_id, None,
                f"right edge {right:.0f} px exceeds canvas width {canvas_w:.0f} px",
            ))
        if bottom > canvas_h:
            issues.append(Issue(
                'out-of-canvas', area.area_id, None,
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
                        'band-too-wide', area.area_id, section_id,
                        f"link band span {span:.0f} px > 600 px guideline "
                        f"— consider increasing link opacity to 0.3–0.4",
                    ))
                elif span > 200:
                    # Only warn for nearest-column violations (first non-source area)
                    if area is area_views[1]:
                        issues.append(Issue(
                            'band-too-wide', area.area_id, section_id,
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
# Width estimate: N chars × font_size × Helvetica width ratio 0.6.
_ADDR_LABEL_H_OFFSET       = 10    # section.py label_offset
_ADDR_LABEL_CHARS          = 10    # len("0x00000000")  — 32-bit
_ADDR_LABEL_CHARS_64       = 18    # len("0x0000000000000000")  — 64-bit
_ADDR_64BIT_THRESHOLD      = 0xFFFF_FFFF   # addresses above this need >8 hex digits
_ADDR_64BIT_EXTRA_CLEARANCE = 20   # extra px so the label is clearly associated with its panel
_HELVETICA_W_RATIO         = 0.6   # character width / font-size for Helvetica


def _addr_label_width(font_size: float) -> float:
    return _ADDR_LABEL_CHARS * font_size * _HELVETICA_W_RATIO


def _addr_label_width_64(font_size: float) -> float:
    return _ADDR_LABEL_CHARS_64 * font_size * _HELVETICA_W_RATIO


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
                    'panel-overlap', a.area_id, None,
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
                'title-overlap', a.area_id, None,
                f"title of '{a.area_id}' (needs y≥{a_title_top:.0f}) overlaps bottom of "
                f"'{b.area_id}' (y={b_bottom:.0f}) by {overlap:.0f} px "
                f"— increase vertical gap to at least {_TITLE_CLEARANCE_PX} px",
            ))
    return issues


def _addr_label_chars_for_area(area) -> int:
    """
    Return the number of characters in the widest address label this panel renders.

    Returns 0 if no visible section in the panel has any address label shown
    (the area does not contribute to column-gap requirements).
    Returns _ADDR_LABEL_CHARS_64 (18) if any visible, labelled section exceeds
    _ADDR_64BIT_THRESHOLD; otherwise returns _ADDR_LABEL_CHARS (10).
    """
    found_any = False
    for sub in area.get_split_area_views():
        for section in sub.sections.get_sections():
            if section.is_hidden() or section.is_break():
                continue
            found_any = True
            if max(section.address, section.address + section.size) > _ADDR_64BIT_THRESHOLD:
                return _ADDR_LABEL_CHARS_64
    return _ADDR_LABEL_CHARS if found_any else 0


def _check_label_overlap(area_views: list) -> list[Issue]:
    """
    Estimated address-label right extent of one panel overlaps the left edge
    of the panel to its right.

    Panels with no visible address labels are skipped entirely.
    Width is estimated from font_size and the actual number of hex characters
    needed for this panel's addresses (10 for 32-bit, 18 for 64-bit).
    Only checked when the two panels share a vertical range so that a label
    at that height could actually reach the neighbouring panel.
    """
    issues = []
    for a in area_views:
        chars = _addr_label_chars_for_area(a)
        if chars == 0:
            continue  # no address labels rendered for this panel
        font_size   = float(a.style.get('font_size', 12))
        label_w     = chars * font_size * _HELVETICA_W_RATIO
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
                    'label-overlap', a.area_id, None,
                    f"address labels of '{a.area_id}' extend to ~{a_label_ext:.0f} px but "
                    f"'{b.area_id}' starts at {b.pos_x} px "
                    f"(gap {gap:.0f} px < {needed} px needed: "
                    f"{chars}-char label at font_size={font_size:.0f})"
                    f" — widen horizontal gap or move panels apart",
                ))
    return issues


def _check_addr_64bit_column_width(area_views: list) -> list[Issue]:
    """
    The horizontal gap between adjacent panels is too narrow to show 64-bit
    address labels (18 characters: "0x" + 16 hex digits) with the required
    extra clearance that visually ties each label to its own panel.

    Only triggered when at least one visible, non-break section in the panel
    has an address or end-address that exceeds the 32-bit range (> 0xFFFFFFFF),
    causing the renderer to emit a label wider than the 10-char 32-bit format.

    Required gap = label_offset + 18-char label width + extra clearance.
    """
    issues = []
    sorted_areas = sorted(area_views, key=lambda a: a.pos_x)

    for i, area in enumerate(sorted_areas):
        # Find the nearest panel to the right that shares a vertical range.
        right_area = None
        for b in sorted_areas[i + 1:]:
            if b.pos_x <= area.pos_x + area.size_x:
                continue  # not actually to the right
            if area.pos_y >= b.pos_y + b.size_y or area.pos_y + area.size_y <= b.pos_y:
                continue  # no vertical overlap — labels at this height can't reach b
            right_area = b
            break

        if right_area is None:
            continue

        gap = right_area.pos_x - (area.pos_x + area.size_x)
        font_size = float(area.style.get('font_size', 12))

        # Check if any visible section with a visible address label needs 64-bit display.
        needs_64bit = False
        for sub in area.get_split_area_views():
            for section in sub.sections.get_sections():
                if section.is_hidden() or section.is_break():
                    continue
                if max(section.address, section.address + section.size - 1) > _ADDR_64BIT_THRESHOLD:
                    needs_64bit = True
                    break
            if needs_64bit:
                break

        if not needs_64bit:
            continue

        needed = (_ADDR_LABEL_H_OFFSET
                  + _addr_label_width_64(font_size)
                  + _ADDR_64BIT_EXTRA_CLEARANCE)

        if gap < needed:
            issues.append(Issue(
                'addr-64bit-column-width', area.area_id, None,
                f"column gap to '{right_area.area_id}' is {gap:.0f} px but "
                f"64-bit address labels need ~{needed:.0f} px "
                f"({_ADDR_LABEL_H_OFFSET} px offset + {_ADDR_LABEL_CHARS_64}-char label "
                f"+ {_ADDR_64BIT_EXTRA_CLEARANCE} px clearance at font_size={font_size:.0f}) "
                f"— widen the gap or move '{right_area.area_id}' further right",
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
                'unresolved-section', 'links', section_id,
                f"'{section_id}' not found in any area after filtering",
            ))
    return issues


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_RULES = {
    'min-height-violated',
    'out-of-canvas',
    'band-too-wide',
    'unresolved-section',
    'panel-overlap',
    'title-overlap',
    'label-overlap',
    'addr-64bit-column-width',
}

PER_SECTION_RULES = [
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
    issues.extend(_check_addr_64bit_column_width(area_views))

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
                        help=('Visual styling. Three forms: '
                              '(omit) = built-in default; '
                              '-t <name> = built-in theme (default, light, monochrome, plantuml); '
                              '-t <path> = custom theme.json file.'))
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

    sys.exit(1 if issues else 0)


if __name__ == '__main__':
    main()
