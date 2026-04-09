# STM32F103 Memory Map — Source Notes

## Primary Sources

| Document | Publisher | URL | Role |
|----------|-----------|-----|------|
| **RM0008** — STM32F101/102/103/105/107 Reference Manual | ST Microelectronics | [st.com product page](https://www.st.com/en/microcontrollers-microprocessors/stm32f103.html) → Documentation tab | STM32-specific memory map, peripheral base addresses, flash/system-memory layout |
| **ARMv7-M Architecture Reference Manual** | Arm Ltd. | [developer.arm.com/documentation/ddi0403/latest](https://developer.arm.com/documentation/ddi0403/latest/) | Cortex-M3 fixed background regions (Code, SRAM, Peripheral, External, PPB) |

RM0008 is a freely downloadable PDF from ST (no account required); look for it on the
STM32F103 product page under the Documentation tab.

---

Memory map data is derived from the ST Microelectronics Reference Manual **RM0008**
(STM32F101xx, STM32F102xx, STM32F103xx, STM32F105xx, STM32F107xx Advanced
ARM-based 32-bit MCUs), specifically:

- **Table 3** — Memory map (Code, SRAM, Peripheral, External RAM/Device, PPB regions)
- **Table 4** — Flash memory organization (128 KiB = 64 pages × 2 KiB)
- **Section 3.3** — Embedded Flash memory (base 0x08000000, size 0x20000 = 128 KiB)
- **Section 3.3.3** — Boot configuration and alias region (0x00000000–0x07FFFFFF)
- **Section 3.4** — System memory and Option Bytes layout
- **Table 1** — APB1/APB2 peripheral base addresses

ARM Cortex-M3 background regions (Code, SRAM, Peripheral, External, PPB) are from
the ARMv7-M Architecture Reference Manual.

## Key Addresses (STM32F103 specific)

| Region | Start | End (exclusive) | Size |
|--------|-------|-----------------|------|
| Boot alias | 0x00000000 | 0x08000000 | 128 MiB |
| Flash Memory | 0x08000000 | 0x08020000 | 128 KiB |
| System Memory | 0x1FFFF000 | 0x1FFFF800 | 2 KiB |
| Option Bytes | 0x1FFFF800 | 0x1FFFF810 | 16 B |
| SRAM (ARM region) | 0x20000000 | 0x40000000 | 512 MiB |
| Peripheral (ARM region) | 0x40000000 | 0x60000000 | 512 MiB |
| M3 Internal Peripherals | 0xE0000000 | 0xE1000000 | 16 MiB |
