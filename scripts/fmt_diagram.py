#!/usr/bin/env python3
"""
Canonical formatter for diagram.json files.

Applies column-aligned formatting: compact arrays (``sections[]``,
``views[].sections[]``, ``links[]``, ``views[].labels[]``) are rendered one
entry per line with field values column-aligned for readability.

Usage:
    python scripts/fmt_diagram.py examples/*/diagram.json
"""

import json
import os
import sys


# ---------------------------------------------------------------------------
# Compact / column-aligned serialiser
# ---------------------------------------------------------------------------

def _compact(value) -> str:
    """Single-line compact JSON.  Dict values use { } with spaces inside."""
    if isinstance(value, dict):
        if not value:
            return '{}'
        parts = ', '.join(f'"{k}": {_compact(v)}' for k, v in value.items())
        return '{ ' + parts + ' }'
    if isinstance(value, list):
        return '[' + ', '.join(_compact(v) for v in value) + ']'
    return json.dumps(value, ensure_ascii=False)


def _aligned_compact_rows(entries: list) -> list:
    """
    Return one compact string per entry, with values column-aligned.

    Commas are placed immediately after values; alignment spaces go between
    fields (after the comma).  The very last column is never padded.

    Example output for sections with optional flags::

        { "id": "data",   "address": "0x20000000", "size": "0x1000", "name": ".data"        },
        { "id": "heap",   "address": "0x20002000", "size": "0x1800", "name": "Heap",  "flags": ["grows-up"] },
        { "id": "stack",  "address": "0x20006800", "size": "0x1800", "name": "Stack", "flags": ["grows-down"] }
    """
    if not entries:
        return []

    # Ordered union of all keys across all entries
    seen: dict = {}
    for e in entries:
        for k in e:
            seen[k] = True
    all_keys = list(seen)
    last_global_key = all_keys[-1] if all_keys else None

    # Max rendered-value width per key
    col_w = {
        key: max((len(_compact(e[key])) for e in entries if key in e), default=0)
        for key in all_keys
    }

    rows = []
    for entry in entries:
        entry_keys = list(entry.keys())
        last_entry_key = entry_keys[-1] if entry_keys else None
        parts = []
        for key in entry_keys:
            val_str = _compact(entry[key])
            is_last_in_entry = (key == last_entry_key)
            is_global_last   = (key == last_global_key)

            if is_last_in_entry and is_global_last:
                parts.append(f'"{key}": {val_str}')
            elif is_last_in_entry:
                parts.append(f'"{key}": {val_str.ljust(col_w[key])}')
            else:
                field = f'"{key}": {val_str},'
                total_w = len(f'"{key}": ') + col_w[key] + 1  # +1 for comma
                parts.append(field.ljust(total_w) + ' ')

        rows.append('{ ' + ''.join(parts) + ' }')
    return rows


# ---------------------------------------------------------------------------
# Multi-line formatter
# ---------------------------------------------------------------------------

INDENT = '  '


def _fmt_value(key: str, value, depth: int) -> str:
    """Return a formatted block for one key:value pair at the given depth."""
    inner = INDENT * (depth + 1)

    # pos / size: compact inline array  [x, y]
    if key in ('pos', 'size') and isinstance(value, list):
        return f'{inner}"{key}": {_compact(value)}'

    # sections / links / labels: one aligned compact line per element
    if key in ('sections', 'links', 'labels') and isinstance(value, list):
        if not value:
            return f'{inner}"{key}": []'
        elem_pad = INDENT * (depth + 2)
        aligned = _aligned_compact_rows(value)
        rows = [f'{inner}"{key}": [']
        for i, row in enumerate(aligned):
            comma = ',' if i < len(value) - 1 else ''
            rows.append(f'{elem_pad}{row}{comma}')
        rows.append(f'{inner}]')
        return '\n'.join(rows)

    # views: expanded array of expanded objects
    if key == 'views' and isinstance(value, list):
        if not value:
            return f'{inner}"{key}": []'
        rows = [f'{inner}"{key}": [']
        for i, view in enumerate(value):
            comma = ',' if i < len(value) - 1 else ''
            rows.append(_fmt_dict(view, depth + 2) + comma)
        rows.append(f'{inner}]')
        return '\n'.join(rows)

    # fallback: scalar / other
    return f'{inner}"{key}": {json.dumps(value, ensure_ascii=False)}'


def _fmt_dict(obj: dict, depth: int) -> str:
    pad = INDENT * depth
    items = list(obj.items())
    if not items:
        return f'{pad}{{}}'
    rows = [f'{pad}{{']
    for i, (k, v) in enumerate(items):
        comma = ',' if i < len(items) - 1 else ''
        rows.append(_fmt_value(k, v, depth) + comma)
    rows.append(f'{pad}}}')
    return '\n'.join(rows)


def format_diagram(data: dict) -> str:
    return _fmt_dict(data, 0) + '\n'


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print("Usage: fmt_diagram.py <diagram.json> [...]", file=sys.stderr)
        sys.exit(1)

    paths = [a for a in args if not a.startswith('--')]

    for path in paths:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        out = format_diagram(data)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f'formatted: {path}')


if __name__ == '__main__':
    main()
