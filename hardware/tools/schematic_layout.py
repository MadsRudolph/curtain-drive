#!/usr/bin/env python3
"""Curtain Drive -- schematic layout script.

Draws hardware/curtain-drive.kicad_sch with the kicad-schematic drawing DSL
(schdraw.py). Re-run this to regenerate the sheet; do not hand-edit the .kicad_sch.

    python3 hardware/tools/schematic_layout.py

Blocks (top to bottom, signal left to right):
  1. 12 V DC input: barrel jack -> polyfuse -> TVS -> VM rail, VM sense divider
  2. USB-C: 5 V for bench use, CC pull-downs, ESD array, D+/D- to the ESP32-C3
  3. 3.3 V buck (AP63203) fed from 12 V OR USB 5 V through Schottky ORing
  4. ESP32-C3-WROOM-02, reset/boot/user buttons, status LED, I2C encoder header
  5. DRV8876 H-bridge with IPROPI current sense -> ADC (sensorless end stop)
"""
import json
import sys
import uuid as _uuid
from pathlib import Path

SKILL = Path.home() / ".claude/skills/kicad-schematic/scripts"
sys.path.insert(0, str(SKILL))
from schdraw import Sheet  # noqa: E402

HW = Path(__file__).resolve().parent.parent
LIBDIR = HW / "lib"
OUT_SCH = HW / "curtain-drive.kicad_sch"
OUT_PRO = HW / "curtain-drive.kicad_pro"


def G(n):
    return round(n * 1.27, 2)


# Footprints -------------------------------------------------------------------
FP_R = "Resistor_SMD:R_0603_1608Metric"
# 0805 where a one-layer track has to pass between the pads (R9, R10, R13 straddle I_SENSE;
# R3 has VBUS under it; R1 is a 1206 because the 0.5 mm +3V3 track runs under it)
FP_R0805 = "Resistor_SMD:R_0805_2012Metric"
FP_C = "Capacitor_SMD:C_0603_1608Metric"
FP_C0805 = "Capacitor_SMD:C_0805_2012Metric"
FP_C1206 = "Capacitor_SMD:C_1206_3216Metric"
FP_CP8 = "Capacitor_SMD:CP_Elec_8x10"
FP_CP6 = "Capacitor_SMD:CP_Elec_6.3x7.7"
FP_LED = "LED_SMD:LED_0603_1608Metric"
FP_SW = "CurtainDrive:SW_SPST_PTS645Sx43SMTR92_Jumpers"   # paired pads bridged inside the switch
FP_SMA = "Diode_SMD:D_SMA"
FP_SOD123 = "Diode_SMD:D_SOD-123"
FP_SOT236 = "Package_TO_SOT_SMD:SOT-23-6"
FP_TSOT236 = "Package_TO_SOT_SMD:TSOT-23-6"
# Single-sided F.Cu laser fab (xTool F1 Ultra): no vias, no bottom copper, SMD only.
FP_HTSSOP = "Package_SO:HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm_Mask2.46x2.31mm"
FP_ESP = "CurtainDrive:ESP32-C3-WROOM-02_NoVias"   # stock footprint minus the EP thermal vias
FP_USBC = "CurtainDrive:USB_C_Receptacle_HRO_TYPE-C-31-M-12_1L"   # VBUS pairs joined by the plug
FP_JACK = "Connector_BarrelJack:BarrelJack_CUI_PJ-036AH-SMT_Horizontal"
FP_FUSE = "Fuse:Fuse_1812_4532Metric"
FP_L = "Inductor_SMD:L_Sunlord_MWSA0503S"
FP_PH2 = "Connector_JST:JST_PH_B2B-PH-SM4-TB_1x02-1MP_P2.00mm_Vertical"
FP_PH4 = "Connector_JST:JST_PH_B4B-PH-SM4-TB_1x04-1MP_P2.00mm_Vertical"

# The root-sheet uuid must match the one recorded in the .kicad_pro.
# pcbnew saves can leave "sheets" empty, so fall back to the existing schematic's uuid.
_sheets = json.loads(OUT_PRO.read_text()).get("sheets") if OUT_PRO.exists() else None
if _sheets:
    sheet_uuid = _sheets[0][0]
elif OUT_SCH.exists():
    import re
    sheet_uuid = re.search(r'\(uuid "([^"]+)"\)', OUT_SCH.read_text()).group(1)
