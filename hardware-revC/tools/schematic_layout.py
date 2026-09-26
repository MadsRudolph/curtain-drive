#!/usr/bin/env python3
"""Curtain Drive Rev C -- schematic layout script (ESP32-WROOM-32, all other parts THT from the DTU shop).

Draws hardware-revC/curtain-drive-revC.kicad_sch with the kicad-schematic drawing DSL
(schdraw.py). Re-run this to regenerate the sheet; do not hand-edit the .kicad_sch.

    python3 hardware-revC/tools/schematic_layout.py

Rev C exists because the module on hand is an ESP32-WROOM-32, not the ESP32-C3-WROOM-02
rev A/B were drawn for, and because every other part must come from the DTU component
shop as a through-hole part. That removes the DRV8876, the AP63203 buck, the USB-C
receptacle, its ESD array and the SMD barrel jack:

  1. 12 V in on a screw terminal -> TVS -> bulk caps -> VM, VM sense divider -> ADC1
  2. LM7805: 5 V logic supply for the L298
  3. LM2575-ADJ buck: 12 V -> 3.3 V for the module (1.00k / 1.69k -> 3.31 V)
  4. ESP32-WROOM-32 with reset/boot/user buttons, status LED, UART flashing header
     (the WROOM-32 has no native USB) and the I2C encoder header
  5. L298 bridge A drives the motor, with four Schottky flyback diodes; a 1 ohm sense
     resistor under bridge A gives 1 V per amp into ADC1 (same scale as rev B's IPROPI)
"""
import json
import sys
import uuid as _uuid
from pathlib import Path

SKILL = Path.home() / ".claude/skills/kicad-schematic/scripts"
sys.path.insert(0, str(SKILL))
from schdraw import Sheet  # noqa: E402

HW = Path(__file__).resolve().parent.parent
OUT_SCH = HW / "curtain-drive-revC.kicad_sch"
OUT_PRO = HW / "curtain-drive-revC.kicad_pro"


def G(n):
    return round(n * 1.27, 2)


# Footprints: every part but U1 is a through-hole part stocked by the DTU component shop.
RAX = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"
RAX10 = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"   # bridges two tracks
RPOWER = "Resistor_THT:R_Axial_Power_L25.0mm_W9.0mm_P27.94mm"        # 5 W cement body
CDISC = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
CDISC_BENT = "CurtainDrive:C_Disc_D5.0mm_W2.5mm_P7.62mm_Bent"   # legs bent out to straddle two tracks
CP5 = "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm"
CP63 = "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm"
CP8 = "Capacitor_THT:CP_Radial_D8.0mm_P3.50mm"
CP10 = "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm"
DO41 = "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal"
FP_TVS = "Diode_THT:D_DO-201AE_P15.24mm_Horizontal"
FP_LED = "LED_THT:LED_D3.0mm"
FP_L = "Inductor_THT:L_Radial_D10.0mm_P5.00mm_Fastron_07M"
FP_SW = "CurtainDrive:SW_PUSH_6mm_Jumpers"            # paired legs bridged inside the switch
FP_ESP = "CurtainDrive:ESP32-WROOM-32_NoVias"         # stock footprint minus the EP thermal vias
FP_L298 = "Package_TO_SOT_THT:TO-220-15_P2.54x5.08mm_StaggerOdd_Lead4.58mm_Vertical"   # Multiwatt15 V
FP_TO220_5 = "CurtainDrive:TO-220-5_Vertical_LongPads"   # stock pads leave a 0.09 mm ring
FP_TO220_3 = "Package_TO_SOT_THT:TO-220-3_Vertical"
FP_TERM = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal"
FP_KK2 = "Connector_Molex:Molex_KK-254_AE-6410-02A_1x02_P2.54mm_Vertical"
FP_KK4 = "Connector_Molex:Molex_KK-254_AE-6410-04A_1x04_P2.54mm_Vertical"
FP_HDR3 = "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical"

# The root-sheet uuid must match the one recorded in the .kicad_pro.
_sheets = json.loads(OUT_PRO.read_text()).get("sheets") if OUT_PRO.exists() else None
if _sheets:
    sheet_uuid = _sheets[0][0]
elif OUT_SCH.exists():
    import re
    sheet_uuid = re.search(r'\(uuid "([^"]+)"\)', OUT_SCH.read_text()).group(1)
