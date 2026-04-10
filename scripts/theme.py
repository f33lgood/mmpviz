import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_THEME_PATH = os.path.normpath(os.path.join(_HERE, '..', 'themes', 'plantuml.json'))


class Theme:
    """
    Loads and resolves visual styling from a theme.json file.

    Style resolution order (later overrides earlier):
      1. DEFAULT (built-in baseline)
      2. theme["defaults"] (user global overrides)
      3. theme["areas"][area_id] (area-level overrides, minus the 'sections' subkey)
      4. theme["areas"][area_id]["sections"][section_id] (section-level overrides)

    Call resolve(area_id, section_id) to get a merged flat style dict.
    """

    DEFAULT = {
        "background": "white",
        "fill": "lightgrey",
        "break_fill": "white",
        "stroke": "black",
        "stroke_width": 1,
        "stroke_dasharray": "3,2",
        "font_size": 16,
        "font_family": "Helvetica",
        "text_fill": "black",
        "text_stroke": "none",
        "text_stroke_width": 0,
        "opacity": 1,
        "break_size": 20,
        "growth_arrow_size": 1,
        "growth_arrow_fill": "white",
        "growth_arrow_stroke": "black",
        "weight": 2,
    }

    DEFAULT_LINKS = {
        "shape": "polygon",
        "fill": "#D8D8D8",
        "stroke": "#888888",
        "stroke_width": 1,
        "opacity": 0.6,
    }

    def __init__(self, path: str = None):
        self._data = {}
        if path is None:
            if os.path.isfile(_DEFAULT_THEME_PATH):
                with open(_DEFAULT_THEME_PATH, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
        else:
            with open(path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)

    def _base(self) -> dict:
        """Merge built-in defaults with theme-level defaults."""
        return {**self.DEFAULT, **{k: v for k, v in self._data.get('defaults', {}).items()}}

    def resolve(self, area_id: str, section_id: str = None,
                palette_index: int = None) -> dict:
        """
        Resolve and return a merged style dict for the given area (and optionally section).

        When ``palette_index`` is provided and the theme defines a ``palette`` array,
        the palette color is used as ``fill`` unless an explicit fill is already set at
        the area or section level.
        """
        base = self._base()

        area_data = self._data.get('areas', {}).get(area_id, {})
        area_style = {k: v for k, v in area_data.items() if k != 'sections'}

        section_style = {}
        if section_id:
            section_style = area_data.get('sections', {}).get(section_id, {})

        merged = {**base, **area_style, **section_style}

        if palette_index is not None:
            palette = self._data.get('palette', [])
            has_explicit_fill = 'fill' in area_style or 'fill' in section_style
            if palette and not has_explicit_fill:
                merged['fill'] = palette[palette_index % len(palette)]

        return merged

    def resolve_links(self) -> dict:
        """Return style dict for links, merging DEFAULT_LINKS with any theme override.
        Does not inherit section defaults — the renderer supplies its own fallbacks
        for each link property via _s(), so merging _base() would cause section
        properties like stroke_dasharray to bleed into link rendering unintentionally.
        """
        return {**self.DEFAULT_LINKS, **self._data.get('links', {})}

    def resolve_labels(self) -> dict:
        """Return merged style dict for labels.
        Labels inherit section defaults (text_fill, font_size, stroke, etc.)
        since they share the same visual language as the diagram body.
        """
        return {**self._base(), **self._data.get('labels', {})}