else:
    sheet_uuid = str(_uuid.uuid4())

sh = Sheet(paper="A3",
           title="Curtain Drive - ESP32-C3 + DRV8876 curtain motor controller",
           project="curtain-drive", uuid=sheet_uuid)
# Project symbol library (DRV8876PWP is not in the stock KiCad libraries).
sh.src._cache.extra_dirs.append(LIBDIR)


def hang(lib, ref, x, y_top, value, fp):
    """Vertical two-pin part with pin 1 at (x, y_top), pin 2 7.62 mm below."""
    return sh.place(lib, ref, at=(x, y_top + 3.81), rot=0, value=value, footprint=fp)


def horiz(lib, ref, x_left, y, value, fp, rot=90):
    """Horizontal two-pin part with pin 1 at (x_left, y), pin 2 7.62 mm right."""
    return sh.place(lib, ref, at=(x_left + 3.81, y), rot=rot, value=value, footprint=fp)


# =============================================================================
# Band 1: power input, USB-C, 3.3 V buck                                 y ~ 35
# =============================================================================
YP = G(28)            # the VM / VBUCK line
sh.note((G(10), G(16)), "1. Power input  (12 V DC jack -> polyfuse -> TVS -> VM;  VM sense divider -> ADC)", size=2)

# --- Block A: DC input --------------------------------------------------------
j1 = sh.place("Connector:Barrel_Jack_Switch", "J1", at=(G(12), YP + 2.54), value="DC IN 12V", footprint=FP_JACK)
f1 = horiz("Device:Polyfuse", "F1", G(23), YP, "2.5A", FP_FUSE)
sh.seg(j1.pin(1), f1.pin(1))
sh.seg(j1.pin(2), (G(20), j1.pin(2).y))
sh.gnd((G(20), j1.pin(2).y))
sh.nc(j1.pin(3))

N1 = (G(36), YP)
# unidirectional TVS: cathode (pin 1) on +12 V, anode on GND
d1 = sh.place("Diode:SMAJ15A", "D1", at=(N1[0], YP + 3.81), rot=270, value="SMAJ15A", footprint=FP_SMA)
c1 = hang("Device:C_Polarized", "C1", G(46), YP, "220uF 25V", FP_CP8)
c2 = hang("Device:C", "C2", G(56), YP, "100nF 50V", FP_C)
r1 = hang("Device:R", "R1", G(66), YP, "47k", "Resistor_SMD:R_1206_3216Metric")             # VM sense top
r2 = hang("Device:R", "R2", G(66), YP + 7.62, "8.2k", FP_R)     # VM sense bottom
c3 = hang("Device:C", "C3", G(74), YP + 7.62, "100nF", FP_C)    # sense filter
RAIL_A = YP + G(14)
for p in (d1, c1, c2):
    sh.seg((p.x, YP + 7.62), (p.x, RAIL_A))
sh.seg(r2.pin(2), (r2.x, RAIL_A))
sh.seg(c3.pin(2), (c3.x, RAIL_A))
sh.seg((d1.x, RAIL_A), (c3.x, RAIL_A))
sh.gnd((c2.x, RAIL_A))
sh.seg((r1.x, YP + 7.62), (c3.x, YP + 7.62))
sh.seg((c3.x, YP + 7.62), (G(80), YP + 7.62))
sh.label((G(80), YP + 7.62), "VM_SENSE", kind="global")
sh.rail(N1, net="+12V", rise=5.08)
sh.note((G(40), YP - 7.62), "VM = +12V (motor supply)")
sh.note((G(36), RAIL_A + G(6)), "VM_SENSE = VM x 8.2/55.2  (12 V -> 1.78 V)")

# ORing diode 12 V -> VBUCK
d2 = sh.place("Device:D_Schottky", "D2", at=(G(90), YP), rot=180, value="SS34", footprint=FP_SMA)
sh.seg(f1.pin(2), d2.pin(2))        # top line: fuse -> N1 -> ... -> D2 anode
sh.label((G(102), YP), "VBUCK")
sh.power("power:PWR_FLAG", (G(110), YP))

