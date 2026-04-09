import xml.etree.ElementTree as ET

from helpers import DefaultAppValues, format_size
from labels import Side
from logger import logger
from section import Section
from svg_builder import SVGBuilder, translate, rotate


def _s(style: dict, key: str, default=None):
    """Shorthand for style dict access with default."""
    return style.get(key, default)


class MapRenderer:
    """
    Renders the memory map diagram to SVG.

    Takes area views, links, and a base style dict, and produces an SVG string via draw().
    No file I/O — the caller (cli.py) writes the result.
    """

    def __init__(self, area_views: list, links, style: dict,
                 size=DefaultAppValues.DOCUMENT_SIZE):
        self.area_views = area_views
        self.links = links
        self.style = style
        self.size = size
        self.svg = SVGBuilder(size[0], size[1])
        self.links_sections = (self._get_valid_linked_sections(links.sections)
                                if links is not None else [])

    def _get_valid_linked_sections(self, linked_sections: list) -> list:
        """
        Compute valid (start_addr, end_addr) pairs for section links.
        A link is valid only if both addresses exist within the same area.
        """
        l_sections = []
        for linked_section in linked_sections:
            appended = False
            multi_section = isinstance(linked_section, list)

            for area in self.area_views:
                start = None
                end = None
                if appended:
                    break

                for section in area.sections.get_sections():
                    if not multi_section:
                        if section.id == linked_section:
                            l_sections.append([section.address, section.address + section.size])
                            appended = True
                            break
                    else:
                        if section.id == linked_section[0]:
                            start = section.address
                        elif section.id == linked_section[1]:
                            end = section.address + section.size
                        if start is not None and end is not None:
                            l_sections.append([start, end])
                            appended = True
                            break

                if multi_section and not appended and (start is not None or end is not None):
                    logger.warning(
                        f"Multi-section link spans different areas (unsupported): "
                        f"{linked_section[0]}, {linked_section[1]}")
                    break

        return l_sections

    def draw(self) -> str:
        """Render the diagram and return the SVG string."""
        svg = self.svg

        # Background rectangle
        bg = svg.rect(0, 0, self.size[0], self.size[1],
                      fill=_s(self.style, 'background', 'white'))
        svg.root.append(bg)

        growths_group = svg.g()

        # Section links (zoom bands from areas[0])
        if self.links_sections:
            svg.root.append(self._draw_section_links())

        # Sub-section links (zoom bands from named detail areas)
        if self.links and self.links.sub_sections:
            svg.root.append(self._draw_sub_section_links())

        # Address links (horizontal lines)
        if self.links:
            svg.root.append(self._draw_links())

        # Areas
        for area_view in self.area_views:
            svg.root.append(self._draw_area(area_view, growths_group))

        # Labels
        svg.root.append(self._draw_labels())

        # Growth arrows (drawn last to appear on top)
        svg.root.append(self._draw_growths(growths_group))

        return svg.to_string()

    # ------------------------------------------------------------------
    # Area drawing
    # ------------------------------------------------------------------

    def _draw_area(self, area, growths_group: ET.Element) -> ET.Element:
        area_group = self.svg.g()

        title = self._make_title(area)
        translate(title, area.pos_x, area.pos_y)
        area_group.append(title)

        for sub_area in area.get_split_area_views():
            subarea_group = self.svg.g()
            subarea_group.append(self._make_main_frame(sub_area))

            for section in sub_area.sections.get_sections():
                if section.is_hidden():
                    continue
                self._make_section(subarea_group, section, sub_area)

            translate(subarea_group, sub_area.pos_x, sub_area.pos_y)
            area_group.append(subarea_group)

        return area_group

    # ------------------------------------------------------------------
    # Section rendering
    # ------------------------------------------------------------------

    def _make_section(self, group: ET.Element, section: Section, area_view) -> ET.Element:
        section.size_x = area_view.size_x
        if section.size_y_override is not None:
            section.size_y = section.size_y_override
            section.pos_y = section.pos_y_in_subarea
        else:
            section.size_y = area_view.to_pixels(section.size)
            section.pos_y = area_view.to_pixels(
                area_view.end_address - section.size - section.address)
        section.pos_x = 0

        group.append(self._make_box(section))
        if not section.is_name_hidden():
            group.append(self._make_name(section))
        if not section.is_address_hidden():
            group.append(self._make_address(section))
        if not section.is_end_address_hidden():
            group.append(self._make_end_address(section))
        if not section.is_size_hidden():
            group.append(self._make_size_label(section))

        return group

    def _make_main_frame(self, area_view) -> ET.Element:
        style = area_view.style
        return self.svg.rect(0, 0, area_view.size_x, area_view.size_y,
                             fill=_s(style, 'background', 'white'),
                             stroke=_s(style, 'stroke', 'black'),
                             stroke_width=_s(style, 'stroke_width', 1))

    def _make_box(self, section: Section) -> ET.Element:
        style = section.style
        if section.is_break():
            fill = _s(style, 'break_fill', _s(style, 'fill', 'lightgrey'))
        else:
            fill = _s(style, 'fill', 'lightgrey')
        return self.svg.rect(section.pos_x, section.pos_y, section.size_x, section.size_y,
                             fill=fill,
                             stroke=_s(style, 'stroke', 'black'),
                             stroke_width=_s(style, 'stroke_width', 1))

    # ------------------------------------------------------------------
    # Text elements
    # ------------------------------------------------------------------

    def _make_text(self, content: str, x, y, style: dict,
                   anchor='middle', baseline='middle', text_type='normal') -> ET.Element:
        if text_type == 'title':
            font_size = '24px'
        elif text_type == 'small':
            font_size = '12px'
        else:
            font_size = _s(style, 'font_size', 16)

        return self.svg.text(
            content, x, y,
            stroke=_s(style, 'text_stroke', 'black'),
            fill=_s(style, 'text_fill', 'black'),
            stroke_width=_s(style, 'text_stroke_width', 0),
            font_size=font_size,
            font_weight='normal',
            font_family=_s(style, 'font_family', 'Helvetica'),
            text_anchor=anchor,
            alignment_baseline=baseline,
        )

    def _make_title(self, area_view) -> ET.Element:
        return self._make_text(
            area_view.title,
            area_view.size_x / 2, -20,
            style=area_view.style,
            anchor='middle',
            text_type='title',
        )

    def _make_name(self, section: Section) -> ET.Element:
        name = section.name if section.name is not None else section.id
        return self._make_text(
            name,
            section.name_label_pos_x, section.name_label_pos_y,
            style=section.style,
            anchor='middle',
        )

    def _make_size_label(self, section: Section) -> ET.Element:
        return self._make_text(
            format_size(section.size),
            section.size_label_pos[0], section.size_label_pos[1],
            style=section.style,
            anchor='start',
            baseline='hanging',
            text_type='small',
        )

    def _make_address(self, section: Section) -> ET.Element:
        return self._make_text(
            f"0x{section.address:08x}",
            section.addr_label_pos_x, section.addr_label_pos_y,
            style=section.style,
            anchor='start',
        )

    def _make_end_address(self, section: Section) -> ET.Element:
        return self._make_text(
            f"0x{section.address + section.size:08x}",
            section.addr_label_pos_x, section.end_addr_label_pos_y,
            style=section.style,
            anchor='start',
            baseline='middle',
        )

    # ------------------------------------------------------------------
    # Growth arrows
    # ------------------------------------------------------------------

    def _draw_growths(self, growths_group: ET.Element) -> ET.Element:
        for area_view in self.area_views:
            for subarea in area_view.get_split_area_views():
                area_growth = self.svg.g()
                for section in subarea.sections.get_sections():
                    if section.is_hidden():
                        continue
                    area_growth.append(self._make_growth(section))
                translate(area_growth, subarea.pos_x, subarea.pos_y)
                growths_group.append(area_growth)
        return growths_group

    def _make_growth(self, section: Section) -> ET.Element:
        group = self.svg.g()
        style = section.style
        multiplier = _s(style, 'growth_arrow_size', 1)
        mid_x = (section.pos_x + section.size_x) / 2
        arrow_head_width = 5 * multiplier
        arrow_head_height = 10 * multiplier
        arrow_length = 10 * multiplier
        arrow_tail_width = 1 * multiplier

        def make_arrow(arrow_start_y, direction):
            pts = [
                (mid_x - arrow_tail_width, arrow_start_y),
                (mid_x - arrow_tail_width, arrow_start_y - direction * arrow_length),
                (mid_x - arrow_head_width, arrow_start_y - direction * arrow_head_height),
                (mid_x, arrow_start_y - direction * (arrow_length + arrow_head_height)),
                (mid_x + arrow_head_width, arrow_start_y - direction * arrow_head_height),
                (mid_x + arrow_tail_width, arrow_start_y - direction * arrow_length),
                (mid_x + arrow_tail_width, arrow_start_y),
            ]
            group.append(self.svg.polyline(
                pts,
                stroke=_s(style, 'growth_arrow_stroke', 'black'),
                stroke_width=1,
                fill=_s(style, 'growth_arrow_fill', 'white')))

        if section.is_grow_up():
            make_arrow(section.pos_y, 1)
        if section.is_grow_down():
            make_arrow(section.pos_y + section.size_y, -1)

        return group

    # ------------------------------------------------------------------
    # Labels
    # ------------------------------------------------------------------

    def _draw_labels(self) -> ET.Element:
        global_labels = self.svg.g()
        for area in self.area_views:
            for subarea in area.get_split_area_views():
                g = self.svg.g()
                if subarea.labels is not None:
                    for label in subarea.labels.labels:
                        if subarea.sections.has_address(label.address):
                            g.append(self._make_label(label, subarea))
                translate(g, subarea.pos_x, subarea.pos_y)
                global_labels.append(g)
        return global_labels

    def _make_arrow_head(self, label, direction: str = 'down') -> ET.Element:
        angle_map = {'left': 90, 'right': 270, 'up': 0, 'down': 180}
        angle = angle_map.get(direction, 180)

        style = label.style
        weight = _s(style, 'weight', 2)
        arrow_head_width = 5 * weight
        arrow_head_height = 10 * weight

        group = self.svg.g()
        pts = [
            (0, -arrow_head_height),
            (-arrow_head_width, -arrow_head_height),
            (0, 0),
            (arrow_head_width, -arrow_head_height),
            (0, -arrow_head_height),
        ]
        poly = self.svg.polyline(pts,
                                  stroke=_s(style, 'stroke', 'black'),
                                  stroke_width=1,
                                  fill=_s(style, 'stroke', 'black'))
        rotate(poly, angle, 0, 0)
        group.append(poly)
        return group

    def _make_label(self, label, area_view) -> ET.Element:
        line_label_spacer = 3
        g = self.svg.g()
        address = label.address
        text = label.text
        label_length = label.length
        style = label.style

        if label.side == Side.RIGHT:
            pos_x_d = area_view.size_x
            direction = 1
            anchor = 'start'
        else:
            pos_x_d = 0
            direction = -1
            anchor = 'end'

        pos_y = area_view.to_pixels_relative(address)
        points = [(pos_x_d, pos_y), (direction * (label_length + pos_x_d), pos_y)]

        def add_arrow_head(dir_str):
            if dir_str == 'in':
                arr_dir = 'left' if label.side == Side.RIGHT else 'right'
                head_x = pos_x_d
            elif dir_str == 'out':
                arr_dir = 'right' if label.side == Side.RIGHT else 'left'
                head_x = direction * (label_length + pos_x_d)
            else:
                logger.warning(f"Invalid label direction '{dir_str}'")
                return

            head = self._make_arrow_head(label, direction=arr_dir)
            translate(head, head_x, pos_y)
            g.append(head)

        if isinstance(label.directions, str):
            add_arrow_head(label.directions)
        elif isinstance(label.directions, list):
            for d in label.directions:
                add_arrow_head(d)

        g.append(self._make_text(
            text,
            direction * (pos_x_d + label_length + line_label_spacer), pos_y,
            style=style,
            anchor=anchor,
        ))

        g.append(self.svg.polyline(
            points,
            stroke=_s(style, 'stroke', 'black'),
            stroke_dasharray=_s(style, 'stroke_dasharray', None),
            stroke_width=_s(style, 'stroke_width', 1),
        ))
        return g

    # ------------------------------------------------------------------
    # Links (address lines and section zoom bands)
    # ------------------------------------------------------------------

    def _draw_links(self) -> ET.Element:
        lines_group = self.svg.g()
        link_style = self.links.style if self.links else {}
        for address in self.links.addresses:
            lines_group.append(self._make_link(address, link_style))
        return lines_group

    def _draw_sub_section_links(self) -> ET.Element:
        """
        Draw link bands that originate from a named detail area rather than areas[0].
        Configured via links.sub_sections: [[source_area_id, section_id], ...].
        The band connects from the source area's section to the first subsequent area
        whose sections span the section's address range.
        """
        group = self.svg.g()
        link_style = self.links.style if self.links else {}

        for source_area_id, section_id in self.links.sub_sections:
            source_area = next(
                (a for a in self.area_views if a.area_id == source_area_id), None)
            if source_area is None:
                logger.warning(
                    f"Sub-section link: source area '{source_area_id}' not found")
                continue

            # Find the section's address range (first occurrence across all areas)
            link_range = None
            for area in self.area_views:
                for section in area.sections.get_sections():
                    if section.id == section_id:
                        link_range = [section.address, section.address + section.size]
                        break
                if link_range:
                    break

            if link_range is None:
                logger.warning(
                    f"Sub-section link: section '{section_id}' not found")
                continue

            # Find target: first area after source_area that covers the range
            source_idx = self.area_views.index(source_area)
            drawn = False
            for area_view in self.area_views[source_idx + 1:]:
                if (link_range[0] >= area_view.sections.lowest_memory and
                        link_range[1] <= area_view.sections.highest_memory):
                    group.append(self._make_poly(
                        area_view, link_range[0], link_range[1],
                        link_style, source_area=source_area))
                    drawn = True
                    break

            if not drawn:
                logger.warning(
                    f"Sub-section link '{section_id}' from '{source_area_id}': "
                    f"no target area found")

        return group

    def _draw_section_links(self) -> ET.Element:
        linked_sections_group = self.svg.g()
        for section_link in self.links_sections:
            drawn = False
            for area_view in self.area_views[1:]:
                if (section_link[0] >= area_view.sections.lowest_memory and
                        section_link[1] <= area_view.sections.highest_memory and
                        section_link[0] >= self.area_views[0].sections.lowest_memory and
                        section_link[1] <= self.area_views[0].sections.highest_memory):
                    linked_sections_group.append(self._make_poly(
                        area_view, section_link[0], section_link[1],
                        self.links.style if self.links else {}))
                    drawn = True
                    break
            if not drawn:
                logger.warning(
                    f"Section link [{hex(section_link[0])}, {hex(section_link[1])}] is "
                    f"outside the shown areas")
        return linked_sections_group

    def _get_points_for_address(self, address, area_view, source_area=None) -> list:
        left = source_area if source_area is not None else self.area_views[0]
        # Find the compressed subarea of the source area that contains this address
        # so the band anchors to the correct pixel row after break compression.
        left_sub = left
        for sub in left.get_split_area_views():
            if sub.start_address <= address <= sub.end_address:
                left_sub = sub
                break

        lx = left.size_x + left.pos_x
        lx2 = lx + 30
        # Use address_to_py_actual so the band aligns with section boxes that have
        # per-section size_y_override (non-proportional) heights.
        ly = left_sub.pos_y + left_sub.address_to_py_actual(address)

        rx = area_view.pos_x
        ry = area_view.pos_y + area_view.address_to_py_actual(address)

        # Outward jog only on the source side; connect straight into the detail stack.
        return [(lx, ly), (lx2, ly), (rx, ry)]

    # Minimum visible band opening (pixels) at the source or detail side.
    # Sections that are tiny relative to their stack would otherwise produce
    # a sub-pixel sliver.  We expand both endpoints symmetrically around the
    # midpoint so the band is always legible.
    _MIN_BAND_OPENING_PX = 4

    def _enforce_min_opening(self, pts_start, pts_end):
        """Expand source-side and detail-side openings to _MIN_BAND_OPENING_PX."""
        MIN = self._MIN_BAND_OPENING_PX
        (lx, ly_s), (lx_j, _), (rx, ry_s) = pts_start
        (_, ry_e), (lx_j2, _), (lx2, ly_e) = pts_end

        # Source side: ly_s >= ly_e (start_address maps to lower SVG y than end_address)
        if ly_s - ly_e < MIN:
            mid = (ly_s + ly_e) / 2
            ly_s, ly_e = mid + MIN / 2, mid - MIN / 2
            pts_start = [(lx, ly_s), (lx_j, ly_s), (rx, ry_s)]
            pts_end   = [(rx, ry_e), (lx_j2, ly_e), (lx2, ly_e)]

        # Detail side: ry_s >= ry_e (same SVG convention)
        if ry_s - ry_e < MIN:
            mid = (ry_s + ry_e) / 2
            ry_s, ry_e = mid + MIN / 2, mid - MIN / 2
            pts_start = [(lx, ly_s), (lx_j, ly_s), (rx, ry_s)]
            pts_end   = [(rx, ry_e), (lx_j2, ly_e), (lx2, ly_e)]

        return pts_start, pts_end

    def _make_poly(self, area_view, start_address, end_address, style: dict,
                   source_area=None) -> ET.Element:
        def find_subarea(address, area):
            for sub in area.get_split_area_views():
                if sub.start_address <= address <= sub.end_address:
                    return sub
            return area

        end_sub = find_subarea(end_address, area_view)
        start_sub = find_subarea(start_address, area_view)

        pts_start = self._get_points_for_address(start_address, start_sub, source_area)
        pts_end = list(reversed(self._get_points_for_address(end_address, end_sub, source_area)))
        pts_start, pts_end = self._enforce_min_opening(pts_start, pts_end)

        shape = _s(style, 'shape', 'polygon')
        fill = _s(style, 'fill', 'none')
        stroke = _s(style, 'stroke', 'black')
        stroke_width = _s(style, 'stroke_width', 1)
        stroke_dasharray = _s(style, 'stroke_dasharray', None)
        opacity = _s(style, 'opacity', 1)

        has_fill = fill not in (None, 'none')
        has_stroke = stroke not in (None, 'none')

        g = self.svg.g()

        if has_fill:
            d = self._band_path_closed(pts_start, pts_end, shape)
            g.append(self.svg.path(d, fill=fill, stroke='none', opacity=opacity))

        if has_stroke:
            top_d, bot_d = self._band_paths_open(pts_start, pts_end, shape)
            g.append(self.svg.path(top_d, fill='none', stroke=stroke,
                                   stroke_width=stroke_width,
                                   stroke_dasharray=stroke_dasharray,
                                   opacity=opacity))
            g.append(self.svg.path(bot_d, fill='none', stroke=stroke,
                                   stroke_width=stroke_width,
                                   stroke_dasharray=stroke_dasharray,
                                   opacity=opacity))

        return g

    def _band_path_closed(self, pts_start, pts_end, shape: str) -> str:
        """SVG path data for a closed filled band (all edges, no stroke)."""
        (lx, ly_t), (lx_j, _), (rx, ry_t) = pts_start
        (_, ry_b), (lx_j2, _), (lx2, ly_b) = pts_end
        mid_x = (lx_j + rx) / 2
        if shape == 'curve':
            return (f'M {lx},{ly_t} L {lx_j},{ly_t} '
                    f'C {mid_x},{ly_t} {mid_x},{ry_t} {rx},{ry_t} '
                    f'L {rx},{ry_b} '
                    f'C {mid_x},{ry_b} {mid_x},{ly_b} {lx_j2},{ly_b} '
                    f'L {lx2},{ly_b} Z')
        else:  # polygon
            return (f'M {lx},{ly_t} L {lx_j},{ly_t} L {rx},{ry_t} '
                    f'L {rx},{ry_b} L {lx_j2},{ly_b} L {lx2},{ly_b} Z')

    def _band_paths_open(self, pts_start, pts_end, shape: str):
        """Two open SVG path data strings for top and bottom band edges (stroke-only)."""
        (lx, ly_t), (lx_j, _), (rx, ry_t) = pts_start
        (_, ry_b), (lx_j2, _), (lx2, ly_b) = pts_end
        mid_x = (lx_j + rx) / 2
        if shape == 'curve':
            top = (f'M {lx},{ly_t} L {lx_j},{ly_t} '
                   f'C {mid_x},{ly_t} {mid_x},{ry_t} {rx},{ry_t}')
            bot = (f'M {lx2},{ly_b} L {lx_j2},{ly_b} '
                   f'C {mid_x},{ly_b} {mid_x},{ry_b} {rx},{ry_b}')
        else:  # polygon
            top = f'M {lx},{ly_t} L {lx_j},{ly_t} L {rx},{ry_t}'
            bot = f'M {lx2},{ly_b} L {lx_j2},{ly_b} L {rx},{ry_b}'
        return top, bot

    def _make_link(self, address, style: dict) -> ET.Element:
        hlines = self.svg.g()
        for area_view in self.area_views[1:]:
            for subarea in area_view.get_split_area_views():
                if not subarea.sections.has_address(address):
                    continue
                pts = self._get_points_for_address(address, subarea)
                for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                    hlines.append(self.svg.line(
                        x1, y1, x2, y2,
                        stroke_width=_s(style, 'stroke_width', 1),
                        stroke=_s(style, 'stroke', 'grey'),
                    ))
        return hlines
