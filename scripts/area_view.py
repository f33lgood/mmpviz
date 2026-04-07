import copy

from helpers import safe_element_list_get, safe_element_dict_get, DefaultAppValues
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
        self.area_id = self.area.get('id', '')

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

    def _overwrite_sections_info(self):
        """
        Apply style and flag overrides to each section.

        Style comes from the theme (area-level + section-level resolution).
        Flags and structural overrides (address, size, type) come from diagram.json area config.
        """
        for section in self.sections.get_sections():
            # Resolve style from theme; fall back to area-level style dict
            if self.theme:
                section.style = self.theme.resolve(self.area_id, section.id)
            else:
                section.style = copy.deepcopy(self.style)

            # Apply diagram config overrides (flags, address, size, type) — no style here
            inner_sections = safe_element_dict_get(self.area, 'sections', []) or []
            for element in inner_sections:
                section_names = safe_element_dict_get(element, 'names', []) or []
                for item in section_names:
                    if item == section.id:
                        section.address = element.get('address', section.address)
                        section.type = element.get('type', section.type)
                        section.size = element.get('size', section.size)
                        # APPEND new flags (config adds to map-file flags)
                        for flag in element.get('flags', []):
                            if flag not in section.flags:
                                section.flags.append(flag)

    def _process(self):
        def recalculate_subarea_size_y(start_mem_addr, end_mem_addr):
            return (self.to_pixels(end_mem_addr - start_mem_addr) /
                    total_non_breaks_size_y_px) * (total_non_breaks_size_y_px + expandable_size_px)

        def area_config_clone(configuration, pos_y_px, size_y_px, start_mem_addr, end_mem_addr):
            new_config = copy.deepcopy(configuration)
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
        breaks_section_size_y_px = self.style.get('break_size', 20)

        if not area_has_breaks:
            self.processed_section_views.append(self)
            return

        total_breaks_size_y_px = self._get_break_total_size_before_transform_px()
        total_non_breaks_size_y_px = self._get_non_breaks_total_size_px(total_breaks_size_y_px)
        expandable_size_px = total_breaks_size_y_px - (breaks_section_size_y_px * breaks_count)

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

            corrected_size_y_px = (
                breaks_section_size_y_px if section_group.is_break_section_group()
                else recalculate_subarea_size_y(start_addr, end_addr)
            )

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

    def _get_break_total_size_before_transform_px(self) -> float:
        total = 0.0
        for _break in self.sections.filter_breaks().get_sections():
            total += self.to_pixels(_break.size)
        return total

    def _get_non_breaks_total_size_px(self, breaks_size_y_sum_px) -> float:
        highest_mem = max(self.end_address, self.sections.highest_memory)
        lowest_mem = min(self.start_address, self.sections.lowest_memory)
        return self.to_pixels(highest_mem - lowest_mem) - breaks_size_y_sum_px
