import copy

from helpers import safe_element_list_get, safe_element_dict_get, format_size
from labels import Labels
from loader import parse_int
from logger import logger


def section_label_min_h(section, font_size: float, size_x: float) -> float:
    """Return the label-driven minimum height for *section*.

    The size label (top-left, 12 px font) and the name label (horizontally
    centred, *font_size* px) must not overlap on the x-axis.  When they
    would, return the minimum height needed to separate them vertically;
    otherwise return 0.0 so the section keeps its floor height.

    Geometry (character-width approximation, 0.6× factor):
      size_label_right  = 2 + len(size_text)  × 0.6 × 12
      name_label_left   = size_x/2 − len(name_text) × 0.6 × font_size / 2
    Conflict → size_label_right > name_label_left.
    """
    SIZE_LABEL_FONT = 12
    name_text = section.name if section.name is not None else section.id
    size_text = format_size(section.size)
    size_label_right = 2.0 + len(size_text) * 0.6 * SIZE_LABEL_FONT
    name_left = size_x / 2.0 - len(name_text) * 0.6 * font_size / 2.0
    if size_label_right > name_left:
        return 30.0 + font_size
    return 0.0


class AreaView:
    """
    AreaView provides the container for a given set of sections and the methods to process
    and transform the information they contain into useful data for graphical representation.

    Layout model: each section is assigned its effective floor height
      max(global_min_section_height, section.min_height, label_conflict_floor)
    and sections are stacked contiguously from the top of the view (high address)
    to the bottom (low address).  The view height equals the sum of all section heights.

    Grows-arrow neighbor constraint: when a section carries a `grows-up` or `grows-down`
    flag, the layout engine automatically raises the adjacent neighbor section's floor to
    (2 × 20 × growth_arrow_size + font_size) px so the arrow does not overlap the neighbor's
    text label.

    `style` is a plain dict (resolved from theme.json at the area level).
    `theme` is the Theme object used to resolve per-section styles.
    `growth_arrow_size` is the `growth_arrow.size` multiplier from the theme (default 1.0).
    """
    pos_y: int
    pos_x: int
    address_to_pxl: float
    total_height_pxl: int
    start_address: int
    end_address: int

    def __init__(self,
                 sections,
                 style: dict,
                 area_config: dict = None,
                 theme=None,
                 labels=None,
                 is_subarea: bool = False,
                 growth_arrow_size: float = 1.0):
        self.sections = sections
        self.processed_section_views = []
        self.is_subarea = is_subarea
        self.growth_arrow_size = growth_arrow_size
        self.area = area_config or {}
        self.style = style
        self.theme = theme
        self.view_id = self.area.get('id', '')

        self.start_address = safe_element_dict_get(self.area, 'start',
                                                   self.sections.lowest_memory)
        self.end_address = safe_element_dict_get(self.area, 'end',
                                                 self.sections.highest_memory)

        pos = self.area.get('pos')
        size = self.area.get('size')
        if pos is None or size is None:
            raise ValueError(
                f"AreaView '{self.view_id}': 'pos' and 'size' must be set on "
                "area_config (assigned by auto-layout)"
            )
        self.pos_x, self.pos_y = pos[0], pos[1]
        self.size_x, self.size_y = size[0], size[1]

        label_style = theme.resolve_labels() if theme else style
        view_id = safe_element_dict_get(self.area, 'id', '')
        label_overrides = theme.resolve_label_overrides(view_id) if theme else {}
        self.labels = Labels(
            safe_element_dict_get(self.area, 'labels', []),
            label_style,
            label_overrides,
        )
        self.title = safe_element_dict_get(self.area, 'title', '')

        # Guard against degenerate address/size ranges that would turn the
        # address-to-pixel conversion into a division by zero.  Both of these
        # indicate a bad diagram (either an all-zero-size section set or a
        # view pinned to zero height), not a legitimate render input.
        if self.size_y <= 0:
            raise ValueError(
                f"AreaView '{self.view_id}': size_y must be > 0, got {self.size_y}"
            )
        if self.end_address <= self.start_address:
            raise ValueError(
                f"AreaView '{self.view_id}': end_address ({self.end_address:#x}) "
                f"must be greater than start_address ({self.start_address:#x}); "
                "check section sizes and any explicit 'start'/'end' overrides"
            )
        self.address_to_pxl = (self.end_address - self.start_address) / self.size_y

        if not self.is_subarea:
            self._process()

    def get_split_area_views(self) -> list:
        """Return the processed area views (always a single-element list: [self])."""
        return self.processed_section_views

    def to_pixels(self, value) -> float:
        """Convert a memory size/offset to pixels (absolute ratio)."""
        return value / self.address_to_pxl

    def to_pixels_relative(self, value) -> float:
        """
        Convert an address to pixels relative to this area's start address.
        Result is measured from the top of the area downward (SVG y-axis convention).

        With the floor-stack layout every section has size_y_override set, so
        address_to_py_actual() gives exact positions for addresses inside a section.
        This method is retained as a fallback for addresses that fall in gaps
        between sections (e.g. label arrows pointing at section boundaries).
        """
        return self.size_y - ((value - self.start_address) / self.address_to_pxl)

    def address_to_py_actual(self, address) -> float:
        """
        Map `address` to a y-pixel offset within this area, using the stacked
        section positions set by _process().

        Iterates sections to find which one owns `address` and interpolates
        within its pixel bounds so that link band endpoints and label arrows
        align exactly with the rendered section box edges.

        Falls back to to_pixels_relative() for addresses in gaps between sections.
        """
        for s in self.sections.get_sections():
            if s.is_break() or s.size == 0:
                continue
            if s.size_y_override is None or s.pos_y_in_subarea is None:
                continue
            s_lo = s.address
            s_hi = s.address + s.size
            if s_lo <= address <= s_hi:
                # frac = 0 at top (high address), 1 at bottom (low address).
                frac = (s_hi - address) / s.size
                return s.pos_y_in_subarea + frac * s.size_y_override
        return self.to_pixels_relative(address)

    def _overwrite_sections_info(self):
        """
        Apply theme styles to each section.

        Style comes from the theme (area-level + section-level resolution).
        Structural overrides (address, size, flags) are already applied during
        section resolution in loader.resolve_view_sections() — no per-view
        override logic is needed here.
        """
        for section in self.sections.get_sections():
            # Resolve style from theme; fall back to area-level style dict
            if self.theme:
                section.style = self.theme.resolve(self.view_id, section.id)
                section.addr_label_style = self.theme.resolve(self.view_id)
            else:
                section.style = copy.deepcopy(self.style)
                section.addr_label_style = copy.deepcopy(self.style)

    def _section_label_min_h(self, section, font_size: float) -> float:
        return section_label_min_h(section, font_size, self.size_x)

    def _process(self):
        """
        Assign each section its floor height and stack them top-to-bottom.

        Pass 1 — floor height for each section:
          non-break: max(global_min_section_height, section.min_height, label_conflict_floor)
          break:     break_height from the style

        Pass 2 — grows-arrow neighbor constraint:
          For each section with a grows-up/down flag, raise the immediately adjacent
          neighbor's floor to (2 × 20 × growth_arrow_size + font_size) px so the rendered
          growth arrow does not overlap the neighbor's text label.
          grows-up  → neighbor is the section with the next-higher address (SVG-above, index i-1)
          grows-down → neighbor is the section with the next-lower  address (SVG-below, index i+1)
          Break neighbors are not raised (they have no text label to protect).

        All sections are sorted high-address-first (SVG top = high address) and
        stacked contiguously.  The view height equals the sum of all section heights.
        """
        self._overwrite_sections_info()

        all_sections = [s for s in self.sections.get_sections() if s.size > 0]
        if not all_sections:
            print("Filtered sections produced no results")
            return

        font_size = float(self.style.get('font_size', 16))
        user_min_h_val = float(self.style.get('min_section_height') or 0)
        break_height_val = float(self.style.get('break_height', 20))

        # Sort high-address-first: SVG y=0 is the top (highest address).
        sorted_sections = sorted(all_sections,
                                 key=lambda s: s.address + s.size, reverse=True)

        # Pass 1: assign each section its initial floor height.
        for s in sorted_sections:
            if s.is_break():
                h = break_height_val
            else:
                h = max(
                    user_min_h_val,
                    s.min_height if s.min_height is not None else 0.0,
                    self._section_label_min_h(s, font_size),
                )
                h = max(h, 1.0)
            s.size_y_override = h

        # Pass 2: grows-arrow neighbor constraint.
        # The arrow occupies arrow_h px at one end of the neighbor section.
        # For the text center (h/2) to clear the arrow tip:
        #   h/2 + font_size/2 < h - arrow_h  →  h > 2*arrow_h + font_size
        arrow_neighbor_floor = 2.0 * 20.0 * self.growth_arrow_size + font_size
        for i, s in enumerate(sorted_sections):
            if s.is_break():
                continue
            if s.is_grow_up() and i > 0:
                nb = sorted_sections[i - 1]
                if not nb.is_break():
                    nb.size_y_override = max(nb.size_y_override, arrow_neighbor_floor)
            if s.is_grow_down() and i < len(sorted_sections) - 1:
                nb = sorted_sections[i + 1]
                if not nb.is_break():
                    nb.size_y_override = max(nb.size_y_override, arrow_neighbor_floor)

        # Stack positions top-to-bottom.
        y = 0.0
        for s in sorted_sections:
            s.pos_y_in_subarea = y
            y += s.size_y_override

        self.size_y = y
        self.address_to_pxl = (self.end_address - self.start_address) / self.size_y
        self.processed_section_views.append(self)

    def apply_section_geometry(self, section) -> None:
        """Set size_x/size_y/pos_x/pos_y on *section* from this area's geometry.

        Uses size_y_override / pos_y_in_subarea set by _process().
        Called by both the renderer and check.py so they share one code path.
        """
        section.size_x = self.size_x
        section.pos_x = 0
        if section.size_y_override is not None:
            section.size_y = section.size_y_override
            section.pos_y = section.pos_y_in_subarea
        else:
            section.size_y = self.to_pixels(section.size)
            section.pos_y = self.to_pixels(
                self.end_address - section.size - section.address)
