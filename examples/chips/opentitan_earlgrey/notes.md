# OpenTitan Earl Grey Memory Map — Notes

## Primary Sources

Repository: **[lowrisc/opentitan](https://github.com/lowrisc/opentitan)** (public, Apache-2.0)

| Source | Location | Role |
|--------|----------|------|
| [`top_earlgrey.hjson`](https://github.com/lowrisc/opentitan/blob/master/hw/top_earlgrey/data/top_earlgrey.hjson) | `hw/top_earlgrey/data/` | Hand-written top-level configuration — authoritative for intent |
| [`top_earlgrey.gen.hjson`](https://github.com/lowrisc/opentitan/blob/master/hw/top_earlgrey/data/autogen/top_earlgrey.gen.hjson) | `hw/top_earlgrey/data/autogen/` | Auto-generated full config — authoritative for final addresses |
| [`xbar_main.gen.hjson`](https://github.com/lowrisc/opentitan/blob/master/hw/top_earlgrey/ip/xbar_main/data/autogen/xbar_main.gen.hjson) | `hw/top_earlgrey/ip/xbar_main/data/autogen/` | Main crossbar address map |
| [`xbar_peri.gen.hjson`](https://github.com/lowrisc/opentitan/blob/master/hw/top_earlgrey/ip/xbar_peri/data/autogen/xbar_peri.gen.hjson) | `hw/top_earlgrey/ip/xbar_peri/data/autogen/` | Peripheral crossbar address map |
| [`memory_map.md`](https://github.com/lowrisc/opentitan/blob/master/hw/top_earlgrey/doc/memory_map.md) | `hw/top_earlgrey/doc/` | Auto-generated documentation — matches `top_earlgrey.gen.hjson` |

**Rule of thumb:** `memory_map.md` is the canonical human-readable reference; it is regenerated from `top_earlgrey.gen.hjson` and kept in sync.

---

## Address Space Summary

| Region | Base | Size | Notes |
|--------|------|------|-------|
| Debug / ROM | `0x00000000` | 128 KiB | LC DMI, RV_DM debug, ROM, RV_DM SRAM |
| Main SRAM | `0x10000000` | 128 KiB | `sram_ctrl_main` RAM |
| Flash | `0x20000000` | 1 MiB | `flash_ctrl` memory |
| APB Peripherals | `0x40000000` | 8 MiB | All `xbar_peri`-attached peripherals + AON cluster |
| Main Peripherals | `0x41000000` | ~2.125 MiB | Flash Ctrl regs, crypto IPs, system ctrl (`xbar_main` devices) |
| RV_PLIC | `0x48000000` | 128 MiB | RISC-V platform interrupt controller |

---

## Known Inconsistencies: gen.hjson vs memory_map.md

A cross-check of all 65+ module/interface entries found three discrepancies:

### 1. `lc_ctrl.dmi` — in `memory_map.md`, absent from `top_earlgrey.gen.hjson` device nodes

- **`memory_map.md`**: `lc_ctrl dmi` at `0x0`, 4 KiB
- **`top_earlgrey.gen.hjson`**: only `lc_ctrl.regs` appears; no `dmi` device node
- **Explanation**: The DMI (Debug Module Interface) port of `lc_ctrl` is accessed through
  the JTAG TAP, not the system bus. It is not a TL-UL device and has no crossbar node.
  `memory_map.md` documents it as a debug-accessible region even though it has no
  system-bus decode entry.
- **Diagram impact**: `DbIF` (0x0–0x1200) combines `lc_ctrl dmi` and `rv_dm dbg` into
  one section; the address range is correct per `memory_map.md`.

### 2. `rv_dm.dbg` — in `memory_map.md`, absent from `top_earlgrey.gen.hjson` device nodes

- **`memory_map.md`**: `rv_dm dbg` at `0x1000`, 0x200 B
- **`top_earlgrey.gen.hjson`**: `rv_dm` has a `mem` node (0x10000, 4 KiB) and a `regs`
  node (0x41200000) but no `dbg` node
- **Explanation**: Same as `lc_ctrl.dmi` — the RISC-V debug module's JTAG port is not
  a system-bus device. `memory_map.md` records it for completeness.
- **Diagram impact**: Same as above; folded into `DbIF`.

### 3. `peri` crossbar node — in `top_earlgrey.gen.hjson`, absent from `memory_map.md`

- **`top_earlgrey.gen.hjson`**: a `peri` node at `0x40000000`, size listed per-xbar
- **`memory_map.md`**: does not list `peri` as a device; lists only the individual
  peripheral modules that sit behind `xbar_peri`
- **Explanation**: `peri` is the crossbar abstraction, not a real register-mapped device.
  `memory_map.md` correctly omits it and lists the devices instead.
- **Diagram impact**: None. The APB Peripherals area covers the entire `xbar_peri`
  window (0x40000000–0x40800000) and shows individual modules.

**All other base addresses and sizes (62+ entries) match exactly between the two files.**

---

## Debug / ROM Region (0x00000000–0x00020000)

Sections as defined in `memory_map.md`:

| Module | Interface | Base | Size |
|--------|-----------|------|------|
| lc_ctrl | dmi | `0x0` | 4 KiB |
| rv_dm | dbg | `0x1000` | 0x200 B |
| rom_ctrl | rom | `0x8000` | 32 KiB |
| rv_dm | mem | `0x10000` | 4 KiB |

**Diagram simplification:** `lc_ctrl dmi` (4 KiB) and `rv_dm dbg` (512 B) are combined
into a single "Debug Interfaces" section spanning `[0x0, 0x1200)`. A break (`···`)
compresses the gap to ROM.

---

## APB Peripheral Bus (0x40000000–0x40800000)

All peripherals use 0x10000-stride slots in the diagram, matching the `xbar_peri`
decoder granularity. Physical register files are much smaller (0x40–0x2000 bytes);
the extra space in each slot is unused address range.

Notable grouped sections:
- **OTP Ctrl** at `0x40130000` covers both `otp_ctrl core` (0x1000 B at 0x40130000)
  and `otp_macro prim` (0x20 B at 0x40138000).
- **LC Ctrl** at `0x40140000` covers `lc_ctrl regs` only; `lc_ctrl dmi` appears in
  the Debug/ROM panel.

Five address holes are break-compressed:
- `0x40160000–0x40300000` (~1.6 MiB between Alert Handler and SPI Hosts)
- `0x40330000–0x40400000` (~832 KiB between USB Device and AON cluster)
- `0x404A0000–0x40500000` (~384 KiB within AON cluster, before SRAM Ctrl Ret)
- `0x40510000–0x40600000` (~960 KiB between SRAM Ctrl Ret registers and Ret SRAM)
- `0x40610000–0x40800000` (~1.9 MiB trailing unused AON space)

---

## Main Peripheral Bus (0x41000000–0x41210000)

These devices are attached directly to `xbar_main` (the primary TL-UL crossbar).

| Module | Interface | Base | Size |
|--------|-----------|------|------|
| flash_ctrl | core | `0x41000000` | 0x200 B |
| flash_ctrl | prim | `0x41008000` | 0x80 B |
| aes | default | `0x41100000` | 0x100 B |
| hmac | default | `0x41110000` | 0x2000 B |
| kmac | default | `0x41120000` | 0x1000 B |
| otbn | default | `0x41130000` | 0x10000 B |
| keymgr | default | `0x41140000` | 0x100 B |
| csrng | default | `0x41150000` | 0x80 B |
| entropy_src | default | `0x41160000` | 0x100 B |
| edn0 | default | `0x41170000` | 0x80 B |
| edn1 | default | `0x41180000` | 0x80 B |
| sram_ctrl_main | regs | `0x411C0000` | 0x40 B |
| rom_ctrl | regs | `0x411E0000` | 0x80 B |
| rv_core_ibex | cfg | `0x411F0000` | 0x100 B |
| rv_dm | regs | `0x41200000` | 0x10 B |

**Flash Ctrl** `core` and `prim` share one diagram slot at `0x41000000`. A break
compresses the 0xF0000 gap to the crypto IPs, and a second break covers the 0x30000
gap between EDN1 and SRAM Ctrl Main.
