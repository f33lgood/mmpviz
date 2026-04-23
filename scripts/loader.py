"""
Diagram loader and validator.

``validate(path)`` is a pure-stdlib structural + cross-reference check for a
``diagram.json`` file.  It is the single source of truth: no optional
``jsonschema`` dependency and therefore no silent two-path divergence.

Returns a list of diagnostic strings.  An empty list means the file is valid.
"""
import json
import re

from logger import logger
from section import Section

_ID_RE = re.compile(r'^[a-z0-9_-]+$')
_HEX_OR_INT_RE = re.compile(r'^(0[xX][0-9a-fA-F]+|[0-9]+)$')

_SECTION_FLAG_ENUM = {"break", "grows-up", "grows-down"}
_LABEL_SIDE_ENUM = {"left", "right"}
_LABEL_DIR_ENUM = {"in", "out"}

# Diagram schema generation. Bump when a breaking semantic change lands in the
# diagram format (new required key, changed key meaning, etc.). Reader policy
# mirrors theme.py's SUPPORTED_SCHEMA_VERSION exactly:
#
#   absent  → treat as legacy; assume this version's semantics (full back-compat
#             with 1.1.1 and earlier, which never declared the field)
#   equal   → silent fast path
#   lower   → warn; per-feature backfills apply when we add them
#   higher  → hard validation error; the reader is too old
#
# Per-feature gates (e.g. "version N introduced key X with a default Y") are
# written when a breaking change actually lands; today there are none.
DIAGRAM_SUPPORTED_VERSION = 1

_ALLOWED_DIAGRAM_KEYS = frozenset(
    ("_comment", "schema_version", "title", "views", "links", "theme")
)
_ALLOWED_VIEW_KEYS = frozenset(("id", "title", "sections", "labels"))
_ALLOWED_SECTION_KEYS = frozenset(
    ("id", "address", "size", "name", "flags", "min_height", "max_height")
)
_ALLOWED_LABEL_KEYS = frozenset(
    ("id", "address", "text", "length", "side", "directions")
)
_ALLOWED_LINK_KEYS = frozenset(("id", "from", "to"))
_ALLOWED_ENDPOINT_KEYS = frozenset(("view", "sections"))


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


def _is_hex_or_int(v) -> bool:
    """True iff ``v`` matches the schema's hex_or_int definition."""
    if isinstance(v, bool):
        return False  # bool is a subclass of int; reject explicitly
    if isinstance(v, int):
        return v >= 0
    if isinstance(v, str):
        return bool(_HEX_OR_INT_RE.match(v))
    return False


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

        # validate() should have rejected malformed addresses before we get
        # here; if it didn't (e.g. someone called load()/resolve_view_sections
        # without validate()), surface a clean error instead of a raw traceback.
        try:
            size_int = parse_int(raw_size)
            addr_int = parse_int(raw_address)
        except (ValueError, TypeError) as exc:
            logger.warning(
                f"View '{view_config.get('id', '?')}': section '{section_id}' "
                f"has non-numeric address/size ({exc}); skipping"
            )
            continue

        flags = list(entry.get('flags') or [])
        min_h = entry.get('min_height')
        max_h = entry.get('max_height')
        try:
            min_h_f = float(min_h) if min_h is not None else None
            max_h_f = float(max_h) if max_h is not None else None
        except (ValueError, TypeError) as exc:
            logger.warning(
                f"View '{view_config.get('id', '?')}': section '{section_id}' "
                f"has non-numeric min_height/max_height ({exc}); skipping"
            )
            continue

        sections.append(Section(
            size=size_int,
            address=addr_int,
            id=section_id,
            flags=flags,
            name=name,
            min_height=min_h_f,
            max_height=max_h_f,
        ))
    return sections


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _check_numeric(value, field_path: str, errors: list,
                   *, allow_float: bool = False, minimum: float = 0) -> bool:
    """Validate a number-or-coerced-number field.  Returns True iff valid."""
    if isinstance(value, bool):
        errors.append(f"{field_path}: must be a number, got boolean")
        return False
    if isinstance(value, (int, float)):
        if value < minimum:
            errors.append(f"{field_path}: must be >= {minimum}, got {value}")
            return False
        return True
    errors.append(f"{field_path}: must be a number, got {type(value).__name__}")
    return False


