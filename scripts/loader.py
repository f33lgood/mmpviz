import json
import os
import re
from importlib.resources import files as _res_files

from section import Section

_ID_RE = re.compile(r'^[a-z0-9_-]+$')
_SCHEMAS_DIR = str(_res_files("schemas"))

try:
    from jsonschema import Draft202012Validator
    _JSONSCHEMA_AVAILABLE = True
except ImportError:
    _JSONSCHEMA_AVAILABLE = False


def _check_id(id_str: str, context: str) -> None:
    """Raise ValueError if id_str violates the [a-z0-9_-] convention."""
    if not _ID_RE.match(id_str):
        raise ValueError(
            f"diagram.json: {context} id={id_str!r} is invalid. "
            "IDs must contain only lowercase letters, digits, underscores (_), "
            "or hyphens (-). No spaces, uppercase, or other characters."
        )


def parse_int(v) -> int:
    """Normalize a hex string or integer to int."""
    if isinstance(v, str):
        return int(v, 0)
    return int(v)


def load(path: str) -> dict:
    """
    Load a diagram.json file and return the parsed dict.

    Raises:
        ValueError: if required fields are missing or types are invalid.
    """
    with open(path, 'r', encoding='utf-8') as f:
        diagram = json.load(f)

    if not isinstance(diagram, dict):
        raise ValueError("diagram.json: top-level value must be a JSON object")

    return diagram


def resolve_view_sections(view_config: dict) -> list:
    """
    Resolve the ordered section list for a single view.

    Each entry in ``view_config['sections']`` must be a full section definition:
    ``{"id": "...", "address": ..., "size": ..., "name": "...", "flags": [...]}``

    Returns an empty list when ``view_config`` has no ``sections`` key or it is empty.
    """
    from logger import logger

    view_entries = view_config.get('sections') or []
    sections = []
    for entry in view_entries:
        section_id = entry.get('id')
        raw_address = entry.get('address')
        raw_size = entry.get('size')
        name = entry.get('name')

        if not section_id:
            logger.warning(
                f"View '{view_config.get('id', '?')}': section entry missing 'id' — skipping")
            continue
        if raw_address is None or raw_size is None:
            logger.warning(
                f"View '{view_config.get('id', '?')}': section '{section_id}' "
                "missing 'address' or 'size' — skipping")
            continue
        if name is None:
            logger.warning(
                f"View '{view_config.get('id', '?')}': section '{section_id}' "
                "missing required 'name' — skipping")
            continue

        flags = list(entry.get('flags') or [])
        min_h = entry.get('min_height')
        max_h = entry.get('max_height')
        sections.append(Section(
            size=parse_int(raw_size),
            address=parse_int(raw_address),
            id=section_id,
            flags=flags,
            name=name,
            min_height=float(min_h) if min_h is not None else None,
            max_height=float(max_h) if max_h is not None else None,
        ))
    return sections


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _fmt_json_path(path) -> str:
    """Format a jsonschema absolute_path deque as a readable location string."""
    parts = list(path)
    result = ''
    for p in parts:
        if isinstance(p, int):
            result += f'[{p}]'
        else:
            result += ('.' if result else '') + str(p)
    return result or '<root>'


def _check_structure(diagram: dict) -> list:
    """Manual structural checks — used when jsonschema is not installed."""
    errors = []
    if 'views' in diagram:
        if not isinstance(diagram['views'], list):
            errors.append("'views' must be a list")
        else:
            for i, view in enumerate(diagram['views']):
                vid = view.get('id')
                if not vid:
                    errors.append(f"views[{i}]: missing 'id'")
                elif not _ID_RE.match(vid):
                    errors.append(
                        f"views[{i}]: id={vid!r} is invalid — use only "
                        "lowercase letters, digits, underscores (_), or hyphens (-)"
                    )
                view_sections = view.get('sections')
                if view_sections is not None and not isinstance(view_sections, list):
                    errors.append(f"views[{i}]: 'sections' must be a list")
                elif view_sections:
                    for j, entry in enumerate(view_sections):
                        if not isinstance(entry, dict):
                            errors.append(f"views[{i}].sections[{j}]: must be an object")
                            continue
                        sid = entry.get('id')
                        if not sid:
                            errors.append(f"views[{i}].sections[{j}]: missing 'id'")
                        elif not _ID_RE.match(sid):
                            errors.append(
                                f"views[{i}].sections[{j}]: id={sid!r} is invalid — use only "
                                "lowercase letters, digits, underscores (_), or hyphens (-)"
                            )
                        if entry.get('address') is None:
                            errors.append(f"views[{i}].sections[{j}]: missing 'address'")
                        if entry.get('size') is None:
                            errors.append(f"views[{i}].sections[{j}]: missing 'size'")
                        if entry.get('name') is None:
                            errors.append(f"views[{i}].sections[{j}]: missing required 'name'")
                        min_h = entry.get('min_height')
                        max_h = entry.get('max_height')
                        if min_h is not None:
                            try:
                                min_h = float(min_h)
                                if min_h < 0:
                                    errors.append(
                                        f"views[{i}].sections[{j}]: 'min_height' must be non-negative")
                            except (TypeError, ValueError):
                                errors.append(
                                    f"views[{i}].sections[{j}]: 'min_height' must be a number")
                        if max_h is not None:
                            try:
                                max_h = float(max_h)
                                if max_h < 0:
                                    errors.append(
                                        f"views[{i}].sections[{j}]: 'max_height' must be non-negative")
                            except (TypeError, ValueError):
                                errors.append(
                                    f"views[{i}].sections[{j}]: 'max_height' must be a number")
                        if (min_h is not None and max_h is not None
                                and isinstance(min_h, (int, float))
                                and isinstance(max_h, (int, float))
                                and min_h > max_h):
                            errors.append(
                                f"views[{i}].sections[{j}]: "
                                f"'min_height' ({min_h}) must not exceed 'max_height' ({max_h})")

    return errors