# --- Block B: USB-C ------------------------------------------------------------
sh.note((G(76), G(48)), "2. USB-C  (5 V bench power + native USB-serial/JTAG of the ESP32-C3)", size=2)
j2 = sh.place("Connector:USB_C_Receptacle_USB2.0_16P", "J2", at=(G(70), G(70)), value="USB-C", footprint=FP_USBC)
YV = j2.pin("A4").y                                  # VBUS row
j2.field_at = {"Reference": (j2.x - 5.08, YV - 5.08), "Value": (j2.x + 2.54, YV - 5.08)}
XE = G(110)                                          # ESD array centre x
u4 = sh.place("Power_Protection:USBLC6-2SC6", "U4", at=(XE, j2.pin("B7").y), value="USBLC6-2SC6", footprint=FP_SOT236)
d5 = sh.place("Device:D_Schottky", "D5", at=(G(116), YV), rot=180, value="B5819W", footprint=FP_SOD123)
sh.seg(j2.pin("A4"), d5.pin(2))                       # VBUS -> (ESD tap) -> D5 anode
sh.seg(d5.pin(1), (G(120), YV))
sh.seg((G(120), YV), (G(120), YP))                    # up into the VBUCK line
sh.seg(u4.pin(5), (u4.pin(5).x, YV))                  # ESD VBUS pin up to VBUS row
# On one layer the ESD array's GND pin is boxed in by the data lines: it leaves over a 0R.
Y16 = u4.pin(2).y + 2.54
sh.seg(u4.pin(2), (u4.pin(2).x, Y16))
r16 = horiz("Device:R", "R16", u4.pin(2).x + 2.54, Y16, "0R", "Resistor_SMD:R_0805_2012Metric")
r16.field_at = {"Reference": (r16.x - 2.2, Y16 - 1.3), "Value": (r16.x + 2.2, Y16 - 1.3)}
sh.seg((u4.pin(2).x, Y16), r16.pin(1))
sh.power("power:GND", (r16.pin(2).x, Y16), rot=90)
# CC pull-downs (5.1k -> UFP / sink)
r3 = horiz("Device:R", "R3", G(88), j2.pin("A5").y, "5.1k", FP_R0805)   # VBUS runs under it
r4 = horiz("Device:R", "R4", G(96), j2.pin("B5").y, "5.1k", FP_R)
r4.field_at = {"Reference": (r4.x - 2.2, r4.y + 2.8), "Value": (r4.x + 2.2, r4.y + 2.8)}
sh.seg(j2.pin("A5"), r3.pin(1))
sh.seg(r3.pin(2), (G(98), r3.y))
sh.power("power:GND", (G(98), r3.y), rot=90)
sh.seg(j2.pin("B5"), r4.pin(1))
sh.seg(r4.pin(2), (G(106), r4.y))
sh.power("power:GND", (G(106), r4.y), rot=90)
# D- (A7/B7) and D+ (A6/B6) through the ESD array
sh.seg(j2.pin("B7"), u4.pin(1))
sh.seg(j2.pin("A7"), (G(84), j2.pin("A7").y))
sh.seg((G(84), j2.pin("A7").y), (G(84), j2.pin("B7").y))
# The receptacle pad row runs D+(B6) D-(A7) D+(A6) D-(B7): on one copper layer A6 is
# boxed in by the two D- pads, so it joins D+ over a 0R jumper that straddles the D- track.
r14 = horiz("Device:R", "R14", G(88), j2.pin("A6").y, "0R", "Resistor_SMD:R_0603_1608Metric")
r14.field_at = {"Reference": (r14.x - 2.2, r14.y - 1.3), "Value": (r14.x + 2.2, r14.y - 1.3)}
sh.seg(j2.pin("A6"), r14.pin(1))
sh.seg(r14.pin(2), u4.pin(3))
sh.seg(j2.pin("B6"), (G(100), j2.pin("B6").y))
sh.seg((G(100), j2.pin("B6").y), (G(100), j2.pin("A6").y))
sh.seg(u4.pin(6), (G(128), u4.pin(6).y))
sh.label((G(128), u4.pin(6).y), "USB_D-", kind="global")
sh.seg(u4.pin(4), (G(128), u4.pin(4).y))
sh.label((G(128), u4.pin(4).y), "USB_D+", kind="global")
sh.nc(j2.pin("A8"), j2.pin("B8"))
sh.gnd(j2.pin("A1"))
sh.gnd(j2.pin("SH"))

