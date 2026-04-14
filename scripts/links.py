import re

from loader import parse_int
from logger import logger

_HEX_RE = re.compile(r'^0x[0-9a-fA-F]+$')


def _is_hex(s: str) -> bool:
    return bool(_HEX_RE.match(s))


class Links:
    """
    Stores the link connections between views.

    Parsed from a list of link entry objects, each with the shape::

        {
          "from": {"view": "<view_id>", "sections": [<specifier>]},
          "to":   {"view": "<view_id>", "sections": [<specifier>]}
        }

    ``sections`` is optional on both sides (omit = the view's full address
    range).  When present it takes one of three forms:

    * ``["section_id", ...]`` — one or more section IDs; the band spans
      from the lowest start address to the highest end address across all
      named sections.
    * ``["0xSTART", "0xEND"]`` — exactly two hex strings; explicit address
      range (detected when the first element matches ``/^0x[0-9a-fA-F]+$/``).

    ``style`` is a plain dict resolved from theme.json for visual styling.

    Validated entries are stored in ``self.entries`` as a list of dicts::

        {
          'id':            str,
          'from_view':     str,
          'from_sections': list[str] | None,   # None = whole view
          'to_view':       str,
          'to_sections':   list[str] | None,   # None = whole view
        }
    """

    def __init__(self, links_config=None, style: dict = None):
        self.style = style or {}
        raw = links_config if links_config is not None else []
        if not isinstance(raw, list):
            logger.warning(
                "diagram 'links' must be a list of link objects; ignoring")
            raw = []
        self.entries = []
        self._validate_entries(raw)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_entries(self, raw: list):
        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                logger.warning(
                    f"Link entry {i} is not an object, skipping: {entry}")
                continue

            from_obj = entry.get('from')
            to_obj = entry.get('to')

            if not isinstance(from_obj, dict):
                logger.warning(
                    f"Link entry {i}: 'from' must be an object, skipping")
                continue
            if not isinstance(to_obj, dict):
                logger.warning(
                    f"Link entry {i}: 'to' must be an object, skipping")
                continue

            from_view = from_obj.get('view')
            to_view = to_obj.get('view')

            if not isinstance(from_view, str) or not from_view:
                logger.warning(
                    f"Link entry {i}: 'from.view' must be a non-empty string, skipping")
                continue
            if not isinstance(to_view, str) or not to_view:
                logger.warning(
                    f"Link entry {i}: 'to.view' must be a non-empty string, skipping")
                continue

            link_id = entry.get('id')
            if not isinstance(link_id, str) or not link_id:
                logger.warning(
                    f"Link entry {i}: 'id' must be a non-empty string, skipping")
                continue

            from_sections = self._validate_sections_spec(
                from_obj.get('sections'), f"Link entry {i} from.sections")
            to_sections = self._validate_sections_spec(
                to_obj.get('sections'), f"Link entry {i} to.sections")

            self.entries.append({
                'id':            link_id,
                'from_view':     from_view,
                'from_sections': from_sections,
                'to_view':       to_view,
                'to_sections':   to_sections,
            })

    def _validate_sections_spec(self, sections, context: str):
        """Return a normalised sections specifier or None if absent/invalid."""
        if sections is None:
            return None
        if not isinstance(sections, list) or len(sections) == 0:
            logger.warning(f"{context}: must be a non-empty list, ignoring")
            return None
        if not all(isinstance(s, str) for s in sections):
            logger.warning(
                f"{context}: all elements must be strings, ignoring")
            return None

        # Address-range form: exactly 2 elements, both valid hex strings.
        if len(sections) == 2 and all(_is_hex(s) for s in sections):
            try:
                parse_int(sections[0])
                parse_int(sections[1])
                return list(sections)
            except (ValueError, TypeError):
                logger.warning(
                    f"{context}: hex address range could not be parsed, ignoring")
                return None

        # Ambiguous mix: some elements look like hex addresses but the list
        # doesn't match the strict address-range form.
        if any(_is_hex(s) for s in sections):
            logger.warning(
                f"{context}: mix of hex addresses and section IDs is ambiguous, "
                f"ignoring")
            return None

        # Section-ID list.
        return list(sections)
