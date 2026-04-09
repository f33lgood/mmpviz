# Caliptra RoT Memory Map — Layout Notes

This file documents the placement rationale for `diagram.json` so that future
automated or AI-assisted layout adjustments preserve the design intent.

---

## Panel Columns

The diagram uses three columns:

| Column | Panel | x pos | Width | Notes |
|--------|-------|-------|-------|-------|
| 1 | Caliptra RoT (overview) | 60 | 200 | Full address range 0x00000000–0x70000000 |
| 2 | SoC Interface | 460 | 260 | Closest zoom to overview; 200 px gap from col 1 |
| 3 | Peripherals (top) + Crypto Subsystem (bottom) | 920 | 220 | 200 px gap from col 2 |

Gaps between all three columns are equal at 200 px. In earlier revisions the gaps
were 160 px each, but three link bands overlap in gap 1 (SoC Interface terminates
there; Peripherals and Crypto pass through), making it look visually denser and
narrower than gap 2. Equal 200 px gaps compensate for this density difference.

**Why SoC Interface is in column 2 (close to the overview):**
The SoC Interface region (0x30000000–0x30080000) sits near the visual centre of the
overview and contains the most externally visible components (Mailbox, AXI DMA, SoC
IFC CSR). Placing its zoom panel immediately adjacent to the overview keeps the
widest link band short and easy to read.

**Why Crypto and Peripherals share column 3 (far from overview):**
These two regions are both on the internal bus and share a conceptual role
(compute / entropy). Grouping them in the same column lets the link bands fan out
together on the right side without conflicting with the SoC Interface band. The extra
horizontal distance also gives the Crypto panel room to be tall.

---

## Column 3 Vertical Split

```
y=80   ┌─────────────────────┐
       │  Peripherals        │  190 px
y=270  └─────────────────────┘
       (50 px gap)
y=320  ┌─────────────────────┐
       │  Crypto Subsystem   │  1000 px
y=1320 └─────────────────────┘
```

**Why Peripherals is on top:**
Peripherals occupies a higher address range (0x20000000) than Crypto (0x10000000).
Placing the higher-address panel above the lower-address panel keeps the column
consistent with the memory-map convention used in the overview (high addresses at
top). The link band from the Peripherals section in the overview connects without
crossing the Crypto band.

**Why Peripherals is short (190 px):**
The Peripherals bus only contains two real peripherals (CSRNG and Entropy Source).
A short panel avoids wasted whitespace. The two 4 KiB sections each get ~72 px at
this height, which is more than enough for name and address labels.

**Why Crypto Subsystem is tall (1000 px):**
The crypto bus has sections with a large size variance: DOE/ECC/SHA512/SHA256 are
32 KiB each, MLDSA is 64 KiB, while HMAC512/AES/SHA3 are only 4 KiB and KeyVault/
PCRVault/DataVault are 8 KiB each. Two constraints drive the height:

1. **Vault address visibility**: vault sections (8 KiB) must reach ≥ 20 px so the
   renderer auto-shows their name and address labels. They sit in a 24 KiB group
   that needs ≥ 97 px total (easily satisfied at 1000 px).

2. **HMAC512/AES/SHA3 label visibility**: these 4 KiB sections are in groups
   alongside 32–64 KiB neighbours. The `_compute_clamped_heights` algorithm falls
   back to pure proportional rendering when the minimum-height constraints for all
   groups combined exceed the available space. At 1000 px (925 px available after
   breaks), combined with `max_section_height: 600` in the crypto-view theme area,
   the algorithm stays proportional without fallback. Each tiny section reaches
   ≈ 16 px — just above the 12 px font size. `hide_name: false` is set in
   `theme.json` to force names even if the section drops below 20 px.

The `max_section_height: 600` override in the `crypto-view` area of `theme.json`
raises the per-group ceiling from the global default of 300 to 600, allowing Group3
(SHA512+SHA256+MLDSA+SHA3, spanning 132 KiB) to reach its proportional height of
≈ 536 px without being clamped.

**Guidance for resizing:**
- Keep `crypto-view` ≥ 925 px; below that the fallback to proportional can trigger
  and HMAC512/AES/SHA3 will drop below the 12 px font size threshold.
- If sections are added to the Peripherals bus, increase `periph-view` height and
  shift `crypto-view` down by the same amount.
- Do not shrink `crypto-view` below 650 px; the vault address labels will disappear.
- The 50 px inter-panel gap marks the bus boundary; keep it ≥ 30 px.

---

## Section Display Notes

| Section | Size | Rendered height | Notes |
|---------|------|----------------|-------|
| HMAC512, AES, SHA3 | 4 KiB | ≈ 16 px | Proportional in their groups at 1000 px panel; `hide_name: false` forces name label |
| Key Vault, PCR Vault, Data Vault | 8 KiB | ≈ 32 px | Auto-show name + addresses at this height |

The auto-hide threshold in the renderer is **20 px**. Any section rendered below
20 px will have its name and address labels suppressed unless `hide_name: false` or
`hide_address: false` is set explicitly in the theme. At 16 px, HMAC512/AES/SHA3
names are forced visible but address labels remain hidden.

---

## Link Bands

Three link bands connect the overview to the zoom panels:

| Band | From (overview section) | To panel | Horizontal span |
|------|------------------------|----------|-----------------|
| SoC Interface | 0x30000000–0x30080000 in col 1 | soc-ifc-view (col 2) | ≈ 200 px |
| Peripherals | 0x20000000–0x20008000 in col 1 | periph-view (col 3 top) | ≈ 660 px |
| Crypto | 0x10000000–0x10080000 in col 1 | crypto-view (col 3 bottom) | ≈ 660 px |

The SoC Interface band (200 px) is within the ≤ 200 px ideal range. The Peripherals
and Crypto bands (660 px) slightly exceed the ≤ 600 px secondary guideline, but link
opacity is set to 0.35 in `theme.json` which keeps overlapping bands legible at this
width.

The Peripherals and Crypto bands do not cross each other because Peripherals (higher
address → higher in overview) connects to the top panel and Crypto (lower address →
lower in overview) connects to the bottom panel.
