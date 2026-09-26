#!/usr/bin/env python3
"""Curtain Drive -- PCB build script (KiCad 10 pcbnew API).

Builds hardware/curtain-drive.kicad_pcb from the schematic netlist:
  * exports the netlist with kicad-cli, loads every footprint, assigns nets
  * places every part at hand-chosen coordinates (board-relative, mm)
  * draws the outline, mounting holes, GND pours on both layers and the
    antenna keep-out under the ESP32-C3 module
  * optionally routes with FreeRouting (--route) and fills the zones

    python3 hardware/tools/pcb_layout.py            # placement only
    python3 hardware/tools/pcb_layout.py --route    # + FreeRouting + zone fill

Board: 70 x 48 mm, SINGLE-SIDED: every part and every track on F.Cu, no vias.
Fabricated on the xTool F1 Ultra fiber laser (etch F.Cu, laser-ablated UV solder
mask, laser-cut outline and holes). FreeRouting is given one copper layer, so it
has nowhere to put a via, and the result is checked for zero vias and zero B.Cu copper.
"""
import subprocess
import sys
from pathlib import Path

import pcbnew
from pcbnew import VECTOR2I, FromMM

# KiCad 10 SWIG wrappers on Python 3.14: some container iterators still call .next()
pcbnew.SwigPyIterator.next = pcbnew.SwigPyIterator.__next__

HW = Path(__file__).resolve().parent.parent
SCH = HW / "curtain-drive-revB.kicad_sch"
PCB = HW / "curtain-drive-revB.kicad_pcb"
NET = HW / "docs" / "curtain-drive-revB.net"
FPLIB = Path("/usr/share/kicad/footprints")
PROJ_FPLIB = HW / "lib"                     # CurtainDrive.pretty: via-free variants
JAR = Path.home() / ".freerouting/freerouting-2.4.1.jar"

W, H = 90.0, 72.0          # board size, mm
X0, Y0 = 100.0, 100.0      # board origin in sheet coordinates
CORNER = 2.0

# -----------------------------------------------------------------------------
# Rev B placement.
#
# Single-sided for the fiber laser, as rev A, but every passive is a through-hole
# part from the DTU component shop. SMD parts (module, driver, buck, ESD array,
# USB-C, barrel jack) sit on the copper side (F); the THT parts sit on the back
# with their leads through the board, soldered on the copper. The board mounts
# copper side down, so the LED, buttons and tall capacitors face the lid.
#
# A THT part's body is on the back, so on the copper side a track can run between
# its two pads: every resistor is a free bridge. The topology is rev A's:
#  * module left edge fans I_SENSE (IO4) + the four driver lines into the DRV8876;
#    R13/R9/R10 straddle the I_SENSE track, VREF is fed inside that pocket;
#  * +3V3 reaches module pin 1 from underneath and loops round the reset block
#    (SW3 bridges EN and GND across the loop);
#  * SW2 bridges GND across the main +3V3 track, SW1 across the I2C lines;
#  * USB-C: R14 (wire link) hops A6 over D-, R16 hops the ESD array's GND over D+,
#    R3 stands on end so VBUS runs between its pads.
# -----------------------------------------------------------------------------
PLACE = {   # SMD parts on the copper side: ref -> (x, y, rot)
    "U1":  (44.0, 19.0, 0),
    "U2":  (25.0, 37.0, -90),
    "U3":  (76.0, 62.0, 180),
    "U4":  (66.0, 19.75, 180),
    "J1":  (10.0, 62.0, -90),
    "J2":  (86.8, 19.75, 90),     # shell front overhangs the edge 0.5 mm so a plug seats fully
}

