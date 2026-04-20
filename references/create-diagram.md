# How to Create a Memory Map Diagram

This is the authoring playbook for `diagram.json`. Sections the mmpviz workflow points into by name:

- **Rules and verification** — six rules every diagram must obey, each paired with a post-render checklist.
- **Collect source context** — what to gather from datasheets, linker scripts, RTL, or headers.
- **Design the view structure** — picking scope, views, and each view's address range.
- **Write `diagram.json`** — the concrete JSON form for views, sections, links, breaks, and labels.

---

## Rules and verification

Six rules govern every authoring decision and every correctness check. Each rule has a decision-time statement (the prose — read while planning) and a verification checklist (the `[ ]` boxes — ticked against the rendered SVG). Same rule, two uses — no separate planning/gate lists.

The rules are ordered for decision flow: Rule 1 is the general principle; Rules 2–4 are applied in sequence — decide root views (Rule 2), then the scope's leaf (Rule 3), then how to render within each view (Rule 4). Rules 5–6 cover coverage/formatting and visual correctness. **When rules conflict, earlier rules win** — in particular, Rule 3 overrides Rule 4.

**The list is the gate.** After rendering, tick every box. Any fail → modify `diagram.json`, re-render, re-run the entire list. Don't mark the diagram done until every box passes on one clean pass.

### Rule 1 — Source fidelity

Every view title, group name, and section name traces to the source. Never invent an umbrella label to tidy up flat siblings — if the cluster isn't in the source, render the siblings flat.

- [ ] Every view title, group name, and section name traces to the source (exception: `···` / `Reserved` for holes).
- [ ] No invented umbrella groupings cluster flat source siblings.

### Rule 2 — Preserve every initiator's view

Each initiator observes the fabric through its own address map. When the source distinguishes multiple address maps, each is a separate **root view** titled after its initiator — never merged for brevity, never silently dropped. Also: one view per address map — don't split a single address map across multiple root views.

**Signals that two address maps are distinct:** separate source sections/tables for each; different address widths (e.g. a narrower peripheral fabric alongside a wider global map); a cross-initiator aperture or address translation (that aperture is the `links` entry between root views).

Identify **every** address map before deciding anything else about views. The set of address maps is the set of root views.

- [ ] Every initiator's address map enumerated in the source appears as a distinct root view, titled after its initiator.
- [ ] Root views that share fabric are connected by a `links` entry.

### Rule 3 — Respect the scope's leaf level

Every diagram has a scope — system, subsystem, or device — and the scope fixes the leaf level that bounds every view:

| Scope | Leaf | Out of scope |
|-------|------|--------------|
| System map | Device or memory block | Device pages, registers |
| Subsystem map | Device | Device pages, registers |
| Device map | Register page | Individual registers |

**Below-leaf items are out of scope even when the source enumerates them — Rule 3 overrides Rule 4.** A system- or subsystem-scope diagram shows a device as a single section; its pages do not appear even if the source lists them.

**Heuristic for spotting below-leaf enumeration.** Source-enumerated siblings sharing a naming prefix (`<X>_<A>`, `<X>_<B>`, `<X>_<C>`) usually mean `<X>` names the device and the suffixes are its pages. At a scope where `<X>` is the leaf, collapse them to one section named `<X>`.

- [ ] No section name reveals below-leaf structure (shared-prefix siblings at system/subsystem scope → collapse to the prefix).
- [ ] No drill-down goes below the scope's leaf level.

### Rule 4 — Show sub-structure within the leaf; choose *how*

When the source enumerates sub-blocks **at or above the leaf level**, they are part of the source and must appear. The choice is *how*, not *whether*. For each such region, pick one of three:

- **Decompose inline** (default) — replace the parent with its sub-block sections in the same view. Self-contained view, no extra column.
- **Drill-down view** — sub-blocks in a separate view linked from the parent. Earns its column only when one of: the source itself documents the child as its own named address map; the child uses a different address space; or inline decomposition is illegible in the parent (sub-block heights fall below the legibility floor even with `min_height` — typical when the parent spans a much larger address range than the child).
- **Opaque box** — parent shown as a single region with no sub-detail. Only when the user doesn't want the detail, or the source mentions sub-blocks only in passing.

