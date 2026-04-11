from helpers import safe_element_dict_get
from loader import parse_int
from logger import logger


class Links:
    """
    Stores the link information between given sections or addresses.
    `style` is a plain dict resolved from theme.json.
    """

    def __init__(self, links_config: dict = None, style: dict = None):
        self.links = links_config or {}
        self.style = style or {}
        self.addresses = safe_element_dict_get(self.links, 'addresses', []) or []
        self.sections = safe_element_dict_get(self.links, 'sections', []) or []
        self.sub_sections = safe_element_dict_get(self.links, 'sub_sections', []) or []
        self._normalize_addresses()
        self._validate_sections()
        self._validate_sub_sections()

    def _normalize_addresses(self):
        """Convert any hex-string addresses to int."""
        normalized = []
        for addr in self.addresses:
            try:
                normalized.append(parse_int(addr))
            except (ValueError, TypeError):
                logger.warning(
                    f"Link address '{addr}' could not be parsed as an integer and will be ignored")
        self.addresses = normalized

    def _validate_sections(self):
        """Remove malformed section link entries with warnings."""
        valid = []
        for entry in self.sections:
            if isinstance(entry, str):
                valid.append(entry)
            elif isinstance(entry, list):
                if len(entry) != 2:
                    logger.warning(
                        f"Section link list must have exactly 2 entries, skipping: {entry}")
                elif not isinstance(entry[0], str) or not isinstance(entry[1], str):
                    logger.warning(
                        f"Section link list elements must be strings, skipping: {entry}")
                else:
                    valid.append(entry)
            else:
                logger.warning(
                    f"Section link '{entry}' must be a string or list of two strings, skipping")
        self.sections = valid

    def _validate_sub_sections(self):
        """Remove malformed sub-section link entries with warnings."""
        valid = []
        for entry in self.sub_sections:
            if (isinstance(entry, list) and len(entry) in (2, 3)
                    and all(isinstance(e, str) for e in entry)):
                valid.append(entry)
            else:
                logger.warning(
                    f"Sub-section link must be [source_view_id, section_id] or "
                    f"[source_view_id, section_id, target_view_id], skipping: {entry}")
        self.sub_sections = valid