# THT parts on the back: ref -> [(pad number, (x, y)), ...]. The first two targets fix
# position and orientation; a third disambiguates parts with paired pads (switches).
THT = {
    # reset / EN block inside the +3V3 loop (y = 6 top, x = 13 west, EN at y = 14.5)
    "SW3": [("1", (9.75, 9.0)), ("2", (9.75, 13.5)), ("1", (16.25, 9.0))],
    "R5":  [("1", (27.0, 6.0)), ("2", (27.0, 13.62))],
    "C10": [("1", (20.7, 6.0)), ("2", (20.7, 8.0))],
    "C11": [("1", (28.5, 2.6)), ("2", (23.5, 2.6))],
    "C9":  [("1", (21.4, 12.9)), ("2", (23.4, 12.9))],
    # VREF / nFAULT / current sense, straddling I_SENSE (x = 19.7), 3.1 mm rows
    "R13": [("1", (15.89, 18.6)), ("2", (23.51, 18.6))],
    "R9":  [("1", (15.89, 21.7)), ("2", (23.51, 21.7))],
    "R10": [("1", (23.51, 24.8)), ("2", (15.89, 24.8))],
    "R12": [("1", (23.2, 27.9)), ("2", (15.58, 27.9))],
    "R11": [("1", (23.2, 31.0)), ("2", (15.58, 31.0))],
    "C13": [("1", (12.0, 27.9)), ("2", (7.0, 27.9))],
    "J3":  [("1", (8.0, 34.14)), ("2", (8.0, 36.68))],
    # driver charge pump, VM decoupling down the VM track (x = 19.67)
    "C12": [("1", (26.5, 44.8)), ("2", (31.5, 44.8))],
    "C15": [("1", (19.67, 44.5)), ("2", (14.67, 44.5))],
    "C14": [("1", (19.67, 48.0)), ("2", (24.67, 48.0))],
    "C16": [("1", (19.67, 54.0)), ("2", (23.17, 54.0))],
    "R19": [("1", (29.5, 30.0)), ("2", (29.5, 37.62))],
    "SW2": [("2", (34.3, 37.0)), ("2", (34.3, 43.5)), ("1", (38.8, 37.0))],
    # below the module: IO2 pull-up, VM sense divider, USER button, I2C header
    "R15": [("1", (49.83, 35.3)), ("2", (49.83, 27.68))],
    "R2":  [("1", (53.0, 28.4)), ("2", (53.0, 36.02))],
    "R1":  [("2", (51.0, 38.8)), ("1", (51.0, 46.42))],
    "C3":  [("1", (54.1, 38.8)), ("2", (54.1, 43.8))],
    "SW1": [("1", (57.5, 28.0)), ("2", (57.5, 32.5)), ("1", (64.0, 28.0))],
    "J4":  [("1", (57.46, 42.0)), ("2", (60.0, 42.0))],
    "R7":  [("1", (60.0, 54.22)), ("2", (60.0, 46.6))],
    "R8":  [("1", (63.3, 54.22)), ("2", (63.3, 46.6))],
    # status LED on IO0
    "R6":  [("1", (55.0, 13.0)), ("2", (62.62, 13.0))],
    "D3":  [("2", (65.0, 13.0)), ("1", (67.54, 13.0))],
    # USB-C fan-out
    "R14": [("1", (77.0, 20.72)), ("2", (77.0, 18.18))],
    "R16": [("1", (68.8, 20.0)), ("2", (68.8, 17.46))],
    "R3":  [("1", (72.0, 23.56)), ("2", (72.0, 26.1))],
    "R4":  [("1", (80.6, 15.3)), ("2", (72.98, 15.3))],
    "D5":  [("2", (81.4, 29.0)), ("1", (81.4, 39.16))],
    # 3.3 V buck
    "D2":  [("1", (86.0, 48.0)), ("2", (86.0, 58.16))],
    "C4":  [("1", (81.4, 52.0)), ("2", (78.9, 52.0))],
    "C5":  [("1", (81.4, 58.0)), ("2", (76.4, 58.0))],
    "L1":  [("1", (67.0, 60.7)), ("2", (62.0, 60.7))],
    "C6":  [("1", (71.5, 65.7)), ("2", (71.5, 60.7))],
    "C7":  [("1", (54.5, 58.5)), ("2", (54.5, 62.0))],
    "C8":  [("1", (46.5, 58.5)), ("2", (46.5, 61.0))],
    # 12 V input
    "F1":  [("1", (21.5, 62.7)), ("2", (26.6, 61.5))],
    "C2":  [("1", (29.5, 56.5)), ("2", (29.5, 51.5))],
    "C1":  [("1", (35.0, 60.0)), ("2", (40.0, 60.0))],
    "D1":  [("1", (29.5, 68.5)), ("2", (44.74, 68.5))],
}
HOLES = [(3.5, 3.5), (86.5, 3.5), (87.0, 69.0), (3.5, 45.0)]

