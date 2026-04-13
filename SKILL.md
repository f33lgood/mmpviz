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

Turn a JSON memory map description into a publication-quality SVG — one command, no dependencies.

---

## Workflow

1. **Extract** memory regions from context (datasheet, linker script, RTL, header): start address, size, and name for each region.
2. **Write `diagram.json`** — declare views and their sections. Omit `pos`/`size`; auto-layout handles placement.
3. **Render**: `python <skill_path>/scripts/mmpviz.py -d diagram.json -o map.svg`
4. **Check**: `python <skill_path>/scripts/check.py -d diagram.json` — exit 0 = clean, 1 = errors, 2 = warnings only.
5. **Fix** any errors from `check.py` or `WARNING` lines from the renderer, then re-render.
6. Repeat until the diagram is correct.

---

## Minimal `diagram.json`

```json
{
  "views": [
    {
      "id": "flash-view",
      "title": "Flash",
      "sections": [
        { "id": "code",   "address": "0x08000000", "size": "0x09000", "name": "Code",       "flags": ["grows-up"] },
        { "id": "consts", "address": "0x08009000", "size": "0x02000", "name": "Const Data"  }
      ]
    },
    {
      "id": "sram-view",
      "title": "SRAM",
      "sections": [
        { "id": "bss",   "address": "0x20000000", "size": "0x00800", "name": ".bss"                      },
        { "id": "stack", "address": "0x20004000", "size": "0x01000", "name": "Stack", "flags": ["grows-down"] }
      ]
    }
  ]
}
```

Key rules:
- Each view declares its own `sections[]` inline — no global section pool
- `id` must match `^[a-z0-9_-]+$` and be unique within its view
- `address` and `size` accept hex strings (`"0x08000000"`) or integers
- `name` is required; use `""` to suppress the label
- Omit `pos`/`size` — auto-layout places every view automatically

---

## Commands

```bash
# Render with default theme
python <skill_path>/scripts/mmpviz.py -d diagram.json -o map.svg

# Render with plantuml theme
python <skill_path>/scripts/mmpviz.py -d diagram.json -t plantuml -o map.svg

# Validate only (no SVG written)
python <skill_path>/scripts/mmpviz.py --validate diagram.json

# Check layout rules
python <skill_path>/scripts/check.py -d diagram.json
```

---

## Checklist

- [ ] Every section has `id`, `address`, `size`, and `name`
- [ ] Section IDs use only `[a-z0-9_-]` and are unique within their view
- [ ] Large address gaps have a `"break"` section to compress them
- [ ] Gap sections are contiguous: `gap.address == previous.address + previous.size`
- [ ] Each `links` entry has both `from.view` and `to.view` referencing valid view IDs
- [ ] Section IDs in `from.sections` exist in the referenced view's `sections[]`
- [ ] `check.py` exits 0 or 2 (no ERRORs)
- [ ] `mmpviz.py` produces no `WARNING` output

---

## Reference Docs

| File | Contents |
|------|----------|
| `references/diagram-schema.md` | All `diagram.json` fields — types, defaults, allowed values |
| `references/theme-schema.md` | All `theme.json` style properties, examples, and tips |
| `references/create-diagram.md` | Step-by-step authoring guide with common pitfalls and fixes |
| `references/check-rules.md` | All `check.py` rules, thresholds, and remediation |

---

## Install as Claude Code Skill

```bash
ln -s "$(pwd)" ~/.claude/skills/mmpviz
```
