from logger import logger


def safe_element_list_get(_list: list, index: int, default=None):
    """
    Get an element from a list checking if both the list and the element exist.
    """
    return _list[index] if _list is not None and len(_list) > index else default


def safe_element_dict_get(_dict: dict, key: str, default=None):
    """
    Get an element from a dict checking if both the dict and the element exist.
    """
    return _dict[key] if _dict is not None and key in _dict else default


def format_size(n: int) -> str:
    """Return a human-readable binary size string (e.g. '32 KiB', '256 MiB')."""
    for unit, shift in (('GiB', 30), ('MiB', 20), ('KiB', 10)):
        threshold = 1 << shift
        if n >= threshold:
            val = n / threshold
            return f"{int(val)} {unit}" if val == int(val) else f"{val:.1f} {unit}"
    return f"{n} B"
