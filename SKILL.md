---
name: mmpviz
description: >
  This skill should be used when the user asks to "generate a memory map diagram",
  "visualize memory layout", "create a memory map SVG", "draw memory regions",
  "show flash and RAM as a diagram", or "produce an embedded memory map".
  Use it when turning address/size data into an SVG memory map diagram.
version: 1.0.0
tools:
  - Read
  - Write
  - Bash
---

# mmpviz — Memory Map Visualizer

Generate SVG memory map diagrams from a JSON description of memory regions.
Takes a `diagram.json` (memory layout + display areas) and optionally a `theme.json` (colors, fonts),
and produces a self-contained `.svg` file.

---

## Prerequisites

Python 3 (standard library only — no pip installs required).

---

## Invocation

```bash
python <skill_path>/scripts/mmpviz.py -d diagram.json [-t theme.json] [-o output.svg]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-d` / `--diagram` | required | Path to `diagram.json` |
| `-t` / `--theme` | built-in defaults | Path to `theme.json` |
| `-o` / `--output` | `map.svg` | Output SVG file path |
| `--validate` | — | Validate `diagram.json` and exit (no SVG written) |

---

## Quick Example

**diagram.json**
```json
{
  "title": "STM32F103 Memory Map",
  "size": [500, 900],
  "sections": [
    { "id": "Flash", "address": "0x08000000", "size": "0x00020000", "type": "area" },
    { "id": "text",  "address": "0x08000000", "size": "0x00009000", "name": "Code", "flags": ["grows-up"] },
    { "id": "rodata","address": "0x08009000", "size": "0x00002000", "name": "Const Data" },

    { "id": "SRAM",  "address": "0x20000000", "size": "0x00005000", "type": "area" },
    { "id": "stack", "address": "0x20004000", "size": "0x00001000", "name": "Stack", "flags": ["grows-down"] }
  ],
  "areas": [
    {
      "id": "flash-view",
      "title": "Flash Memory",
      "range": ["0x08000000", "0x08020000"],
      "pos": [50, 80],
      "size": [180, 750]
    },
    {
      "id": "sram-view",
      "title": "SRAM",
      "range": ["0x20000000", "0x20005000"],
      "pos": [270, 80],
      "size": [180, 750]
    }
  ],
  "links": {
    "sections": [["Flash", "SRAM"]]
  }
}
```

**Generate SVG:**
```bash
python <skill_path>/scripts/mmpviz.py -d diagram.json -o memory_map.svg
```

**With a theme:**
```bash
python <skill_path>/scripts/mmpviz.py -d diagram.json -t <skill_path>/examples/dark_theme.json -o memory_map.svg
```

---

## `diagram.json` Structure

Two top-level concepts:

### `sections[]` — memory regions

```json
{ "id": "text", "address": "0x08000000", "size": "0x9000", "name": "Code", "flags": ["grows-up"] }
```

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Unique identifier (used as theme key) |
| `address` | yes | Start address (hex string or integer) |
| `size` | yes | Size in bytes (hex string or integer) |
| `type` | no | `"area"` for a container region, `"section"` (default) for a leaf |
| `name` | no | Display label (falls back to `id`) |
| `flags` | no | `"grows-up"`, `"grows-down"`, `"break"`, `"hidden"` |

### `areas[]` — display panels

```json
{
  "id": "flash-view",
  "title": "Flash Memory",
  "range": ["0x08000000", "0x08020000"],
  "pos": [50, 80],
  "size": [180, 750]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Unique identifier — **matches `theme.json` area key** |
| `range` | no | `[min_addr, max_addr]` — filters which sections appear |
| `pos` | no | `[x, y]` pixel position on canvas |
| `size` | no | `[width, height]` pixel dimensions |
| `sections` | no | Per-section flag/address overrides within this area |
| `labels` | no | Address annotation lines |

---

## `theme.json` Structure (optional)

```json
{
  "defaults": {
    "background": "#1a1a2e",
    "fill": "#16213e",
    "text_fill": "#a8dadc",
    "font_size": 13
  },
  "areas": {
    "flash-view": {
      "fill": "#08c6ab",
      "text_fill": "white",
      "sections": {
        "text": { "fill": "#1d6fa4" }
      }
    }
  },
  "links":  { "fill": "#212b38", "opacity": 0.6 },
  "labels": { "stroke": "#a8dadc", "stroke_dasharray": "5,3" }
}
```

Resolution order: `defaults` → `areas[area_id]` → `areas[area_id].sections[section_id]`

Ready-made themes: `examples/dark_theme.json`, `examples/light_theme.json`

---

## Reference Docs

| File | Contents |
|------|----------|
| `references/diagram-schema.md` | All `diagram.json` fields with types, defaults, allowed values |
| `references/theme-schema.md` | All `theme.json` fields with types and defaults |
| `references/create-diagram.md` | Step-by-step guide for authoring a diagram from scratch |
| `references/apply-theme.md` | How to choose and customize a theme |

---

## Install as Claude Code Skill

```bash
ln -s "$(pwd)" ~/.claude/skills/mmpviz
```

After linking, agents can invoke the skill via its absolute path:
```bash
python ~/.claude/skills/mmpviz/scripts/mmpviz.py -d diagram.json -o map.svg
```
