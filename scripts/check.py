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

from area_view import AreaView, section_label_min_h
from links import Links
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
                sub.apply_section_geometry(section)
                result.append((area.view_id, section, sub))
    return result


# ---------------------------------------------------------------------------
# Individual rule checkers
# ---------------------------------------------------------------------------

def _check_min_height_violated(view_id: str, section, sub) -> list[Issue]:
    """
    Section height is below its effective minimum: max(global min_section_height,
    section min_height, geometry-derived label-conflict floor).

    The label-conflict floor (30 + font_size px) is only non-zero when the
    size label (top-left) and the name label (centred) would overlap horizontally
    given the section's rendered width.  For wide views it is typically 0.

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
    font_size = float(sub.style.get('font_size', 12))
    label_floor = section_label_min_h(section, font_size, sub.size_x)
    effective_min = max(global_min, section_min, label_floor)
    if effective_min <= 0:
        return []
    if section.size_y < effective_min - 1e-6:
        return [Issue(
            'min-height-violated', view_id, section.id,
            f"height {section.size_y:.1f} px < effective min {effective_min:.0f} px "
            f"(global min_section_height={global_min:.0f}, "
            f"section min_height={section_min:.0f}, "
            f"label floor={label_floor:.0f}) "
            f"— proportional fallback likely triggered; add break sections to "
            f"reduce competing sections or lower the floor",
        )]
    return []


def _check_min_height_below_global(view_id: str, section, sub) -> list[Issue]:
    """
    Per-section min_height is configured below the global min_section_height,
    effectively undercutting the global floor for this section.

    Prefer using min_section_height globally; only set a per-section min_height
    when a section needs a floor *higher* than the global one.
    """
    if section.is_break() or section.min_height is None:
        return []
    global_min = sub.style.get('min_section_height')
    try:
        global_min = float(global_min) if global_min is not None else 0.0
    except (TypeError, ValueError):
        global_min = 0.0
    if global_min <= 0:
        return []
    if section.min_height < global_min - 1e-6:
        return [Issue(
            'min-height-below-global', view_id, section.id,
            f"section min_height={section.min_height:.0f} px is below global "
            f"min_section_height={global_min:.0f} px — per-section override undercuts "
            f"the global floor; set min_height >= {global_min:.0f} px or remove it",
        )]
    return []


def _check_min_height_on_break(view_id: str, section, sub) -> list[Issue]:
    """
    A break-flagged section has min_height set, which the layout engine ignores.
    Break sections always render at break_height px regardless of min_height.
    """
    if not section.is_break() or section.min_height is None:
        return []
    break_h = float(sub.style.get('break_height', 20))
    return [Issue(
        'min-height-on-break', view_id, section.id,
        f"section has min_height={section.min_height:.0f} px but is flagged 'break' "
        f"— break sections always render at break_height={break_h:.0f} px; "
        f"remove min_height or remove the 'break' flag",
    )]


_NAME_LABEL_H_MARGIN = 4   # px from section border to name text edge (each side)


def _check_section_name_overflow(view_id: str, section, sub) -> list[Issue]:
    """
    Section name text is wider than the panel, even when on its own line.

    The name label is rendered as a single horizontal SVG <text> centred in
    the panel — there is no wrapping.  When the estimated text width exceeds
    (size_x − 2 × _NAME_LABEL_H_MARGIN) the text visually overflows the
    section box and bleeds into adjacent sections.  The renderer cannot fix
    this automatically; the name must be shortened in diagram.json.

    Estimated width = len(name) × 0.6 × font_size.
    """
    if section.is_break():
        return []
    font_size = float(sub.style.get('font_size', 12))
    name = section.name if section.name is not None else section.id
    name_width = len(name) * 0.6 * font_size
    max_width = sub.size_x - 2 * _NAME_LABEL_H_MARGIN
    if name_width <= max_width:
        return []
    max_chars = int(max_width / (0.6 * font_size))
    return [Issue(
        'section-name-overflow', view_id, section.id,
        f"name '{name}' ({len(name)} chars, est. {name_width:.0f} px) exceeds "
        f"section panel width {sub.size_x:.0f} px "
        f"(max ~{max_width:.0f} px ≈ {max_chars} chars at font_size={font_size:.0f}) "
        f"— shorten the name in diagram.json",
    )]


def _check_section_height_conflict(view_id: str, section, sub) -> list[Issue]:
    """
    A section's min_height exceeds its max_height.

    max_height is currently accepted but ignored by the floor-stack layout
    model, so the conflict has no effect on today's rendered output.  The
    check remains an ERROR because the declaration is logically inconsistent
    on its own terms, and would produce a broken render if max_height is
    re-enabled as a ceiling in a future release.
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