else:
    sheet_uuid = str(_uuid.uuid4())

sh = Sheet(paper="A3",
           title="Curtain Drive Rev C - ESP32-WROOM-32 + L298 curtain motor controller (THT)",
           project="curtain-drive", uuid=sheet_uuid)


def hang(lib, ref, x, y_top, value, fp):
    """Vertical two-pin part with pin 1 at (x, y_top), pin 2 7.62 mm below."""
    return sh.place(lib, ref, at=(x, y_top + 3.81), rot=0, value=value, footprint=fp)


def horiz(lib, ref, x_left, y, value, fp, rot=90):
    """Horizontal two-pin part with pin 1 at (x_left, y), pin 2 7.62 mm right."""
    return sh.place(lib, ref, at=(x_left + 3.81, y), rot=rot, value=value, footprint=fp)


def diode_up(ref, x, y_anode, value, fp):
    """Vertical diode, cathode on top, anode at (x, y_anode)."""
    return sh.place("Device:D_Schottky", ref, at=(x, y_anode - 3.81), rot=270, value=value, footprint=fp)


# =============================================================================
# Band 1: power input, 5 V, 3.3 V                                      y ~ 36
# =============================================================================
YP = G(28)            # the +12 V bus
sh.note((G(8), G(16)), "1. 12 V input  (TVS, VM sense -> ADC1)", size=2)

# --- Block A: 12 V input ------------------------------------------------------
j1 = sh.place("Connector:Screw_Terminal_01x02", "J1", at=(G(10), YP), mirror="y",
              value="12V IN", footprint=FP_TERM)
sh.seg(j1.pin(2), (G(18), j1.pin(2).y))
sh.gnd((G(18), j1.pin(2).y))
X_TVS = G(24)
# Unidirectional TVS: cathode (pin 1) to +12V, anode to GND.
d1 = sh.place("Diode:1.5KExxA", "D1", at=(X_TVS, YP + 3.81), rot=270, value="1.5KE15A", footprint=FP_TVS)
c1 = hang("Device:C_Polarized", "C1", G(32), YP, "220uF 50V", CP10)
c2 = hang("Device:C", "C2", G(40), YP, "100nF", CDISC)
r1 = hang("Device:R", "R1", G(48), YP, "46.4k", RAX)             # VM sense top
r2 = hang("Device:R", "R2", G(48), YP + 7.62, "8.25k", RAX)      # VM sense bottom
c3 = hang("Device:C", "C3", G(56), YP + 7.62, "100nF", CDISC)    # sense filter
RAIL_A = YP + G(14)
for p in (d1, c1, c2):
    sh.seg((p.x, YP + 7.62), (p.x, RAIL_A))
sh.seg(r2.pin(2), (r2.x, RAIL_A))
sh.seg(c3.pin(2), (c3.x, RAIL_A))
sh.seg((d1.x, RAIL_A), (c3.x, RAIL_A))
sh.gnd((c2.x, RAIL_A))
sh.seg((r1.x, YP + 7.62), (c3.x, YP + 7.62))
sh.seg((c3.x, YP + 7.62), (G(62), YP + 7.62))
sh.label((G(62), YP + 7.62), "VM_SENSE", kind="global")
sh.seg(j1.pin(1), (G(126), YP))                      # the +12 V bus, across the band
sh.rail((X_TVS, YP), net="+12V", rise=5.08)
sh.note((G(30), RAIL_A + G(8)), "VM_SENSE = VM x 8.25/54.65  (12 V -> 1.81 V)")

# --- Block B: 5 V for the L298 logic ------------------------------------------
sh.note((G(84), G(22)), "2. 5 V logic  (LM7805, L298 Vss)", size=2)
XB = G(90)
YB = YP + G(10)
u4 = sh.place("Regulator_Linear:L7805", "U4", at=(G(98), YB), value="LM7805", footprint=FP_TO220_3)
sh.seg((XB, YP), (XB, u4.pin("IN").y))
c5 = hang("Device:C", "C5", XB, u4.pin("IN").y, "100nF", CDISC)
sh.seg((XB, u4.pin("IN").y), u4.pin("IN"))
sh.gnd(c5.pin(2))
sh.gnd(u4.pin("GND"))
X5 = G(106)
sh.seg(u4.pin("OUT"), (X5, u4.pin("OUT").y))
sh.rail((X5, u4.pin("OUT").y), net="+5V", rise=5.08)