def _check_hex_or_int(value, field_path: str, errors: list) -> bool:
    """Validate a hex_or_int field.  Returns True iff valid."""
    if not _is_hex_or_int(value):
        errors.append(
            f"{field_path}: must be a non-negative integer or hex/decimal string, "
            f"got {value!r}"
        )
        return False
    return True


def _check_diagram_schema_version(value, errors: list) -> None:
    """Validate the optional top-level ``schema_version`` in diagram.json.

    Policy mirrors ``theme.py`` exactly: absent is silent legacy, equal is
    silent, lower warns, higher is a fatal validation error. See
    ``DIAGRAM_SUPPORTED_VERSION`` for the rationale.
    """
    # bool is a subclass of int; reject explicitly so ``true`` doesn't sneak through
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(
            f"schema_version: must be an integer, got {type(value).__name__}"
        )
        return
    if value == DIAGRAM_SUPPORTED_VERSION:
        return
    if value < DIAGRAM_SUPPORTED_VERSION:
        logger.warning(
            f"diagram.json declares schema_version {value}; "
            f"current is {DIAGRAM_SUPPORTED_VERSION}. Some keys may be deprecated."
        )
        return
    errors.append(
        f"schema_version: diagram requires schema_version {value} but this "
        f"mmpviz build only supports up to {DIAGRAM_SUPPORTED_VERSION}. "
        "Upgrade mmpviz."
    )


def _check_additional_properties(obj: dict, allowed: frozenset,
                                 container_path: str, errors: list) -> None:
    # Leading-underscore keys are reserved for free-form author notes
    # (e.g. "_note", "_comment") and are ignored by the renderer.  Typos
    # never start with an underscore, so allowing them does not weaken
    # the silent-failure guarantees.
    extras = [k for k in obj.keys()
              if k not in allowed and not (isinstance(k, str) and k.startswith('_'))]
    for k in extras:
        errors.append(
            f"{container_path}: unknown property {k!r} — "
            f"allowed keys are {sorted(allowed)}"
        )


def _check_label(entry, path: str, errors: list) -> None:
    if not isinstance(entry, dict):
        errors.append(f"{path}: must be an object")
        return
    _check_additional_properties(entry, _ALLOWED_LABEL_KEYS, path, errors)
    lid = entry.get('id')
    if lid is None:
        errors.append(f"{path}: missing 'id'")
    elif not isinstance(lid, str) or not _ID_RE.match(lid):
        errors.append(
            f"{path}: id={lid!r} is invalid — use only lowercase letters, "
            "digits, underscores (_), or hyphens (-)"
        )
    if 'address' not in entry:
        errors.append(f"{path}: missing 'address'")
    else:
        _check_hex_or_int(entry['address'], f"{path}.address", errors)
    if 'text' in entry and not isinstance(entry['text'], str):
        errors.append(f"{path}.text: must be a string")
    if 'length' in entry:
        _check_numeric(entry['length'], f"{path}.length", errors, allow_float=True)
    if 'side' in entry:
        s = entry['side']
        if s not in _LABEL_SIDE_ENUM:
            errors.append(
                f"{path}.side: must be one of {sorted(_LABEL_SIDE_ENUM)}, got {s!r}"
            )
    if 'directions' in entry:
        d = entry['directions']
        if isinstance(d, str):
            if d not in _LABEL_DIR_ENUM:
                errors.append(
                    f"{path}.directions: must be one of {sorted(_LABEL_DIR_ENUM)}, "
                    f"got {d!r}"
                )
        elif isinstance(d, list):
            for k, item in enumerate(d):
                if not isinstance(item, str) or item not in _LABEL_DIR_ENUM:
                    errors.append(
                        f"{path}.directions[{k}]: must be one of "
                        f"{sorted(_LABEL_DIR_ENUM)}, got {item!r}"
                    )
        else:
            errors.append(
                f"{path}.directions: must be a string or list of strings"
            )