def _check_uniqueness(diagram: dict) -> list:
    """Check for duplicate view IDs and duplicate section IDs within a view.
    These cross-reference constraints cannot be expressed in JSON Schema.
    """
    errors = []
    if not isinstance(diagram.get('views'), list):
        return errors
    seen_view_ids: set = set()
    for i, view in enumerate(diagram['views']):
        if not isinstance(view, dict):
            continue
        vid = view.get('id')
        if vid:
            if vid in seen_view_ids:
                errors.append(
                    f"views[{i}]: duplicate id={vid!r} — all view ids must be unique"
                )
            seen_view_ids.add(vid)
        secs = view.get('sections')
        if not isinstance(secs, list):
            continue
        seen_section_ids: set = set()
        for j, entry in enumerate(secs):
            if not isinstance(entry, dict):
                continue
            sid = entry.get('id')
            if sid:
                if sid in seen_section_ids:
                    errors.append(
                        f"views[{i}].sections[{j}]: "
                        f"duplicate id={sid!r} within view '{vid}'"
                    )
                seen_section_ids.add(sid)
    return errors


def _check_deprecated(diagram: dict) -> list:
    """Return warning strings for deprecated fields present in the diagram."""
    warnings = []
    if 'size' in diagram:
        warnings.append(
            "diagram 'size' is deprecated — canvas dimensions are now computed "
            "automatically from view content; remove this field"
        )
    for i, view in enumerate(diagram.get('views', [])):
        if not isinstance(view, dict):
            continue
        vid = view.get('id', f'views[{i}]')
        if 'pos' in view:
            warnings.append(
                f"views[{i}] (id={vid!r}): 'pos' is deprecated — "
                "view placement is controlled by auto-layout; remove this field"
            )
        if 'size' in view:
            warnings.append(
                f"views[{i}] (id={vid!r}): 'size' is deprecated — "
                "view dimensions are controlled by auto-layout; remove this field"
            )
    return warnings


def validate(path: str) -> list:
    """
    Validate a diagram.json file. Returns a list of error strings (empty = valid).

    Structural validation uses schemas/diagram.schema.json via the jsonschema
    library when available. Cross-reference checks (duplicate IDs) always run
    in Python regardless.
    """
    errors = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            diagram = json.load(f)
    except json.JSONDecodeError as e:
        return [f"JSON parse error: {e}"]
    except OSError as e:
        return [f"Cannot open file: {e}"]

    # ------------------------------------------------------------------ #
    # Structural validation                                                #
    # ------------------------------------------------------------------ #
    if _JSONSCHEMA_AVAILABLE:
        schema_path = os.path.join(_SCHEMAS_DIR, 'diagram.schema.json')
        try:
            with open(schema_path, encoding='utf-8') as sf:
                schema = json.load(sf)
            validator = Draft202012Validator(schema)
            for error in sorted(
                validator.iter_errors(diagram),
                key=lambda e: (list(e.absolute_path), e.message),
            ):
                errors.append(f"{_fmt_json_path(error.absolute_path)}: {error.message}")
        except OSError:
            errors.extend(_check_structure(diagram))
    else:
        errors.extend(_check_structure(diagram))

    # ------------------------------------------------------------------ #
    # Cross-reference checks (cannot be expressed in JSON Schema)         #
    # ------------------------------------------------------------------ #
    errors.extend(_check_uniqueness(diagram))

    # ------------------------------------------------------------------ #
    # Deprecation warnings (prefixed so callers can distinguish)          #
    # ------------------------------------------------------------------ #
    for w in _check_deprecated(diagram):
        errors.append(f"DEPRECATED: {w}")

    return errors