# --- Block C: 3.3 V buck -------------------------------------------------------
sh.note((G(122), G(16)), "3. 3.3 V buck  (LM2575-ADJ, 52 kHz;  Vout = 1.23 V x (1 + 1.69k/1.00k) = 3.31 V)", size=2)
u3 = sh.place("Regulator_Switching:LM2575BT-ADJ", "U3", at=(G(142), YB + 2.54),
              value="LM2575T-ADJ", footprint=FP_TO220_5)
XC = G(126)
sh.seg((XC, YP), (XC, u3.pin("VIN").y))
c4 = hang("Device:C_Polarized", "C4", XC, u3.pin("VIN").y, "47uF 50V", CP63)
sh.seg((XC, u3.pin("VIN").y), u3.pin("VIN"))
sh.gnd(c4.pin(2))
pon = u3.pin(5)                                       # ON/OFF low = on
sh.gnd(pon, drop=G(2))
sh.gnd(u3.pin("GND"))
pout = u3.pin("OUT")
XD = G(156)
sh.seg(pout, (XD, pout.y))
d2 = diode_up("D2", XD, pout.y + 7.62, "1N5817", DO41)          # catch diode, anode to GND
sh.gnd(d2.pin("A"))
l1 = horiz("Device:L", "L1", G(158), pout.y, "120uH 1A", FP_L)
sh.seg((XD, pout.y), l1.pin(1))
X33 = G(182)
sh.seg(l1.pin(2), (X33, pout.y))
c7 = hang("Device:C_Polarized", "C7", G(168), pout.y, "470uF 10V", CP8)
c8 = hang("Device:C", "C8", G(174), pout.y, "100nF", CDISC)
sh.gnd(c7.pin(2))
sh.gnd(c8.pin(2))
r17 = hang("Device:R", "R17", X33, pout.y, "1.69k", RAX)          # Vout -> FB
r18 = hang("Device:R", "R18", X33, pout.y + 7.62, "1.00k", RAX)   # FB -> GND
sh.gnd(r18.pin(2))
pfb = u3.pin("FB")
XFB = G(186)
YFB = pfb.y - G(6)                                    # over the +3V3 rail symbol
sh.seg(pfb, (pfb.x + G(2), pfb.y))
sh.seg((pfb.x + G(2), pfb.y), (pfb.x + G(2), YFB))
sh.seg((pfb.x + G(2), YFB), (XFB, YFB))
sh.seg((XFB, YFB), (XFB, r17.pin(2).y))
sh.seg((XFB, r17.pin(2).y), r17.pin(2))
sh.rail((G(174), pout.y), net="+3V3", rise=5.08)
sh.note((G(122), YB + G(22)), "Fixed LM2575T-3.3 instead: fit R17 as a wire link, leave R18 out.")

# --- Power flags (corner row) -------------------------------------------------
XF, YF = G(256), G(18)
sh.note((XF - G(6), YF - G(7)), "Power flags", size=1.27)
for i, net in enumerate(("+12V", "+3V3")):   # +5V is driven by the LM7805
    x = XF + i * G(14)
    sh.power(f"power:{net}", (x, YF)); sh.power("power:PWR_FLAG", (x - 7.62, YF)); sh.seg((x - 7.62, YF), (x, YF))
x = XF + 3 * G(14)
sh.power("power:PWR_FLAG", (x, YF)); sh.power("power:GND", (x, YF + 2.54)); sh.seg((x, YF), (x, YF + 2.54))

# =============================================================================
# Band 2: ESP32-WROOM-32                                               y ~ 155
# =============================================================================
sh.note((G(70), G(64)),
        "4. ESP32-WROOM-32  (flash over UART J5: hold BOOT, tap RESET;  IO12 left open, it must read low at reset)", size=2)