"Has sub-blocks" is **not** a drill-down justification — nearly every region has sub-blocks. When in doubt, decompose inline. A view may mix modes across its regions.

Drill-downs form a chain (overview → drill-down → further drill-down), never a graph — one column per link, no sideways branches. Below-leaf sub-blocks (Rule 3) don't enter this three-way choice at all: they collapse into the leaf parent.

- [ ] Every source region with sub-blocks **at or above the leaf level** is either decomposed inline or drilled-down (never silently dropped).
- [ ] Each drill-down cites one of the three justifications (child has its own named address map / different address space / inline illegible). Otherwise inline it.

### Rule 5 — Coverage and formatting

Every view covers its `[Lo, Hi)` end-to-end with explicit, contiguous sections. Section names are concise and don't encode sizes. Sizing uses the right tool: `"break"` for holes/reserved ranges; `"min_height"` for real named regions that need a taller floor. Hex width is uniform within a view.

- [ ] Section names have no size string embedded in `name` (size labels are rendered automatically). Aim for ≤19 characters to keep the name on the same horizontal line as the size label at default settings; longer names trigger two-line layout automatically, and the `section-name-overflow` check flags names that would overflow the panel even in two-line mode.
- [ ] Each view has `[Lo, Hi)` matching the source — `Hi` is the last source-described aperture, not padded to the architectural ceiling.
- [ ] `[Lo, Hi)` covered end-to-end; every unmentioned sub-range is a `break`-flagged hole named `···`. *(Fix: compute `gap_size = next.address − prev.address − prev.size` and insert a `break`-flagged hole.)*
- [ ] Every section has an explicit `size`.
- [ ] Real named regions use `min_height` for a taller floor; `"break"` is reserved for holes and reserved ranges only. *(Fix: remove the flag. `max_height` is accepted but ignored in the floor-stack layout model.)*
- [ ] Address literals within a view use uniform hex width.
- [ ] `min_section_height` in the theme provides the universal baseline (default: 20 px). Per-section `"min_height"` is only used when a specific section needs a floor *higher* than the global baseline — never lower, never redundantly equal. *(Fix: remove `"min_height"` entries that merely repeat `min_section_height`, or raise them above it only if that section genuinely needs a taller floor.)*

### Rule 6 — Visual correctness (from the rendered SVG)

The rendered output must match authorial intent: labels readable, no section dominates, link bands land where expected, drill-down panels aren't near-empty. These checks need the rendered SVG.

