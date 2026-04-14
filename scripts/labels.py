from dataclasses import dataclass

from loader import parse_int
from logger import logger


class Side:
    RIGHT = 'right'
    LEFT = 'left'


@dataclass
class Label:
    """
    Stores single label information for a given address.
    `style` is a plain dict resolved from theme.json, with any per-label
    overrides already merged in.
    """
    id: str
    address: int
    text: str
    length: int
    directions: object  # str or list
    side: str
    style: dict

    def __init__(self, style: dict):
        self.id = ''
        self.style = style
        self.address = 0
        self.text = 'Label'
        self.length = 20
        self.directions = []
        self.side = Side.RIGHT


class Labels:
    """
    Container for labels, built from the diagram.json label list for a given area.
    """

    def __init__(self, labels_config: list, style: dict, label_overrides: dict = None):
        self.style = style
        self.label_overrides = label_overrides or {}
        self.labels = self._build(labels_config)

    def _build(self, labels_config: list) -> list:
        result = []
        for i, element in enumerate(labels_config or []):
            label_id = element.get('id')
            if not isinstance(label_id, str) or not label_id:
                logger.warning(f"Label entry {i}: 'id' must be a non-empty string, skipping")
                continue

            raw_address = element.get('address')
            if raw_address is None:
                logger.warning(f"Label '{label_id}': no 'address' found, skipping")
                continue

            override = self.label_overrides.get(label_id, {})
            label = Label(style={**self.style, **override})
            label.id = label_id
            label.address = parse_int(raw_address)
            label.text = element.get('text', 'Label')
            label.length = element.get('length', 20)
            label.directions = element.get('directions', [])
            label.side = element.get('side', Side.RIGHT)

            result.append(label)
        return result