XU, YU = G(130), G(106)
u1 = sh.place("RF_Module:ESP32-WROOM-32", "U1", at=(XU, YU), value="ESP32-WROOM-32", footprint=FP_ESP)
# EN: 10k pull-up + 1uF delay + reset button
pen = u1.pin("EN")
XEN = G(92)
sh.seg(pen, (XEN, pen.y))
r5 = hang("Device:R", "R5", XEN, pen.y - 7.62, "10k", RAX)
sh.rail(r5.pin(1), net="+3V3")
c9 = hang("Device:C_Polarized", "C9", XEN, pen.y, "1uF 50V", CP5)
sh.gnd(c9.pin(2))
sw3 = sh.place("Switch:SW_Push", "SW3", at=(G(82), pen.y), value="RESET", footprint=FP_SW)
sh.seg(sw3.pin(2), (XEN, pen.y))
sh.gnd(sw3.pin(1))
# ADC1 inputs (the only ADC usable with Wi-Fi on) on the sensor pins
for pin, name in (("SENSOR_VP", "VM_SENSE"), ("SENSOR_VN", "I_SENSE")):
    p = u1.pin(pin)
    sh.seg(p, (p.x - G(4), p.y))
    sh.label((p.x - G(4), p.y), name, kind="global")
# flash pins and unused IO
for pin in ("SHD/SD2", "SWP/SD3", "SCS/CMD", "SCK/CLK", "SDO/SD0", "SDI/SD1", "NC",
            "IO2", "IO5", "IO12", "IO13", "IO14", "IO15", "IO16", "IO17", "IO18",
            "IO22", "IO25", "IO26", "IO27", "IO34", "IO35"):
    sh.nc(u1.pin(pin))
# right-hand pins leave as global labels
XR = XU + G(16)
for pin, name in (("IO0", "BOOT"), ("TXD0/IO1", "TXD0"), ("RXD0/IO3", "RXD0"), ("IO4", "USER"),
                  ("IO19", "SDA"), ("IO21", "SCL"), ("IO23", "LED"),
                  ("IO32", "M_IN1"), ("IO33", "M_IN2")):
    p = u1.pin(pin)
    sh.seg(p, (XR, p.y))
    sh.label((XR, p.y), name, kind="global")
# 3V3 + decoupling
p33 = u1.pin("VDD")
Y33 = p33.y - G(10)
sh.seg(p33, (p33.x, Y33))
sh.seg((p33.x, Y33), (G(146), Y33))
c10 = hang("Device:C_Polarized", "C10", G(138), Y33, "10uF 50V", CP5)
c11 = hang("Device:C", "C11", G(146), Y33, "100nF", CDISC)
sh.seg(c10.pin(2), (c10.x, Y33 + G(8)))
sh.seg(c11.pin(2), (c11.x, Y33 + G(8)))
sh.seg((c10.x, Y33 + G(8)), (c11.x, Y33 + G(8)))
sh.gnd((G(142), Y33 + G(8)))
sh.rail((p33.x, Y33), net="+3V3")
sh.gnd(u1.pin("GND"))

# --- peripherals to the right of the module ---------------------------------
XP = G(176)
# UART flashing header: adapter RX <- TXD0, adapter TX -> RXD0
sh.note((XP - G(2), G(70)), "UART (flashing)", size=1.27)
j5 = sh.place("Connector_Generic:Conn_01x03", "J5", at=(XP + G(14), G(76)), value="UART", footprint=FP_HDR3)
for n, name in ((1, "TXD0"), (2, "RXD0")):
    p = j5.pin(n)
    sh.seg((XP, p.y), p)
    sh.label((XP, p.y), name, kind="global")
sh.seg(j5.pin(3), (XP + G(6), j5.pin(3).y))
sh.gnd((XP + G(6), j5.pin(3).y))
sh.note((XP + G(16), G(78)), "1 = TX (out), 2 = RX (in), 3 = GND")
# BOOT and USER buttons (internal pull-ups)
for i, (ref, name, val) in enumerate((("SW2", "BOOT", "BOOT"), ("SW1", "USER", "USER"))):
    y = G(88) + i * G(8)
    sw = sh.place("Switch:SW_Push", ref, at=(XP + G(8), y), value=val, footprint=FP_SW)
    sh.seg((XP, y), sw.pin(1))
    sh.label((XP, y), name, kind="global")
    sh.seg(sw.pin(2), (XP + G(16), y))
    sh.power("power:GND", (XP + G(16), y), rot=90)
