# Curtain drive rev B: bill of materials and build notes

Rev B has the same circuit, ICs and firmware pin map as rev A. What changes is that
every passive, diode, LED, switch and header is a **through-hole part in stock at the
DTU component shop** (`dtu_component_shop.csv`). The four ICs, the USB-C receptacle
and the barrel jack stay SMD, because no through-hole equivalent exists or the shop
does not stock one.

The board is still made on the xTool F1 Ultra: one copper layer (F.Cu), no vias.
The SMD parts sit on the copper side. The through-hole parts go on the **other**
face, with their leads pushed through the laser-cut holes and soldered on the
copper. Holes are not plated, so each lead is soldered on the copper side only.

## Parts from the component shop

"Shop row" is the `Part_Number` column of the shop CSV.

| Ref | Qty | Value | Shop row | Footprint |
|---|---|---|---|---|
| R1, R10 | 2 | 46.4 kΩ | `46K4` | axial, 7.62 mm |
| R2 | 1 | 8.25 kΩ | `8K25` | axial, 7.62 mm |
| R3 | 1 | 5.11 kΩ | `5K11` | axial, **standing**, 2.54 mm |
| R4 | 1 | 5.11 kΩ | `5K11` | axial, 7.62 mm |
| R5, R9, R13, R15, R19 | 5 | 10 kΩ | `10K0` | axial, 7.62 mm |
| R6 | 1 | 221 Ω | `221R` | axial, 7.62 mm |
| R7, R8 | 2 | 4.75 kΩ | `4K75` | axial, 7.62 mm |
| R11 | 1 | 1 kΩ, 1 % | `1K00` | axial, 7.62 mm |
| R12 | 1 | 1 kΩ | `1K00` | axial, 7.62 mm |
| R14, R16 | 2 | wire link | (offcut lead) | 2.54 mm |
| C2, C3, C5, C6, C11, C14, C15 | 7 | 100 nF ceramic | `100n` (Ceramic) | disc, 5 mm |
| C12 | 1 | 22 nF ceramic | `22n` (Ceramic) | disc, 5 mm |
| C13 | 1 | 10 nF ceramic | `10n` (Ceramic) | disc, 5 mm |
| C1 | 1 | 220 µF 50 V | `220µF 50V` | radial Ø10, 5 mm |
| C4 | 1 | 47 µF 50 V | `47µF 50V` | radial Ø6.3, 2.5 mm |
| C7 | 1 | 470 µF 10 V | `470µF 10V` | radial Ø8, 3.5 mm |
| C8 | 1 | 220 µF 10 V | `220µF 10V` | radial Ø6.3, 2.5 mm |
| C9 | 1 | 1 µF 50 V | `1µF 50V` | radial Ø5, 2 mm |
| C10 | 1 | 10 µF 50 V | `10µF 50V` | radial Ø5, 2 mm |
| C16 | 1 | 68 µF 50 V | `68µF 50V` | radial Ø8, 3.5 mm |
| L1 | 1 | 10 µH 3 A | `10µ 3A` | radial Ø10, 5 mm |
| D1 | 1 | 1.5KE15A (unidirectional TVS) | `1.5KE15A` | DO-201AE, 15.24 mm |
| D2, D5 | 2 | 1N5817 Schottky | `1N5817` | DO-41, 10.16 mm |
| D3 | 1 | 3 mm LED, green | `LED 3MM GRØN` | 3 mm |
| SW1, SW2, SW3 | 3 | 6 mm tact switch | `Pushbutton` | 6.5 × 4.5 mm |
| J3 | 1 | 2-pin header, 2.54 mm | `2-Pin Male` (Molex) | KK-254 |
| J4 | 1 | 4-pin header, 2.54 mm | `4-Pin Male` (Molex) | KK-254 |

## Parts not in the shop

| Ref | Part | Note |
|---|---|---|
| U1 | ESP32-C3-WROOM-02 (4 MB) | as rev A |
| U2 | TI DRV8876PWPR, HTSSOP-16 | as rev A |
| U3 | Diodes AP63203WU-7, TSOT-23-6 | as rev A |
| U4 | ST USBLC6-2SC6, SOT-23-6 | as rev A |
| J1 | CUI PJ-036AH-SMT barrel jack | as rev A |
| J2 | HRO TYPE-C-31-M-12 USB-C | as rev A |
| F1 | Bourns MF-R250 (2.5 A hold, radial) | The shop has no fuses. Either buy one, or bridge the two F1 holes with a wire link and rely on the barrel-jack supply's own limit. The footprint is the MF-RG300 radial pattern (5.1 mm pitch), which the MF-R250 also fits. |

## Values that changed from rev A, and why

