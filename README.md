# mmpviz

Turn a JSON memory map into a publication-quality SVG diagram — in one command, with zero dependencies.

```bash
python scripts/mmpviz.py -d diagram.json -t theme.json -o map.svg
```

---

## What is this?

Embedded systems have memory maps — address ranges for Flash, SRAM, peripherals, security subsystems — but communicating them clearly is hard. Datasheets use cramped tables. Hand-drawn diagrams go stale. Most drawing tools make you place every box by hand.

**mmpviz** takes a JSON description of your memory layout and generates a structured SVG that you can drop into documentation, presentations, or datasheets. The layout engine computes positions automatically from address ranges: just describe the addresses and let the tool draw.

---

## Examples

### STM32F103 — ARM Cortex-M3

Five linked panels: full address space overview, Flash zoom, System Memory, APB peripheral bus, and M3 internal peripherals. Every `Reserved` gap is compressed to a break. Links connect the top-level overview to each detail panel.

![STM32F103 memory map](examples/chips/stm32f103/golden.svg)

```bash
python scripts/mmpviz.py \
  -d examples/chips/stm32f103/diagram.json \
  -t examples/chips/stm32f103/theme.json \
  -o stm32.svg
```

---

### PULPissimo RISC-V SoC — four-level zoom

SoC overview → APB peripheral bus → Chip Control detail → uDMA channel breakdown. Each level is a separate panel linked by zoom bands. The uDMA panel shows individual channel registers at 128-byte granularity.

![PULPissimo memory map](examples/chips/pulpissimo/golden.svg)

---

### Caliptra Root-of-Trust

RISC-V security subsystem with separate panels for ROM, Crypto Subsystem, Peripherals, SoC Interface, ICCM, and DCCM — each independently color-coded via theme overrides.

![Caliptra memory map](examples/chips/caliptra/golden.svg)

---

### OpenTitan Earl Grey — 65+ peripherals

Full TL-UL crossbar SoC with 71 sections across four panels. Auto-layout fits the entire peripheral address space without manual positioning.

![OpenTitan Earl Grey memory map](examples/chips/opentitan_earlgrey/golden.svg)

---

## Key features

- **Auto-layout** — omit `pos`/`size` entirely. The tool builds a containment graph, assigns panels to columns by depth, and sizes each panel so every section is readable. Canvas grows to fit.
- **Multi-level zoom** — link panels together with address-matched zoom bands. Drill from a 4GB overview down to 128-byte register blocks.
- **Break compression** — mark sparse address gaps as `"break"` sections. They collapse to a thin separator; the remaining panel height is redistributed proportionally.
- **Growth arrows** — annotate stack/heap regions with directional arrows via `"grows-up"` / `"grows-down"` flags.
- **Address labels** — attach annotated leader lines to any address, on either side of the panel, in any direction.
- **Per-section colors** — full visual control through `theme.json` without touching diagram data. Four built-in themes: `default`, `light`, `monochrome`, `plantuml`. Custom themes can inherit from any built-in with `"extends"`.
- **Auto-hide** — address, name, and size labels suppress themselves when a section is too small to fit them.
- **No dependencies** — Python 3 stdlib only. No pip, no venv, no build step.

---

## Quick start

**1. Get the tool**

```bash
git clone https://github.com/f33lgood/mmpviz
cd mmpviz
```

**2. Run an example**

```bash
python scripts/mmpviz.py \
  -d examples/chips/stm32f103/diagram.json \
  -t examples/chips/stm32f103/theme.json \
  -o map.svg
```

Open `map.svg` in any browser or SVG viewer.

**3. Build your own**

Create `diagram.json` with your memory regions:

```json
{
  "sections": [
    { "id": "Flash", "address": "0x08000000", "size": "0x20000", "type": "area" },
    { "id": "code",  "address": "0x08000000", "size": "0x09000", "name": "Code",  "flags": ["grows-up"] },
    { "id": "data",  "address": "0x08009000", "size": "0x02000", "name": "Const Data" },

    { "id": "SRAM",  "address": "0x20000000", "size": "0x05000", "type": "area" },
    { "id": "bss",   "address": "0x20000000", "size": "0x00800", "name": ".bss" },
    { "id": "stack", "address": "0x20004000", "size": "0x01000", "name": "Stack", "flags": ["grows-down"] }
  ],
  "areas": [
    { "id": "Flash", "title": "Flash Memory", "range": ["0x08000000", "0x08020000"] },
    { "id": "SRAM",  "title": "SRAM",         "range": ["0x20000000", "0x20005000"] }
  ]
}
```

```bash
python scripts/mmpviz.py -d diagram.json -o map.svg
```

That is all — `pos`, `size`, and `theme.json` are optional. The layout engine handles column placement and panel sizing automatically.

---

## How it works

Two inputs, one output:

| File | Purpose |
|------|---------|
| `diagram.json` | **What** to draw — sections, addresses, flags, area definitions, links |
| `theme.json` | **How** it looks — colors, fonts, per-section overrides |
| `map.svg` | Output — self-contained SVG, renders in any browser |

The `id` field in `diagram.json` sections is the key that connects data to theme overrides. Sections without a theme entry use the area default, which falls back to the global default.

**Validate before rendering:**
```bash
python scripts/mmpviz.py -d diagram.json --validate
```

---

## Examples index

| Example | Description |
|---------|-------------|
| `examples/chips/stm32f103/` | STM32F103 ARM Cortex-M3 — 5-panel map with APB peripheral detail |
| `examples/chips/caliptra/` | Caliptra RoT RISC-V security subsystem |
| `examples/chips/opentitan_earlgrey/` | OpenTitan Earl Grey TL-UL SoC (65+ peripherals) |
| `examples/chips/pulpissimo/` | PULP RISC-V SoC — four-level zoom with µDMA channel detail |
| `examples/themes/default/` | Default (neutral gray) theme |
| `examples/themes/light/` | Light theme |
| `examples/themes/monochrome/` | Monochrome theme |
| `examples/themes/plantuml/` | PlantUML theme |
| `examples/link/cortex_m3/` | Cortex-M3 link style reference |
| `examples/break/` | Break section compression |
| `examples/labels/` | Address label styles |
| `examples/stack/` | Stack/heap growth arrows |

Built-in themes in `themes/`: `default.json` (auto-loaded), `light.json`, `monochrome.json`, `plantuml.json`

---

## Reference documentation

| File | Contents |
|------|----------|
| `references/create-diagram.md` | Step-by-step authoring guide |
| `references/diagram-schema.md` | All `diagram.json` fields, types, and defaults |
| `references/theme-schema.md` | All `theme.json` style properties |
| `references/apply-theme.md` | Choosing and customizing themes |
| `references/layout-guide.md` | Canvas sizing, manual placement, output targets |
| `references/auto-layout-algorithm.md` | Auto-layout implementation reference |
| `references/check-rules.md` | Validation rules and remediation |
| `references/llm-guide.md` | AI-assisted diagram authoring guide |

---

## Testing

```bash
python -m pytest tests/
```

Covers section flags, loader, theme resolution, pixel math, SVG builder, renderer integration, auto-layout column assignment, and golden-file regression (all examples re-rendered and diffed against stored reference SVGs).

---

## AI agent skill

See `SKILL.md` for details. Install with:

```bash
ln -s "$(pwd)" ~/.claude/skills/mmpviz
```
