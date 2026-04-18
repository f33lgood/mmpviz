# mmpviz — Memory Map / Address Map Visualizer

**Turn a JSON description of your memory layout into a publication-quality SVG diagram.**

No coordinates. No manual box placement. Just describe the address ranges and let mmpviz compute the layout.

![ARM CoreSight Dual View](https://raw.githubusercontent.com/f33lgood/mmpviz/main/examples/chips/arm_coresight_dual_view/golden.svg)

---

## Install

```bash
pip install mmpviz
```

`mmpviz` has no runtime dependencies — stdlib only. Schema and cross-reference validation run automatically on every render.

---

## Quick Start

**1. Create `diagram.json`**

```json
{
  "views": [
    {
      "id": "flash",
      "bits": 32,
      "sections": [
        { "id": "bootloader", "name": "Bootloader", "address": "0x00000000", "size": "0x8000" },
        { "id": "app",        "name": "Application","address": "0x00008000", "size": "0x78000" }
      ]
    }
  ]
}
```

**2. Render**

```bash
mmpviz -d diagram.json -o map.svg
```

**3. Choose a layout algorithm** (optional)

```bash
mmpviz -d diagram.json -o map.svg --layout algo4
```

| Flag | Description |
|------|-------------|
| `--layout algo1` | One column per DAG level |
| `--layout algo2` | Algo-1 + height-rebalancing |
| `--layout algo3` | Algo-2 + routing lanes for non-adjacent links (default) |
| `--layout algo4` | Algo-3 + vertical column alignment to minimise link length |

---

## Themes

Two built-in themes ship with mmpviz:

| Theme | Flag | Appearance |
|-------|------|------------|
| `default` | `-t default` | Neutral gray fills, clean monochrome |
| `plantuml` | `-t plantuml` | Warm yellow fills, PlantUML-style palette |

```bash
mmpviz -d diagram.json -o map.svg -t plantuml
```

**Theme resolution — first match wins:**

| `-t` flag | `theme.json` next to diagram? | Theme used |
|-----------|-------------------------------|------------|
| `-t plantuml` (or any name/path) | yes or no | The `-t` value — sibling is ignored |
| *(omit)* | **yes** | The sibling `theme.json` |
| *(omit)* | no | Built-in `default` |

For a custom theme, place a `theme.json` next to `diagram.json` and extend a built-in:

```json
{ "schema_version": 1, "extends": "plantuml" }
```

---

## Features

- **Zero required dependencies** — pure Python stdlib
- **Auto-layout** — DAG-based column assignment, height rebalancing, routing lanes for crossing-free link bridges
- **Multi-view diagrams** — model interconnected address spaces with typed links (connector, band)
- **Themes** — built-in `default` and `plantuml`; fully customisable `theme.json`
- **Per-section overrides** — granular fill, stroke, height floor/ceiling per section or view
- **Scales from MCUs to SoCs** — tested on OpenTitan Earl Grey (65+ peripherals)

---

## More Examples

Real-world chip diagrams, theme showcases, and layout comparisons are in the
[examples/](https://github.com/f33lgood/mmpviz/tree/main/examples) directory on GitHub.

Full documentation: [github.com/f33lgood/mmpviz](https://github.com/f33lgood/mmpviz)
