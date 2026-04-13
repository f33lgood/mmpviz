import xml.etree.ElementTree as ET

# Register the SVG namespace so output uses <svg ...> not <ns0:svg ...>
ET.register_namespace('', 'http://www.w3.org/2000/svg')
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')

SVG_NS = 'http://www.w3.org/2000/svg'


def _tag(name: str) -> str:
    return f'{{{SVG_NS}}}{name}'


def _to_svg_attrs(**kwargs) -> dict:
    """
    Convert Python keyword arguments to SVG attribute names.
    Translates underscores to hyphens (e.g. stroke_width → stroke-width).
    Drops None values.
    """
    result = {}
    for k, v in kwargs.items():
        if v is None:
            continue
        svg_key = k.replace('_', '-')
        result[svg_key] = str(v)
    return result


class SVGBuilder:
    """
    Thin wrapper around xml.etree.ElementTree for generating SVG documents.
    Replaces the svgwrite API used in the original linkerscope.

    Usage:
        svg = SVGBuilder(400, 700)
        rect = svg.rect(0, 0, 400, 700, fill='white')
        svg.root.append(rect)
        svg.save('output.svg')
    """

    def __init__(self, width, height, origin_x=0, origin_y=0):
        self.root = ET.Element(_tag('svg'), {
            'width': str(width),
            'height': str(height),
            'viewBox': f'{origin_x} {origin_y} {width} {height}',
        })

    def rect(self, x, y, width, height, **attrs) -> ET.Element:
        """Create a <rect> element."""
        elem = ET.Element(_tag('rect'))
        elem.set('x', str(x))
        elem.set('y', str(y))
        elem.set('width', str(width))
        elem.set('height', str(height))
        for k, v in _to_svg_attrs(**attrs).items():
            elem.set(k, v)
        return elem

    def text(self, content: str, x, y, **attrs) -> ET.Element:
        """Create a <text> element."""
        elem = ET.Element(_tag('text'))
        elem.set('x', str(x))
        elem.set('y', str(y))
        elem.text = str(content)
        for k, v in _to_svg_attrs(**attrs).items():
            elem.set(k, v)
        return elem

    def path(self, d: str, **attrs) -> ET.Element:
        """Create a <path> element. d is the SVG path data string."""
        elem = ET.Element(_tag('path'))
        elem.set('d', d)
        for k, v in _to_svg_attrs(**attrs).items():
            elem.set(k, v)
        return elem

    def polyline(self, points: list, **attrs) -> ET.Element:
        """
        Create a <polyline> element.
        points: list of (x, y) tuples.
        """
        pts_str = ' '.join(f'{x},{y}' for x, y in points)
        elem = ET.Element(_tag('polyline'))
        elem.set('points', pts_str)
        for k, v in _to_svg_attrs(**attrs).items():
            elem.set(k, v)
        return elem

    def circle(self, cx, cy, r, **attrs) -> ET.Element:
        """Create a <circle> element."""
        elem = ET.Element(_tag('circle'))
        elem.set('cx', str(cx))
        elem.set('cy', str(cy))
        elem.set('r', str(r))
        for k, v in _to_svg_attrs(**attrs).items():
            elem.set(k, v)
        return elem

    def line(self, x1, y1, x2, y2, **attrs) -> ET.Element:
        """Create a <line> element."""
        elem = ET.Element(_tag('line'))
        elem.set('x1', str(x1))
        elem.set('y1', str(y1))
        elem.set('x2', str(x2))
        elem.set('y2', str(y2))
        for k, v in _to_svg_attrs(**attrs).items():
            elem.set(k, v)
        return elem

    def g(self, **attrs) -> ET.Element:
        """Create a <g> (group) element."""
        elem = ET.Element(_tag('g'))
        for k, v in _to_svg_attrs(**attrs).items():
            elem.set(k, v)
        return elem

    def to_string(self) -> str:
        """Serialize the SVG document to a string."""
        return ET.tostring(self.root, encoding='unicode', xml_declaration=False)

    def save(self, path: str):
        """Write the SVG document to a file."""
        svg_str = self.to_string()
        with open(path, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n')
            f.write(svg_str)


def translate(elem: ET.Element, x, y) -> ET.Element:
    """
    Apply a translate transform to an element (helper, mirrors svgwrite's .translate()).
    If the element already has a transform, the new translate is prepended.
    """
    existing = elem.get('transform', '')
    new_transform = f'translate({x},{y})'
    elem.set('transform', f'{new_transform} {existing}'.strip())
    return elem


def rotate(elem: ET.Element, angle, cx=0, cy=0) -> ET.Element:
    """Apply a rotate transform to an element."""
    existing = elem.get('transform', '')
    new_transform = f'rotate({angle},{cx},{cy})'
    elem.set('transform', f'{new_transform} {existing}'.strip())
    return elem
