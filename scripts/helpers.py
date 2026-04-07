from logger import logger


class DefaultAppValues:
    DOCUMENT_SIZE = (400, 700)
    POSITION_X = 50
    POSITION_Y = 50
    SIZE_X = 200
    SIZE_Y = 500
    TITLE = ''


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