# --- Block C: 3.3 V buck -------------------------------------------------------
sh.note((G(126), G(16)), "3. 3.3 V buck  (AP63203, 1.1 MHz, 2 A; input = 12 V OR USB 5 V via Schottky OR)", size=2)
u3 = sh.place("Regulator_Switching:AP63203WU", "U3", at=(G(150), YP + 2.54), value="AP63203WU", footprint=FP_TSOT236)
sh.seg(d2.pin(1), u3.pin("IN"))                        # VBUCK line
c4 = hang("Device:C", "C4", G(128), YP, "10uF 50V", FP_C1206)
c5 = hang("Device:C", "C5", G(136), YP, "100nF 50V", FP_C)
RAIL_C = YP + G(8)
sh.seg(c4.pin(2), (c4.x, RAIL_C))
sh.seg(c5.pin(2), (c5.x, RAIL_C))
sh.seg((c4.x, RAIL_C), (c5.x, RAIL_C))
sh.gnd(((c4.x + c5.x) / 2, RAIL_C))
sh.seg(u3.pin("EN"), (G(141), u3.pin("EN").y))
sh.seg((G(141), u3.pin("EN").y), (G(141), YP))
sh.gnd(u3.pin("GND"), drop=5.08)
c6 = horiz("Device:C", "C6", G(160), u3.pin("BST").y, "100nF", FP_C)
sh.seg(u3.pin("BST"), c6.pin(1))
sh.seg(c6.pin(2), (c6.pin(2).x, YP))
l1 = horiz("Device:L", "L1", G(170), YP, "4.7uH 3A", FP_L)
sh.seg(u3.pin("SW"), l1.pin(1))
X3 = G(200)
sh.seg(l1.pin(2), (X3, YP))
sh.seg(u3.pin("FB"), (G(180), u3.pin("FB").y))
sh.seg((G(180), u3.pin("FB").y), (G(180), YP))
c7 = hang("Device:C", "C7", G(186), YP, "22uF 10V", FP_C0805)
c8 = hang("Device:C", "C8", G(194), YP, "22uF 10V", FP_C0805)
sh.seg(c7.pin(2), (c7.x, RAIL_C))
sh.seg(c8.pin(2), (c8.x, RAIL_C))
sh.seg((c7.x, RAIL_C), (c8.x, RAIL_C))
sh.gnd(((c7.x + c8.x) / 2, RAIL_C))
sh.rail((X3, YP), net="+3V3", rise=5.08)
sh.note((G(160), YP + G(17)), "FB tied to VOUT (fixed 3.3 V part)")

# --- Power flags (corner row) -------------------------------------------------
XF, YF = G(256), G(18)
sh.note((XF - G(6), YF - G(7)), "Power flags", size=1.27)
for i, net in enumerate(("+12V", "+3V3")):
    x = XF + i * G(18)
    sh.power(f"power:{net}", (x, YF)); sh.power("power:PWR_FLAG", (x - 7.62, YF)); sh.seg((x - 7.62, YF), (x, YF))
x = XF + 2 * G(18)
sh.power("power:PWR_FLAG", (x, YF)); sh.power("power:GND", (x, YF + 2.54)); sh.seg((x, YF), (x, YF + 2.54))

# =============================================================================
# Band 2: ESP32-C3                                                       y ~ 147
# =============================================================================
sh.note((G(86), G(83)), "4. ESP32-C3-WROOM-02  (native USB, strapping: IO2 high via R15, IO8 high via R19, IO9 = BOOT)", size=2)
u1 = sh.place("RF_Module:ESP32-C3-WROOM-02", "U1", at=(G(140), G(116)), value="ESP32-C3-WROOM-02", footprint=FP_ESP)
# EN: 10k pull-up + 1uF delay + reset button
XEN = G(94)
sh.seg(u1.pin("EN"), (G(90), u1.pin("EN").y))
r5 = hang("Device:R", "R5", XEN, u1.pin("EN").y - 7.62, "10k", FP_R)
sh.rail(r5.pin(1), net="+3V3")
c9 = hang("Device:C", "C9", XEN, u1.pin("EN").y, "1uF", FP_C)
sh.gnd(c9.pin(2))
sw3 = sh.place("Switch:SW_Push", "SW3", at=(G(86), u1.pin("EN").y), value="RESET", footprint=FP_SW)
sh.gnd(sw3.pin(1))
# ADC / I2C / control nets leave as global labels. The GPIO choice follows the
# single-sided layout: I_SENSE (IO4) and the four DRV8876 lines (IO5..IO8) leave the
# module's left edge in the reverse of the driver's pin order, so they fan straight in
# without crossing; I2C + USER sit below the USB pair on the right.
XL = G(120)
for pin, name in (("IO0", "LED"), ("IO3", "VM_SENSE"), ("IO4", "I_SENSE"),
                  ("IO5", "M_nFAULT"), ("IO6", "M_nSLEEP"), ("IO7", "M_IN2"), ("IO8", "M_IN1")):
    p = u1.pin(pin)
    sh.seg(p, (XL, p.y))
    sh.label((XL, p.y), name, kind="global")
