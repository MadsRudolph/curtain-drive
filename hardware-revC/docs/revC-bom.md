# Curtain drive rev C: bill of materials and build notes

Rev C is a redesign around the module actually on hand, an **ESP32-WROOM-32**
(38 pads), instead of the ESP32-C3-WROOM-02 that rev A and B were drawn for. At the
same time, **every other part is a through-hole part from the DTU component shop**
(`dtu_component_shop.csv`); the module is the only SMD part. That rules out rev B's
DRV8876 driver, AP63203 buck, USB-C receptacle, USB ESD array and SMD barrel jack:

| Rev B | Rev C | Why |
|---|---|---|
| DRV8876 (HTSSOP) | **L298** (Multiwatt15), bridge A, four 1N5817 flyback diodes | shop part; the L298 has no internal diodes |
| DRV8876 IPROPI + 1 k | **1 Ω 5 W** under bridge A (R11) | same 1 V per amp scale, so the firmware's stall threshold carries over |
| AP63203 buck | **LM317T** + TO-220 heatsink, 1N5817 in series with its input, 1N4003 reverse protection | the proven shop-part ESP32 supply (kicad-laser-pcb `references/esp32.md`); 243R / 392R sets 3.27 V |
| 2 × 22 µF on 3V3 | **470 µF 10 V (C7) on the module's 3V3** | Wi-Fi TX peaks of 300–500 mA collapsed a 10 µF rail on the esp32-solder-test board (22 resets in 30 s) |
| (none) | **LM7805** | the L298's logic supply (Vss) needs 4.5 to 7 V |
| SMD barrel jack | **2-pole screw terminal** (J1) | the shop has no DC jack |
| USB-C, USBLC6, CC resistors | **UART header J5** (TX, RX, GND) | the WROOM-32 has no native USB, and the shop has no USB-serial chip |
| PTC fuse F1 | none | the shop has no fuses: use a current-limited 12 V supply |

The board keeps rev B's 90 × 72 mm outline and its four mounting holes.

The board is made on the xTool F1 Ultra: one copper layer (F.Cu), no vias. The module
sits on the copper side. Every other part goes on the **other** face, with its leads
through the laser-cut holes and soldered on the copper. Holes are not plated.

## Parts from the component shop

"Shop row" is the `Part_Number` column of the shop CSV.

| Ref | Qty | Value | Shop row | Footprint |
|---|---|---|---|---|
| U2 | 1 | L298 dual full bridge | `L298` | Multiwatt15, standing |
| U3 | 1 | LM317T | `LM317T` | TO-220, standing, with the `TO-220 Heatsink` |
| U4 | 1 | LM7805 | `LM7805` | TO-220, standing |
| R1 | 1 | 46.4 kΩ | `46K4` | axial, 7.62 mm |
| R2 | 1 | 8.25 kΩ | `8K25` | axial, 7.62 mm |
| R5, R13, R14, R15 | 4 | 10 kΩ | `10K0` | axial, 7.62 mm |
| R6 | 1 | 221 Ω | `221R` | axial, 7.62 mm |
| R7, R8 | 2 | 4.75 kΩ | `4K75` | axial, 7.62 mm |
| R11 | 1 | 1 Ω 5 W | `1R 5W` | power resistor, 27.94 mm |
| R12 | 1 | 1.00 kΩ | `1K00` | axial, 7.62 mm |
| R17 | 1 | 243 Ω | `243R` | axial, 7.62 mm |
| R18 | 1 | 392 Ω | `392R` | axial, 7.62 mm |
| C2, C3, C5, C8, C11, C13, C15 | 7 | 100 nF ceramic | `100n` (Ceramic) | disc, 5 mm |
| C14 | 1 | 100 nF ceramic | `100n` (Ceramic) | disc, **legs bent out to 7.62 mm** |
| C1 | 1 | 220 µF 50 V | `220µF 50V` | radial Ø10, 5 mm |
| C7 | 1 | 470 µF 10 V | `470µF 10V` | radial Ø8, 3.5 mm |
| C9 | 1 | 1 µF 50 V | `1µF 50V` | radial Ø5, 2 mm |
| C4, C10 | 2 | 10 µF 50 V | `10µF 50V` | radial Ø5, 2 mm |
| C16 | 1 | 68 µF 50 V | `68µF 50V` | radial Ø8, 3.5 mm |
| D1 | 1 | 1.5KE15A (unidirectional TVS) | `1.5KE15A` | DO-201AE, 15.24 mm |
| D2, D6, D7, D8, D9 | 5 | 1N5817 Schottky | `1N5817` | DO-41, 10.16 mm |
| D10 | 1 | 1N4003 | `1N4003` | DO-41, 10.16 mm |
| D3 | 1 | 3 mm LED, green | `LED 3MM GRØN` | 3 mm |
| SW1, SW2, SW3 | 3 | 6 mm tact switch | `Pushbutton` | 6.5 × 4.5 mm |
| J1 | 1 | 2-pole screw terminal, 5.08 mm | `2 pol skrueterminal` | 5.08 mm |
| J3 | 1 | 2-pin header, 2.54 mm | `2-Pin Male` (Molex) | KK-254 |
| J4 | 1 | 4-pin header, 2.54 mm | `4-Pin Male` (Molex) | KK-254 |
| J5 | 1 | 3 pins of a straight male header | `Header Male` | 2.54 mm |

## Not from the shop

| Ref | Part | Note |
|---|---|---|
| U1 | ESP32-WROOM-32 (any of -32, -32D, -32E, 4 MB) | the module on hand; same 38-pad footprint |