_TITLE_FONT_SIZE = 24   # pt — title text is always rendered at 24 px
_TITLE_Y_OFFSET  = 20   # px above panel top edge (from renderer._make_title)
_TITLE_CHAR_W    = 0.6  # Helvetica character width ratio


def _check_title_overlap(area_views: list) -> list[Issue]:
    """
    Title overlap — two flavours:

    1. **Vertical** — a panel's title intrudes into the body of the panel
       directly above it in the same column.  Titles are rendered
       _TITLE_Y_OFFSET px above the panel's top edge; a _TITLE_CLEARANCE_PX
       clearance zone is required.

    2. **Horizontal** — two panel titles at the same vertical level
       (adjacent columns, or top row) overlap in the inter-column gap.
       Title width is estimated as len(title) × _TITLE_CHAR_W × _TITLE_FONT_SIZE.
    """
    issues = []

    # --- Flavour 1: vertical title-body intrusion ---
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

    # --- Flavour 2: horizontal title-title collision ---
    for i, a in enumerate(area_views):
        if not a.title:
            continue
        a_cy  = a.pos_x + a.size_x / 2
        a_ty  = a.pos_y - _TITLE_Y_OFFSET
        a_hw  = len(a.title) * _TITLE_CHAR_W * _TITLE_FONT_SIZE / 2
        a_x0, a_x1 = a_cy - a_hw, a_cy + a_hw

        for b in area_views[i + 1:]:
            if not b.title:
                continue
            b_cy  = b.pos_x + b.size_x / 2
            b_ty  = b.pos_y - _TITLE_Y_OFFSET
            b_hw  = len(b.title) * _TITLE_CHAR_W * _TITLE_FONT_SIZE / 2
            b_x0, b_x1 = b_cy - b_hw, b_cy + b_hw

            # Must be at the same vertical level (within one title line height)
            if abs(a_ty - b_ty) > _TITLE_FONT_SIZE:
                continue
            # Horizontal bounding boxes must overlap
            if a_x0 >= b_x1 or b_x0 >= a_x1:
                continue
            overlap_px = min(a_x1, b_x1) - max(a_x0, b_x0)
            issues.append(Issue(
                'title-overlap', a.view_id, None,
                f"title of '{a.view_id}' (x=[{a_x0:.0f},{a_x1:.0f}]) overlaps "
                f"title of '{b.view_id}' (x=[{b_x0:.0f},{b_x1:.0f}]) by {overlap_px:.0f} px "
                f"— shorten one or both titles",
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
            if section.is_break():
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
                if section.is_break():
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
    Two sections in the same view have overlapping address ranges.  Three
    sub-cases are emitted as distinct rule names so they can be filtered
    independently:

    - ``section-overlap`` (WARN): two visible (non-break) sections overlap.
      Common cause — including a parent region and its named children in the
      same view; the parent's box visually covers the children, making labels
      unreadable.  Fix: remove one layer from ``sections[]``.

    - ``break-overlaps-section`` (ERROR): a break's range overlaps a visible
      section's range.  The layout engine treats the overlapping region as
      part of the break and silently drops the visible section from the
      rendered output — the section exists in ``diagram.json`` but never
      appears in the SVG.  Fix: recompute the break's size so it ends exactly
      at the next real section's base address.

    - ``section-overlap`` (WARN): two break sections overlap.  Overlapping
      breaks are redundant — they claim the same address range twice.  No
      rendering consequence, but the intent is unclear.  Fix: resize the
      breaks so their ranges are non-overlapping.
    """
    issues = []
    for av in area_views:
        secs = sorted(
            av.sections.get_sections(),
            key=lambda s: s.address,
        )
        for i, s1 in enumerate(secs):
            s1_end = s1.address + s1.size
            s1_is_break = 'break' in s1.flags
            for s2 in secs[i + 1:]:
                if s2.address >= s1_end:
                    break  # sorted — no more overlaps with s1
                s2_is_break = 'break' in s2.flags
                if s1_is_break and s2_is_break:
                    issues.append(Issue(
                        'section-overlap', av.view_id, s1.id,
                        f"break '{s1.id}' [{hex(s1.address)}, +{hex(s1.size)}] overlaps "
                        f"break '{s2.id}' [{hex(s2.address)}, +{hex(s2.size)}] — "
                        f"overlapping breaks are redundant; resize them so their "
                        f"ranges do not overlap",
                    ))
                elif s1_is_break or s2_is_break:
                    brk, vis = (s1, s2) if s1_is_break else (s2, s1)
                    b_lo, b_hi = brk.address, brk.address + brk.size
                    v_lo, v_hi = vis.address, vis.address + vis.size
                    issues.append(Issue(
                        'break-overlaps-section', av.view_id, vis.id,
                        f"break '{brk.id}' [{hex(b_lo)}, {hex(b_hi)}] overlaps "
                        f"non-break section '{vis.id}' [{hex(v_lo)}, {hex(v_hi)}] "
                        f"— '{vis.id}' will be swallowed by the break and not render. "
                        f"Fix: recompute the break's size so it ends exactly where "
                        f"'{vis.id}' begins (break.size = {hex(v_lo)} − "
                        f"{hex(b_lo)} = {hex(v_lo - b_lo)}).",
                        level='ERROR',
                    ))
                else:
                    issues.append(Issue(
                        'section-overlap', av.view_id, s1.id,
                        f"'{s1.id}' [{hex(s1.address)}, +{hex(s1.size)}] overlaps "
                        f"'{s2.id}' [{hex(s2.address)}, +{hex(s2.size)}]; "
                        f"remove one layer from this view's sections[]",
                    ))
    return issues


def _check_uncovered_gap(area_views: list) -> list[Issue]:
    """
    Any address range within the view's extent [Lo, Hi] that is not covered
    by any section — break or non-break — is reported.

    Lo = lowest section start address; Hi = highest section end address
    (both derived from the sections in the view).  Coverage is the union of
    all sections' [address, address+size) intervals walked in address order.
    Any hole in that union is a separate WARN issue naming the sections on
    either side.

    Two sections that touch exactly (s1.end == s2.start) are fully covered
    and do not trigger this rule.  Overlapping sections (already flagged by
    section-overlap) do not produce additional gap issues here.
    """
    issues = []
    for av in area_views:
        secs = sorted(av.sections.get_sections(), key=lambda s: s.address)
        if not secs:
            continue
        # cursor starts at the first section address = av.start_address,
        # so there is never a leading hole.
        cursor = av.start_address
        prev_id = None
        for s in secs:
            if s.address > cursor:
                hole_lo, hole_hi = cursor, s.address
                issues.append(Issue(
                    'uncovered-gap', av.view_id, prev_id,
                    f"address range [{hex(hole_lo)}, {hex(hole_hi)}) "
                    f"({hex(hole_hi - hole_lo)}) has no section defined "
                    f"between '{prev_id}' and '{s.id}' — "
                    f"add a break section spanning this range",
                ))
            cursor = max(cursor, s.address + s.size)
            prev_id = s.id
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


def _check_link_section_form(area_views: list,
                             links_config: list) -> list[Issue]:
    """
    Warn when ``from.sections`` or ``to.sections`` uses a more specific form
    than necessary.  Emits two rule names so they can be filtered separately:

    - ``link-address-range-mappable`` (WARN): an address-range form
      (``["0xA", "0xB"]``) resolves exactly to one or more defined non-break
      sections.  Use section IDs instead — they are more readable and survive
      address-map edits.

    - ``link-redundant-sections`` (WARN): the sections list is equivalent to
      the whole-view default (either enumerates every visible non-break
      section, or is an address range spanning the view's full extent).
      Omit the ``sections`` field instead.

    Address-range forms that genuinely don't correspond to any defined
    section (e.g. virtual→physical mappings) are left untouched.
    """
    if not area_views or not isinstance(links_config, list):
        return []

    from loader import parse_int as _parse_int

    av_by_id = {av.view_id: av for av in area_views}
    issues = []

    def _is_addr_range_form(spec):
        return (isinstance(spec, list) and len(spec) == 2
                and isinstance(spec[0], str) and spec[0].startswith('0x')
                and isinstance(spec[1], str) and spec[1].startswith('0x'))

    def _visible_sections(area):
        return sorted(
            (s for s in area.sections.get_sections()
             if 'break' not in s.flags),
            key=lambda s: s.address,
        )

    def _sections_covering_range(area, lo, hi):
        """Return the list of section IDs whose union is exactly ``[lo, hi)``,
        or ``None`` if the range doesn't line up with a contiguous run of
        non-break sections.  ``None`` is the 'legitimate address-range form'
        signal — the link refers to a range that no section names."""
        ids = []
        cur = lo
        for s in _visible_sections(area):
            s_end = s.address + s.size
            if s_end <= cur:
                continue
            if s.address != cur:
                return None  # gap between cur and next section's start
            ids.append(s.id)
            cur = s_end
            if cur >= hi:
                break
        if cur == hi and ids:
            return ids
        return None

    def _ids_combined_range(area, id_list):
        """Return (min_start, max_end) over every section whose id is in
        ``id_list``, or ``None`` if any id is missing from the view (in which
        case ``unresolved-section`` catches it).  Mirrors the renderer's
        ``_resolve_link_addr_range`` section-list branch."""
        ids_set = set(id_list)
        starts, ends = [], []
        seen = set()
        for s in area.sections.get_sections():
            if s.id in ids_set:
                starts.append(s.address)
                ends.append(s.address + s.size)
                seen.add(s.id)
        if not starts or seen != ids_set:
            return None
        return (min(starts), max(ends))

    def _resolve_spec_range(area, spec):
        """Resolve a sections spec to (lo, hi) or None. Mirrors
        _resolve_link_addr_range without the full-view default."""
        if not spec:
            return None
        if _is_addr_range_form(spec):
            try:
                return (_parse_int(spec[0]), _parse_int(spec[1]))
            except (ValueError, TypeError):
                return None
        return _ids_combined_range(area, spec)

    for entry in links_config:
        if not isinstance(entry, dict):
            continue
        link_id = entry.get('id', '<unnamed>')

        # Pre-resolve the 'from' range so we can simulate the renderer's
        # behavior when 'to.sections' is omitted — for cross-address-space
        # links the omit-default is clamp(from_range), not the whole to-view.
        from_ep = entry.get('from', {})
        from_area = av_by_id.get(from_ep.get('view')) if isinstance(from_ep, dict) else None
        from_range = None
        if from_area is not None:
            from_spec = from_ep.get('sections') if isinstance(from_ep, dict) else None
            if not from_spec:
                from_range = (from_area.start_address, from_area.end_address)
            else:
                from_range = _resolve_spec_range(from_area, from_spec)

        for side in ('from', 'to'):
            endpoint = entry.get(side, {})
            if not isinstance(endpoint, dict):
                continue
            view_id = endpoint.get('view')
            spec = endpoint.get('sections')
            if not spec or not isinstance(spec, list):
                continue  # omitted / missing — preferred whole-view default
            area = av_by_id.get(view_id)
            if area is None:
                continue  # unresolved-section catches missing view

            # Compute the effective destination range the renderer would
            # use if this side's spec were omitted. The 'from' side always
            # falls back to the whole view; the 'to' side clamps from_range
            # (or the whole to-view if 'from' is also unresolved).
            if side == 'from':
                omit_lo, omit_hi = area.start_address, area.end_address
            else:
                if from_range is None:
                    omit_lo, omit_hi = area.start_address, area.end_address
                else:
                    omit_lo = max(from_range[0], area.start_address)
                    omit_hi = min(from_range[1], area.end_address)

            if _is_addr_range_form(spec):
                try:
                    lo = _parse_int(spec[0])
                    hi = _parse_int(spec[1])
                except (ValueError, TypeError):
                    continue
                # 1) redundant: clamped spec range equals what omitting
                #    would produce → same anchor, field adds no info.
                spec_lo = max(lo, area.start_address)
                spec_hi = min(hi, area.end_address)
                if (lo <= area.start_address and hi >= area.end_address
                        and spec_lo == omit_lo and spec_hi == omit_hi):
                    issues.append(Issue(
                        'link-redundant-sections', f'links[{link_id}].{side}', view_id,
                        f"address range [{spec[0]}, {spec[1]}] spans the whole "
                        f"'{view_id}' view — omit the '{side}.sections' field "
                        f"to use the whole-view default",
                    ))
                    continue
                # 2) range maps exactly onto defined section(s) → prefer IDs.
                ids = _sections_covering_range(area, lo, hi)
                if ids:
                    id_repr = ', '.join(f"'{i}'" for i in ids)
                    issues.append(Issue(
                        'link-address-range-mappable', f'links[{link_id}].{side}', view_id,
                        f"address range [{spec[0]}, {spec[1]}] in '{view_id}' "
                        f"resolves exactly to section(s) [{id_repr}] — replace "
                        f"the address range with section IDs for readability",
                    ))
            else:
                # Section-ID-list form. Redundant only when the clamped
                # combined range equals what omitting would produce — for
                # cross-address-space links, omitting would clamp from_range
                # instead and yield a different (often out-of-bounds) anchor.
                total = _ids_combined_range(area, spec)
                if total is None:
                    continue
                spec_lo = max(total[0], area.start_address)
                spec_hi = min(total[1], area.end_address)
                if (total[0] <= area.start_address
                        and total[1] >= area.end_address
                        and spec_lo == omit_lo and spec_hi == omit_hi):
                    issues.append(Issue(
                        'link-redundant-sections', f'links[{link_id}].{side}', view_id,
                        f"'{side}.sections' lists {len(spec)} section ID(s) whose "
                        f"combined range spans the whole '{view_id}' view — omit "
                        f"the field to use the whole-view default",
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


def _check_label_out_of_range(area_views: list) -> list[Issue]:
    """
    A label's address falls outside the view's address range
    [start_address, end_address].

    The renderer only draws a label when its address falls within a
    section's half-open [addr, addr+size) interval or at exactly the
    view's end address (the end of the last section).  A label whose
    address is outside [Lo, Hi] is silently not rendered.
    """
    issues = []
    for av in area_views:
        if not av.labels or not av.labels.labels:
            continue
        lo = av.start_address
        hi = av.end_address
        for label in av.labels.labels:
            if label.address < lo or label.address > hi:
                issues.append(Issue(
                    'label-out-of-range', av.view_id, label.id,
                    f"label '{label.id}' address {hex(label.address)} is outside "
                    f"the view's address range [{hex(lo)}, {hex(hi)}] — "
                    f"the label will not be rendered; correct the address in diagram.json",
                ))
    return issues


def _check_link_address_range_order(links_config: list) -> list[Issue]:
    """
    A link's ``from.sections`` or ``to.sections`` uses the address-range
    form ``["0xLO", "0xHI"]`` but LO >= HI.

    The renderer passes the range to the band-geometry code without
    checking order, so an inverted range produces a crossed or
    collapsed band.  Fix: swap the two values so LO < HI.
    """
    from loader import parse_int as _parse_int
    issues = []
    for entry in links_config:
        if not isinstance(entry, dict):
            continue
        link_id = entry.get('id', '<unnamed>')
        for side in ('from', 'to'):
            ep = entry.get(side, {})
            if not isinstance(ep, dict):
                continue
            spec = ep.get('sections')
            if not (isinstance(spec, list) and len(spec) == 2
                    and isinstance(spec[0], str) and spec[0].startswith('0x')
                    and isinstance(spec[1], str) and spec[1].startswith('0x')):
                continue
            try:
                lo = _parse_int(spec[0])
                hi = _parse_int(spec[1])
            except (ValueError, TypeError):
                continue
            if lo >= hi:
                issues.append(Issue(
                    'link-address-range-order',
                    f'links[{link_id}].{side}', None,
                    f"address range [{spec[0]}, {spec[1]}] has lo >= hi "
                    f"({hex(lo)} >= {hex(hi)}) — swap the two values; "
                    f"lo must be strictly less than hi",
                    level='ERROR',
                ))
    return issues


def _check_link_self_referential(links_config: list) -> list[Issue]:
    """
    A link's ``from.view`` and ``to.view`` reference the same view.

    A self-referential band is drawn from the right edge of the panel
    back to its left edge, producing a degenerate shape that overlaps
    or wraps around the panel body.
    """
    issues = []
    for entry in links_config:
        if not isinstance(entry, dict):
            continue
        link_id = entry.get('id', '<unnamed>')
        from_ep = entry.get('from', {})
        to_ep   = entry.get('to',   {})
        if not isinstance(from_ep, dict) or not isinstance(to_ep, dict):
            continue
        from_view = from_ep.get('view')
        to_view   = to_ep.get('view')
        if from_view and to_view and from_view == to_view:
            issues.append(Issue(
                'link-self-referential', f'links[{link_id}]', None,
                f"link connects view '{from_view}' to itself — a self-referential "
                f"band produces degenerate geometry overlapping the panel body",
            ))
    return issues


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_RULES = {
    'min-height-violated',
    'min-height-below-global',
    'min-height-on-break',
    'section-height-conflict',
    'section-name-overflow',
    'out-of-canvas',
    'link-anchor-out-of-bounds',
    'link-address-range-mappable',
    'link-redundant-sections',
    'unresolved-section',
    'section-overlap',
    'break-overlaps-section',
    'uncovered-gap',
    'panel-overlap',
    'title-overlap',
    'label-overlap',
    'addr-64bit-column-width',
    'label-out-of-range',
    'link-address-range-order',
    'link-self-referential',
}

PER_SECTION_RULES = [
    _check_min_height_violated,
    _check_min_height_below_global,
    _check_min_height_on_break,
    _check_section_height_conflict,
    _check_section_name_overflow,
]


def run_checks(diagram: dict, area_views: list,
               enabled_rules: set) -> list[Issue]:
    # Canvas bounds are always derived from actual content (no diagram 'size' field).
    if area_views:
        canvas_w = max(av.pos_x + av.size_x for av in area_views) + 110
        canvas_h = max(av.pos_y + av.size_y for av in area_views) + 30
    else:
        canvas_w, canvas_h = 400.0, 700.0
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

    # Label rules
    issues.extend(_check_label_out_of_range(area_views))

    # Link rules
    issues.extend(_check_link_address_range_order(links_config))
    issues.extend(_check_link_self_referential(links_config))
    issues.extend(_check_link_anchor_out_of_bounds(area_views, links_config))
    issues.extend(_check_link_section_form(area_views, links_config))
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
                        help=('Visual styling. Resolution order (first match wins): '
                              '(1) -t <name>  built-in theme by name: default, plantuml; '
                              '(2) -t <path>  path to a custom theme.json file; '
                              '(3) omit -t    theme.json in the same directory as diagram.json, if present; '
                              '(4) omit -t    built-in default theme. '
                              'Providing -t always takes priority over a sibling theme.json.'))
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

    # Load theme: explicit -t > auto-discovered theme.json next to diagram > built-in default
    _theme_arg = args.theme
    if _theme_arg is None:
        _sibling = os.path.join(os.path.dirname(os.path.abspath(args.diagram)), 'theme.json')
        if os.path.isfile(_sibling):
            _theme_arg = _sibling
    try:
        theme = Theme(_theme_arg)
    except (OSError, Exception) as e:
        print(f"Error loading theme: {e}", file=sys.stderr)
        sys.exit(1)

    base_style = theme.resolve('')
    links = Links(links_config=diagram.get('links', []),
                  style=theme.resolve_links())
    area_views, _ = get_area_views(base_style, diagram, theme, links=links)
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
