import json
import os

from logger import logger

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_THEME_PATH = os.path.normpath(os.path.join(_HERE, '..', 'themes', 'default.json'))

SUPPORTED_SCHEMA_VERSION = 1

_BUILTIN_NAMES = {
    "default": "default.json",
    "plantuml": "plantuml.json",
}
_THEMES_DIR = os.path.normpath(os.path.join(_HERE, '..', 'themes'))
_MAX_INHERITANCE_DEPTH = 10
_KNOWN_TOP_LEVEL_KEYS = frozenset({
    "schema_version", "extends",
    "style", "views", "links", "labels"
})


class ThemeError(Exception):
    pass


class Theme:
    """
    Loads and resolves visual styling from a theme.json file.

    Style resolution order (later overrides earlier):
      1. DEFAULT (built-in baseline)
      2. theme["style"] (user global overrides)
      3. theme["views"][view_id] (view-level overrides, minus the 'sections' subkey)
      4. theme["views"][view_id]["sections"][section_id] (section-level overrides)

    Call resolve(view_id, section_id) to get a merged flat style dict.

    Inheritance: theme files may declare "extends": "<name-or-path>" to inherit
    from a base theme. Built-in names: default, plantuml.
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
        "break_height": 20,
        "growth_arrow_size": 1,
        "growth_arrow_fill": "white",
        "growth_arrow_stroke": "black",
        "label_arrow_size": 2,
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
        resolved = self._resolve_path_arg(path)
        if resolved is not None:
            self._data = self._load_and_merge(os.path.abspath(resolved), set())

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_path_arg(path_arg):
        """Convert the raw -t argument to a file path string, or None."""
        if path_arg is None:
            return _DEFAULT_THEME_PATH if os.path.isfile(_DEFAULT_THEME_PATH) else None
        if path_arg in _BUILTIN_NAMES:
            return os.path.join(_THEMES_DIR, _BUILTIN_NAMES[path_arg])
        return path_arg

    @staticmethod
    def _resolve_extends_path(value, current_dir):
        """Resolve an 'extends' value to an absolute file path."""
        if value in _BUILTIN_NAMES:
            return os.path.join(_THEMES_DIR, _BUILTIN_NAMES[value])
        if os.path.isabs(value):
            return value
        return os.path.normpath(os.path.join(current_dir, value))

    # ------------------------------------------------------------------
    # Loading and inheritance
    # ------------------------------------------------------------------

    def _load_and_merge(self, abs_path, chain):
        """Recursively load a theme file, resolving 'extends' inheritance."""
        if abs_path in chain:
            raise ThemeError(
                f"Circular theme inheritance detected: {abs_path} "
                f"already in chain {sorted(chain)}"
            )
        if len(chain) >= _MAX_INHERITANCE_DEPTH:
            raise ThemeError(
                f"Theme inheritance chain exceeds maximum depth of {_MAX_INHERITANCE_DEPTH}"
            )

        chain = chain | {abs_path}

        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except OSError as e:
            raise ThemeError(f"Cannot open theme file '{abs_path}': {e}") from e

        self._validate_schema_version(raw, abs_path)
        self._validate_structure(raw, abs_path)

        extends_value = raw.get("extends")
        if extends_value is not None:
            parent_path = self._resolve_extends_path(
                extends_value, os.path.dirname(abs_path)
            )
            if not os.path.isfile(parent_path):
                raise ThemeError(
                    f"Theme '{abs_path}' extends '{extends_value}' "
                    f"but '{parent_path}' does not exist"
                )
            parent = self._load_and_merge(parent_path, chain)
            return self._merge(parent, raw)

        # Strip meta-keys before returning
        return {k: v for k, v in raw.items() if k not in ("schema_version", "extends")}

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_schema_version(raw, path):
        sv = raw.get("schema_version")
        if sv is None:
            return
        if sv == SUPPORTED_SCHEMA_VERSION:
            return
        if sv < SUPPORTED_SCHEMA_VERSION:
            logger.warning(
                f"Theme '{path}' declares schema_version {sv}; "
                f"current is {SUPPORTED_SCHEMA_VERSION}. Some keys may be deprecated."
            )
        else:
            raise ThemeError(
                f"Theme '{path}' requires schema_version {sv} but this mmpviz build "
                f"only supports up to {SUPPORTED_SCHEMA_VERSION}. Upgrade mmpviz."
            )

    @staticmethod
    def _validate_structure(raw, path):
        for key in raw:
            if key not in _KNOWN_TOP_LEVEL_KEYS:
                logger.warning(f"Theme '{path}': unrecognized top-level key '{key}' (ignored)")
        for block in ("style", "views", "links", "labels"):
            val = raw.get(block)
            if val is not None and not isinstance(val, dict):
                raise ThemeError(
                    f"Theme '{path}': '{block}' must be a dict, got {type(val).__name__}"
                )

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    @staticmethod
    def _merge(parent, child):
        """Deep-merge child onto parent. Child values win. Returns a new dict."""
        result = {}

        # Shallow-merge flat blocks
        for block in ("style", "links", "labels"):
            merged = {**parent.get(block, {}), **child.get(block, {})}
            if merged:
                result[block] = merged

        # Views: two-level merge
        p_views = parent.get("views", {})
        c_views = child.get("views", {})
        if p_views or c_views:
            result["views"] = Theme._merge_views(p_views, c_views)

        return result

    @staticmethod
    def _merge_views(p_views, c_views):
        result = {}
        for vid in set(p_views) | set(c_views):
            p = p_views.get(vid, {})
            c = c_views.get(vid, {})
            p_secs = p.get("sections", {})
            c_secs = c.get("sections", {})
            merged_secs = {}
            for sid in set(p_secs) | set(c_secs):
                merged_secs[sid] = {**p_secs.get(sid, {}), **c_secs.get(sid, {})}
            merged = {k: v for k, v in p.items() if k != "sections"}
            merged.update({k: v for k, v in c.items() if k != "sections"})
            if merged_secs:
                merged["sections"] = merged_secs
            result[vid] = merged
        return result

    # ------------------------------------------------------------------
    # Style resolution (unchanged API)
    # ------------------------------------------------------------------

    def _base(self) -> dict:
        """Merge built-in defaults with theme-level style."""
        return {**self.DEFAULT, **{k: v for k, v in self._data.get('style', {}).items()}}

    def resolve(self, view_id: str, section_id: str = None) -> dict:
        """Resolve and return a merged style dict for the given view (and optionally section)."""
        base = self._base()

        area_data = self._data.get('views', {}).get(view_id, {})
        area_style = {k: v for k, v in area_data.items() if k != 'sections'}

        section_style = {}
        if section_id:
            section_style = area_data.get('sections', {}).get(section_id, {})

        return {**base, **area_style, **section_style}

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