# Skeleton tracks laid (and locked) before FreeRouting runs: net, width, polyline.
# A point is (x, y) in board mm, (ref, pad) for that pad's centre, or
# (ref, pad, "x", y) for that pad's x at the given y.
PREROUTE = [
    # --- +3V3 ---------------------------------------------------------------
    ("+3V3", 0.5, [("U1", "1"), (29.0, 13.0), (29.0, 6.0), (13.0, 6.0), (13.0, 21.7)]),
    ("+3V3", 0.5, [(13.0, 18.6), ("R13", "1")]),
    ("+3V3", 0.5, [(13.0, 21.7), ("R9", "1")]),
    ("+3V3", 0.5, [("C11", "1"), (28.5, 6.0)]),
    ("+3V3", 0.5, [("U1", "1"), (47.0, 13.0), (47.0, 40.25), (29.5, 40.25), ("R19", "2")]),
    ("+3V3", 0.5, [("U2", "16"), (29.5, 39.86)]),
    ("+3V3", 0.5, [(47.0, 35.3), ("R15", "1")]),
    ("+3V3", 0.5, [(47.0, 40.25), (56.0, 40.25), (56.0, 54.22), ("R8", "1")]),
    ("+3V3", 0.5, [("J4", "1"), (57.46, 54.22)]),
    ("+3V3", 0.5, [("L1", "2"), (59.5, 60.7), (59.5, 54.22)]),
    ("+3V3", 0.5, [(59.5, 58.5), ("C8", "1")]),
    ("+3V3", 0.5, [("L1", "2"), (62.0, 67.5), (77.9, 67.5), (77.9, 63.3), ("U3", "1")]),
    # --- module left edge: I_SENSE and the four driver lines ----------------
    ("I_SENSE", 0.3, [("U1", "3"), (19.7, 16.0), (19.7, 27.9), ("C13", "1")]),
    ("M_nFAULT", 0.3, [("U1", "4"), ("U2", "4", "x", 17.5), ("U2", "4")]),
    ("M_nSLEEP", 0.3, [("U1", "5"), ("U2", "3", "x", 19.0), ("U2", "3")]),
    ("M_IN2", 0.3, [("U1", "6"), ("U2", "2", "x", 20.5), ("U2", "2")]),
    ("M_IN1", 0.3, [("U1", "7"), ("U2", "1", "x", 22.0), ("U2", "1")]),
    ("M_IN1", 0.3, [("U2", "1", "x", 30.0), ("R19", "1")]),
    ("M_nFAULT", 0.3, [("R13", "2"), ("U2", "4", "x", 18.6)]),
    ("Net-(U2-VREF)", 0.3, [("R9", "2"), ("U2", "5", "x", 21.7), ("U2", "5")]),
    ("Net-(U2-VREF)", 0.3, [("R10", "1"), ("U2", "5", "x", 24.8)]),
    ("Net-(U2-IPROPI)", 0.3, [("R12", "1"), ("R11", "1"), ("U2", "6", "x", 31.8), ("U2", "6")]),
    # --- EN, BOOT ------------------------------------------------------------
    ("Net-(U1-EN)", 0.3, [("U1", "2"), (16.25, 14.5), (16.25, 13.5)]),
    ("Net-(U1-EN)", 0.3, [("R5", "2"), (27.0, 14.5)]),
    ("Net-(U1-EN)", 0.3, [("C9", "1"), (21.4, 14.5)]),
    ("Net-(U1-IO9)", 0.3, [("U1", "8"), (33.5, 23.5), (33.5, 28.0), (34.3, 28.8), (34.3, 37.0)]),
    # --- DRV8876: exposed pad joins its GND pins top and bottom -------------
    ("GND", 0.3, [("U2", "7"), (23.38, 35.8)]),
    ("GND", 0.3, [("U2", "9"), (22.72, 38.3)]),
    ("GND", 0.3, [("U2", "15"), (26.62, 38.3)]),
    # outputs to the motor header, necked between the 0.65 mm pins
    ("Net-(J3-Pin_1)", 0.3, [("U2", "8"), (21.5, 34.14)]),
    ("Net-(J3-Pin_1)", 0.8, [(21.5, 34.14), ("J3", "1")]),
    ("Net-(J3-Pin_2)", 0.3, [("U2", "10"), (23.38, 41.0), (22.0, 41.0)]),
    ("Net-(J3-Pin_2)", 0.8, [(22.0, 41.0), (10.5, 41.0), (10.5, 36.68), ("J3", "2")]),
    # bottom row: VM west to its decoupling, VCP/CPH/CPL to their capacitors
    ("+12V", 0.3, [("U2", "11"), (24.03, 42.3), (21.0, 42.3)]),
    ("+12V", 0.8, [(21.0, 42.3), (19.67, 42.3), (19.67, 56.5), (51.0, 56.5), ("R1", "1")]),
    ("Net-(U2-VCP)", 0.3, [("U2", "12"), ("C14", "2")]),
    ("Net-(U2-CPH)", 0.3, [("U2", "13"), (25.33, 43.8), ("C12", "1")]),
    ("Net-(U2-CPL)", 0.3, [("U2", "14"), (25.97, 41.6), (31.5, 41.6), ("C12", "2")]),
    # --- 12 V trunk: fuse down past C1/D1, along the bottom edge to D2 --------
    ("+12V", 0.8, [(29.5, 56.5), ("D1", "1")]),
    ("+12V", 0.8, [("D1", "1"), (29.5, 71.2), (83.8, 71.2), (83.8, 62.0), (86.0, 59.8), ("D2", "2")]),
    ("+12V", 0.8, [("F1", "2"), (29.5, 61.5)]),
    ("+12V", 0.8, [(29.5, 60.0), ("C1", "1")]),
    ("Net-(F1-Pad1)", 0.8, [("J1", "1"), ("F1", "1")]),
    # --- module right edge: IO2 pull-up and VM sense from under the module ---
    ("Net-(U1-IO2)", 0.3, [("U1", "16"), (49.83, 16.0), ("R15", "2")]),
    ("VM_SENSE", 0.3, [("U1", "15"), (51.0, 17.5), ("R1", "2"), ("C3", "1")]),
    ("VM_SENSE", 0.3, [(51.0, 28.4), ("R2", "1")]),
    ("GND", 0.4, [("R2", "2"), (55.3, 34.5), (55.3, 28.0), (57.5, 28.0)]),   # divider foot, else walled in
    # --- I2C + USER ------------------------------------------------------------
    ("Net-(U1-IO10)", 0.3, [("U1", "10"), (58.9, 25.0), (58.9, 32.5), (57.5, 32.5)]),
    ("SDA", 0.3, [("U1", "11"), (60.0, 23.5), ("J4", "2"), ("R7", "2")]),
    ("SCL", 0.3, [("U1", "12"), (62.54, 22.0), ("J4", "3"), (62.54, 45.0), ("R8", "2")]),
    # --- status LED -------------------------------------------------------------
    ("LED", 0.3, [("U1", "18"), ("R6", "1")]),
    ("Net-(D3-A)", 0.3, [("R6", "2"), ("D3", "2")]),
    # --- USB-C pad row: fan out, hop A6 over D- (R14), CC1 pull-down over VBUS -
    ("Net-(J2-D+-PadB6)", 0.3, [("J2", "B6"), (78.1, 19.0), ("R14", "2"), (69.8, 18.18), (69.2, 18.7), ("U4", "3")]),
    ("Net-(J2-D+-PadA6)", 0.3, [("J2", "A6"), (77.0, 20.0), ("R14", "1")]),
    ("Net-(J2-D--PadA7)", 0.3, [("J2", "A7"), (75.9, 19.5), (75.9, 21.9), (68.5, 21.9), ("U4", "1")]),
    ("Net-(J2-D--PadA7)", 0.3, [("J2", "B7"), (79.6, 20.5), (78.2, 21.9), (75.9, 21.9)]),
    ("Net-(J2-CC1)", 0.3, [("J2", "A5"), (81.0, 21.0), (79.6, 22.4), (72.0, 22.4), ("R3", "1")]),
    ("Net-(J2-CC2)", 0.3, [("J2", "B5"), (80.6, 18.0), ("R4", "1")]),
    ("Net-(D5-A)", 0.5, [("J2", "A4"), (81.4, 22.2), ("D5", "2")]),
    ("Net-(D5-A)", 0.3, [("U4", "5"), (66.0, 19.75), (66.0, 24.8), (81.4, 24.8)]),
    ("USB_D+", 0.3, [("U4", "4"), ("U1", "14")]),
    ("USB_D-", 0.3, [("U4", "6"), ("U1", "13")]),
    ("Net-(U4-GND)", 0.3, [("U4", "2"), ("R16", "1")]),
    # --- buck: VBUCK down the east edge, switch node, bootstrap ----------------
    ("/VBUCK", 0.5, [("D5", "1"), (81.4, 59.0), (78.5, 61.05), ("U3", "3"), ("U3", "2")]),
    ("/VBUCK", 0.5, [("D2", "1"), (81.4, 48.0)]),
    ("Net-(U3-SW)", 0.3, [("U3", "5"), (73.0, 62.0)]),
    ("Net-(U3-SW)", 0.8, [(73.0, 62.0), (71.5, 62.0), ("C6", "2"), ("L1", "1")]),
    ("Net-(U3-BST)", 0.3, [("U3", "6"), (73.5, 64.0), ("C6", "1")]),
]
POWER_NETS = ("+12V", "Net-(F1-Pad1)", "Net-(J3-Pin_1)", "Net-(J3-Pin_2)", "Net-(U3-SW)")   # 0.8 mm
SUPPLY_NETS = ("+3V3", "/VBUCK", "Net-(D5-A)")                                                # 0.5 mm
# GND pads in the pocket above the USB pair: their only copper-free link to the rest of
# GND is through the USB-C shell / plug (jumper groups), so they route as their own net.
USB_POCKET_GND = ("R4", "R16", "D3")