**The 3.3 V supply is the one proven on real hardware** (`esp32-solder-test`, see the
kicad-laser-pcb skill's `references/esp32.md`): an LM317T with 243R/392R, a big bulk
cap at the module and the firmware's Wi-Fi TX power capped at 8.5 dBm. From 12 V the
LM317 dissipates about 1 W on average and up to 2 W while transmitting, so **fit the
shop's TO-220 heatsink to U3**. Its tab faces the bottom edge, and the space behind it
is kept clear for the heatsink. C7 sits where the module's 3V3 line leaves the
antenna keep-out, about 16 mm from pin 2, on a 0.8 mm track.

## Making the board on the F1 Ultra

The layout uses 0.2 mm clearance and 0.3 mm tracks (0.5 mm for 3V3 and 5 V, 0.8 mm for
12 V, the motor and the sense resistor). That is inside the 0.15 mm gaps and traces the
esp32-node coupon cut cleanly. The module's pads are 0.9 mm wide on a 1.27 mm pitch,
0.37 mm apart, so the mask openings leave little room for misalignment.

The files come from the board:

    python3 tools/laser_export.py hardware-revC/curtain-drive-revC.kicad_pcb

They land in `production/laser/`. The per-layer DXFs and the Excellon drill file in
`production/` are for reference; don't feed them to XCS.

1. Sand the copper lightly with 400 grit.
2. **Copper:** import `curtain-drive-revC-ablate.dxf` and Make compound. Check that the
   removed copper is black and the copper you keep is white, as in
   `curtain-drive-revC-preview.png`. Run the `Traces` preset. It is etched copper side
   up, as drawn: do **not** mirror it.
3. **Holes and outline:** `curtain-drive-revC-cut.dxf` with the `Cut/Drill` preset.
   It shares the ablate file's frame.
4. Solder mask, if used: `curtain-drive-revC-mask.dxf` with `RemoveSolderMask`. Delete
   its REFERENCE layer (the board outline) after aligning.

The layout is script-built: `tools/schematic_layout.py` draws the schematic and
`tools/pcb_layout.py --route` places, routes (FreeRouting 2.1 on one layer, GND poured)
and fills the board. Re-run them rather than editing the files by hand.

## Assembly

1. Solder the module (U1) first, on the copper side. Its centre GND pad (39) is
   optional: the three GND pins at the edges carry the ground.
2. Fit everything else from the bare side and solder it on the copper. Low parts first:
   - the resistors, R11 last of them;
   - the diodes;
   - the disc capacitors (C14's legs bent out to 7.62 mm);
   - the switches and headers;
   - U4, U3 (with its heatsink) and U2;
   - the electrolytics last.
3. Polarity:
   - Electrolytics: `+` on the square pad.
   - D1, D2, D6 to D10: the cathode band goes to the pad marked K on the fab layer (square pad).
   - D3: the flat side (cathode) goes to the square pad.
4. **Trim the leads flush after soldering.** The module's pads are 0.37 mm apart; a
   long lead end near them can short them.
5. **Solder all four legs of every switch**, even if a leg looks unused. The two
   internally joined leg pairs carry signals across tracks.

## Flashing

The WROOM-32 has no USB. Flash it over J5 with any 3.3 V USB-serial adapter:

1. Power the board from 12 V on J1. J5 has no supply pin: an adapter's 3.3 V pin
   cannot carry the module's Wi-Fi current.
2. Wire J5 pin 1 (TX, the module's output) to the adapter's RX, pin 2 (RX) to the
   adapter's TX, and pin 3 to GND.
3. Hold BOOT (SW2), tap RESET (SW3), release BOOT. The module is now in its
   download mode (R15 holds IO0 high otherwise).
4. `esphome run firmware/curtain-drive-revc.yaml`, choosing the adapter's serial port.
   After the first flash, updates go over Wi-Fi.

## Bench checks before connecting the motor

- **Meter before power.** No short from 12 V, 5 V or 3V3 to GND, and no bridges
  between module pins 1/2/3 (GND/3V3/EN), 34/35 (RXD0/TXD0) or 25 (IO0) and its
  neighbours.
- **3.3 V rail.** 3.2 to 3.3 V on C7. About 1.2 V means the ADJ pin sits at 0 V (R17 or
  its joint open, or ADJ bridged to GND). Close to 12 V means R18 is open.
- **ROM log.** At 115200 baud on J5, tapping RESET prints the boot banner. A string of
  `POWERON_RESET`s once Wi-Fi starts means the 3.3 V rail is sagging.
- **5 V rail.** 4.8 to 5.2 V on C15.
- **VM_SENSE at 12.0 V in.** It should read about 1.81 V at the ADC pin with the 6.624 ratio.
- **I_SENSE with the motor stalled.** Expect 1 V per amp, from R11.
- **The L298 has no current limit or thermal warning.** The stall detection in the
  firmware is its only protection. Bench-test from a current-limited supply (2.5 A),
  and fit a TO-220 heatsink to U2's tab if it runs hot during long moves.
- **Motor speed.** The L298 drops about 2 V, where the DRV8876 dropped almost none. If
  the curtain moves too slowly at `duty_max: 0.50`, raise it in the firmware.

## Mechanical

The board is 90 × 72 mm with four M2.5 holes at (3.5, 3.5), (86.5, 3.5), (87, 69)
and (3.5, 45), measured from the top-left corner of the copper side, as rev B. The
tallest back-side parts are U2 standing (about 22 mm, more with a heatsink), U3 with
its heatsink, R11 (about 10 mm) and C1 (about 20 mm). Mount the board copper side down on
standoffs; only the module is on that side. The rev B enclosure does **not** fit
rev C: the barrel jack and USB-C openings become a screw-terminal wire entry, and
the parts on the back are taller.
