# mmpviz

SVG memory map visualizer for embedded systems. Takes a JSON description of memory regions and produces a diagram like this:

```
Flash Memory          SRAM
┌──────────┐╌╌╌╌╌╌╌╌┌──────────┐
│  0x0800  │         │  0x2000  │
│          │         │          │
│   Code   │         │   .bss   │
│   ↑↑↑    │         │          │
├──────────┤         ├──────────┤
│ Const    │         │   Heap   │
├──────────┤         ├──────────┤
│    ≈≈    │         │  Stack   │
│          │         │   ↓↓↓    │
└──────────┘╌╌╌╌╌╌╌╌└──────────┘
```

---

## Requirements

Python 3 — standard library only. No pip installs, no virtual environment.

---

## Usage

```bash
python scripts/mmpviz.py -d diagram.json [-t theme.json] [-o output.svg]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-d` / `--diagram` | required | Memory map description |
| `-t` / `--theme` | built-in defaults | Visual styling |
| `-o` / `--output` | `map.svg` | Output file |
| `--validate` | — | Check `diagram.json` and exit |

**Quick start:**
```bash
python scripts/mmpviz.py -d examples/chips/stm32f103/diagram.json -t examples/chips/stm32f103/theme.json -o map.svg
```

---

## How it works

Two input files, one output SVG:

**`diagram.json`** — what to draw (memory regions, layout, size):
```json
{
  "sections": [
    { "id": "Flash", "address": "0x08000000", "size": "0x00020000", "type": "area" },
    { "id": "text",  "address": "0x08000000", "size": "0x00009000", "name": "Code", "flags": ["grows-up"] }
  ],
  "areas": [
    { "id": "flash-view", "title": "Flash", "range": ["0x08000000", "0x08020000"], "pos": [50, 80], "size": [180, 750] }
  ]
}
```

**`theme.json`** — how it looks (colors, fonts):
```json
{
  "defaults": { "background": "white", "fill": "#caf0f8", "text_fill": "#023e8a" },
  "areas": {
    "flash-view": { "sections": { "text": { "fill": "#48cae4" } } }
  }
}
```

The `area.id` in `diagram.json` is the key that connects to `theme.json` overrides.

---

## Examples

Each subdirectory under `examples/` contains a `diagram.json`, `theme.json`, and a `golden.svg` (reference output used by the regression test suite).

**Feature demos** (`examples/`):

| Directory | Description |
|-----------|-------------|
| `examples/stack/` | Single panel, growth arrows, large address gap |
| `examples/break/` | Four panels demonstrating all four break styles (~, ≈, /, …) |
| `examples/labels/` | Address annotation labels — directions, sides, arrow heads |
| `examples/link/` | Cross-area zoom bands and address link lines (6 style variants + cortex_m3 reference) |

**Real-world chip examples** (`examples/chips/`):

| Directory | Description |
|-----------|-------------|
| `examples/chips/stm32f103/` | ARM Cortex-M3 MCU — 5-area map with APB peripheral detail |
| `examples/chips/caliptra/` | Caliptra RoT RISC-V security subsystem |
| `examples/chips/opentitan_earlgrey/` | OpenTitan Earl Grey TL-UL crossbar SoC (65+ peripherals) |
| `examples/chips/pulpissimo/` | PULP RISC-V SoC — multi-level zoom with µDMA channel detail |

**Built-in themes** (`themes/`): `light.json`, `monochrome.json`, `plantuml.json`

---

## Reference Documentation

| File | Contents |
|------|----------|
| `references/diagram-schema.md` | All `diagram.json` fields — types, defaults, allowed values |
| `references/theme-schema.md` | All `theme.json` style properties |
| `references/create-diagram.md` | Step-by-step guide: writing a diagram from scratch |
| `references/apply-theme.md` | Choosing and customizing a theme |
| `references/layout-guide.md` | Canvas sizing, output format targets, manual placement templates |
| `references/check-rules.md` | All `check.py` validation rules — thresholds and remediation |
| `references/auto-layout-algorithm.md` | Auto-layout implementation reference with planned-vs-implemented table |
| `references/llm-guide.md` | Rules of thumb for AI/LLM-assisted diagram authoring |

---

## Features

- **Auto-layout**: column placement and section heights computed automatically from address ranges — no `pos`/`size` needed in `diagram.json`. The tool builds a DAG from address containment, assigns areas to columns by topological depth, and expands the canvas to fit.
- **Areas**: one panel per memory bus (Flash, SRAM, peripherals, …)
- **Break sections**: compress large empty regions with `"flags": ["break"]`
- **Growth arrows**: show stack/heap growth direction with `"grows-up"` / `"grows-down"`
- **Labels**: annotate specific addresses with arrow lines
- **Links**: draw connecting bands between matching regions across areas
- **Per-section colors**: full control via `theme.json` without touching diagram data
- **Auto-hide**: address/name/size labels hide automatically when a section is too small to fit them

---

## Use as an AI Agent Skill

See `SKILL.md` for invocation details and install instructions.

```bash
ln -s "$(pwd)" ~/.claude/skills/mmpviz
```

---

## Testing

```bash
python -m pytest tests/
```

Tests cover: section flags, loader, theme resolution, area pixel math, SVG builder, renderer integration, auto-layout column assignment, and golden-file regression (all examples re-rendered and compared to stored reference SVGs).