def mm(x, y):
    return VECTOR2I(FromMM(X0 + x), FromMM(Y0 + y))


def kid(node, tag):
    for k in node:
        if isinstance(k, list) and k and getattr(k[0], "value", lambda: None)() == tag:
            return k
    return None


def kids(node, tag):
    return [k for k in node if isinstance(k, list) and k and getattr(k[0], "value", lambda: None)() == tag]


def sval(x):
    return x.value() if hasattr(x, "value") else str(x)


def load_netlist():
    import sexpdata
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr",
                    "-o", str(NET), str(SCH)], check=True, capture_output=True)
    tree = sexpdata.loads(NET.read_text())
    comps = {}
    for c in kids(kid(tree, "components"), "comp"):
        ref = sval(kid(c, "ref")[1])
        fp = sval(kid(c, "footprint")[1])
        val = sval(kid(c, "value")[1])
        sheet = sval(kid(kid(c, "sheetpath"), "tstamps")[1])
        ts = sval(kid(c, "tstamps")[1])
        comps[ref] = (fp, val, sheet.rstrip("/") + "/" + ts)
    nets = {}
    for n in kids(kid(tree, "nets"), "net"):
        name = sval(kid(n, "name")[1])
        nodes = [(sval(kid(x, "ref")[1]), sval(kid(x, "pin")[1])) for x in kids(n, "node")]
        nets[name] = nodes
    return comps, nets


