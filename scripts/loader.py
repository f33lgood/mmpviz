import json
import re

from section import Section

_ID_RE = re.compile(r'^[a-z0-9_-]+$')


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
        sections.append(Section(
            size=parse_int(raw_size),
            address=parse_int(raw_address),
            id=section_id,
            flags=flags,
            name=name,
        ))
    return sections


def validate(path: str) -> list:
    """
    Validate a diagram.json file. Returns a list of error strings (empty = valid).
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
    # Views                                                                #
    # ------------------------------------------------------------------ #
    if 'views' in diagram:
        if not isinstance(diagram['views'], list):
            errors.append("'views' must be a list")
        else:
            seen_view_ids: set = set()

            for i, view in enumerate(diagram['views']):
                vid = view.get('id')
                if not vid:
                    errors.append(f"views[{i}]: missing 'id'")
                else:
                    if not _ID_RE.match(vid):
                        errors.append(
                            f"views[{i}]: id={vid!r} is invalid — use only "
                            "lowercase letters, digits, underscores (_), or hyphens (-)"
                        )
                    if vid in seen_view_ids:
                        errors.append(
                            f"views[{i}]: duplicate id={vid!r} — all view ids must be unique"
                        )
                    seen_view_ids.add(vid)

                view_sections = view.get('sections')
                if view_sections is not None and not isinstance(view_sections, list):
                    errors.append(f"views[{i}]: 'sections' must be a list")
                elif view_sections:
                    seen_section_ids: set = set()
                    for j, entry in enumerate(view_sections):
                        if not isinstance(entry, dict):
                            errors.append(f"views[{i}].sections[{j}]: must be an object")
                            continue

                        sid = entry.get('id')
                        if not sid:
                            errors.append(
                                f"views[{i}].sections[{j}]: missing 'id'")
                        else:
                            if not _ID_RE.match(sid):
                                errors.append(
                                    f"views[{i}].sections[{j}]: "
                                    f"id={sid!r} is invalid — use only "
                                    "lowercase letters, digits, underscores (_), "
                                    "or hyphens (-)"
                                )
                            if sid in seen_section_ids:
                                errors.append(
                                    f"views[{i}].sections[{j}]: "
                                    f"duplicate id={sid!r} within view '{vid}'"
                                )
                            seen_section_ids.add(sid)
                        if entry.get('address') is None:
                            errors.append(
                                f"views[{i}].sections[{j}]: missing 'address'")
                        if entry.get('size') is None:
                            errors.append(
                                f"views[{i}].sections[{j}]: missing 'size'")
                        if entry.get('name') is None:
                            errors.append(
                                f"views[{i}].sections[{j}]: missing required 'name'")

    size = diagram.get('size')
    if size is not None and (not isinstance(size, list) or len(size) != 2):
        errors.append("'size' must be a list of [width, height]")

    return errors