# status LED, active high
YLED = G(106)
r6 = horiz("Device:R", "R6", XP + G(2), YLED, "221", RAX)
sh.seg((XP, YLED), r6.pin(1))
sh.label((XP, YLED), "LED", kind="global")
d3 = sh.place("Device:LED", "D3", at=(r6.pin(2).x + G(3), YLED + 3.81), rot=90, value="3mm green", footprint=FP_LED)
sh.seg(r6.pin(2), d3.pin("A"))
sh.gnd(d3.pin("K"))
# I2C encoder header (AS5600 breakout) with the bus pull-ups
YJ4 = G(128)
j4 = sh.place("Connector_Generic:Conn_01x04", "J4", at=(XP + G(26), YJ4), value="ENCODER I2C", footprint=FP_KK4)
sh.seg(j4.pin(1), (XP + G(20), j4.pin(1).y))
sh.seg((XP + G(20), j4.pin(1).y), (XP + G(20), j4.pin(1).y - G(6)))
sh.rail((XP + G(20), j4.pin(1).y - G(6)), net="+3V3")
sh.seg(j4.pin(2), (XP + G(12), j4.pin(2).y))
r7 = hang("Device:R", "R7", XP + G(12), j4.pin(2).y - 7.62, "4.75k", RAX)
sh.rail(r7.pin(1), net="+3V3")
sh.seg((XP + G(12), j4.pin(2).y), (XP, j4.pin(2).y))
sh.label((XP, j4.pin(2).y), "SDA", kind="global")
sh.seg(j4.pin(3), (XP + G(4), j4.pin(3).y))
r8 = hang("Device:R", "R8", XP + G(4), j4.pin(3).y - 7.62, "4.75k", RAX)
sh.rail(r8.pin(1), net="+3V3")
sh.seg((XP + G(4), j4.pin(3).y), (XP, j4.pin(3).y))
sh.label((XP, j4.pin(3).y), "SCL", kind="global")
sh.seg(j4.pin(4), (XP + G(20), j4.pin(4).y))
sh.gnd((XP + G(20), j4.pin(4).y))
sh.note((XP + G(28), YJ4 + G(6)), "1 = 3V3, 2 = SDA, 3 = SCL, 4 = GND")

# =============================================================================
# Band 3: L298 motor driver                                            y ~ 240
# =============================================================================
sh.note((G(40), G(146)),
        "5. Motor driver  (L298 bridge A, PWM on IN1/IN2, EnA tied high;  1 R sense -> 1 V per A -> ADC1 -> stall = end stop)", size=2)
XL, YL = G(90), G(172)
u2 = sh.place("Driver_Motor:L298HN", "U2", at=(XL, YL), value="L298", footprint=FP_L298)
# control inputs, pulled down so the bridge brakes (both low) while the module boots.
# EnA is tied to Vss: the ESP32 drives the bridge with IN1/IN2 alone.
p1, p2 = u2.pin("IN1"), u2.pin("IN2")
XA13, XB14 = XL - G(31), XL - G(19)          # IN2 stops short so R13 can hang from IN1
sh.seg(p1, (XL - G(35), p1.y))
sh.label((XL - G(35), p1.y), "M_IN1", kind="global")
sh.seg(p2, (XB14, p2.y))
sh.label((XB14, p2.y), "M_IN2", kind="global")
r13 = hang("Device:R", "R13", XA13, p1.y, "10k", RAX)
r14 = hang("Device:R", "R14", XB14, p2.y, "10k", RAX)
sh.gnd(r13.pin(2))
sh.gnd(r14.pin(2))
pena = u2.pin("EnA")
sh.seg(pena, (pena.x - G(3), pena.y))
sh.power("power:+5V", (pena.x - G(3), pena.y), rot=90)
# bridge B unused: inputs and enable to GND
XB2 = XL - G(17)
for pin in ("IN3", "IN4", "EnB"):
    sh.seg(u2.pin(pin), (XB2, u2.pin(pin).y))
