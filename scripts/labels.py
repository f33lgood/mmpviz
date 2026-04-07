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
    `style` is a plain dict resolved from theme.json.
    """
    address: int
    text: str
    length: int
    directions: object  # str or list
    side: str
    style: dict

    def __init__(self, style: dict):
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

    def __init__(self, labels_config: list, style: dict):
        self.style = style
        self.labels = self._build(labels_config)

    def _build(self, labels_config: list) -> list:
        result = []
        for element in (labels_config or []):
            label = Label(style=dict(self.style))

            raw_address = element.get('address')
            if raw_address is None:
                logger.warning("A label without 'address' was found and will be skipped")
                continue

            label.address = parse_int(raw_address)
            label.text = element.get('text', 'Label')
            label.length = element.get('length', 20)
            label.directions = element.get('directions', [])
            label.side = element.get('side', Side.RIGHT)

            result.append(label)
        return result
