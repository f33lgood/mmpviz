import xml.etree.ElementTree as ET

from helpers import DefaultAppValues, format_size
from labels import Side
from logger import logger
from section import Section
from svg_builder import SVGBuilder, translate, rotate

# Addresses above this value need 64-bit (16 hex digit) label format.
_ADDR_64BIT_THRESHOLD = 0xFFFF_FFFF


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
                 growth_arrow: dict = None,
                 size=DefaultAppValues.DOCUMENT_SIZE, origin=(0, 0)):
        self.area_views = area_views
        self.links = links
        self.style = style
        self.growth_arrow = growth_arrow or {}
        self.size = size
        self.origin = origin
        ox, oy = origin
        self.svg = SVGBuilder(size[0], size[1], origin_x=ox, origin_y=oy)

    def draw(self) -> str:
        """Render the diagram and return the SVG string."""
        svg = self.svg
        ox, oy = self.origin

        # Background rectangle — covers the full viewBox (origin may be negative)
        bg = svg.rect(ox, oy, self.size[0], self.size[1],
                      fill=_s(self.style, 'background', 'white'))
        svg.root.append(bg)

        growths_group = svg.g()

        # Link bands (zoom connectors between views)
        if self.links and self.links.entries:
            svg.root.append(self._draw_link_bands())

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

        # Use 16-digit (64-bit) address labels for ALL sections in a view
        # if any address in the view exceeds the 32-bit range — keeps labels
        # visually consistent within a view and matches check.py's width estimate.
        is_64bit = any(
            s.address > _ADDR_64BIT_THRESHOLD
            for sub in area.get_split_area_views()
            for s in sub.sections.get_sections()
            if not s.is_hidden() and not s.is_break() and s.size > 0
        )

        for sub_area in area.get_split_area_views():
            subarea_group = self.svg.g()
            subarea_group.append(self._make_main_frame(sub_area))

            for section in sub_area.sections.get_sections():
                if section.is_hidden():
                    continue
                self._make_section(subarea_group, section, sub_area, is_64bit)

            translate(subarea_group, sub_area.pos_x, sub_area.pos_y)
            area_group.append(subarea_group)

        return area_group

    # ------------------------------------------------------------------
    # Section rendering
    # ------------------------------------------------------------------

    def _make_section(self, group: ET.Element, section: Section, area_view,
                      is_64bit: bool = False) -> ET.Element:
        area_view.apply_section_geometry(section)

        group.append(self._make_box(section))
        group.append(self._make_name(section))
        group.append(self._make_address(section, is_64bit))
        group.append(self._make_end_address(section, is_64bit))
        if not section.is_break():
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
        name = section.name
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

    def _make_address(self, section: Section, is_64bit: bool = False) -> ET.Element:
        fmt = '016x' if is_64bit else '08x'
        return self._make_text(
            f"0x{section.address:{fmt}}",
            section.addr_label_pos_x, section.addr_label_pos_y,
            style=section.addr_label_style,
            anchor='start',
        )

    def _make_end_address(self, section: Section, is_64bit: bool = False) -> ET.Element:
        fmt = '016x' if is_64bit else '08x'
        return self._make_text(
            f"0x{section.address + section.size:{fmt}}",
            section.addr_label_pos_x, section.end_addr_label_pos_y,
            style=section.addr_label_style,
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
        ga = self.growth_arrow
        multiplier = _s(ga, 'size', 1)
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
                stroke=_s(ga, 'stroke', 'black'),
                stroke_width=1,
                fill=_s(ga, 'fill', 'white')))

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
        label_arrow_size = _s(style, 'arrow_size', 2)
        arrow_head_width = 5 * label_arrow_size
        arrow_head_height = 10 * label_arrow_size

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
    # Links (section zoom bands)
    # ------------------------------------------------------------------

    def _resolve_endpoint_range(self, sections, view) -> list | None:
        """
        Resolve a ``sections`` specifier to an ``[start_addr, end_addr]`` pair.

        Parameters
        ----------
        sections : list[str] | None
            A validated sections specifier from a link entry's ``from`` or ``to``
            endpoint.  ``None`` means the view's full address range.
        view : AreaView
            The view that owns this endpoint (source for ``from``, destination
            for ``to``).

        Returns
        -------
        [start_addr, end_addr] or None if resolution fails.
        """
        from loader import parse_int as _parse_int
        import re as _re
        _HEX_RE = _re.compile(r'^0x[0-9a-fA-F]+$')
        from_sections = sections
        from_area = view

        if from_sections is None:
            return [from_area.start_address, from_area.end_address]

        # Address-range form: exactly 2 hex strings.
        if len(from_sections) == 2 and all(_HEX_RE.match(s) for s in from_sections):
            try:
                return [_parse_int(from_sections[0]), _parse_int(from_sections[1])]
            except (ValueError, TypeError):
                logger.warning(f"Link: could not parse address range {from_sections}")
                return None

        # Section-ID list: compute min-start to max-end across all named sections.
        starts = []
        ends = []
        for sid in from_sections:
            found = False
            for section in from_area.sections.get_sections():
                if section.id == sid:
                    starts.append(section.address)
                    ends.append(section.address + section.size)
                    found = True
                    break
            if not found:
                logger.warning(
                    f"Link: section '{sid}' not found in view '{from_area.view_id}'")

        if not starts:
            return None
        return [min(starts), max(ends)]

    @staticmethod
    def _normalize_link_style(links_style: dict) -> dict:
        """Translate connector or band format to the internal flat style keys.

        Priority: band > connector (an explicit 'band' key overrides an
        inherited 'connector' so child themes can switch rendering modes).
        """
        band = links_style.get('band')
        if band is not None:
            src = band.get('source',      {})
            mid = band.get('middle',      {})
            dst = band.get('destination', {})

            def _shape(seg: dict, default: str = 'straight') -> str:
                v = seg.get('shape', default)
                return 'curve' if v == 'curve' else 'polygon'

            return {
                'source_seg_shape':   _shape(src),
                'source_seg_width':   src.get('width',   0),
                'source_seg_lheight': src.get('sheight', 'source'),
                'source_seg_rheight': src.get('dheight', 'source'),
                'middle_seg_shape':   _shape(mid),
                'middle_seg_lheight': mid.get('sheight', 'source'),
                'middle_seg_rheight': mid.get('dheight', 'destination'),
                'dest_seg_shape':     _shape(dst),
                'dest_seg_width':     dst.get('width',   0),
                'dest_seg_lheight':   dst.get('sheight', 'destination'),
                'dest_seg_rheight':   dst.get('dheight', 'destination'),
                'fill':               band.get('fill',             'none'),
                'stroke':             band.get('stroke',           'none'),
                'stroke_width':       band.get('stroke_width',     1),
                'stroke_dasharray':   band.get('stroke_dasharray', None),
                'opacity':            band.get('opacity',          1),
            }

        connector = links_style.get('connector')
        if connector is not None:
            src        = connector.get('source',      {})
            dst        = connector.get('destination', {})
            mid        = connector.get('middle',      {})
            fill       = connector.get('fill',        'none')
            opacity    = connector.get('opacity',     1)
            mid_width  = mid.get('width', 10)
            mid_shape  = mid.get('shape', 'curve')
            seg_shape  = 'curve' if mid_shape == 'curve' else 'polygon'
            line_cap   = 'butt'  if mid_shape == 'curve' else 'round'
            return {
                '_connector_mode':       True,
                'source_seg_width':      src.get('width', 25),
                'dest_seg_width':        dst.get('width', 25),
                'middle_seg_shape':      seg_shape,
                'middle_seg_line_width': mid_width,
                'middle_seg_line_cap':   line_cap,
                'fill':                  fill,
                'opacity':               opacity,
            }

        return links_style

    def _draw_link_bands(self) -> ET.Element:
        """
        Draw all link bands from ``self.links.entries``.

        Each entry specifies a source view + optional section range and a
        destination view + optional section range.  The band is rendered as a
        trapezoid whose source-side height corresponds to ``from.sections`` and
        whose destination-side height corresponds to ``to.sections`` (or the
        full destination view when ``to.sections`` is absent).
        """
        group = self.svg.g()
        links_style = self.links.style if self.links else {}
        base_link_style = self._normalize_link_style(links_style)
        link_overrides = links_style.get('overrides', {})
        av_by_id = {av.view_id: av for av in self.area_views}

        for entry in self.links.entries:
            override = link_overrides.get(entry.get('id', ''), {})
            link_style = {**base_link_style, **override}
            from_view_id = entry['from_view']
            to_view_id = entry['to_view']

            from_area = av_by_id.get(from_view_id)
            to_area = av_by_id.get(to_view_id)

            if from_area is None:
                logger.warning(
                    f"Link: source view '{from_view_id}' not found, skipping")
                continue
            if to_area is None:
                logger.warning(
                    f"Link: target view '{to_view_id}' not found, skipping")
                continue

            from_range = self._resolve_endpoint_range(
                entry['from_sections'], from_area)
            if from_range is None:
                logger.warning(
                    f"Link from '{from_view_id}' to '{to_view_id}': "
                    f"could not resolve source range, skipping")
                continue

            to_range = None
            if entry['to_sections']:
                to_range = self._resolve_endpoint_range(
                    entry['to_sections'], to_area)
                if to_range is None:
                    logger.warning(
                        f"Link from '{from_view_id}' to '{to_view_id}': "
                        f"could not resolve destination range, skipping")
                    continue

            group.append(self._make_poly(
                to_area, from_range[0], from_range[1],
                link_style, source_area=from_area,
                to_start=to_range[0] if to_range else None,
                to_end=to_range[1] if to_range else None))

        return group

    # Minimum visible band opening (pixels) at the source or destination side.
    # Sections that are tiny relative to their stack would otherwise produce
    # a sub-pixel sliver.  We expand both endpoints symmetrically around the
    # midpoint so the band is always legible.
    _MIN_BAND_OPENING_PX = 4

    def _enforce_min_opening(self, ly_src_t, ly_src_b, ry_dst_t, ry_dst_b):
        """Expand source-side and destination-side openings to _MIN_BAND_OPENING_PX."""
        MIN = self._MIN_BAND_OPENING_PX
        # Source side: ly_src_t >= ly_src_b (start address maps to lower SVG y)
        if ly_src_t - ly_src_b < MIN:
            mid = (ly_src_t + ly_src_b) / 2
            ly_src_t, ly_src_b = mid + MIN / 2, mid - MIN / 2
        # Destination side
        if ry_dst_t - ry_dst_b < MIN:
            mid = (ry_dst_t + ry_dst_b) / 2
            ry_dst_t, ry_dst_b = mid + MIN / 2, mid - MIN / 2
        return ly_src_t, ly_src_b, ry_dst_t, ry_dst_b

    @staticmethod
    def _seg_cmd(x1, x2, y1, y2, shape):
        """One SVG path command traversing from (x1,y1) to (x2,y2).

        Returns an empty string for zero-width segments so callers can filter
        them out with a simple truthiness check.
        """
        if x1 == x2:
            return ''
        mid_x = (x1 + x2) / 2
        if shape == 'curve':
            return f'C {mid_x},{y1} {mid_x},{y2} {x2},{y2}'
        return f'L {x2},{y2}'

    def _make_poly(self, area_view, start_address, end_address, style: dict,
                   source_area=None, to_start=None, to_end=None) -> ET.Element:
        def find_sub(address, area):
            for sub in area.get_split_area_views():
                if sub.start_address <= address <= sub.end_address:
                    return sub
            return area

        # Source pixel coordinates — use address_to_py_actual so the band aligns
        # with section boxes that have per-section size_y_override heights.
        left = source_area if source_area is not None else self.area_views[0]
        src_t_sub = find_sub(start_address, left)
        src_b_sub = find_sub(end_address, left)
        lx = left.size_x + left.pos_x
        ly_src_t = src_t_sub.pos_y + src_t_sub.address_to_py_actual(start_address)
        ly_src_b = src_b_sub.pos_y + src_b_sub.address_to_py_actual(end_address)

        # Destination address range: use the explicitly resolved to.sections range
        # when provided; otherwise clamp the source range to the destination view's
        # address range so the band never extends off-screen.
        if to_start is not None and to_end is not None:
            dest_lo = max(to_start, area_view.start_address)
            dest_hi = min(to_end, area_view.end_address)
        else:
            dest_lo = max(start_address, area_view.start_address)
            dest_hi = min(end_address, area_view.end_address)

        dst_t_sub = find_sub(dest_lo, area_view)
        dst_b_sub = find_sub(dest_hi, area_view)
        rx = area_view.pos_x
        ry_dst_t = dst_t_sub.pos_y + dst_t_sub.address_to_py_actual(dest_lo)
        ry_dst_b = dst_b_sub.pos_y + dst_b_sub.address_to_py_actual(dest_hi)

        ly_src_t, ly_src_b, ry_dst_t, ry_dst_b = self._enforce_min_opening(
            ly_src_t, ly_src_b, ry_dst_t, ry_dst_b)

        src_center = (ly_src_t + ly_src_b) / 2
        dst_center = (ry_dst_t + ry_dst_b) / 2
        src_span   = ly_src_t - ly_src_b
        dst_span   = ry_dst_t - ry_dst_b

        # Connector mode: render source trapezoid + middle line + dest trapezoid
        # as three independent elements so each shape is geometrically exact.
        # A single connected polygon cannot represent this correctly because the
        # source/dest junction heights (mid_width) and the middle-segment heights
        # (0, collapsed) differ at the same x, causing discontinuities in the path.
        if _s(style, '_connector_mode'):
            return self._render_connector(
                lx, lx_j=lx + _s(style, 'source_seg_width', 25),
                rx_j=rx - _s(style, 'dest_seg_width', 25), rx=rx,
                src_center=src_center, dst_center=dst_center,
                src_span=src_span, dst_span=dst_span,
                style=style)

        # Segment geometry
        src_w = _s(style, 'source_seg_width', 30)
        dst_w = _s(style, 'dest_seg_width', 0)
        src_shape = _s(style, 'source_seg_shape', 'polygon')
        mid_shape = _s(style, 'middle_seg_shape', 'polygon')
        dst_shape = _s(style, 'dest_seg_shape', 'polygon')
        src_lh = _s(style, 'source_seg_lheight', 'source')
        src_rh = _s(style, 'source_seg_rheight', 'source')
        mid_lh = _s(style, 'middle_seg_lheight', 'source')
        mid_rh = _s(style, 'middle_seg_rheight', 'destination')
        dst_lh = _s(style, 'dest_seg_lheight', 'destination')
        dst_rh = _s(style, 'dest_seg_rheight', 'destination')

        lx_j = lx + src_w
        rx_j = rx - dst_w

        # Edge height model: lheight/rheight selects the SPAN; the CENTER of each
        # edge is fixed by which segment it belongs to:
        #   source_seg edges  → centered on source region
        #   dest_seg edges    → centered on destination region
        #   middle_seg left   → centered on source region
        #   middle_seg right  → centered on destination region
        # This keeps each segment naturally aligned to its side while still
        # allowing the span to reference either side's pixel height.

        def edge(center, height_ref):
            """(t, b) = (center + span/2, center − span/2) using the named span.

            height_ref may be:
              'source'      – use the source-side pixel span
              'destination' – use the destination-side pixel span
              <number>      – literal span in pixels (0 collapses the edge to a point)
            """
            if isinstance(height_ref, (int, float)):
                span = float(height_ref)
            elif height_ref == 'source':
                span = src_span
            else:
                span = dst_span
            return center + span / 2, center - span / 2

        sl_t, sl_b = edge(src_center, src_lh)   # source seg  left  edge  (at lx)
        sr_t, sr_b = edge(src_center, src_rh)   # source seg  right edge  (at lx_j)
        ml_t, ml_b = edge(src_center, mid_lh)   # middle seg  left  edge  (at lx_j)
        mr_t, mr_b = edge(dst_center, mid_rh)   # middle seg  right edge  (at rx_j)
        dl_t, dl_b = edge(dst_center, dst_lh)   # dest   seg  left  edge  (at rx_j)
        dr_t, dr_b = edge(dst_center, dst_rh)   # dest   seg  right edge  (at rx)

        # Visual style
        fill = _s(style, 'fill', 'none')
        stroke = _s(style, 'stroke', 'black')
        stroke_width = _s(style, 'stroke_width', 1)
        stroke_dasharray = _s(style, 'stroke_dasharray', None)
        opacity = _s(style, 'opacity', 1)
        mid_stroke_w = _s(style, 'middle_seg_line_width', None)

        has_fill = fill not in (None, 'none')
        has_stroke = stroke not in (None, 'none')

        g = self.svg.g()

        if has_fill:
            d = self._band_path_closed(
                lx, lx_j, rx_j, rx,
                sl_t, sr_t, ml_t, mr_t, dl_t, dr_t,
                sl_b, sr_b, ml_b, mr_b, dl_b, dr_b,
                src_shape, mid_shape, dst_shape)
            g.append(self.svg.path(d, fill=fill, stroke='none', opacity=opacity))

        if has_stroke:
            top_d, bot_d = self._band_paths_open(
                lx, lx_j, rx_j, rx,
                sl_t, sr_t, ml_t, mr_t, dl_t, dr_t,
                sl_b, sr_b, ml_b, mr_b, dl_b, dr_b,
                src_shape, mid_shape, dst_shape)
            g.append(self.svg.path(top_d, fill='none', stroke=stroke,
                                   stroke_width=stroke_width,
                                   stroke_dasharray=stroke_dasharray,
                                   opacity=opacity))
            g.append(self.svg.path(bot_d, fill='none', stroke=stroke,
                                   stroke_width=stroke_width,
                                   stroke_dasharray=stroke_dasharray,
                                   opacity=opacity))

        # Middle segment centerline stroke — constant perpendicular width along
        # the curve, avoiding the apparent thinning that a vertical-offset filled
        # band shows at the steepest point of an S-curve.
        if mid_stroke_w:
            center_l = (ml_t + ml_b) / 2
            center_r = (mr_t + mr_b) / 2
            cmd = self._seg_cmd(lx_j, rx_j, center_l, center_r, mid_shape)
            if cmd:
                center_color = _s(style, 'middle_seg_line_stroke',
                                  fill if has_fill else stroke)
                mid_cap = _s(style, 'middle_seg_line_cap', 'round')
                mid_d = f'M {lx_j},{center_l} {cmd}'
                g.append(self.svg.path(
                    mid_d, fill='none',
                    stroke=center_color,
                    stroke_width=mid_stroke_w,
                    stroke_linecap=mid_cap,
                    stroke_dasharray=stroke_dasharray,
                    opacity=opacity))

        return g

    def _render_connector(self, lx, lx_j, rx_j, rx,
                          src_center, dst_center, src_span, dst_span,
                          style: dict) -> ET.Element:
        """Render a connector as three independent elements.

        Source trapezoid (filled polygon) + middle line (stroke) + dest
        trapezoid (filled polygon).  Keeping them separate avoids the
        continuity mismatch that occurs when trying to join the source/dest
        junction edges (height = mid_width) with the collapsed zero-height
        middle segment inside a single closed polygon.
        """
        fill      = _s(style, 'fill', 'none')
        opacity   = _s(style, 'opacity', 1)
        mid_w     = _s(style, 'middle_seg_line_width', 10)
        mid_shape = _s(style, 'middle_seg_shape', 'curve')
        mid_cap   = _s(style, 'middle_seg_line_cap', 'butt')

        # Source trapezoid: outer edge = source span, inner edge = mid_width
        sl_t = src_center + src_span / 2
        sl_b = src_center - src_span / 2
        sr_t = src_center + mid_w / 2
        sr_b = src_center - mid_w / 2

        # Dest trapezoid: inner edge = mid_width, outer edge = dest span
        dl_t = dst_center + mid_w / 2
        dl_b = dst_center - mid_w / 2
        dr_t = dst_center + dst_span / 2
        dr_b = dst_center - dst_span / 2

        g = self.svg.g()
        has_fill = fill not in (None, 'none')

        if has_fill:
            d_src = (f'M {lx},{sl_t} L {lx_j},{sr_t} '
                     f'L {lx_j},{sr_b} L {lx},{sl_b} Z')
            g.append(self.svg.path(d_src, fill=fill, stroke='none', opacity=opacity))

            d_dst = (f'M {rx_j},{dl_t} L {rx},{dr_t} '
                     f'L {rx},{dr_b} L {rx_j},{dl_b} Z')
            g.append(self.svg.path(d_dst, fill=fill, stroke='none', opacity=opacity))

        # Middle line: stroke centered between src_center and dst_center
        cmd = self._seg_cmd(lx_j, rx_j, src_center, dst_center, mid_shape)
        if cmd and mid_w:
            mid_d = f'M {lx_j},{src_center} {cmd}'
            g.append(self.svg.path(
                mid_d, fill='none', stroke=fill,
                stroke_width=mid_w, stroke_linecap=mid_cap,
                opacity=opacity))

        return g

    def _band_path_closed(self,
                          lx, lx_j, rx_j, rx,
                          src_lh_t, src_rh_t, mid_lh_t, mid_rh_t, dst_lh_t, dst_rh_t,
                          src_lh_b, src_rh_b, mid_lh_b, mid_rh_b, dst_lh_b, dst_rh_b,
                          src_shape, mid_shape, dst_shape) -> str:
        """SVG path data for a closed filled band."""
        cmd = self._seg_cmd
        parts = [f'M {lx},{src_lh_t}']
        # Top edge: left to right
        parts.append(cmd(lx,   lx_j, src_lh_t, src_rh_t, src_shape))
        parts.append(cmd(lx_j, rx_j, mid_lh_t, mid_rh_t, mid_shape))
        parts.append(cmd(rx_j, rx,   dst_lh_t, dst_rh_t, dst_shape))
        # Cross to bottom of right edge
        parts.append(f'L {rx},{dst_rh_b}')
        # Bottom edge: right to left
        parts.append(cmd(rx,   rx_j, dst_rh_b, dst_lh_b, dst_shape))
        parts.append(cmd(rx_j, lx_j, mid_rh_b, mid_lh_b, mid_shape))
        parts.append(cmd(lx_j, lx,   src_rh_b, src_lh_b, src_shape))
        parts.append('Z')
        return ' '.join(p for p in parts if p)

    def _band_paths_open(self,
                         lx, lx_j, rx_j, rx,
                         src_lh_t, src_rh_t, mid_lh_t, mid_rh_t, dst_lh_t, dst_rh_t,
                         src_lh_b, src_rh_b, mid_lh_b, mid_rh_b, dst_lh_b, dst_rh_b,
                         src_shape, mid_shape, dst_shape):
        """Two open SVG path data strings for top and bottom band edges (stroke-only)."""
        cmd = self._seg_cmd
        # Top edge: left to right
        top = ' '.join(p for p in [
            f'M {lx},{src_lh_t}',
            cmd(lx,   lx_j, src_lh_t, src_rh_t, src_shape),
            cmd(lx_j, rx_j, mid_lh_t, mid_rh_t, mid_shape),
            cmd(rx_j, rx,   dst_lh_t, dst_rh_t, dst_shape),
        ] if p)
        # Bottom edge: left to right
        bot = ' '.join(p for p in [
            f'M {lx},{src_lh_b}',
            cmd(lx,   lx_j, src_lh_b, src_rh_b, src_shape),
            cmd(lx_j, rx_j, mid_lh_b, mid_rh_b, mid_shape),
            cmd(rx_j, rx,   dst_lh_b, dst_rh_b, dst_shape),
        ] if p)
        return top, bot