sh.seg((XB2, u2.pin("IN3").y), (XB2, u2.pin("EnB").y))
sh.gnd((XB2, u2.pin("EnB").y))
sh.nc(u2.pin("OUT3"), u2.pin("OUT4"))
# Vss (+5V) up and left to its decoupling cap
pvss = u2.pin("Vss")
YVSS = pvss.y - G(8)
sh.seg(pvss, (pvss.x, YVSS))
sh.seg((pvss.x, YVSS), (XL - G(18), YVSS))
c15 = hang("Device:C", "C15", XL - G(18), YVSS, "100nF", CDISC)
sh.gnd(c15.pin(2))
sh.rail((pvss.x, YVSS), net="+5V")
# Vs (+12V) up and right to its decoupling
pvs = u2.pin("Vs")
YVS = pvs.y - G(4)
sh.seg(pvs, (pvs.x, YVS))
sh.seg((pvs.x, YVS), (XL + G(20), YVS))
c14 = hang("Device:C", "C14", XL + G(14), YVS, "100nF", CDISC_BENT)
c16 = hang("Device:C_Polarized", "C16", XL + G(20), YVS, "68uF 50V", CP8)
sh.gnd(c14.pin(2))
sh.gnd(c16.pin(2))
sh.rail((pvs.x + G(4), YVS), net="+12V")
# ground and current sense
sh.gnd(u2.pin("GND"))
sh.gnd(u2.pin("SENSE_B"))
psa = u2.pin("SENSE_A")
YS = psa.y + G(4)
sh.seg(psa, (psa.x, YS))
XR11 = psa.x - G(4)
sh.seg((psa.x, YS), (XR11, YS))
r11 = hang("Device:R", "R11", XR11, YS, "1R 5W", RPOWER)
sh.gnd(r11.pin(2))
r12 = horiz("Device:R", "R12", XR11 - G(4) - 7.62, YS, "1k", RAX)
sh.seg(r12.pin(2), (XR11, YS))
XIS = r12.pin(1).x - G(4)
sh.seg(r12.pin(1), (XIS - G(4), YS))
c13 = hang("Device:C", "C13", XIS, YS, "100nF", CDISC)
sh.gnd(c13.pin(2))
sh.label((XIS - G(4), YS), "I_SENSE", kind="global")
# outputs -> motor block
for pin, name in (("OUT1", "MOTOR_A"), ("OUT2", "MOTOR_B")):
    p = u2.pin(pin)
    sh.seg(p, (p.x + G(4), p.y))
    sh.label((p.x + G(4), p.y), name)

# --- motor header with the four flyback diodes --------------------------------
XJ = G(134)
YJ = G(168)
j3 = sh.place("Connector_Generic:Conn_01x02", "J3", at=(XJ, YJ), mirror="y", value="MOTOR", footprint=FP_KK2)
XA, XBB = XJ + G(12), XJ + G(22)
YA = j3.pin(1).y
YBn = j3.pin(2).y + G(10)
Y12 = YA - G(12)
sh.seg(j3.pin(1), (XA, YA))
sh.label((XJ + G(6), YA), "MOTOR_A")
sh.seg(j3.pin(2), (XJ + G(8), j3.pin(2).y))
sh.seg((XJ + G(8), j3.pin(2).y), (XJ + G(8), YBn))
sh.seg((XJ + G(8), YBn), (XBB, YBn))
sh.label((XJ + G(8), YBn - G(4)), "MOTOR_B")
d6 = diode_up("D6", XA, YA, "1N5817", DO41)             # MOTOR_A -> +12V
d7 = diode_up("D7", XA, YA + 7.62, "1N5817", DO41)      # GND -> MOTOR_A
d8 = diode_up("D8", XBB, YBn, "1N5817", DO41)           # MOTOR_B -> +12V
d9 = diode_up("D9", XBB, YBn + 7.62, "1N5817", DO41)    # GND -> MOTOR_B
sh.seg(d6.pin("K"), (XA, Y12))
sh.seg(d8.pin("K"), (XBB, Y12))
sh.seg((XA, Y12), (XBB, Y12))
sh.rail((XA, Y12), net="+12V")
sh.gnd(d7.pin("A"))
sh.gnd(d9.pin("A"))

sh.note((G(10), G(212)), "I_SENSE = 1.0 V per amp of motor current (R11 = 1 ohm under bridge A; also flows in slow decay).  Running ~0.3-0.8 A, stalled >1.8 A -> firmware stops within 60 ms.")
sh.note((G(10), G(215)), "The L298 has no current limit: the stall detection is the only protection, so keep the supply current-limited when bench testing.")
sh.note((G(10), G(218)), "Motor is a 6 V rated servo gearmotor on a 12 V bus: firmware caps PWM duty at 50 %. The L298 drops ~2-3 V, so the duty may need raising.")

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