- **The VM sense divider is 46.4k / 8.25k** (rev A: 47k / 8.2k), because the shop stocks E96 values only. The ratio is 6.624 instead of 6.732. The firmware substitution `vm_divider` in `firmware/curtain-drive.yaml` is already set to 6.624 for rev B, with rev A's value in the comment.
- **The VREF divider is 10k / 46.4k** (rev A: 10k / 47k). VREF, and with it ITRIP, drops by 0.2 %.
- **The I2C pull-ups are both 4.75 kΩ.** Rev A had 4.7k on SDA but 10k on SCL, a mismatch carried over from the first schematic. Both lines now match.
- **The buck output is 470 µF + 220 µF electrolytic**, where rev A used 2 × 22 µF ceramic. The shop has no ceramic above 100 nF. See the bench check below.
- **D1 is a 1.5KE15A**, a unidirectional TVS, with its cathode on +12 V. (Rev A's SMAJ15A was drawn backwards, and is fixed there too.)
- **The 0 Ω jumpers R14 and R16 are wire links**: a bent offcut of a resistor lead, 2.54 mm long.

## Making the board on the F1 Ultra

The layout uses 0.2 mm clearance and 0.3 mm tracks (0.2 mm minimum). That is inside the
0.15 mm gaps and 0.15 mm traces the esp32-node test coupon cut cleanly on 2026-09-26.
The laser files come from the board:

    python3 tools/laser_export.py hardware-revB/curtain-drive-revB.kicad_pcb

They land in `production/laser/`. The positive `production/*.dxf` files are for reference;
don't feed them to XCS.

1. Sand the copper lightly with 400 grit.
2. **Copper:** import `curtain-drive-revB-ablate.dxf` and Make compound. Check that the
   removed copper is black and the copper you keep is white, as in
   `curtain-drive-revB-preview.png`. Run the `Traces` preset (Framing, Auto height,
   Process). It is etched copper side up, as drawn: do **not** mirror it. Copper is on
   F.Cu seen from above.
3. **Holes and outline:** `curtain-drive-revB-cut.dxf` with the `Cut/Drill` preset.
   It shares the ablate file's frame.
4. Solder mask, only if the board has one: `curtain-drive-revB-mask.dxf` with
   `RemoveSolderMask`. Delete its REFERENCE layer (the board outline) after aligning.

## Assembly

1. Solder the SMD parts first, on the copper side: U1, U2, U3, U4, J1 and J2.
2. Fit the through-hole parts from the bare side and solder them on the copper. Low parts first:
   - the resistors and wire links, R3 standing on end;
   - the diodes;
   - the disc capacitors;
   - the switches;
   - the headers;
   - the electrolytics and L1 last.
3. Polarity:
   - Electrolytics: `+` on the square pad.
   - D1, D2, D5: the cathode band goes to the pad marked K on the fab layer (square pad).
   - D3: the flat side (cathode) goes to the square pad.
4. **Trim the leads flush after soldering.** Several leads sit next to SMD parts, for example R16 beside U4. A long lead end can short a neighbour.
5. The tact switches carry ground across tracks: SW2 bridges GND over +3V3, SW1 over SDA/SCL, and SW3 into the reset block. That relies on each switch's two internally joined leg pairs. **Solder all four legs of every switch**, even if a leg looks unused.

## Bench checks before connecting the motor

- **3.3 V rail with electrolytic output caps.** The AP63203 datasheet recommends 22 to 68 µF of ceramic on the output. The electrolytics' ESR adds a low-frequency zero. In a current-mode converter with internal compensation that is normally stable, but ripple will be higher. Check the 3V3 ripple and a load step (ESP32 Wi-Fi transmit bursts) on a scope. If the rail rings, tack a 22 µF 1206 ceramic across C8's two solder joints on the copper side. They are 2.5 mm apart, so a 1206 spans them.
- **VM_SENSE reading at 12.0 V in.** It should read about 1.81 V at the ADC pin with the 6.624 ratio.
- **I_SENSE with the motor stalled.** Expect 1 V per amp, as rev A.

## Mechanical

The board is 90 × 72 mm, larger than rev A's 80 × 62 mm, because through-hole parts need the room. It has four M2.5 holes at (3.5, 3.5), (86.5, 3.5), (87, 69) and (3.5, 45), measured from the top-left corner of the copper side. The tallest back-side parts are C1 (about 20 mm), L1 (about 14 mm) and F1 (about 12 mm). The SMD connectors are on the copper side. Mount the board **copper side down on standoffs of at least 8 mm**; the barrel jack (6.5 mm tall) is the tallest part on that side. The jack and USB-C then sit underneath the board, at the box wall. The rev A enclosure does **not** fit rev B yet.
