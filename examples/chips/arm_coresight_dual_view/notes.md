# Arm CoreSight: CPU + Debugger Memory Map Views — Notes

## What This Example Demonstrates

This example shows how to represent **two overlapping perspectives of the same physical
address space** in a single diagram:

1. **CPU (AXI Master) view** — what the application processor sees when it issues load/store
   instructions. The CPU can access Trusted Memory, system peripherals, and DRAM via the
   AXI interconnect.

2. **Debugger (DAP) view** — what an external debugger connected via JTAG/SWD can access
   through the CoreSight Debug Access Port (DAP). The DAP provides two distinct access
   ports (APs):
   - **AXI-AP** — bridges the DAP to the system AXI interconnect, giving the debugger the
     *same physical address space* as the CPU (shared sections in this diagram).
   - **APB-AP** — connects to a dedicated Debug APB fabric that is **not routed** to the
     CPU's AXI master port. Only the debugger can reach these addresses.

The key insight: many devices appear at the **same address in both views** (BootROM,
TrustedSRAM, system peripherals, DRAM), but the Debug APB region (`0x20000000`) is
**visible only in the Debugger view**. The CPU has no system-bus path to that range.

---

## Address Map Summary

### Shared (CPU + Debugger via AXI-AP)

| Region | Base | Size | Notes |
|--------|------|------|-------|
| Secure Boot ROM | `0x00000000` | 64 KiB | Immutable boot firmware |
| Trusted SRAM | `0x00010000` | 512 KiB | Secure scratchpad / BL1 workspace |
| GIC-600 Distributor | `0x2C000000` | 64 KiB | Interrupt distributor registers |
| GIC-600 Redistributors | `0x2C010000` | 256 KiB | Per-CPU (4×64 KiB) redistributors |
| Generic Timer | `0x2C050000` | 64 KiB | System counter / timer frames |
| Watchdog | `0x2C060000` | 64 KiB | Generic watchdog |
| UART0 | `0x2C070000` | 64 KiB | Primary serial console |
| UART1 | `0x2C080000` | 64 KiB | Secondary serial port |
| SPI0 | `0x2C090000` | 64 KiB | SPI flash controller |
| I2C0 | `0x2C0A0000` | 64 KiB | I2C peripheral bus |
| DRAM | `0x80000000` | 1 GiB | Main DRAM (also used by ETR as trace buffer) |

### Debugger-only via Debug APB (APB-AP)

The Debug APB is physically placed at `0x20000000` but the CPU's interconnect has no
routing to this range. A hardware firewall or absent crossbar entry prevents CPU
load/store from reaching it. An external debugger accesses it through the DAP APB-AP.

| Component | Base | Size | Notes |
|-----------|------|------|-------|
| ROM Table | `0x20000000` | 64 KiB | CoreSight ROM Table — debugger uses this to auto-discover all debug components |
| CPU0 CoreDebug | `0x20010000` | 64 KiB | Halt, single-step, breakpoint control |
| CPU0 CTI | `0x20020000` | 64 KiB | Cross Trigger Interface — synchronize events across cores |
| CPU0 ETM | `0x20030000` | 64 KiB | Embedded Trace Macrocell — instruction-level trace |
| CPU1 CoreDebug | `0x20040000` | 64 KiB | |
| CPU1 CTI | `0x20050000` | 64 KiB | |
| CPU1 ETM | `0x20060000` | 64 KiB | |
| CPU2 CoreDebug | `0x20070000` | 64 KiB | |
| CPU2 CTI | `0x20080000` | 64 KiB | |
| CPU2 ETM | `0x20090000` | 64 KiB | |
| CPU3 CoreDebug | `0x200A0000` | 64 KiB | |
| CPU3 CTI | `0x200B0000` | 64 KiB | |
| CPU3 ETM | `0x200C0000` | 64 KiB | |
| Cross Trigger Matrix | `0x200D0000` | 64 KiB | CTM — global cross-trigger routing |
| STM | `0x200E0000` | 64 KiB | System Trace Macrocell — software trace via STP protocol |
| ETF / Funnel | `0x200F0000` | 64 KiB | Embedded Trace FIFO and trace funnel |
| TPIU | `0x20100000` | 64 KiB | Trace Port Interface Unit — off-chip trace output |

---

## Diagram Structure and mmpviz Technique

### The "Dual-Root" Pattern

This diagram uses **two root views** side by side in the left column:
- `cpu-view` — the CPU's perspective
- `debugger-view` — the debugger's perspective (a superset)

Both views share the same section pool and the same address range
(`0x00000000`–`0xC0000000`). They are deliberately made **structurally identical** —
same number of entries in the same address order — so a reader can compare them
line-by-line. The difference is exactly one slot:

| Position | CPU view | Debugger view |
|----------|----------|---------------|
| `0x00000000` | Secure Boot ROM | Secure Boot ROM |
| `0x00010000` | Trusted SRAM | Trusted SRAM |
| `0x00090000` | ··· (break) | ··· (break) |
| **`0x20000000`** | **`Debug APB — CPU: no access` (break)** | **`Debug APB` (real section + band)** |
| `0x20110000` | ··· (break) | ··· (break) |
| `0x2C000000` | System Peripherals | System Peripherals |
| `0x2C0B0000` | ··· (break) | ··· (break) |
| `0x80000000` | DRAM (1 GiB) | DRAM (1 GiB) |