def _check_section(entry, path: str, errors: list) -> None:
    if not isinstance(entry, dict):
        errors.append(f"{path}: must be an object")
        return
    _check_additional_properties(entry, _ALLOWED_SECTION_KEYS, path, errors)
    sid = entry.get('id')
    if sid is None:
        errors.append(f"{path}: missing 'id'")
    elif not isinstance(sid, str) or not _ID_RE.match(sid):
        errors.append(
            f"{path}: id={sid!r} is invalid — use only lowercase letters, "
            "digits, underscores (_), or hyphens (-)"
        )
    if 'address' not in entry:
        errors.append(f"{path}: missing 'address'")
    else:
        _check_hex_or_int(entry['address'], f"{path}.address", errors)
    if 'size' not in entry:
        errors.append(f"{path}: missing 'size'")
    else:
        _check_hex_or_int(entry['size'], f"{path}.size", errors)
    if 'name' not in entry:
        errors.append(f"{path}: missing required 'name'")
    elif not isinstance(entry['name'], str):
        errors.append(f"{path}.name: must be a string")
    if 'flags' in entry:
        flags = entry['flags']
        if not isinstance(flags, list):
            errors.append(f"{path}.flags: must be a list")
        else:
            for k, fl in enumerate(flags):
                if not isinstance(fl, str) or fl not in _SECTION_FLAG_ENUM:
                    errors.append(
                        f"{path}.flags[{k}]: must be one of "
                        f"{sorted(_SECTION_FLAG_ENUM)}, got {fl!r}"
                    )
    min_h = entry.get('min_height')
    max_h = entry.get('max_height')
    if min_h is not None:
        _check_numeric(min_h, f"{path}.min_height", errors, allow_float=True)
    if max_h is not None:
        _check_numeric(max_h, f"{path}.max_height", errors, allow_float=True)
    if (isinstance(min_h, (int, float)) and isinstance(max_h, (int, float))
            and not isinstance(min_h, bool) and not isinstance(max_h, bool)
            and min_h > max_h):
        errors.append(
            f"{path}: 'min_height' ({min_h}) must not exceed 'max_height' ({max_h})"
        )


def _check_endpoint(ep, path: str, errors: list) -> None:
    if not isinstance(ep, dict):
        errors.append(f"{path}: must be an object")
        return
    _check_additional_properties(ep, _ALLOWED_ENDPOINT_KEYS, path, errors)
    view = ep.get('view')
    if not isinstance(view, str) or not view:
        errors.append(f"{path}.view: must be a non-empty string")
    if 'sections' in ep:
        secs = ep['sections']
        if not isinstance(secs, list):
            errors.append(f"{path}.sections: must be a list of strings")
        else:
            for k, s in enumerate(secs):
                if not isinstance(s, str):
                    errors.append(f"{path}.sections[{k}]: must be a string")


def _check_link(entry, path: str, errors: list) -> None:
    if not isinstance(entry, dict):
        errors.append(f"{path}: must be an object")
        return
    _check_additional_properties(entry, _ALLOWED_LINK_KEYS, path, errors)
    lid = entry.get('id')
    if lid is None:
        errors.append(f"{path}: missing 'id'")
    elif not isinstance(lid, str) or not _ID_RE.match(lid):
        errors.append(
            f"{path}: id={lid!r} is invalid — use only lowercase letters, "
            "digits, underscores (_), or hyphens (-)"
        )
    if 'from' not in entry:
        errors.append(f"{path}: missing 'from'")
    else:
        _check_endpoint(entry['from'], f"{path}.from", errors)
    if 'to' not in entry:
        errors.append(f"{path}: missing 'to'")
    else:
        _check_endpoint(entry['to'], f"{path}.to", errors)


