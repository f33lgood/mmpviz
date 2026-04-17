import json
import os
from importlib.resources import files as _res_files

from logger import logger

_THEMES_PKG       = _res_files("themes")
_DEFAULT_THEME_PATH = str(_THEMES_PKG.joinpath("default.json"))
_THEMES_DIR         = str(_THEMES_PKG)

SUPPORTED_SCHEMA_VERSION = 1

_BUILTIN_NAMES = {
    "default": "default.json",
    "plantuml": "plantuml.json",
}
_MAX_INHERITANCE_DEPTH = 10
_KNOWN_TOP_LEVEL_KEYS = frozenset({
    "schema_version", "extends",
    "base", "views", "links", "labels", "growth_arrow"
})


class ThemeError(Exception):
    pass


class Theme:
    """
    Loads and resolves visual styling from a theme.json file.

    Style resolution order (later overrides earlier):
      1. DEFAULT (schema-migration backfill — see below)
      2. theme["base"] (user global overrides)
      3. theme["views"][view_id] (view-level overrides, minus the 'sections' subkey)
      4. theme["views"][view_id]["sections"][section_id] (section-level overrides)

    Call resolve(view_id, section_id) to get a merged flat style dict.

    Inheritance: theme files may declare "extends": "<name-or-path>" to inherit
    from a base theme. Built-in names: default, plantuml.

    DEFAULT policy:
        Authoritative defaults live in ``themes/default.json`` (and
        ``plantuml.json``). DEFAULT is NOT a mirror of those files — it exists
        only to backfill base keys that a user-authored theme might omit when
        that theme targets an older schema_version than the current build.

        When a future schema_version introduces a new base key, add it to
        DEFAULT gated by its introduction version (e.g. via a
        ``_BASE_DEFAULTS_BY_VERSION`` dict) so themes declaring an older
        ``schema_version`` still render. While schema_version == 1 is the only
        version, DEFAULT stays empty and all consumers rely on
        ``themes/default.json`` plus per-call ``style.get(key, fallback)``
        safety nets in the renderer.
    """

    DEFAULT: dict = {}

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
        for block in ("base", "views", "links", "labels", "growth_arrow"):
            val = raw.get(block)
            if val is not None and not isinstance(val, dict):
                raise ThemeError(
                    f"Theme '{path}': '{block}' must be a dict, got {type(val).__name__}"
                )

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_links(p_links: dict, c_links: dict) -> dict:
        """Merge two links dicts.

        connector and band sub-objects are merged two levels deep so that a
        child theme can override individual nested keys (e.g. connector.fill)
        without losing keys it did not mention (e.g. connector.source.width).
        overrides is merged shallowly per link id.
        """
        result = {}
        for mode in ('connector', 'band'):
            p = p_links.get(mode, {})
            c = c_links.get(mode, {})
            if not p and not c:
                continue
            merged = dict(p)
            for k, v in c.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k] = {**merged[k], **v}
                else:
                    merged[k] = v
            result[mode] = merged

        # overrides: shallow merge per link id
        p_ov = p_links.get('overrides', {})
        c_ov = c_links.get('overrides', {})
        if p_ov or c_ov:
            merged_ov = {}
            for lid in set(p_ov) | set(c_ov):
                merged_ov[lid] = {**p_ov.get(lid, {}), **c_ov.get(lid, {})}
            result['overrides'] = merged_ov

        return result

    @staticmethod
    def _merge(parent, child):
        """Deep-merge child onto parent. Child values win. Returns a new dict."""
        result = {}

        # Shallow-merge flat blocks
        for block in ("base", "labels", "growth_arrow"):
            merged = {**parent.get(block, {}), **child.get(block, {})}
            if merged:
                result[block] = merged

        # Links: two-level merge (connector/band sub-objects merged shallowly)
        p_links = parent.get("links", {})
        c_links = child.get("links", {})
        if p_links or c_links:
            result["links"] = Theme._merge_links(p_links, c_links)

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
            # merge sections map: shallow merge per section id
            p_secs = p.get("sections", {})
            c_secs = c.get("sections", {})
            merged_secs = {}
            for sid in set(p_secs) | set(c_secs):
                merged_secs[sid] = {**p_secs.get(sid, {}), **c_secs.get(sid, {})}
            # merge labels map: shallow merge per label id
            p_labs = p.get("labels", {})
            c_labs = c.get("labels", {})
            merged_labs = {}
            for lid in set(p_labs) | set(c_labs):
                merged_labs[lid] = {**p_labs.get(lid, {}), **c_labs.get(lid, {})}
            # flat view-level style (exclude sub-maps)
            merged = {k: v for k, v in p.items() if k not in ("sections", "labels")}
            merged.update({k: v for k, v in c.items() if k not in ("sections", "labels")})
            if merged_secs:
                merged["sections"] = merged_secs
            if merged_labs:
                merged["labels"] = merged_labs
            result[vid] = merged
        return result

    # ------------------------------------------------------------------
    # Style resolution (unchanged API)
    # ------------------------------------------------------------------

    def _base(self) -> dict:
        """Merge built-in defaults with the theme's base block."""
        return {**self.DEFAULT, **self._data.get('base', {})}

    def resolve(self, view_id: str, section_id: str = None) -> dict:
        """Resolve and return a merged style dict for the given view (and optionally section)."""
        base = self._base()

        area_data = self._data.get('views', {}).get(view_id, {})
        area_style = {k: v for k, v in area_data.items() if k not in ('sections', 'labels')}

        section_style = {}
        if section_id:
            section_style = area_data.get('sections', {}).get(section_id, {})

        return {**base, **area_style, **section_style}

    def resolve_label_overrides(self, view_id: str) -> dict:
        """Return per-label style overrides for a view, keyed by label id."""
        area_data = self._data.get('views', {}).get(view_id, {})
        return area_data.get('labels', {})

    def resolve_growth_arrow(self) -> dict:
        """Return the resolved growth arrow style dict."""
        return self._data.get('growth_arrow', {})

    def resolve_links(self) -> dict:
        """Return the resolved links style dict.

        All link keys are provided by the inherited theme chain (themes/default.json
        defines the complete set). The renderer handles any missing keys via _s()
        per-property fallbacks, so no Python-level defaults are needed here.
        """
        return self._data.get('links', {})

    def resolve_labels(self) -> dict:
        """Return merged style dict for labels.
        Labels inherit section defaults (text_fill, font_size, stroke, etc.)
        since they share the same visual language as the diagram body.
        """
        return {**self._base(), **self._data.get('labels', {})}
