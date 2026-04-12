import copy

from helpers import safe_element_list_get, safe_element_dict_get, DefaultAppValues, format_size
from labels import Labels
from loader import parse_int
from logger import logger


class AreaView:
    """
    AreaView provides the container for a given set of sections and the methods to process
    and transform the information they contain into useful data for graphical representation.

    `style` is a plain dict (resolved from theme.json at the area level).
    `theme` is the Theme object used to resolve per-section styles.
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
                 is_subarea: bool = False):
        self.sections = sections
        self.processed_section_views = []
        self.is_subarea = is_subarea
        self.area = area_config or {}
        self.style = style
        self.theme = theme
        self.view_id = self.area.get('id', '')

        self.start_address = safe_element_dict_get(self.area, 'start',
                                                   self.sections.lowest_memory)
        self.end_address = safe_element_dict_get(self.area, 'end',
                                                 self.sections.highest_memory)

        self.pos_x = safe_element_list_get(
            safe_element_dict_get(self.area, 'pos'), 0,
            default=DefaultAppValues.POSITION_X)
        self.pos_y = safe_element_list_get(
            safe_element_dict_get(self.area, 'pos'), 1,
            default=DefaultAppValues.POSITION_Y)
        self.size_x = safe_element_list_get(
            safe_element_dict_get(self.area, 'size'), 0,
            default=DefaultAppValues.SIZE_X)
        self.size_y = safe_element_list_get(
            safe_element_dict_get(self.area, 'size'), 1,
            default=DefaultAppValues.SIZE_Y)

        label_style = theme.resolve_labels() if theme else style
        self.labels = Labels(safe_element_dict_get(self.area, 'labels', []), label_style)
        self.title = safe_element_dict_get(self.area, 'title', DefaultAppValues.TITLE)
        self.address_to_pxl = (self.end_address - self.start_address) / self.size_y

        if not self.is_subarea:
            self._process()

    def get_split_area_views(self) -> list:
        """
        Get current area view split in multiple area views around break sections.
        """
        return self.processed_section_views

    def to_pixels(self, value) -> float:
        """Convert a memory size/offset to pixels (absolute ratio)."""
        return value / self.address_to_pxl

    def to_pixels_relative(self, value) -> float:
        """
        Convert an address to pixels relative to this area's start address.
        Result is measured from the top of the area downward (SVG y-axis convention).
        """
        return self.size_y - ((value - self.start_address) / self.address_to_pxl)

    def address_to_py_actual(self, address) -> float:
        """
        Map `address` to a y-pixel offset within this (sub)area, respecting
        per-section size_y_override positions when set.

        When the per-section height algorithm assigns non-proportional heights,
        to_pixels_relative() returns a proportional estimate that does not match
        the actual rendered position.  This method looks up the section that owns
        `address` and interpolates within its actual override bounds, so that link
        band endpoints align exactly with the rendered section box edges.

        Falls back to to_pixels_relative() when no overrides are present.
        """
        for s in self.sections.get_sections():
            if s.is_hidden() or s.is_break() or s.size == 0:
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

        Palette indices are assigned in address order, counting only non-break
        sections (break sections are visual separators and do not consume a
        palette slot).
        """
        # Pre-pass: assign a palette index to each non-break section.
        palette_index = 0
        palette_indices = {}
        for section in self.sections.get_sections():
            if not section.is_break():
                palette_indices[section.id] = palette_index
                palette_index += 1

        for section in self.sections.get_sections():
            # Resolve style from theme; fall back to area-level style dict
            if self.theme:
                section.style = self.theme.resolve(
                    self.view_id, section.id,
                    palette_index=palette_indices.get(section.id))
                section.addr_label_style = self.theme.resolve(self.view_id)
            else:
                section.style = copy.deepcopy(self.style)
                section.addr_label_style = copy.deepcopy(self.style)

    def _compute_per_section_heights(self, sections, available_px, min_h, max_h):
        """
        Distribute `available_px` among sections using a per-section iterative
        lock-at-min_h algorithm (proposal §2.3).

        Phase 1: iteratively lock sections below min_h at min_h, re-proportionalise
        the remaining budget for unlocked sections until convergence.

        Phase 2 (post-process): cap any section that still exceeds max_h and
        redistribute the freed surplus to floored (min_h-locked) sections first,
        then to any remaining uncapped section.

        Separating the two phases is critical: mixing ceiling locks into the
        floor-locking overflow check causes a false overflow when a large section
        simultaneously needs a max_h cap and several small sections need min_h
        floors (the cap consumes budget before the floors can be satisfied).

        Hidden/break sections are excluded; size-0 sections are skipped.
        Returns {id(section): height_px}.
        """
        sections = [s for s in sections if s.size > 0]
        if not sections or available_px <= 0:
            return {}

        def sbytes(s):
            return max(s.size, 1)

        total_bytes = sum(sbytes(s) for s in sections)
        heights = {id(s): available_px * sbytes(s) / total_bytes for s in sections}
        locked = {}
        lock_is_floor = set()

        # Phase 1: lock sections at min_h only (no max_h ceiling here).
        for _ in range(len(sections) + 1):
            new_locks = {}
            new_floors = set()
            for s in sections:
                if id(s) in locked or s.is_hidden() or s.is_break():
                    continue
                h = heights[id(s)]
                lo = (min_h.get(id(s), 0.0) if isinstance(min_h, dict)
                      else (float(min_h) if min_h is not None else 0.0))
                if h < lo:
                    new_locks[id(s)] = lo
                    new_floors.add(id(s))

            if not new_locks:
                break

            proposed_locked_px = sum(locked.values()) + sum(new_locks.values())
            if proposed_locked_px >= available_px:
                # Cannot honour all min_h floors — fall back to pure proportional.
                return {id(s): available_px * sbytes(s) / total_bytes for s in sections}

            locked.update(new_locks)
            lock_is_floor.update(new_floors)

            locked_bytes = sum(sbytes(s) for s in sections if id(s) in locked)
            free_px = available_px - sum(locked.values())
            free_bytes = total_bytes - locked_bytes

            for s in sections:
                if id(s) in locked:
                    heights[id(s)] = locked[id(s)]
                elif free_bytes > 0:
                    heights[id(s)] = free_px * sbytes(s) / free_bytes

        # Phase 2: apply max_h ceiling and redistribute freed surplus.
        if max_h is not None:
            hi = float(max_h)
            surplus = 0.0
            for s in sections:
                if not s.is_hidden() and not s.is_break() and heights[id(s)] > hi:
                    surplus += heights[id(s)] - hi
                    heights[id(s)] = hi
            if surplus > 1e-6:
                floored = [s for s in sections if id(s) in lock_is_floor]
                if floored:
                    floor_bytes = sum(sbytes(s) for s in floored)
                    for s in floored:
                        heights[id(s)] += surplus * sbytes(s) / floor_bytes
                else:
                    uncapped = [s for s in sections
                                if not s.is_hidden() and not s.is_break()
                                and heights[id(s)] < hi]
                    if uncapped:
                        unc_bytes = sum(sbytes(s) for s in uncapped)
                        for s in uncapped:
                            heights[id(s)] += surplus * sbytes(s) / unc_bytes

        # Redistribute any residual surplus from the floor-locking phase.
        if locked:
            total_h = sum(heights[id(s)] for s in sections)
            surplus = available_px - total_h
            if surplus > 1e-6:
                floored = [s for s in sections if id(s) in lock_is_floor]
                if floored:
                    floor_bytes = sum(sbytes(s) for s in floored)
                    for s in floored:
                        heights[id(s)] += surplus * sbytes(s) / floor_bytes

        return heights

    def _section_label_min_h(self, section, font_size: float) -> float:
        """Return the label-driven minimum height for *section*.

        The size label (top-left, 12 px font) and the name label (horizontally
        centred, *font_size* px) must not overlap on the x-axis.  When they
        would, return the minimum height needed to separate them vertically;
        otherwise return 0.0 so the section keeps its proportional height.

        Geometry (character-width approximation, 0.6× factor):
          size_label_right  = 2 + len(size_text)  × 0.6 × 12
          name_label_left   = size_x/2 − len(name_text) × 0.6 × font_size / 2
        Conflict → size_label_right > name_label_left.
        """
        SIZE_LABEL_FONT = 12
        name_text = section.name if section.name is not None else section.id
        size_text = format_size(section.size)
        size_label_right = 2.0 + len(size_text) * 0.6 * SIZE_LABEL_FONT
        name_left = self.size_x / 2.0 - len(name_text) * 0.6 * font_size / 2.0
        if size_label_right > name_left:
            return 30.0 + font_size
        return 0.0

    def _compute_clamped_heights(self, section_groups, available_px, min_section_h, max_section_h):
        """
        Distribute `available_px` among non-break subarea groups using an iterative
        floor/ceiling algorithm:
          - Each group's minimum height is derived from min_section_h so that the
            *smallest* visible section within that group will be at least min_section_h
            pixels tall when rendered linearly inside the subarea.
          - max_section_h caps any single subarea's height (optional).
        Returns a dict {id(group): height_px}.
        """
        non_break = [g for g in section_groups if not g.is_break_section_group()]
        if not non_break:
            return {}

        def group_range(g):
            return max(g.highest_memory - g.lowest_memory, 1)

        def min_required(g):
            if min_section_h is None:
                return 0
            rng = group_range(g)
            visible = [s for s in g.get_sections()
                       if 'hidden' not in s.flags and 'break' not in s.flags and s.size > 0]
            if not visible:
                return float(min_section_h)
            min_prop = min(s.size / rng for s in visible)
            return min_section_h / min_prop if min_prop > 0 else float(min_section_h)

        total_bytes = sum(group_range(g) for g in non_break)
        heights = {id(g): available_px * group_range(g) / total_bytes for g in non_break}

        # locked: groups whose height has been fixed at a floor or ceiling.
        # Once locked, a group is excluded from re-proportionalization so that
        # floors set in earlier iterations are not silently undone.
        locked = {}        # id(g) -> locked height
        lock_is_floor = set()  # ids of groups locked at their floor (not their cap)

        for _ in range(50):
            new_locks = {}
            new_floors = set()
            for g in non_break:
                if id(g) in locked:
                    continue
                lo = min_required(g)
                hi = max(max_section_h, lo) if max_section_h is not None else float('inf')
                h = heights[id(g)]
                if h < lo:
                    new_locks[id(g)] = lo
                    new_floors.add(id(g))
                elif h > hi:
                    new_locks[id(g)] = hi

            if not new_locks:
                break

            locked.update(new_locks)
            lock_is_floor.update(new_floors)

            locked_px = sum(locked.values())
            if locked_px >= available_px:
                # Cannot satisfy all constraints — fall back to proportional
                heights = {id(g): available_px * group_range(g) / total_bytes for g in non_break}
                locked.clear()
                lock_is_floor.clear()
                break

            locked_bytes = sum(group_range(g) for g in non_break if id(g) in locked)
            free_px = available_px - locked_px
            free_bytes = total_bytes - locked_bytes

            for g in non_break:
                if id(g) in locked:
                    heights[id(g)] = locked[id(g)]
                elif free_bytes > 0:
                    heights[id(g)] = free_px * group_range(g) / free_bytes

        # If all groups were locked and the total is less than available_px, the
        # remaining space has nowhere to go (every group hit a constraint).
        # Redistribute the surplus proportionally among floored groups so the
        # panel has no blank stripe.
        if locked:
            total_h = sum(heights[id(g)] for g in non_break)
            surplus = available_px - total_h
            if surplus > 1e-6:
                floored = [g for g in non_break if id(g) in lock_is_floor]
                if floored:
                    floor_bytes = sum(group_range(g) for g in floored)
                    for g in floored:
                        heights[id(g)] = locked[id(g)] + surplus * group_range(g) / floor_bytes

        return heights

    def _process(self):
        def recalculate_subarea_size_y(start_mem_addr, end_mem_addr):
            return (self.to_pixels(end_mem_addr - start_mem_addr) /
                    total_non_breaks_size_y_px) * (total_non_breaks_size_y_px + expandable_size_px)

        def area_config_clone(configuration, pos_y_px, size_y_px, start_mem_addr, end_mem_addr):
            new_config = copy.deepcopy(configuration)
            # Preserve the parent area's size_x; only override size_y.
            # Using DefaultAppValues.SIZE_X would break link-band geometry when
            # auto-layout assigns a column width != 200.
            if 'size' not in new_config:
                new_config['size'] = [DefaultAppValues.SIZE_X, DefaultAppValues.SIZE_Y]
            if new_config.get('pos') is None:
                new_config['pos'] = [DefaultAppValues.POSITION_X, DefaultAppValues.POSITION_Y]
            new_config['size'][1] = size_y_px
            new_config['pos'][1] = pos_y_px - size_y_px
            new_config['start'] = start_mem_addr
            new_config['end'] = end_mem_addr
            return new_config

        self._overwrite_sections_info()

        if len(self.sections.get_sections()) == 0:
            print("Filtered sections produced no results")
            return

        split_section_groups = self.sections.split_sections_around_breaks()

        breaks_count = len(self.sections.filter_breaks().get_sections())
        area_has_breaks = breaks_count >= 1
        breaks_section_size_y_px = self.style.get('break_height', 20)

        if not area_has_breaks:
            # Apply min/max section-height clamping even when there are no breaks.
            # Without this, sections whose byte size is small relative to the
            # view's address range render at sub-20-px heights and text overlaps.
            max_section_h = self.style.get('max_section_height', None)
            font_size = float(self.style.get('font_size', 16))
            user_min_h = self.style.get('min_section_height', None)
            user_min_h_val = float(user_min_h) if user_min_h is not None else 0.0

            all_visible = [
                s for s in self.sections.get_sections()
                if not s.is_hidden() and not s.is_break() and s.size > 0
            ]

            if all_visible and (user_min_h_val > 0.0 or max_section_h is not None):
                total_range = max(self.end_address - self.start_address, 1)
                section_bytes = sum(s.size for s in all_visible)
                available_for_sections = section_bytes / total_range * self.size_y

                # Use user_min_h only (not label-conflict inflation) so that
                # very long section names in a small panel don't push the total
                # minimum above available_px and trigger the proportional fallback.
                per_section_min_h = {id(s): user_min_h_val for s in all_visible}

                section_px = self._compute_per_section_heights(
                    all_visible, available_for_sections, per_section_min_h, max_section_h)

                if section_px:
                    # Stack sections high-address-first within the section block.
                    # The block is anchored at the address-proportional top of the
                    # highest section; gaps between the block and panel edges are preserved.
                    sorted_vis = sorted(all_visible,
                                       key=lambda s: s.address + s.size, reverse=True)
                    highest_top = max(s.address + s.size for s in all_visible)
                    block_top_px = self.to_pixels_relative(highest_top)
                    y = block_top_px
                    for s in sorted_vis:
                        s.size_y_override = section_px.get(id(s), 0.0)
                        s.pos_y_in_subarea = y
                        y += s.size_y_override

            self.processed_section_views.append(self)
            return

        total_breaks_size_y_px = self._get_break_total_size_before_transform_px()
        total_non_breaks_size_y_px = self._get_non_breaks_total_size_px(total_breaks_size_y_px)
        expandable_size_px = total_breaks_size_y_px - (breaks_section_size_y_px * breaks_count)
        available_for_non_breaks = total_non_breaks_size_y_px + expandable_size_px

        max_section_h = self.style.get('max_section_height', None)

        font_size = float(self.style.get('font_size', 16))
        user_min_h = self.style.get('min_section_height', None)
        user_min_h_val = float(user_min_h) if user_min_h is not None else 0.0

        clamped_heights = None
        # Collect only VISIBLE (non-hidden, non-break) sections.
        # Hidden sections act as sub-section overlays in other views and must
        # NOT be included here — their sizes overlap with visible sections and
        # would inflate total_bytes, diluting visible section heights.
        all_visible = []
        for g in split_section_groups:
            if not g.is_break_section_group():
                all_visible.extend([
                    s for s in g.get_sections()
                    if not s.is_hidden() and not s.is_break() and s.size > 0
                ])

        # Per-section min_h: apply the label-conflict floor only for sections
        # where the size label (top-left) and name label (centred) would overlap
        # on the x-axis at the current section width.  Non-conflicting sections
        # keep their proportional height (floor = 0.0 or user_min_h).
        per_section_min_h = {
            id(s): max(user_min_h_val, self._section_label_min_h(s, font_size))
            for s in all_visible
        }

        section_px = self._compute_per_section_heights(
            all_visible, available_for_non_breaks, per_section_min_h, max_section_h)

        if section_px:
            # Assign size_y_override and pos_y_in_subarea per visible section,
            # then derive each group's height as the sum of its visible section heights.
            group_heights = {}
            for g in split_section_groups:
                if g.is_break_section_group():
                    continue
                visible_in_group = [
                    s for s in g.get_sections()
                    if not s.is_hidden() and not s.is_break() and s.size > 0
                ]
                # Sort high-address-first: top of SVG = highest address.
                sorted_vis = sorted(visible_in_group,
                                    key=lambda s: s.address + s.size, reverse=True)
                y = 0.0
                for s in sorted_vis:
                    s.size_y_override = section_px.get(id(s), 0.0)
                    s.pos_y_in_subarea = y
                    y += s.size_y_override
                if y > 0:
                    group_heights[id(g)] = y
            clamped_heights = group_heights if group_heights else None

        last_area_pos = self.pos_y + self.size_y

        for i, section_group in enumerate(split_section_groups):
            if section_group is split_section_groups[0]:
                start_addr = self.start_address
                end_addr = (split_section_groups[1].lowest_memory
                            if len(split_section_groups) > 1 else self.end_address)
            elif section_group is split_section_groups[-1]:
                end_addr = max(self.end_address, section_group.highest_memory)
                start_addr = split_section_groups[-2].highest_memory
            elif section_group.is_break_section_group():
                start_addr = section_group.lowest_memory
                end_addr = section_group.highest_memory
            else:
                start_addr = split_section_groups[i - 1].highest_memory
                end_addr = split_section_groups[i + 1].lowest_memory

            if section_group.is_break_section_group():
                corrected_size_y_px = breaks_section_size_y_px
            elif clamped_heights is not None:
                corrected_size_y_px = clamped_heights.get(id(section_group),
                                                           recalculate_subarea_size_y(start_addr, end_addr))
            else:
                corrected_size_y_px = recalculate_subarea_size_y(start_addr, end_addr)

            subconfig = area_config_clone(
                self.area, last_area_pos, corrected_size_y_px, start_addr, end_addr)
            last_area_pos = subconfig['pos'][1]

            self.processed_section_views.append(AreaView(
                sections=section_group,
                area_config=subconfig,
                style=self.style,
                theme=self.theme,
                is_subarea=True,
            ))

    def apply_section_geometry(self, section) -> None:
        """Set size_x/size_y/pos_x/pos_y on *section* from this subarea's geometry.

        Uses size_y_override / pos_y_in_subarea when the per-section height
        algorithm has run; falls back to proportional pixel mapping otherwise.
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

    def _get_break_total_size_before_transform_px(self) -> float:
        total = 0.0
        for _break in self.sections.filter_breaks().get_sections():
            total += self.to_pixels(_break.size)
        return total

    def _get_non_breaks_total_size_px(self, breaks_size_y_sum_px) -> float:
        highest_mem = max(self.end_address, self.sections.highest_memory)
        lowest_mem = min(self.start_address, self.sections.lowest_memory)
        return self.to_pixels(highest_mem - lowest_mem) - breaks_size_y_sum_px
