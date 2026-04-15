---
name: mmpviz
description: >
  Use this skill whenever the user wants to visualize, diagram, or document a memory map,
  memory layout, address map, or address space — from any source (datasheet, linker script,
  RTL, header file). Key trigger concepts: memory map, memory layout, address map, address space.
version: 1.0.0
tools:
  - Read
  - Write
  - Bash
---

# mmpviz — Memory Map Visualizer

Turn a JSON memory map description into a publication-quality SVG — one command, no dependencies.

---

## File naming

**Input (`-d`):** use the filename the user already has or specifies. Default to `diagram.json` in the current directory when no name is given.

**Output (`-o`):** derive from the input — replace the `.json` extension with `.svg` (e.g. `stm32.json` → `stm32.svg`). Place it next to the input file unless the user asks otherwise.

---

## Workflow

1. **Create the input file** — collect memory regions from context, design the view structure, then write `diagram.json`.
   Consult `references/create-diagram.md` for detailed guidance on each of these sub-steps.
2. **Render**: `python <skill_path>/scripts/mmpviz.py -d <input> -o <output>` (`mmpviz.py` lives in `scripts/` alongside this SKILL.md — use its absolute path)
   The render pipeline runs automatically in order: schema validate → layout check → SVG render.
   `[ERROR]` lines abort before the SVG is written; `[WARNING]` lines are printed but the SVG is still produced.
   Errors and warnings are expected on the first render — they drive the next step.
3. **Fix errors and warnings** — for each `[ERROR]` or `[WARNING]` line, consult `references/check-rules.md` to identify the rule, its cause, and the recommended fix. Edit the input file and re-render. Repeat until there are no `[ERROR]` or `[WARNING]` lines.
4. **Post-render checks** — once the render is clean (no errors or warnings), review the SVG for visual issues not caught by the checker:
   - **Section label overflow**: name truncated or overflowing its box — set `"min_height"` on that section, or flag it `"break"`.
   - **Dominant section**: one section crowds out neighbours — set `"max_height"` on it.
   - **Wrong column layout**: a view lands in the wrong column — verify `links[]` entries reference the correct view IDs.
   - **Link band to wrong panel**: band connects to the wrong detail view — verify `to.view` matches the exact `id` of the intended target view.
   Apply any necessary fixes to the input file and re-render.
5. **Done** — both files are valid and visually correct.

---

## Commands

```bash
# Render (schema validate + layout check + SVG)
python <skill_path>/scripts/mmpviz.py -d <input> -o <output>

# Render with plantuml theme
python <skill_path>/scripts/mmpviz.py -d <input> -t plantuml -o <output>

# Format input file in-place, then render
python <skill_path>/scripts/mmpviz.py -d <input> -o <output> --fmt

# Format input file in-place only (no render)
python <skill_path>/scripts/mmpviz.py -d <input> --fmt
```

---

## Reference Docs

Read these as needed — don't load all at once.

| File | When to read |
|------|--------------|
| `references/create-diagram.md` | Authoring `diagram.json` — views, sections, links, breaks, labels |
| `references/diagram-schema.md` | Full field reference — types, defaults, allowed values |
| `references/check-rules.md` | Diagnosing `[ERROR]`/`[WARNING]` output |
| `references/theme-schema.md` | Customising visual style via `theme.json` |
| `references/auto-layout-algorithm.md` | Layout engine internals — read only if diagnosing unexpected column or height behaviour |

## Examples

`examples/` contains ready-to-render diagrams paired with their golden SVG outputs.
Browse these for patterns before authoring from scratch:

| Directory | What it demonstrates |
|-----------|----------------------|
| `examples/chips/` | Real chip memory maps (STM32, RISC-V, ARM CoreSight, etc.) |
| `examples/link/` | Link band styles (connector, band) and anchor variants |
| `examples/stack/` | Stack and guard-page layout patterns |
| `examples/diagram/break/` | Break section usage for large address gaps |
| `examples/diagram/labels/` | Address label annotations |
| `examples/layout/` | Per-section and global height overrides; column ordering |
| `examples/themes/` | Per-section and per-link style overrides |

Each example contains a `diagram.json` and a `golden.svg`.

