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

Authoring rules and field-level details live in `references/create-diagram.md`. Read it before Step 1 — the workflow references its sections by name but doesn't restate their content.

1. **Plan the views.** Read `references/create-diagram.md` — the *Rules and verification*, *Collect source context*, and *Design the view structure* sections — then sketch a views plan: list each view you intend to create with its type (`root` or `drill-down`) and, for every drill-down, one sentence on why it earns its column. The plan is a *forward check* — it catches obvious mistakes early, but the definitive gate is Step 5 (the same rule list, run against the rendered output). Keep the plan lightweight; don't over-polish it.

2. **Write `diagram.json`** per the plan, following create-diagram.md's *Write `diagram.json`* section for field-level details (addresses, sizes, breaks, links, labels).

3. **Render**: `python <skill_path>/scripts/mmpviz.py -d <input> -o <output>` (`mmpviz.py` lives in `scripts/` alongside this SKILL.md — use its absolute path).
   The render pipeline runs automatically in order: schema validate → layout check → SVG render.
   `[ERROR]` lines abort before the SVG is written; `[WARNING]` lines are printed but the SVG is still produced.
   Errors and warnings are expected on the first render — they drive the next step.

4. **Fix errors and warnings** — for each `[ERROR]` or `[WARNING]` line, consult `references/check-rules.md` to identify the rule, its cause, and the recommended fix. Edit the input file and re-render. Repeat until there are no `[ERROR]` or `[WARNING]` lines.

5. **Verification gate — this is the gate, not Step 1.** With a clean render and the SVG open, work through **every checkbox** in create-diagram.md's *Rules and verification* section — the same six-rule list you read during planning, now ticked off against the rendered artifact. Each failed check has a fix recipe inline; apply it, modify `diagram.json`, and go back to Step 3. Iterate until every item passes on a single clean pass — no skipping, no "good enough." The loop is the mechanism that catches the dominant failure modes (invented umbrellas, unjustified drill-downs, real regions flagged as `break`, illegible labels) that forward-planning alone lets slip.

6. **Done** — only when every Step 5 check passed on the most recent render.

---

## Commands

```bash
# Render (schema validate + layout check + SVG)
python <skill_path>/scripts/mmpviz.py -d <input> -o <output>

# Render with plantuml theme
python <skill_path>/scripts/mmpviz.py -d <input> -t plantuml -o <output>

# Render with a specific layout algorithm (default is usually right)
# Run mmpviz.py --help for the current list of --layout choices and what they do.
python <skill_path>/scripts/mmpviz.py -d <input> -o <output> --layout <algo>

# Format input file in-place, then render
python <skill_path>/scripts/mmpviz.py -d <input> -o <output> --fmt

# Format input file in-place only (no render)
python <skill_path>/scripts/mmpviz.py -d <input> --fmt
```

**Theme resolution.** When `-t` is omitted, `mmpviz` first looks for a `theme.json` sibling of `diagram.json`; if none exists, it falls back to the built-in default theme. Explicit `-t <name|path>` always wins over a sibling file.

---

## Reference Docs

Read on demand — don't load all at once. The three **core playbook** files are the ones to reach for while authoring; `theme-schema.md` is optional.

**Core playbook** (author-facing):

| File | When to read |
|------|--------------|
| `references/create-diagram.md` | Authoring `diagram.json` — rules, views, sections, links, breaks, labels, verification checklist. Read before Step 1 of the workflow. |
| `references/diagram-schema.md` | Full field reference — types, defaults, allowed values. Consult when writing JSON fields. |
| `references/check-rules.md` | Diagnosing `[ERROR]` / `[WARNING]` output. Consult in workflow Step 4. |

**Optional** (only when relevant):

| File | When to read |
|------|--------------|
| `references/theme-schema.md` | Customising visual style via `theme.json`. Skip unless the user asks for a specific theme or per-section colour. |

Layout-engine internals live in `docs/auto-layout-algorithm.md` (developer-facing, not part of the authoring path). Picking a `--layout` algorithm is empirical — start with the default and switch only if the canvas shape or link routing isn't acceptable. The internals doc is only useful if you're modifying the layout code itself.

## Examples

`examples/` contains ready-to-render diagrams paired with their golden SVG outputs.
Browse these for patterns before authoring from scratch:

| Directory | What it demonstrates |
|-----------|----------------------|
| `examples/chips/` | Real chip memory maps (STM32, RISC-V, ARM CoreSight, etc.) |
| `examples/link/` | Link band styles (connector, band) and anchor variants |
| `examples/stack/` | Stack and guard-page layout patterns |
| `examples/diagram/` | Break sections for large address gaps, and address label annotations |
| `examples/layout/` | Height overrides (`height_override`, `height_global`), column ordering (`column_order`), and layout-algorithm behaviour demos |
| `examples/themes/` | Per-section and per-link style overrides |

Each example contains a `diagram.json` and a `golden.svg`.
