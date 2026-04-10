import json

from section import Section


def parse_int(v) -> int:
    """Normalize a hex string or integer to int."""
    if isinstance(v, str):
        return int(v, 0)
    return int(v)


def load(path: str) -> tuple:
    """
    Load a diagram.json file.

    Returns:
        (sections, diagram_dict) where sections is a list of Section objects
        built from diagram["sections"], and diagram_dict is the full parsed JSON
        for use by the caller (areas, links, size, etc.).

    Raises:
        ValueError: if required fields are missing or types are invalid.
    """
    with open(path, 'r', encoding='utf-8') as f:
        diagram = json.load(f)

    raw_sections = diagram.get('sections', [])
    if not isinstance(raw_sections, list):
        raise ValueError("diagram.json: 'sections' must be a list")

    sections = []
    for entry in raw_sections:
        section_id = entry.get('id')
        if not section_id:
            raise ValueError(f"diagram.json: section missing required 'id': {entry}")

        raw_address = entry.get('address')
        raw_size = entry.get('size')
        if raw_address is None or raw_size is None:
            raise ValueError(f"diagram.json: section '{section_id}' missing 'address' or 'size'")

        address = parse_int(raw_address)
        size = parse_int(raw_size)

        flags = entry.get('flags', [])
        if isinstance(flags, str):
            flags = [f.strip() for f in flags.split(',')]

        name = entry.get('name')

        sections.append(Section(
            size=size,
            address=address,
            id=section_id,
            flags=flags,
            name=name,
        ))

    return sections, diagram


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

    if 'sections' not in diagram:
        errors.append("Missing required top-level key: 'sections'")
    elif not isinstance(diagram['sections'], list):
        errors.append("'sections' must be a list")
    else:
        for i, entry in enumerate(diagram['sections']):
            if not entry.get('id'):
                errors.append(f"sections[{i}]: missing 'id'")
            if entry.get('address') is None:
                errors.append(f"sections[{i}]: missing 'address'")
            if entry.get('size') is None:
                errors.append(f"sections[{i}]: missing 'size'")

    if 'views' in diagram:
        if not isinstance(diagram['views'], list):
            errors.append("'views' must be a list")
        else:
            for i, view in enumerate(diagram['views']):
                if not view.get('id'):
                    errors.append(f"views[{i}]: missing 'id'")

    size = diagram.get('size')
    if size is not None and (not isinstance(size, list) or len(size) != 2):
        errors.append("'size' must be a list of [width, height]")

    return errors