sh.nc(u1.pin("IO1"))
# status LED, active high on IO0
XLED, YLED = G(70), G(108)
r6 = horiz("Device:R", "R6", XLED, YLED, "1k", FP_R)
sh.seg((XLED - G(8), YLED), r6.pin(1))
sh.label((XLED - G(8), YLED), "LED", kind="global")
d3 = sh.place("Device:LED", "D3", at=(r6.pin(2).x, YLED + 3.81), rot=90, value="STATUS", footprint=FP_LED)
sh.gnd(d3.pin(1))
# IN1 on IO8: the strapping pin must read high for the serial bootloader and the
# DRV8876 input pulls down, so R19 holds it up (nSLEEP keeps the bridge off at boot).
Y19 = YLED + G(18)
r19 = horiz("Device:R", "R19", XLED, Y19, "10k", FP_R)
sh.seg((XLED - G(8), Y19), r19.pin(1))
sh.label((XLED - G(8), Y19), "M_IN1", kind="global")
sh.rail(r19.pin(2), net="+3V3")
# BOOT button on IO9 (internal pull-up), USER button on IO10
p9 = u1.pin("IO9")
sh.seg(p9, (G(90), p9.y))
sw2 = sh.place("Switch:SW_Push", "SW2", at=(G(86), p9.y), value="BOOT", footprint=FP_SW)
sh.gnd(sw2.pin(1))
p10 = u1.pin("IO10")
sw1 = sh.place("Switch:SW_Push", "SW1", at=(G(108), G(136)), value="USER", footprint=FP_SW)
sh.seg(p10, (G(112), p10.y))
sh.seg((G(112), p10.y), sw1.pin(2))
sh.gnd(sw1.pin(1))
# IO2 is a strapping pin; Espressif recommend holding it high against glitches
p2 = u1.pin("IO2")
r15 = horiz("Device:R", "R15", G(104), p2.y, "10k", FP_R)
r15.field_at = {"Reference": (r15.x - 2.2, r15.y + 2.8), "Value": (r15.x + 2.2, r15.y + 2.8)}
sh.seg(r15.pin(2), p2)
sh.rail(r15.pin(1), net="+3V3", rise=5.08)
# I2C on IO20/IO21 (right-hand pins)
for pin, name in (("IO20/RXD", "SDA"), ("IO21/TXD", "SCL")):
    p = u1.pin(pin)
    sh.seg(p, (G(160), p.y))
    sh.label((G(160), p.y), name, kind="global")
# USB data
XU = G(122)
for pin, name in (("IO18", "USB_D-"), ("IO19", "USB_D+")):
    p = u1.pin(pin)
    sh.seg(p, (XU, p.y))
    sh.label((XU, p.y), name, kind="global")
