# Geometry constants that mirror the renderer's size-label placement.
# Size label is rendered at (pos_x+2, pos_y+2) with text_type='small' (12 px)
# and baseline='hanging', so it occupies y = [pos_y+2, pos_y+14] inside the section.
_SIZE_LABEL_TOP_OFFSET = 2
_SIZE_LABEL_FONT_SIZE  = 12   # renderer's fixed 'small' font size


class Section:
    """
    Holds logical and graphical information for a given section, as well as other properties such as
    style, visibility, type, flags, etc.

    `style` is a plain dict resolved from theme.json — use .get() to access values.
    """
    size: int
    address: int
    id: str
    size_x: int
    size_y: int
    pos_x: int
    pos_y: int
    label_offset: int = 10
    style: dict

    def __init__(self, size, address, id, _type, parent, flags=None, name=None):
        self.type = _type
        self.parent = parent
        self.size = size
        self.address = address
        self.id = id
        self.name = name
        self.size_y = 0
        self.size_x = 0
        self.style = {}
        self.flags = flags if flags is not None else []
        self.size_y_override = None   # set by per-section height algorithm
        self.pos_y_in_subarea = None  # set by per-section height algorithm

    def is_grow_up(self):
        return 'grows-up' in self.flags

    def is_grow_down(self):
        return 'grows-down' in self.flags

    def is_break(self):
        return 'break' in self.flags

    def is_hidden(self):
        return 'hidden' in self.flags

    def _should_element_be_hidden(self, attribute):
        return str(attribute).lower() in ('true', 'yes')

    def is_address_hidden(self):
        return self._should_element_be_hidden(self.style.get('hide_address', False))

    def is_end_address_hidden(self):
        return self._should_element_be_hidden(self.style.get('hide_end_address', False))

    def is_name_hidden(self):
        if self._should_element_be_hidden(self.style.get('hide_name', False)):
            return True
        # Auto-fix: name overflows the section box — suppress it.
        if self.size_y > 0:
            font_size = float(self.style.get('font_size', 16))
            if self.size_y < font_size:
                return True
        return False

    def is_size_hidden(self):
        if self._should_element_be_hidden(self.style.get('hide_size', False)):
            return True
        if self.size_y > 0:
            # Section is too short for the size label itself (12 px hanging).
            if self.size_y < _SIZE_LABEL_FONT_SIZE:
                return True
            # Auto-fix: size label would overlap the name label.
            if not self.is_name_hidden():
                font_size = float(self.style.get('font_size', 16))
                name_label_top = self.size_y / 2 - font_size / 2
                if name_label_top < _SIZE_LABEL_TOP_OFFSET + _SIZE_LABEL_FONT_SIZE:
                    return True
        return False

    @property
    def addr_label_pos_x(self):
        return self.size_x + self.label_offset

    @property
    def addr_label_pos_y(self):
        return self.pos_y + self.size_y

    @property
    def end_addr_label_pos_y(self):
        return self.pos_y

    @property
    def name_label_pos_x(self):
        return self.size_x / 2

    @property
    def size_label_pos(self):
        return self.pos_x + 2, self.pos_y + 2

    @property
    def name_label_pos_y(self):
        return self.pos_y + (self.size_y / 2)
