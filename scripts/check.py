#!/usr/bin/env python3
"""
check.py — Layout rule checker for mmpviz diagrams.

Validates diagram.json + theme.json against layout rules without producing SVG
output.  Runs the same layout engine as mmpviz.py and checks the computed
section heights and panel positions against the rules below.

This module is also imported by mmpviz.py: run_checks() is called automatically
as part of the render pipeline before SVG generation.

Issue levels:
  ERROR   — rendering would produce a broken or unusable diagram; mmpviz aborts
  WARNING — rendering continues but the output may be hard to read

Exit codes (standalone use):
  0  — no issues found
  1  — one or more ERRORs detected
  2  — warnings only (no ERRORs)

Usage:
  python3 scripts/check.py -d diagram.json
  python3 scripts/check.py -d diagram.json -t theme.json
  python3 scripts/check.py -d diagram.json -t theme.json --format json
  python3 scripts/check.py -d diagram.json -t theme.json --rules label-overlap,link-anchor-out-of-bounds
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
from loader import load
from theme import Theme

# Re-use the get_area_views helper from mmpviz without importing main().
from mmpviz import get_area_views, _auto_layout


# ---------------------------------------------------------------------------
# Issue dataclass
# ---------------------------------------------------------------------------

class Issue:
    """A single check finding."""

    def __init__(self, rule: str, view_id: str,
                 section_id: str | None, message: str, level: str = 'WARN'):
        self.rule = rule
        self.view_id = view_id
        self.section_id = section_id
        self.message = message
        self.level = level  # 'ERROR' or 'WARN'

    def __str__(self) -> str:
        loc = f"{self.view_id}/{self.section_id}" if self.section_id else self.view_id
        prefix = 'ERROR' if self.level == 'ERROR' else 'WARNING'
        return f"[{prefix}] {self.rule} in {loc}: {self.message}"

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "rule": self.rule,
            "view": self.view_id,
            "section": self.section_id,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Height computation helper
# ---------------------------------------------------------------------------

def _populate_section_heights(area_views: list) -> list:
    """
    Compute size_y / pos_y / size_x for every visible section in every subarea.

    Returns a flat list of (view_id, section, subarea) triples.
    """
    result = []
    for area in area_views:
        for sub in area.get_split_area_views():
            for section in sub.sections.get_sections():
                if section.is_hidden():
                    continue
                sub.apply_section_geometry(section)
                result.append((area.view_id, section, sub))
    return result


# ---------------------------------------------------------------------------
# Individual rule checkers
# ---------------------------------------------------------------------------

def _check_min_height_violated(view_id: str, section, sub) -> list[Issue]:
    """
    Section height is below its effective minimum (max of global min_section_height
    and the section's own min_height).

    This indicates the proportional-fallback was triggered: the algorithm
    could not satisfy all minimum-height constraints simultaneously and fell
    back to pure proportional rendering, allowing sections to be shorter than
    the configured floor.
    """
    if section.is_break():
        return []
    global_min = sub.style.get('min_section_height')
    try:
        global_min = float(global_min) if global_min is not None else 0.0
    except (TypeError, ValueError):
        global_min = 0.0
    section_min = section.min_height if section.min_height is not None else 0.0
    effective_min = max(global_min, section_min)
    if effective_min <= 0:
        return []
    if section.size_y < effective_min - 1e-6:
        return [Issue(
            'min-height-violated', view_id, section.id,
            f"height {section.size_y:.1f} px < effective min {effective_min:.0f} px "
            f"(global min_section_height={global_min:.0f}, "
            f"section min_height={section_min:.0f}) "
            f"— proportional fallback likely triggered; add break sections to "
            f"reduce competing sections or lower the floor",
        )]
    return []


def _check_section_height_conflict(view_id: str, section, sub) -> list[Issue]:
    """
    A section's min_height exceeds its max_height.

    When both are set and min > max, the height algorithm receives contradictory
    constraints.  The floor-locking phase will lock the section at min_height,
    but the ceiling phase will then cap it at max_height (below the floor),
    producing an incorrect height.  This conflict must be fixed in diagram.json.
    """
    if section.is_break():
        return []
    min_h = section.min_height
    max_h = section.max_height
    if min_h is None or max_h is None:
        return []
    if min_h > max_h:
        return [Issue(
            'section-height-conflict', view_id, section.id,
            f"min_height ({min_h:.0f} px) > max_height ({max_h:.0f} px) "
            f"— fix in diagram.json sections[]",
            level='ERROR',
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
                'out-of-canvas', area.view_id, None,
                f"right edge {right:.0f} px exceeds canvas width {canvas_w:.0f} px",
                level='ERROR',
            ))
        if bottom > canvas_h:
            issues.append(Issue(
                'out-of-canvas', area.view_id, None,
                f"bottom edge {bottom:.0f} px exceeds canvas height {canvas_h:.0f} px",
                level='ERROR',
            ))
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
                    'panel-overlap', a.view_id, None,
                    f"panel [{a.pos_x},{a.pos_y} {a.size_x}×{a.size_y}] physically overlaps "
                    f"'{b.view_id}' [{b.pos_x},{b.pos_y} {b.size_x}×{b.size_y}]"
                    f" — adjust column assignment or add break sections to reduce view height",
                    level='ERROR',
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
                'title-overlap', a.view_id, None,
                f"title of '{a.view_id}' (needs y≥{a_title_top:.0f}) overlaps bottom of "
                f"'{b.view_id}' (y={b_bottom:.0f}) by {overlap:.0f} px "
                f"— vertical gap must be at least {_TITLE_CLEARANCE_PX} px; "
                f"add break sections or increase min_height to reduce view height",
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
            if section.address > _ADDR_64BIT_THRESHOLD:
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
                    'label-overlap', a.view_id, None,
                    f"address labels of '{a.view_id}' extend to ~{a_label_ext:.0f} px but "
                    f"'{b.view_id}' starts at {b.pos_x} px "
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
                if section.address > _ADDR_64BIT_THRESHOLD:
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
                'addr-64bit-column-width', area.view_id, None,
                f"column gap to '{right_area.view_id}' is {gap:.0f} px but "
                f"64-bit address labels need ~{needed:.0f} px "
                f"({_ADDR_LABEL_H_OFFSET} px offset + {_ADDR_LABEL_CHARS_64}-char label "
                f"+ {_ADDR_64BIT_EXTRA_CLEARANCE} px clearance at font_size={font_size:.0f}) "
                f"— widen the gap or move '{right_area.view_id}' further right",
            ))

    return issues


def _check_section_overlap(area_views: list) -> list[Issue]:
    """
    Two visible (non-hidden, non-break) sections in the same view have
    overlapping address ranges.

    A common mistake is including a parent section (e.g. ``APB1``) and its
    named children (e.g. ``UART0``, ``SPI0``) in the same view.  The parent's
    visual box covers all children, making labels unreadable.  Fix: remove
    whichever layer should not be rendered from this view's ``sections[]``.
    """
    issues = []
    for av in area_views:
        visible = sorted(
            (s for s in av.sections.get_sections()
             if 'hidden' not in s.flags and 'break' not in s.flags),
            key=lambda s: s.address,
        )
        for i, s1 in enumerate(visible):
            s1_end = s1.address + s1.size
            for s2 in visible[i + 1:]:
                if s2.address >= s1_end:
                    break  # sorted — no more overlaps with s1
                issues.append(Issue(
                    'section-overlap', av.view_id, s1.id,
                    f"'{s1.id}' [{hex(s1.address)}, +{hex(s1.size)}] overlaps "
                    f"'{s2.id}' [{hex(s2.address)}, +{hex(s2.size)}]; "
                    f"remove one layer from this view's sections[]",
                ))
    return issues


# ---------------------------------------------------------------------------
# Gap coverage helpers (used by _check_uncovered_gap)
# ---------------------------------------------------------------------------

def _gap_fully_covered(gap_lo: int, gap_hi: int,
                       sorted_break_ranges: list) -> bool:
    """
    Return True if the union of sorted_break_ranges fully covers [gap_lo, gap_hi].

    Accepts consecutive or overlapping breaks — the union is walked left-to-right,
    advancing a cursor each time a break extends it.  A hole exists only when
    the next break starts beyond the current cursor position.
    """
    cur = gap_lo
    for blo, bhi in sorted_break_ranges:
        if blo > cur:
            break  # hole between cur and blo
        if bhi > cur:
            cur = bhi
        if cur >= gap_hi:
            return True
    return cur >= gap_hi


def _first_gap_hole(gap_lo: int, gap_hi: int,
                    sorted_break_ranges: list) -> int:
    """Return the first address in [gap_lo, gap_hi) not covered by any break."""
    cur = gap_lo
    for blo, bhi in sorted_break_ranges:
        if blo > cur:
            return cur
        if bhi > cur:
            cur = bhi
        if cur >= gap_hi:
            break
    return cur


def _check_uncovered_gap(area_views: list) -> list[Issue]:
    """
    A large address gap between two consecutive visible sections in a view is
    not fully covered by break sections.

    Coverage is determined by the **union** of all break sections in the view —
    consecutive or chained breaks that together span the full gap are correctly
    recognised as covering it.

    Two conditions trigger this rule:

    1. **No break coverage** and the gap exceeds 5× the total visible content.
    2. **Partial break coverage** (breaks overlap the gap but leave holes) and
       the gap exceeds the size of its flanking sections.

    Fix: add or extend break section(s) so their union spans the entire gap.
    """
    issues = []
    for av in area_views:
        secs = av.sections.get_sections()
        # Sort breaks once; _gap_fully_covered / _first_gap_hole require sorted input.
        break_ranges = sorted(
            [(s.address, s.address + s.size)
             for s in secs if 'break' in s.flags],
            key=lambda r: r[0],
        )
        visible = sorted(
            (s for s in secs
             if 'hidden' not in s.flags and 'break' not in s.flags),
            key=lambda s: s.address,
        )
        if len(visible) < 2:
            continue
        total_visible = sum(s.size for s in visible) or 1
        for i in range(len(visible) - 1):
            s1, s2 = visible[i], visible[i + 1]
            gap_lo = s1.address + s1.size
            gap_hi = s2.address
            if gap_hi <= gap_lo:
                continue  # no gap (overlap handled by section-overlap)
            gap_size = gap_hi - gap_lo

            if _gap_fully_covered(gap_lo, gap_hi, break_ranges):
                continue

            # Check whether any breaks at least partially overlap this gap.
            has_partial = any(blo < gap_hi and bhi > gap_lo
                              for blo, bhi in break_ranges)

            if (gap_size > 5 * total_visible
                    or (has_partial and gap_size > max(s1.size, s2.size))):
                if has_partial:
                    first_hole = _first_gap_hole(gap_lo, gap_hi, break_ranges)
                    detail = (f" — break sections partially cover this gap; "
                              f"first uncovered portion starts at {hex(first_hole)}, "
                              f"{hex(gap_hi - first_hole)} short of '{s2.id}'")
                else:
                    detail = (f" is {gap_size // total_visible}× the total visible "
                              f"content — sections will appear very small")
                issues.append(Issue(
                    'uncovered-gap', av.view_id, s1.id,
                    f"uncovered gap of {hex(gap_size)} between '{s1.id}' and "
                    f"'{s2.id}'{detail}; "
                    f"add or extend a break section spanning the full gap",
                ))
    return issues


# ---------------------------------------------------------------------------
# Link anchor helpers (used by _check_link_anchor_out_of_bounds)
# ---------------------------------------------------------------------------

def _resolve_link_addr_range(sections_spec, area) -> list | None:
    """
    Resolve a link endpoint sections specifier to [addr_lo, addr_hi].

    Mirrors the logic of renderer.MapRenderer._resolve_endpoint_range without
    the SVG dependency.  Returns None if the specifier cannot be resolved.
    """
    from loader import parse_int as _parse_int
    if sections_spec is None:
        return [area.start_address, area.end_address]
    # Address-range form: exactly 2 hex strings.
    if (len(sections_spec) == 2
            and isinstance(sections_spec[0], str)
            and sections_spec[0].startswith('0x')):
        try:
            return [_parse_int(sections_spec[0]), _parse_int(sections_spec[1])]
        except (ValueError, TypeError):
            return None
    # Section-ID list.
    starts, ends = [], []
    for sid in sections_spec:
        for section in area.sections.get_sections():
            if section.id == sid:
                starts.append(section.address)
                ends.append(section.address + section.size)
                break
    if not starts:
        return None
    return [min(starts), max(ends)]


def _link_anchor_y(addr: int, area) -> float:
    """
    Return the absolute SVG y-coordinate for `addr` within `area`.

    Mirrors renderer._get_points_for_address: search split subareas for one
    that contains `addr`, then delegate to address_to_py_actual.  Falls back
    to the main area when no subarea matches (which may extrapolate outside
    [pos_y, pos_y + size_y] if `addr` is out of the view's address range).
    """
    sub = area
    for s in area.get_split_area_views():
        if s.start_address <= addr <= s.end_address:
            sub = s
            break
    return sub.pos_y + sub.address_to_py_actual(addr)


def _check_link_anchor_out_of_bounds(area_views: list,
                                     links_config: list) -> list[Issue]:
    """
    A link band's source-side or destination-side y-anchor falls outside the
    panel's rendered pixel range [pos_y, pos_y + size_y].

    When the anchor is out of range, the band is drawn partially or fully
    outside the panel rectangle and no longer aligns with the sections it is
    supposed to annotate.

    For section-ID specifiers this should never fire — sections are always
    within their panel.  It can fire for address-range specifiers
    (e.g. ``"sections": ["0x0", "0x5000"]``) when the explicit addresses
    extend beyond the view's actual address range.

    Fix: correct the address range in ``links[].from.sections`` or
    ``links[].to.sections`` so it stays within the referenced view's address
    extent, or remove the explicit range to span the full view.
    """
    if not area_views or not isinstance(links_config, list):
        return []

    av_by_id = {av.view_id: av for av in area_views}
    issues = []

    for entry in links_config:
        if not isinstance(entry, dict):
            continue
        from_view_id = entry.get('from', {}).get('view')
        to_view_id   = entry.get('to',   {}).get('view')
        if not from_view_id or not to_view_id:
            continue
        from_area = av_by_id.get(from_view_id)
        to_area   = av_by_id.get(to_view_id)
        if from_area is None or to_area is None:
            continue  # unresolved-section will catch these

        label = f"{from_view_id} → {to_view_id}"

        # --- Source side ---
        from_range = _resolve_link_addr_range(
            entry.get('from', {}).get('sections'), from_area)
        if from_range is not None:
            for addr, side in [(from_range[0], 'bottom'), (from_range[1], 'top')]:
                y = _link_anchor_y(addr, from_area)
                p_top = from_area.pos_y
                p_bot = from_area.pos_y + from_area.size_y
                if y < p_top - 1 or y > p_bot + 1:
                    issues.append(Issue(
                        'link-anchor-out-of-bounds', from_view_id, label,
                        f"source band {side} anchor y={y:.0f} is outside "
                        f"panel y=[{p_top:.0f}, {p_bot:.0f}] "
                        f"(address {hex(addr)} outside view range "
                        f"[{hex(from_area.start_address)}, {hex(from_area.end_address)}])"
                        f" — correct the address in links[].from.sections",
                        level='ERROR',
                    ))

        # --- Destination side ---
        # Apply the same clamping the renderer uses so we test the actual pixel
        # coordinates it will produce.
        raw_to_spec = entry.get('to', {}).get('sections')
        if raw_to_spec:
            raw_to_range = _resolve_link_addr_range(raw_to_spec, to_area)
            if raw_to_range is not None:
                dest_lo = max(raw_to_range[0], to_area.start_address)
                dest_hi = min(raw_to_range[1], to_area.end_address)
            else:
                dest_lo, dest_hi = to_area.start_address, to_area.end_address
        elif from_range is not None:
            dest_lo = max(from_range[0], to_area.start_address)
            dest_hi = min(from_range[1], to_area.end_address)
        else:
            dest_lo, dest_hi = to_area.start_address, to_area.end_address

        for addr, side in [(dest_lo, 'bottom'), (dest_hi, 'top')]:
            y = _link_anchor_y(addr, to_area)
            p_top = to_area.pos_y
            p_bot = to_area.pos_y + to_area.size_y
            if y < p_top - 1 or y > p_bot + 1:
                issues.append(Issue(
                    'link-anchor-out-of-bounds', to_view_id, label,
                    f"destination band {side} anchor y={y:.0f} is outside "
                    f"panel y=[{p_top:.0f}, {p_bot:.0f}] "
                    f"(effective address {hex(addr)})"
                    f" — correct the address in links[].to.sections",
                    level='ERROR',
                ))

    return issues


def _check_unresolved_link_sections(area_views: list,
                                    links_config: list) -> list[Issue]:
    """Section or view IDs referenced in link entries do not exist."""
    if not isinstance(links_config, list):
        return []

    # Collect section IDs per view and all view IDs.
    sections_by_view: dict = {}
    area_view_ids = set()
    for area in area_views:
        area_view_ids.add(area.view_id)
        sids = set()
        for sub in area.get_split_area_views():
            for s in sub.sections.get_sections():
                sids.add(s.id)
        sections_by_view[area.view_id] = sids

    issues = []

    for entry in links_config:
        if not isinstance(entry, dict):
            continue
        for side in ('from', 'to'):
            endpoint = entry.get(side, {})
            if not isinstance(endpoint, dict):
                continue
            view_id = endpoint.get('view')
            if view_id and view_id not in area_view_ids:
                issues.append(Issue(
                    'unresolved-section', f'links.{side}', view_id,
                    f"view '{view_id}' not found",
                    level='ERROR',
                ))
                continue
            sections = endpoint.get('sections')
            if not sections or not isinstance(sections, list):
                continue
            # Address-range form: ["0x...", "0x..."] — no section IDs to validate.
            if (len(sections) == 2
                    and isinstance(sections[0], str)
                    and isinstance(sections[1], str)
                    and sections[0].startswith('0x')
                    and sections[1].startswith('0x')):
                continue
            view_sids = sections_by_view.get(view_id, set())
            for sid in sections:
                if sid not in view_sids:
                    issues.append(Issue(
                        'unresolved-section', f'links.{side}.sections', sid,
                        f"'{sid}' not found in view '{view_id}'",
                        level='ERROR',
                    ))

    return issues


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_RULES = {
    'min-height-violated',
    'section-height-conflict',
    'out-of-canvas',
    'link-anchor-out-of-bounds',
    'unresolved-section',
    'section-overlap',
    'uncovered-gap',
    'panel-overlap',
    'title-overlap',
    'label-overlap',
    'addr-64bit-column-width',
}

PER_SECTION_RULES = [
    _check_min_height_violated,
    _check_section_height_conflict,
]


def run_checks(diagram: dict, area_views: list,
               enabled_rules: set) -> list[Issue]:
    # Canvas bounds are always derived from actual content (no diagram 'size' field).
    if area_views:
        canvas_w = max(av.pos_x + av.size_x for av in area_views) + 110
        canvas_h = max(av.pos_y + av.size_y for av in area_views) + 30
    else:
        canvas_w, canvas_h = float(DefaultAppValues.DOCUMENT_SIZE[0]), float(DefaultAppValues.DOCUMENT_SIZE[1])
    links_config = diagram.get('links', [])

    issues = []

    # Per-section rules (run all; filter by enabled_rules at the end)
    section_data = _populate_section_heights(area_views)
    for view_id, section, sub in section_data:
        for rule_fn in PER_SECTION_RULES:
            issues.extend(rule_fn(view_id, section, sub))

    # Area-level rules
    issues.extend(_check_out_of_canvas(area_views, canvas_w, canvas_h))
    issues.extend(_check_panel_overlap(area_views))
    issues.extend(_check_title_overlap(area_views))
    issues.extend(_check_label_overlap(area_views))
    issues.extend(_check_addr_64bit_column_width(area_views))

    # Section geometry rules
    issues.extend(_check_section_overlap(area_views))
    issues.extend(_check_uncovered_gap(area_views))

    # Link rules
    issues.extend(_check_link_anchor_out_of_bounds(area_views, links_config))
    issues.extend(_check_unresolved_link_sections(area_views, links_config))

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
                              '-t <name> = built-in theme (default, plantuml); '
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
        diagram = load(args.diagram)
    except (ValueError, OSError) as e:
        print(f"Error loading diagram: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        theme = Theme(args.theme)
    except (OSError, Exception) as e:
        print(f"Error loading theme: {e}", file=sys.stderr)
        sys.exit(1)

    base_style = theme.resolve('')
    area_views = get_area_views(base_style, diagram, theme)
    if not area_views:
        print("Error: no views could be created.", file=sys.stderr)
        sys.exit(1)

    issues = run_checks(diagram, area_views, enabled_rules)

    if args.format == 'json':
        print(json.dumps([i.to_dict() for i in issues], indent=2))
    else:
        if not issues:
            print("OK — no issues found")
        else:
            for issue in issues:
                print(issue)

    errors = [i for i in issues if i.level == 'ERROR']
    warnings = [i for i in issues if i.level == 'WARN']
    if errors:
        sys.exit(1)
    elif warnings:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