# 3V3 + decoupling
p33 = u1.pin("3V3")
Y33 = p33.y - G(8)
sh.seg(p33, (p33.x, Y33))
sh.seg((p33.x, Y33), (G(152), Y33))
c10 = hang("Device:C", "C10", G(145), Y33, "10uF", FP_C0805)
c11 = hang("Device:C", "C11", G(152), Y33, "100nF", FP_C)
sh.seg(c10.pin(2), (c10.x, Y33 + G(8)))
sh.seg(c11.pin(2), (c11.x, Y33 + G(8)))
sh.seg((c10.x, Y33 + G(8)), (c11.x, Y33 + G(8)))
sh.gnd((G(148), Y33 + G(8)))
sh.rail((p33.x, Y33), net="+3V3")
sh.gnd(u1.pin("GND"))
# I2C encoder header (AS5600 breakout) with the bus pull-ups
j4 = sh.place("Connector_Generic:Conn_01x04", "J4", at=(G(196), G(124)), value="ENCODER I2C", footprint=FP_PH4)
sh.seg(j4.pin(1), (G(190), j4.pin(1).y))
sh.seg((G(190), j4.pin(1).y), (G(190), j4.pin(1).y - G(6)))
sh.rail((G(190), j4.pin(1).y - G(6)), net="+3V3")
sh.seg(j4.pin(2), (G(182), j4.pin(2).y))
r7 = hang("Device:R", "R7", G(182), j4.pin(2).y - 7.62, "4.7k", FP_R)
sh.rail(r7.pin(1), net="+3V3")
sh.label((G(182), j4.pin(2).y), "SDA", kind="global")
sh.seg(j4.pin(3), (G(172), j4.pin(3).y))
r8 = hang("Device:R", "R8", G(172), j4.pin(3).y - 7.62, "4.7k", FP_R)     # matches SDA
sh.rail(r8.pin(1), net="+3V3")
sh.label((G(172), j4.pin(3).y), "SCL", kind="global")
sh.seg(j4.pin(4), (G(190), j4.pin(4).y))
sh.gnd((G(190), j4.pin(4).y))
sh.note((G(192), G(132)), "1 = 3V3, 2 = SDA, 3 = SCL, 4 = GND")

# =============================================================================
# Band 3: DRV8876 motor driver                                           y ~ 236
# =============================================================================
sh.note((G(86), G(150)), "5. Motor driver  (DRV8876: PWM mode IN1/IN2, IPROPI = 1 mA per A -> 1 k -> 1 V/A into the ADC -> stall = end stop)", size=2)
u2 = sh.place("CurtainDrive:DRV8876PWP", "U2", at=(G(140), G(186)), value="DRV8876PWP", footprint=FP_HTSSOP)
# charge pump flying cap
c12 = hang("Device:C", "C12", G(120), u2.pin("CPH").y, "22nF 50V", FP_C)
sh.seg(u2.pin("CPH"), c12.pin(1))
sh.seg(u2.pin("CPL"), c12.pin(2))
# control inputs from the MCU
XD = G(122)
for pin, name in (("EN/IN1", "M_IN1"), ("PH/IN2", "M_IN2"), ("nSLEEP", "M_nSLEEP")):
    p = u2.pin(pin)
    sh.seg(p, (XD, p.y))
    sh.label((XD, p.y), name, kind="global")