def _check_structure(diagram: dict) -> list:
    """Structural validation — the single authoritative path."""
    errors: list = []
    if not isinstance(diagram, dict):
        errors.append("<root>: must be an object")
        return errors
    _check_additional_properties(diagram, _ALLOWED_DIAGRAM_KEYS, "<root>", errors)

    if 'title' in diagram and not isinstance(diagram['title'], str):
        errors.append("title: must be a string")
    if '_comment' in diagram:
        c = diagram['_comment']
        if not isinstance(c, list) or not all(isinstance(x, str) for x in c):
            errors.append("_comment: must be a list of strings")
    if 'schema_version' in diagram:
        _check_diagram_schema_version(diagram['schema_version'], errors)
    if 'theme' in diagram:
        t = diagram['theme']
        if not isinstance(t, (str, dict)):
            errors.append(
                f"theme: must be a string (built-in name) or an object "
                f"(inline theme), got {type(t).__name__}"
            )

    if 'views' in diagram:
        views = diagram['views']
        if not isinstance(views, list):
            errors.append("views: must be a list")
        else:
            for i, view in enumerate(views):
                vpath = f"views[{i}]"
                if not isinstance(view, dict):
                    errors.append(f"{vpath}: must be an object")
                    continue
                _check_additional_properties(view, _ALLOWED_VIEW_KEYS, vpath, errors)
                vid = view.get('id')
                if vid is None:
                    errors.append(f"{vpath}: missing 'id'")
                elif not isinstance(vid, str) or not _ID_RE.match(vid):
                    errors.append(
                        f"{vpath}: id={vid!r} is invalid — use only lowercase "
                        "letters, digits, underscores (_), or hyphens (-)"
                    )
                if 'title' in view and not isinstance(view['title'], str):
                    errors.append(f"{vpath}.title: must be a string")
                vsecs = view.get('sections')
                if vsecs is not None:
                    if not isinstance(vsecs, list):
                        errors.append(f"{vpath}.sections: must be a list")
                    else:
                        for j, sec in enumerate(vsecs):
                            _check_section(sec, f"{vpath}.sections[{j}]", errors)
                vlabels = view.get('labels')
                if vlabels is not None:
                    if not isinstance(vlabels, list):
                        errors.append(f"{vpath}.labels: must be a list")
                    else:
                        for j, lab in enumerate(vlabels):
                            _check_label(lab, f"{vpath}.labels[{j}]", errors)

    if 'links' in diagram:
        links = diagram['links']
        if not isinstance(links, list):
            errors.append("links: must be a list")
        else:
            for i, link in enumerate(links):
                _check_link(link, f"links[{i}]", errors)

    return errors


def _check_uniqueness(diagram: dict) -> list:
    """Duplicate view IDs, duplicate section IDs within a view, duplicate link IDs."""
    errors = []
    views = diagram.get('views')
    if isinstance(views, list):
        seen_view_ids: set = set()
        for i, view in enumerate(views):
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
            seen_label_ids: set = set()
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
            labels = view.get('labels')
            if isinstance(labels, list):
                for j, lab in enumerate(labels):
                    if not isinstance(lab, dict):
                        continue
                    lid = lab.get('id')
                    if lid:
                        if lid in seen_label_ids:
                            errors.append(
                                f"views[{i}].labels[{j}]: "
                                f"duplicate id={lid!r} within view '{vid}'"
                            )
                        seen_label_ids.add(lid)

    links = diagram.get('links')
    if isinstance(links, list):
        seen_link_ids: set = set()
        for i, link in enumerate(links):
            if not isinstance(link, dict):
                continue
            lid = link.get('id')
            if isinstance(lid, str) and lid:
                if lid in seen_link_ids:
                    errors.append(
                        f"links[{i}]: duplicate id={lid!r} — all link ids must be unique"
                    )
                seen_link_ids.add(lid)
    return errors


def _check_cross_refs(diagram: dict) -> list:
    """Link endpoints must refer to a declared view id."""
    errors = []
    views = diagram.get('views')
    if not isinstance(views, list):
        return errors
    valid_view_ids = {
        v.get('id') for v in views
        if isinstance(v, dict) and isinstance(v.get('id'), str)
    }
    links = diagram.get('links')
    if not isinstance(links, list):
        return errors
    for i, link in enumerate(links):
        if not isinstance(link, dict):
            continue
        for side in ('from', 'to'):
            ep = link.get(side)
            if not isinstance(ep, dict):
                continue
            view = ep.get('view')
            if isinstance(view, str) and view and view not in valid_view_ids:
                errors.append(
                    f"links[{i}].{side}.view: references unknown view "
                    f"{view!r}; declared views are {sorted(valid_view_ids)}"
                )
    return errors


def validate(path: str) -> list:
    """
    Validate a diagram.json file.  Returns a list of diagnostic strings;
    empty list means the file is valid.

    Legacy layout fields (diagram-level ``size``, view-level ``pos`` / ``size``)
    were removed when auto-layout became the only layout engine — they now
    surface as "unknown key" errors from the structural check.  Fix by
    deleting them from the diagram.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            diagram = json.load(f)
    except json.JSONDecodeError as e:
        return [f"JSON parse error: {e}"]
    except OSError as e:
        return [f"Cannot open file: {e}"]

    errors = []
    errors.extend(_check_structure(diagram))
    errors.extend(_check_uniqueness(diagram))
    errors.extend(_check_cross_refs(diagram))
    return errors