- [ ] No section label is vertically overflowing its box (labels always render; a too-short section causes text to overlap neighbours). *(Fix: raise `min_section_height` in the theme. The engine automatically raises floors for label-conflict and grows-arrow-neighbor cases — see `check-rules.md` (`min-height-violated`) for details. If overflow persists after those auto-raises, shorten the section name or widen the view. For a hole, flag it `"break"` instead.)*
- [ ] No section name overflows the panel width horizontally — the `section-name-overflow` check flags this. *(Fix: shorten the name in `diagram.json`. The layout engine cannot wrap or truncate names automatically.)*
- [ ] No single section dominates its view and crowds out its neighbours. *(In the floor-stack model every section gets only its minimum readable height — dominance by byte size no longer occurs. If a section still appears too tall, the floor is being raised by a `min_height` or `min_section_height` setting; reduce it.)*
- [ ] Every link band connects the intended source region to the intended target view. *(Fix: verify `links[]` entries reference the correct view IDs and that `to.view` matches the target view's `id`.)*
- [ ] No drill-down panel is near-empty relative to its parent (fewer than ~3 visible rows, or vast whitespace). *(Fix: if the view is intentionally small — e.g. a single-section zoom — set `"min_height"` on its section(s) to give the panel a readable height. If the view is legitimately thin because it duplicates content better shown inline, collapse the drill-down and decompose the sub-blocks inline — Rule 4.)*

If canvas shape or link routing isn't satisfactory after the checks pass, try a different layout algorithm via `--layout` (run `mmpviz.py --help` for choices; see `docs/auto-layout-algorithm.md` for how each algorithm works).

---

## Collect source context

### Scope and hierarchy

Choose the diagram's scope first; that fixes the hierarchy depth and the leaf level (Rule 3). Work top-down — don't start at the register level and aggregate upward.

| Scope | Hierarchy levels covered | Typical depth |
|-------|--------------------------|---------------|
| Full chip / SoC | system → subsystem → device | 3 levels |
| One subsystem | subsystem → device → device page | 3 levels |
| One peripheral | device → device page → registers | 3 levels |

Deepest hierarchy supported: **system → subsystem → device → device page → registers** (5 levels, 4 links). Most diagrams use 2–3.

### Gather region data

Different source types expose region data differently:

| Source | What to extract |
|--------|-----------------|
| **Datasheet / memory map table** | Region name, base address, size (or end address), access type, sub-block breakdowns, aperture assignments |
| **Linker script (`.ld` / `.icf`)** | `MEMORY` entries (origin + length), `SECTIONS` assignments splitting a region into sub-sections (`.text`, `.data`, `.bss`, stack, heap) |
| **RTL / hardware description** | Address decoder ranges, bus fabric apertures, peripheral base addresses and sizes, per-initiator address remappings |
| **C/C++ header (`#define`)** | `BASE_ADDR` + `SIZE` macros; register-block sizes; guard-page or reserved-range constants |

Invariants for every region:

- **`address`** — base address in hex. Uniform hex width within a view: 32-bit → 8 digits (`0x00000000`, not `0x0`); 64-bit → 16 digits.
- **`size`** — extent in hex; compute `size = end − base` if the source gives an end address. Required on every section (including holes and breaks). Never embed a size in `name` — sizes are rendered automatically and size-less sections can't lay out.
- **`name`** — no size annotation; use `···` or `...` for holes, `Reserved` for reserved ranges. Aim for ≤19 characters at default settings so the name fits on the same line as the size label; the `section-name-overflow` check flags names that overflow the panel even when the name is on its own line.
- **Hierarchy level** — determines which view the region belongs to (given the scope's leaf, Rule 3).

---

## Design the view structure

### Map hierarchy levels to views

Each diagram covers one scope. Given the scope, the root view and the drill-down chain are:

| Scope | Root view | Drill-down chain |
|-------|-----------|------------------|
| System map | Primary CPU address map | Subsystem → device (one column per level) |
| Subsystem map | Subsystem address space | Device → device page |
| Device map | Device address space | Device page → registers |

Secondary-initiator root views (Rule 2) sit alongside the primary; use `links` to connect them where apertures cross.

### Determine each view's address range `[Lo, Hi)`

Fix the half-open range before enumerating sections. This prevents size-less holes encoded in names and views that stop short of the decoded space.

1. **Pick `Lo` and `Hi` from the source.**
   - Full decoded space (system-wide, CPU initiator): `Lo = 0x00000000` (or `0x0000_0000_0000_0000` for 64-bit). `Hi` = end of the highest aperture the source enumerates. Extend to the architectural limit only if the source covers or reserves the full space — don't pad a sparse tail.
   - Scoped view (subsystem, device, aperture): `Lo = aperture_base`, `Hi = aperture_base + aperture_size`.
2. **Cover `[Lo, Hi)` end-to-end.** Every address belongs to exactly one section. Unmentioned sub-ranges → `break`-flagged holes named `···`. Explicitly reserved ranges → `break`-flagged, named `Reserved` or `···`.
3. **Verify contiguity.** `section[i].address + section[i].size == section[i+1].address` for every adjacent pair. First section starts at `Lo`; last ends at `Hi`. A one-byte error leaves a blank stripe.

---

## Write `diagram.json`

### Views with sections

Each entry in the `views` array is one panel. Sections are declared inline. Every section needs `id`, `address`, `size`, `name`.

```json
"views": [
  {
    "id": "flash-view",
    "title": "Flash Memory",
    "sections": [
      { "id": "code",   "address": "0x08000000", "size": "0x09000", "name": "Code"       },
      { "id": "consts", "address": "0x08009000", "size": "0x02000", "name": "Const Data" }
    ]
  },
  {
    "id": "sram-view",
    "title": "SRAM",
    "sections": [
      { "id": "bss",   "address": "0x20000000", "size": "0x00800", "name": ".bss"  },
      { "id": "stack", "address": "0x20004000", "size": "0x01000", "name": "Stack" }
    ]
  }
]
```

Canvas and panel positions are computed automatically.

**Regions that appear in multiple views.** Declare the section inline in each view — duplication makes each view self-contained:

```json
"views": [
  { "id": "overview",     "sections": [{ "id": "flash", "address": "0x08000000", "size": "0x20000", "name": "Flash" }] },
  { "id": "flash-detail", "sections": [{ "id": "flash", "address": "0x08000000", "size": "0x20000", "name": "Flash" }] }
]
```

### Links

When one view is a drill-down of a section in another view, draw a band with a `links` entry:

```json
"links": [
  { "id": "code-link", "from": { "view": "flash-view", "sections": ["code"] }, "to": { "view": "code-detail-view" } }
]
```

- `id` — required, unique across all links; used as the key in `theme.json` under `links.overrides[link_id]`.
- `from.sections` — pins the source-side vertical anchor; omit to span the full source view.
- `to.sections` — pins the destination anchor (useful for virtual→physical mappings); omit to span the full destination view.

**Choose the right `sections` form.** Both `from.sections` and `to.sections` accept three forms — prefer them in this order:

1. **Section IDs** (preferred): `["code"]` or `["uart0", "uart1"]`. Readable and survives address changes.
2. **Omitted**: leave the field out when the band spans the whole view on that side. Do **not** enumerate every section ID to achieve the same thing.
3. **Address range**: `["0x08000000", "0x08020000"]`. Only when pinning to an address range that doesn't correspond to any single section — e.g. a virtual→physical mapping.

**Cross-address-space links need `to.sections`.** When source and destination use different address spaces, without `to.sections` the tool tries to use the source address as the y-anchor on the destination side and fails with `link-anchor-out-of-bounds`.

### Break sections

Use `"flags": ["break"]` for holes and reserved ranges. The section still needs real `address` and `size` to keep contiguity — the flag only affects rendering (compacted to the theme's `break_height`, default 20 px; size label suppressed).

```json
{ "id": "unused", "address": "0x0800B000", "size": "0x00005000", "name": "···", "flags": ["break"] }
```

**Don't `break` a real named region** — use `min_height` to give it a taller floor. Flagging a real region as `break` makes it indistinguishable from a hole (Rule 5). (`max_height` is accepted but ignored in the floor-stack model.)

**Naming large breaks.** When a break sits at a view's top/bottom edge or two breaks are adjacent, the flanking address labels don't show the extent — embed the range in the name:

```json
{ "id": "gap0", "address": "0x10000000", "size": "0x0FF00000", "name": "··· (0x1000_0000, 256 MiB)", "flags": ["break"] }
```

Keep the full name ≤19 characters. Longer names may cause the size label and name label to overlap horizontally, which triggers an automatic height floor (`30 + font_size` px); whether it triggers depends on the section's rendered width — wide views are unaffected.

**Computing break size in large address spaces.** A single-nibble slip in a 16-digit hex gap is invisible and triggers `uncovered-gap`. Verify programmatically:

```
gap_size        = next_section_address − current_section_end
verify: hex(int(gap_address, 16) + int(gap_size, 16)) == next_address
```

### Growth-direction markers

For stack or heap regions that grow toward a boundary, flag `grows-up` or `grows-down` to draw a directional arrow. See `diagram-schema.md` for the full flag list.

```json
{ "id": "stack", "address": "0x20004000", "size": "0x01000", "name": "Stack", "flags": ["grows-down"] }
```

### Labels

Annotate a specific address with a label line:

```json
"labels": [
  { "id": "end-of-code", "address": "0x08009000", "text": "End of code", "length": 80, "side": "right", "directions": ["in"] }
]
```

`id` is required, unique within the view; it keys into `theme.json` under `views[view_id].labels[label_id]` for per-label overrides.

---

## Further reference

| File | Contents |
|------|----------|
| `diagram-schema.md` | Complete `diagram.json` field reference — types, defaults, allowed values |
| `theme-schema.md` | Complete `theme.json` field reference — style properties, examples |
| `check-rules.md` | All check rule descriptions, severity levels, and fix guidance |
| `../docs/auto-layout-algorithm.md` | How the auto-layout engine assigns columns, orders views, and routes links |
| `../schemas/diagram.schema.json` | Machine-readable JSON Schema for `diagram.json` |
| `../schemas/theme.schema.json` | Machine-readable JSON Schema for `theme.json` |