def add_zone(board, net, layer, pts, rule_area=False):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    if net is not None:
        z.SetNet(net)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(FromMM(X0 + x), FromMM(Y0 + y))
    if rule_area:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowZoneFills(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        ls = pcbnew.LSET()
        ls.addLayer(pcbnew.F_Cu)
        z.SetLayerSet(ls)
    else:
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetMinThickness(FromMM(0.25))
        z.SetLocalClearance(FromMM(0.25))
        z.SetThermalReliefGap(FromMM(0.4))
        z.SetThermalReliefSpokeWidth(FromMM(0.4))
    board.Add(z)
    return z


def outline(board):
    r = FromMM(CORNER)
    L, T, R, B = FromMM(X0), FromMM(Y0), FromMM(X0 + W), FromMM(Y0 + H)

    def line(a, b):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(VECTOR2I(*a)); s.SetEnd(VECTOR2I(*b))
        s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(FromMM(0.1))
        board.Add(s)

    def arc(start, mid, end):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
        s.SetArcGeometry(VECTOR2I(*start), VECTOR2I(*mid), VECTOR2I(*end))
        s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(FromMM(0.1))
        board.Add(s)

    k = int(r * (1 - 0.70710678))
    line((L + r, T), (R - r, T))
    arc((R - r, T), (R - k, T + k), (R, T + r))
    line((R, T + r), (R, B - r))
    arc((R, B - r), (R - k, B - k), (R - r, B))
    line((R - r, B), (L + r, B))
    arc((L + r, B), (L + k, B - k), (L, B - r))
    line((L, B - r), (L, T + r))
    arc((L, T + r), (L + k, T + k), (L + r, T))


def lay_preroutes(board, fps):
    """Lay the PREROUTE skeleton as locked F.Cu tracks (FreeRouting keeps locked wires)."""
    def pad_mm(ref, num):
        pos = next(pd for pd in fps[ref].Pads() if pd.GetNumber() == num).GetPosition()
        return pcbnew.ToMM(pos.x) - X0, pcbnew.ToMM(pos.y) - Y0

    for net, width, pts in PREROUTE:
        xy = []
        for pt in pts:
            if isinstance(pt[0], str) and len(pt) == 4:        # (ref, pad, "x", y)
                xy.append((pad_mm(pt[0], pt[1])[0], pt[3]))
            elif isinstance(pt[0], str):                       # (ref, pad)
                xy.append(pad_mm(*pt))
            else:
                xy.append(pt)
        ni = board.FindNet(net)
        for (x1, y1), (x2, y2) in zip(xy, xy[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(mm(x1, y1)); t.SetEnd(mm(x2, y2))
            t.SetWidth(FromMM(width)); t.SetLayer(pcbnew.F_Cu)
            t.SetNet(ni); t.SetLocked(True)
            board.Add(t)


def place_tht(fp, targets):
    """Put a through-hole part on the back (non-copper) side with its pads on targets.

    targets is [(pad number, (x, y)), ...]. Every rotation is tried, and for pads that
    share a number (a switch's internally bridged pairs) every choice of physical pad,
    until all targets land within 0.02 mm."""
    import itertools
    fp.SetPosition(mm(0, 0))
    fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    for rot in (0, 90, 180, 270):
        fp.SetOrientationDegrees(rot)
        o = fp.GetPosition()
        rel = {}
        for pd in fp.Pads():
            q = pd.GetPosition()
            rel.setdefault(pd.GetNumber(), []).append(
                (pcbnew.ToMM(q.x - o.x), pcbnew.ToMM(q.y - o.y)))
        for combo in itertools.product(*(rel.get(n, []) for n, _ in targets)):
            if len(set(combo)) < len(combo):
                continue
            (dx, dy), (tx, ty) = combo[0], targets[0][1]
            ox, oy = tx - dx, ty - dy
            if all(abs(ox + cx - x) < 0.02 and abs(oy + cy - y) < 0.02
                   for (cx, cy), (_, (x, y)) in zip(combo, targets)):
                fp.SetPosition(mm(ox, oy))
                return
    sys.exit(f"{fp.GetReference()}: no rotation puts its pads on {targets}")


def build():
    comps, nets = load_netlist()
    board = pcbnew.BOARD()
    ds = board.GetDesignSettings()
    board.SetCopperLayerCount(1)        # F.Cu only: a via has nowhere to go
    ds.m_MinClearance = FromMM(0.2)
    ds.m_TrackMinWidth = FromMM(0.2)
    ds.m_ViasMinSize = FromMM(0.5)
    ds.m_MinThroughDrill = FromMM(0.2)
    ds.m_CopperEdgeClearance = FromMM(0.3)
    try:
        dnc = ds.m_NetSettings.GetDefaultNetclass()
        dnc.SetClearance(FromMM(0.2)); dnc.SetTrackWidth(FromMM(0.3))
        dnc.SetViaDiameter(FromMM(0.7)); dnc.SetViaDrill(FromMM(0.35))
    except Exception as e:  # noqa: BLE001
        print("netclass defaults not set:", e)

    netmap = {}
    for name in nets:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        netmap[name] = ni
    pad_net = {}
    for name, nodes in nets.items():
        for ref, pin in nodes:
            pad_net[(ref, pin)] = name

    fps = {}
    for ref, (fpid, val, path) in comps.items():
        lib, name = fpid.split(":")
        libdir = PROJ_FPLIB if (PROJ_FPLIB / f"{lib}.pretty").exists() else FPLIB
        fp = pcbnew.FootprintLoad(str(libdir / f"{lib}.pretty"), name)
        if fp is None:
            sys.exit(f"footprint not found: {fpid}")
        fp.SetReference(ref)
        fp.SetValue(val)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetPath(pcbnew.KIID_PATH(path))
        if ref in PLACE:
            x, y, rot = PLACE[ref]
            fp.SetPosition(mm(x, y))
            fp.SetOrientationDegrees(rot)
        else:
            board.Add(fp)                  # Flip() needs the board for its layer map
            place_tht(fp, THT[ref])
        for pad in fp.Pads():
            key = (ref, pad.GetNumber())
            if key in pad_net:
                pad.SetNet(netmap[pad_net[key]])
        # small parts: hide value text on silk to keep it clean
        fp.Value().SetVisible(False)
        fp.Reference().SetTextSize(VECTOR2I(FromMM(0.8), FromMM(0.8)))
        fp.Reference().SetTextThickness(FromMM(0.12))
        if ref in ("U2", "U3", "U4"):
            fp.Reference().SetLayer(pcbnew.F_Fab)      # keep the silkscreen clean; refs stay on F.Fab
        elif ref in THT:
            fp.Reference().SetLayer(pcbnew.B_Fab)      # back parts: outline on B.SilkS, ref on B.Fab
        if ref in PLACE:
            board.Add(fp)
        fps[ref] = fp

    outline(board)
    lay_preroutes(board, fps)
    for i, (x, y) in enumerate(HOLES, 1):
        fp = pcbnew.FootprintLoad(str(FPLIB / "MountingHole.pretty"), "MountingHole_2.7mm_M2.5")
        fp.SetReference(f"H{i}")
        fp.SetPosition(mm(x, y))
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        fp.SetAttributes(pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        board.Add(fp)

    # antenna keep-out: no copper on either layer under the module antenna.
    # (GND pours are added after routing so the router connects GND with tracks too.)
    ux = PLACE["U1"][0]
    add_zone(board, None, pcbnew.F_Cu, [(ux - 14.5, 0.0), (ux + 14.5, 0.0), (ux + 14.5, 12.0), (ux - 14.5, 12.0)], rule_area=True)

    # silkscreen title
    t = pcbnew.PCB_TEXT(board)
    t.SetText("CURTAIN DRIVE rev B")
    t.SetPosition(mm(62.0, 69.2))
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(VECTOR2I(FromMM(0.9), FromMM(0.9)))
    t.SetTextThickness(FromMM(0.15))
    board.Add(t)

    board.SetFileName(str(PCB))
    apply_netclasses(board)
    pcbnew.SaveBoard(str(PCB), board)
    print("wrote", PCB, "with", len(fps), "footprints,", len(nets), "nets")
    return board


def apply_netclasses(board):
    """Power (0.8 mm) and Supply (0.5 mm) netclasses, set on the board itself so every
    save (and the DSN export FreeRouting sees) carries them."""
    ns = board.GetDesignSettings().m_NetSettings
    for name, width in (("Power", 0.8), ("Supply", 0.5)):
        nc = pcbnew.NETCLASS(name)
        nc.SetTrackWidth(FromMM(width)); nc.SetClearance(FromMM(0.2))
        nc.SetViaDiameter(FromMM(0.8)); nc.SetViaDrill(FromMM(0.4))
        ns.SetNetclass(name, nc)
    ns.ClearNetclassPatternAssignments()
    for n in POWER_NETS:
        ns.SetNetclassPatternAssignment(n, "Power")
    for n in SUPPLY_NETS:
        ns.SetNetclassPatternAssignment(n, "Supply")
    board.SynchronizeNetsAndNetClasses(True)


def split_jumpered_pads(board):
    """Give FreeRouting only the copper it must build.

    KiCad knows some same-net pads are already joined off the board (jumper pad groups
    and duplicate-number pads: the USB-C shell, the plug's paired VBUS/GND contacts,
    the tact switches' internal bridges); FreeRouting does not, and would try to join
    them with a track it has no room for. So for the route only: the redundant pads
    lose their net, and the GND pads in the pocket above the USB pair route as their
    own net. Returns what restore_jumpered_pads() needs to put the netlist back.
    """
    gnd = board.FindNet("GND")
    pocket = pcbnew.NETINFO_ITEM(board, "GND_USB_POCKET")
    board.Add(pocket)
    saved = []
    j2 = board.FindFootprintByReference("J2")
    for pad in j2.Pads():
        num, y = pad.GetNumber(), pad.GetPosition().y
        if num in ("A9", "B4"):                                   # VBUS pair the plug bridges
            saved.append((pad, pad.GetNetCode())); pad.SetNetCode(0)
        elif num in ("A12", "B1") or (num == "SH" and y < j2.GetPosition().y):
            saved.append((pad, pad.GetNetCode())); pad.SetNet(pocket)
    for ref in USB_POCKET_GND:
        for pad in board.FindFootprintByReference(ref).Pads():
            if pad.GetNetCode() == gnd.GetNetCode():
                saved.append((pad, pad.GetNetCode())); pad.SetNet(pocket)
    for fp in board.GetFootprints():
        if fp.GetReference().startswith("SW"):
            seen = set()
            for pad in fp.Pads():
                if pad.GetNumber() in seen:
                    saved.append((pad, pad.GetNetCode())); pad.SetNetCode(0)
                seen.add(pad.GetNumber())
    return saved


def restore_jumpered_pads(board, saved):
    gnd = board.FindNet("GND")
    for t in board.GetTracks():
        if t.GetNetname() == "GND_USB_POCKET":
            t.SetNet(gnd)
    for pad, code in saved:
        pad.SetNetCode(code)


def check_dsn_one_layer(text):
    """The DSN must offer FreeRouting exactly one copper layer: with nowhere to put a
    via it cannot make one. (An injected (autoroute_settings (vias off) ...) scope, the
    FreeRouting 1.9 trick, makes 2.4 see zero routable pins, so it is not used.)"""
    import re
    layers = re.findall(r"\(layer\s+([^\s()]+)\s*\(type\s+(?:signal|power)\)", text)
    if layers != ["F.Cu"]:
        sys.exit(f"DSN has copper layers {layers}, expected only F.Cu")


def route():
    dsn = HW / "docs" / "curtain-drive-revB.dsn"
    ses = HW / "docs" / "curtain-drive-revB.ses"
    board = pcbnew.LoadBoard(str(PCB))
    board.SetCopperLayerCount(1)            # the saved file can come back with two; F.Cu only
    apply_netclasses(board)
    saved = split_jumpered_pads(board)
    m = 0.5
    rect = [(m, m), (W - m, m), (W - m, H - m), (m, H - m)]
    if PLANE_GND:
        # GND poured before the export: FreeRouting treats it as a plane and leaves
        # its pads to the fill (checked for islands by DRC afterwards).
        add_zone(board, board.FindNet("GND"), pcbnew.F_Cu, rect)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    ok = pcbnew.ExportSpecctraDSN(board, str(dsn))
    print("dsn export:", ok)
    check_dsn_one_layer(dsn.read_text())
    if ses.exists():
        ses.unlink()
    cmd = ["java", "-Djava.awt.headless=true", "-jar", str(JAR), "-de", str(dsn), "-do", str(ses),
           "-mp", "100", "-mt", "6"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
    print(r.stdout[-600:])
    if not ses.exists():
        sys.exit("freerouting produced no .ses\n" + r.stderr[-2000:])
    ok = pcbnew.ImportSpecctraSES(board, str(ses))
    print("ses import:", ok)
    restore_jumpered_pads(board, saved)
    # FreeRouting necks traces down to squeeze between fine-pitch pads; lift any such
    # stub back up to the board minimum so DRC's track_width rule holds.
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetWidth() < board.GetDesignSettings().m_TrackMinWidth:
            t.SetWidth(board.GetDesignSettings().m_TrackMinWidth)
    if not PLANE_GND:
        add_zone(board, board.FindNet("GND"), pcbnew.F_Cu, rect)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(str(PCB), board)
    print("routed + filled, saved", PCB)
    check_single_sided()


def check_single_sided():
    """Reload and refuse anything the laser cannot make: vias or copper off F.Cu."""
    board = pcbnew.LoadBoard(str(PCB))
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    off = [t for t in board.GetTracks() if t.GetClass() != "PCB_VIA" and t.GetLayer() != pcbnew.F_Cu]
    print(f"single-sided check: {len(vias)} vias, {len(off)} tracks off F.Cu")
    if vias or off:
        sys.exit("NOT single-sided")


PLANE_GND = "--gnd-traces" not in sys.argv     # default: GND is a pour, not routed as tracks


if __name__ == "__main__":
    build()
    if "--route" in sys.argv:
        route()