The CPU view shows a break labeled **"Debug APB — CPU: no access"** at the exact
addresses 0x20000000–0x20110000. This directly answers the question "can the CPU
access the Debug APB?" — no, because there is no system-bus routing to that range.
The Debugger view shows the same address range as a real mapped section with a link
band to the detail panel.

### Link Routing

The diagram uses **three explicit link bands**, all via `links.sub_sections`:

```json
"sub_sections": [
  ["cpu-view",      "SysPeriph", "shared-periph-detail"],
  ["debugger-view", "SysPeriph", "shared-periph-detail"],
  ["debugger-view", "DebugAPB",  "debug-apb-detail"]
]
```

Both `cpu-view` and `debugger-view` connect to the **same** `shared-periph-detail`
panel. This single panel with two incoming bands is the explicit visual statement: the
same physical registers are reachable from both access domains.

#### Why explicit targets are needed (and how they work)

`links.sub_sections` normally uses *first-match routing*: for `[source, section]` it
finds the first view appearing after `source` in `views[]` whose section set covers the
named section's address range. Both `cpu-view` and `debugger-view` cover the SysPeriph
range (`0x2C000000`–`0x2C0B0000`), so first-match routing from `cpu-view` would
incorrectly land on `debugger-view` instead of `shared-periph-detail`.

The **explicit target** form `[source, section, target]` bypasses this entirely: the
renderer draws the band directly from `source` to `target`, using `section` only to
determine the band's vertical endpoints on each panel. This feature was added to
`links.sub_sections` specifically to support *fan-in* patterns — multiple source views
converging on the same detail panel.

### Section Reuse for Shared Regions

Sections like `BootROM`, `TrustedSRAM`, `DRAM`, and the full `SysPeriph` hierarchy are
defined once but referenced in **both** `cpu-view` and `debugger-view`. This correctly
conveys that the same physical memory address (e.g., `0x2C000000` for GIC) is accessible
from both perspectives, while keeping the canonical address/size data in a single place.

---

## Limitations and Simplifications

- **Addresses are indicative.** The exact Debug APB base address (`0x20000000`) and the
  system peripheral addresses (`0x2C000000`) are inspired by Arm reference platforms
  (see sources below) but rounded for clarity. Real SoC designs vary by vendor.

- **DRAM is accessible by both views** but not linked to a detail panel here; it is shown
  as a proportional block in both overviews. The ETR (Embedded Trace Router) can also
  write trace data directly into DRAM via the AXI-AP — this captures the dual-role of
  DRAM as both a CPU data store and a trace sink.

- **CPU0–CPU3 are modeled** with 3 CoreSight components each (CoreDebug + CTI + ETM).
  In practice each Cortex-A55/A510/X3 core may also expose a PMU (Performance Monitoring
  Unit) and additional trace components; these are omitted for diagram clarity.

---

## Primary Sources

| Source | Description |
|--------|-------------|
| [Arm Neoverse V2 Reference Design Technical Overview (ID 102759)](https://documentation-service.arm.com/static/632b1f40e68c6809a6b4162b) | Section 7.2.1 (AP System Memory Map) and 7.2.6 (Debug Memory Maps) provide the clearest published example of CPU and Debugger views documented separately in the same chip TRM. |
| [Understanding the CoreSight DAP (Arm Developer PDF)](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Tutorial%20Guide%20Diagrams%20and%20Screenshots/Arm%20Development%20Studio/Understanding%20the%20CoreSight%20DAP/Understanding_the_CoreSight_DAP.pdf) | Tutorial explaining DAP, MEM-AP, AHB-AP, APB-AP, and ROM Tables — fundamental architecture behind the dual-view concept. |
| [Lauterbach App Note: Setup of the Debugger for a CoreSight System](https://www2.lauterbach.com/pdf/app_arm_coresight.pdf) | Page 24 ("Real-time Memory Access") confirms that an AXI/AHB MEM-AP uses "the same mapping as from core view", making system memory a shared address space. |
| [Arm CoreSight Technology System Design Guide (DGI 0012D)](https://developer.arm.com/documentation/dgi0012/d/) | Figures 4-2 and 4-3 show the canonical CoreSight system architecture diagram with system memory bus and Debug APB as separate access paths. |
| [Arm Corstone SSE-300 Application Note (AN547 / DAI0547B)](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/DAI0547B_SSE300_PLUS_U55_FPGA_for_mps3.pdf) | Section 3.7 (Memory Map Overview) lists both CPU-accessible and debug-subsystem regions in the same table, demonstrating the co-existence of both views in a product document. |
| [Arm Juno Development Platform SoC TRM (DDI0515)](https://developer.arm.com/documentation/ddi0515/f/) | Contains separate CPU system map and CoreSight debug component map sections; the Juno CoreSight components are placed at `0x20000000` — the base address used in this diagram. |
