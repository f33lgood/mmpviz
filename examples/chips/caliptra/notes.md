# Caliptra RoT Memory Map — Notes

## Primary Sources

Repository: **[chipsalliance/caliptra-rtl](https://github.com/chipsalliance/caliptra-rtl)** (public, Apache-2.0)

| Source | Location | Role |
|--------|----------|------|
| [`config_defines.svh`](https://github.com/chipsalliance/caliptra-rtl/blob/main/src/integration/rtl/config_defines.svh) | `src/integration/rtl/` | Top-level base-address and size macros — authoritative |
| [`CaliptraHardwareSpecification.md`](https://github.com/chipsalliance/caliptra-rtl/blob/main/docs/CaliptraHardwareSpecification.md) v2.1 | `docs/` | HW Spec, Table 3.3 — address map and peripheral sizes |
| [`caliptra_top.sv`](https://github.com/chipsalliance/caliptra-rtl/blob/main/src/integration/rtl/caliptra_top.sv) | `src/integration/rtl/` | Top-level module instantiation — confirms bus topology |

**Rule of thumb:** `config_defines.svh` is the canonical address map; `CaliptraHardwareSpecification.md` Table 3.3 provides peripheral sizes.

---

## Address Space Summary

| Region | Base | Size | Notes |
|--------|------|------|-------|
| ROM | `0x00000000` | 96 KiB | Boot ROM |
| Crypto Subsystem | `0x10000000` | 512 KiB | Crypto engines + vaults |
| Peripherals | `0x20000000` | 32 KiB | CSRNG, Entropy Source |
| SoC Interface | `0x30000000` | 512 KiB | Mailbox, SHA accel, AXI DMA, SoC IFC CSR, Mailbox SRAM |
| ICCM | `0x40000000` | 256 KiB | Instruction Closely Coupled Memory |
| DCCM | `0x50000000` | 256 KiB | Data Closely Coupled Memory |
| PIC | `0x60000000` | 256 MiB | Platform Interrupt Controller |

All base addresses and sizes verified against `config_defines.svh`.

---

## Known Discrepancies and Corrections

### 1. SHA3 size — diagram had 8 KiB, corrected to 4 KiB

- **Previous diagram**: SHA3 at `0x10040000`, size `0x00002000` (8 KiB)
- **HW Spec v2.1 Table 3.3**: SHA3/SHA3 Accelerator at `0x10040000`, size `0x00001000` (4 KiB)
- **Correction**: Changed to `0x00001000` (4 KiB). `CrEnd` gap adjusted accordingly from `0x10042000` to `0x10041000`.

### 2. CSRNG and Entropy Source bus placement

- **Bus**: Peripherals bus (`0x20000000`), not Crypto Subsystem (`0x10000000`)
- **CSRNG**: `0x20002000`, 4 KiB
- **Entropy Source**: `0x20003000`, 4 KiB
- **Initial 8 KiB gap** (`0x20000000–0x20002000`) and **trailing 16 KiB** (`0x20004000–0x20008000`) are reserved/unused

---

## Crypto Subsystem (0x10000000–0x10080000)

| Module | Base | Size | Notes |
|--------|------|------|-------|
| DOE | `0x10000000` | 32 KiB | Deobfuscation Engine |
| ECC | `0x10008000` | 32 KiB | Secp384r1 |
| HMAC512 | `0x10010000` | 4 KiB | |
| AES | `0x10011000` | 4 KiB | |
| *(reserved)* | `0x10012000` | 24 KiB | break-compressed |
| Key Vault | `0x10018000` | 8 KiB | |
| PCR Vault | `0x1001A000` | 8 KiB | |
| Data Vault | `0x1001C000` | 8 KiB | |
| *(reserved)* | `0x1001E000` | 8 KiB | break-compressed |
| SHA512 | `0x10020000` | 32 KiB | |
| SHA256 | `0x10028000` | 32 KiB | |
| MLDSA/MLKEM | `0x10030000` | 64 KiB | |
| SHA3 | `0x10040000` | 4 KiB | corrected from 8 KiB |
| *(reserved)* | `0x10041000` | ~252 KiB | break-compressed |

---

## Peripherals Bus (0x20000000–0x20008000)

| Module | Base | Size | Notes |
|--------|------|------|-------|
| *(reserved)* | `0x20000000` | 8 KiB | break-compressed (PeriGap0) |
| CSRNG | `0x20002000` | 4 KiB | |
| Entropy Source | `0x20003000` | 4 KiB | |
| *(reserved)* | `0x20004000` | 16 KiB | break-compressed (PeriEnd) |

---

## SoC Interface (0x30000000–0x30080000)

| Module | Base | Size | Notes |
|--------|------|------|-------|
| *(reserved)* | `0x30000000` | 128 KiB | break-compressed (SocGap0) |
| Mailbox CSR | `0x30020000` | 4 KiB | |
| SHA512 Accel | `0x30021000` | 4 KiB | |
| AXI DMA | `0x30022000` | 4 KiB | |
| *(reserved)* | `0x30023000` | 52 KiB | visible gap section (SocMid) |
| SoC IFC CSR | `0x30030000` | 64 KiB | |
| Mailbox SRAM | `0x30040000` | 256 KiB | |
