# PULPissimo Memory Map — Sources and Inconsistencies

This file records the primary sources used for the memory map diagram and known
discrepancies between them, so that future edits start from a known baseline rather
than re-discovering the same conflicts.

---

## Primary Sources

| Source | Repository / Location | Role |
|--------|----------------------|------|
| [`soc_mem_map.svh`](https://github.com/pulp-platform/pulpissimo/blob/master/hw/includes/soc_mem_map.svh) | [pulp-platform/pulpissimo](https://github.com/pulp-platform/pulpissimo) `hw/includes/` | RTL address decoder — ground truth for hardware |
| [`memorymap.tex`](https://github.com/pulp-platform/pulpissimo/blob/master/doc/datasheet/content/memorymap.tex) | [pulp-platform/pulpissimo](https://github.com/pulp-platform/pulpissimo) `doc/datasheet/content/` | Datasheet — may lag the RTL |
| [`memory_map.h`](https://github.com/pulp-platform/pulp-runtime/blob/master/include/archi/chips/pulpissimo/memory_map.h) | [pulp-platform/pulp-runtime](https://github.com/pulp-platform/pulp-runtime) `include/archi/chips/pulpissimo/` | Software header — defines offsets used by the SDK |
| [`udma.json`](https://github.com/pulp-platform/pulp-configs/blob/master/configs/chips/pulpissimo/udma.json) | [pulp-platform/pulp-configs](https://github.com/pulp-platform/pulp-configs) `configs/chips/pulpissimo/` | uDMA peripheral configuration — authoritative for channel list |

All three repositories are public (Apache-2.0 / SolderPad).

**Rule of thumb:** When sources disagree, prefer `soc_mem_map.svh` (RTL) for address
ranges and `udma.json` for the uDMA channel list.

---

## System-Level Address Space

According to `soc_mem_map.svh`, the entire system is allocated within:

```
CLUSTER: [0x1000_0000, 0x2000_0000)   256 MiB
```

**"Cluster" ≠ "AXI Plug".** The CLUSTER range [0x10000000, 0x20000000) is the full
system window reserved for connecting an optional PULP cluster processor. The AXI Plug
is only the 4 MiB bridge interface at [0x10000000, 0x10400000) within that window.
In PULPissimo (without an attached cluster), most of the CLUSTER window is unused.
The diagram shows the AXI Plug section labelled as "AXI Plug" — not "Cluster".

### Top-level regions (direct children of the system map)

| Region | Start | End | Size |
|--------|-------|-----|------|
| AXI_PLUG | 0x1000_0000 | 0x1040_0000 | 4 MiB |
| BOOT_ROM | 0x1A00_0000 | 0x1A04_0000 | 256 KiB |
| PERIPHERALS | 0x1A10_0000 | 0x1A14_0000 | 256 KiB |
| PRIVATE_BANK0 | 0x1C00_0000 | 0x1C00_8000 | 32 KiB |
| PRIVATE_BANK1 | 0x1C00_8000 | 0x1C01_0000 | 32 KiB |
| TCDM | 0x1C01_0000 | 0x1C09_0000 | 512 KiB |

Notes:
- PRIVATE_BANK0, PRIVATE_BANK1, and TCDM are **siblings** in the address hierarchy —
  they are not sub-regions of an "L2 Memory" container. The label "L2 TCDM" in the
  diagram is a functional grouping for readability, not a hardware hierarchy.
- The diagram's `"L2 Memory"` overview section (0x1C000000, 576 KiB) and `l2-view`
  panel are an approximation that groups all three banks as if they were one region;
  this is acceptable for a high-level overview.

---

## Peripheral Bus (PERIPHERALS)

PERIPHERALS spans `[0x1A10_0000, 0x1A14_0000)` (256 KiB) per `soc_mem_map.svh`.

The current diagram sizes APB Bus as 136 KiB (ending at 0x1A12_2000). The gap from
0x1A122000 to 0x1A140000 (120 KiB) is reserved/unused Chip Control space.

### Sub-regions within PERIPHERALS (per `soc_mem_map.svh`)

| Peripheral | Start | End | Notes |
|-----------|-------|-----|-------|
| GPIO | 0x1A10_1000 | 0x1A10_2000 | (see FLL note below) |
| UDMA | 0x1A10_2000 | 0x1A10_4000 | |
| SOC_CTRL | 0x1A10_4000 | 0x1A10_5000 | |
| ADV_TIMER | 0x1A10_5000 | 0x1A10_6000 | |
| SOC_EVENT_GEN | 0x1A10_6000 | 0x1A10_7000 | |
| Reserved | 0x1A10_7000 | 0x1A10_9000 | 8 KiB |
| INTERRUPT_CTRL | 0x1A10_9000 | 0x1A10_B000 | labeled "Event Unit" in diagram |
| APB_TIMER | 0x1A10_B000 | 0x1A10_C000 | |
| HWPE | 0x1A10_C000 | 0x1A10_D000 | |
| Reserved | 0x1A10_D000 | 0x1A10_F000 | 8 KiB |
| VIRTUAL_STDOUT | 0x1A10_F000 | 0x1A11_0000 | |
| DEBUG | 0x1A11_0000 | 0x1A12_0000 | 64 KiB |
| CHIP_CTRL | 0x1A12_0000 | 0x1A14_0000 | 128 KiB; contains FLL and Pad Config |

CHIP_CTRL sub-regions:

| Sub-region | Start | End |
|-----------|-------|-----|
| FLL | 0x1A12_0000 | 0x1A12_1000 |
| PAD_CFG | 0x1A12_1000 | 0x1A12_2000 |
| (reserved) | 0x1A12_2000 | 0x1A14_0000 | |

---

## Known Inconsistencies

### 1. FLL address — software header vs RTL

- **Diagram** (follows `memory_map.h`): `FLL` shown at `0x1A10_0000–0x1A10_1000`
- **RTL** (`soc_mem_map.svh`): FLL is within CHIP_CTRL at `0x1A12_0000–0x1A12_1000`
- **`memory_map.h`**: defines `ARCHI_FLL_OFFSET = 0x00000000` relative to
  `ARCHI_SOC_PERIPHERALS_ADDR = 0x1A100000`, placing a software-visible FLL interface
  at 0x1A100000.
- **Impact**: The current diagram has *two* FLL entries: `"FLL"` at 0x1A100000 (from
  software header) and `"FLL Cfg"` at 0x1A120000 (from RTL). What occupies
  0x1A100000–0x1A101000 in the RTL is unclear — it may be a legacy alias or an
  unlabeled region.
- **Decision needed**: Either remove `"FLL"` at 0x1A100000 and rename it to indicate
  the ambiguity, or verify in hardware simulation which address is actually decoded.

### 2. Boot ROM size — datasheet vs RTL

- **Datasheet** (`memorymap.tex`): 8 KiB (0x2000)
- **RTL** (`soc_mem_map.svh`): 256 KiB (0x40000)
- **Diagram**: uses 256 KiB (RTL is authoritative for decoder range)
- The datasheet likely describes the actual ROM content size; the RTL decoder allocates
  a larger window.

### 3. CHIP_CTRL total size vs diagram APB Bus range

- **RTL**: CHIP_CTRL (and thus PERIPHERALS) ends at 0x1A14_0000
- **Diagram**: APB Bus section sized as 136 KiB (ends at 0x1A12_2000)
- Gap2 covers 0x1A122000–0x1C000000 and absorbs the unused tail of CHIP_CTRL.
  This is acceptable for a high-level diagram. A corrected version would size APB Bus
  at 256 KiB (0x40000) ending at 0x1A140000, with Gap2 starting at 0x1A140000.

### 4. HW Filter in uDMA channels

- **Diagram** (previously): included a "HW Filter" channel at 0x1A102400
- **`udma.json`**: only 7 channels — UART, SPIM, I2C×2, SDIO, I2S, CPI. HW Filter
  is a GAP8/VEGA-only optional IP.
- **Status**: HW Filter has been removed from the diagram.

### 5. L2 memory hierarchy naming

- **RTL**: PRIVATE_BANK0, PRIVATE_BANK1, TCDM are peers at the same level
- **Diagram**: groups them under a single "L2 TCDM (576 KiB)" overview section and
  an "L2 TCDM Memory" detail panel
- This is a presentational simplification, not a hardware hierarchy. The label "L2"
  is conventional (second-level memory) but not an RTL block name.

### 6. uDMA channel addresses — global config offset

- The uDMA base at 0x1A102000 begins with a 0x80-byte global configuration block
  (clock gate / event routing), followed by per-channel registers at 0x80-byte strides.
- Some software headers (e.g. channel ID enumerations) number channels starting from
  0, which can make UART appear to start at 0x1A102000. In fact UART starts at
  0x1A102080 (after the global config block).

---

## Pending Diagram Corrections

1. Clarify or remove `"FLL"` at 0x1A100000 (see inconsistency #1 above).
2. Optionally extend APB Bus to 0x1A140000 and move Gap2 start to 0x1A140000 to
   match the RTL PERIPHERALS range.
3. If a CHIP_CTRL detail view is added, FLL and Pad Config should appear as
   sub-regions within it.
