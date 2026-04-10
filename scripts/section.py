class Section:
    """
    Holds logical and graphical information for a given section, as well as other properties such as
    style, visibility, flags, etc.

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

    def __init__(self, size, address, id, flags=None, name=None):
        self.size = size
        self.address = address
        self.id = id
        self.name = name
        self.size_y = 0
        self.size_x = 0
        self.style = {}
        self.addr_label_style = {}  # view-level style (no section overrides) for address labels
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