# PMODE high = PWM mode; VREF divider 10k/47k -> 2.72 V -> ITRIP 2.7 A
XV = G(108)
sh.seg(u2.pin("PMODE"), (XV, u2.pin("PMODE").y))
sh.rail((XV, u2.pin("PMODE").y), net="+3V3")
r9 = hang("Device:R", "R9", XV, u2.pin("PMODE").y, "10k", FP_R0805)
r10 = hang("Device:R", "R10", XV, u2.pin("PMODE").y + 7.62, "47k", FP_R0805)
sh.gnd(r10.pin(2))
sh.seg(u2.pin("VREF"), r10.pin(1))
sh.seg(u2.pin("IMODE"), (G(120), u2.pin("IMODE").y))
sh.gnd((G(120), u2.pin("IMODE").y), drop=1.27)
# outputs
j3 = sh.place("Connector_Generic:Conn_01x02", "J3", at=(G(160), u2.pin("OUT1").y), value="MOTOR", footprint=FP_PH2)
sh.seg(u2.pin("OUT1"), j3.pin(1))
sh.seg(u2.pin("OUT2"), j3.pin(2))
# IPROPI -> 1k to GND (1 V/A), RC filter into the ADC
pi = u2.pin("IPROPI")
r11 = hang("Device:R", "R11", G(156), pi.y, "1k 1%", FP_R)
r12 = horiz("Device:R", "R12", G(162), pi.y, "1k", FP_R)
sh.seg(pi, r12.pin(1))
c13 = hang("Device:C", "C13", G(172), pi.y, "10nF", FP_C)
sh.seg(r12.pin(2), (G(178), pi.y))
sh.label((G(178), pi.y), "I_SENSE", kind="global")
RAIL_I = pi.y + G(7)
sh.seg(r11.pin(2), (r11.x, RAIL_I))
sh.seg(c13.pin(2), (c13.x, RAIL_I))
sh.seg((r11.x, RAIL_I), (c13.x, RAIL_I))
sh.gnd((G(164), RAIL_I), drop=1.27)
# nFAULT open-drain with pull-up
pf = u2.pin("nFAULT")
sh.seg(pf, (G(196), pf.y))
r13 = hang("Device:R", "R13", G(192), pf.y - 7.62, "10k", FP_R0805)
sh.rail(r13.pin(1), net="+3V3")
sh.label((G(196), pf.y), "M_nFAULT", kind="global")
# VM supply, charge pump reservoir, decoupling
pvm = u2.pin("VM")
YVM = pvm.y - G(10)
sh.seg(pvm, (pvm.x, YVM))
sh.seg((G(112), YVM), (G(156), YVM))
sh.rail((pvm.x, YVM), net="+12V")
pvcp = u2.pin("VCP")
sh.seg(pvcp, (pvcp.x, YVM + G(6)))
sh.seg((pvcp.x, YVM + G(6)), (G(156), YVM + G(6)))
c14 = hang("Device:C", "C14", G(156), YVM, "100nF 16V", FP_C)           # VCP-VM
c15 = hang("Device:C", "C15", G(122), YVM, "100nF 50V", FP_C)           # VM bypass
c16 = hang("Device:C_Polarized", "C16", G(112), YVM, "100uF 25V", FP_CP6)
RAIL_V = YVM + G(8)
sh.seg(c15.pin(2), (c15.x, RAIL_V))
sh.seg(c16.pin(2), (c16.x, RAIL_V))
sh.seg((c16.x, RAIL_V), (c15.x, RAIL_V))
sh.gnd((G(117), RAIL_V))
# grounds
YG = u2.pin("GND").y + 2.54
for pin in ("GND", "PGND", "PAD"):
    sh.seg(u2.pin(pin), (u2.pin(pin).x, YG))
sh.seg((u2.pin("GND").x, YG), (u2.pin("PAD").x, YG))
sh.gnd((u2.pin("PGND").x, YG))
sh.note((G(10), G(208)), "ITRIP = VREF / (R11 x A_IPROPI) = 2.72 V / (1 k x 1 mA/A) = 2.7 A  (fixed off-time chopping, IMODE = GND, auto-retry)")
sh.note((G(10), G(211)), "I_SENSE = 1.0 V per amp of motor current.  Running ~0.3-0.8 A, stalled at the end stop >2 A -> firmware stops within 50 ms.")
sh.note((G(10), G(214)), "Motor is a 6 V rated servo gearmotor on a 12 V bus: firmware caps PWM duty at 50 % (VM_SENSE lets it scale with supply).")

# =============================================================================
problems = sh.check()
for p in problems:
    print("CHECK:", p)
if any("error" in str(p).lower() for p in problems):
    sys.exit("geometry errors")

sh.emit(str(OUT_SCH))
print("wrote", OUT_SCH)

if not OUT_PRO.exists():
    pro = {
        "board": {"design_settings": {"defaults": {}, "rules": {}}, "layer_presets": [], "viewports": []},
        "boards": [], "cvpcb": {"equivalence_files": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": OUT_PRO.name, "version": 3},
        "net_settings": {
            "classes": [{
                "bus_width": 12, "clearance": 0.2, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
                "diff_pair_width": 0.2, "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1,
                "name": "Default", "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647,
                "schematic_color": "rgba(0, 0, 0, 0.000)", "track_width": 0.25, "via_diameter": 0.6,
                "via_drill": 0.3, "wire_width": 6}],
            "meta": {"version": 4}, "net_colors": None, "netclass_assignments": None, "netclass_patterns": []},
        "pcbnew": {"last_paths": {"gencad": "", "idf": "", "netlist": "", "plot": "", "pos_files": "", "specctra_dsn": "", "step": "", "svg": "", "vrml": ""}, "page_layout_descr_file": ""},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [[sheet_uuid, "Root"]],
        "text_variables": {},
    }
    OUT_PRO.write_text(json.dumps(pro, indent=2))
    print("wrote", OUT_PRO)
