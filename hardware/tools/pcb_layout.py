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
SCH = HW / "curtain-drive.kicad_sch"
PCB = HW / "curtain-drive.kicad_pcb"
NET = HW / "docs" / "curtain-drive.net"
FPLIB = Path("/usr/share/kicad/footprints")
PROJ_FPLIB = HW / "lib"                     # CurtainDrive.pretty: via-free variants
JAR = Path.home() / ".freerouting/freerouting-2.4.1.jar"

W, H = 80.0, 62.0          # board size, mm
X0, Y0 = 100.0, 100.0      # board origin in sheet coordinates
CORNER = 2.0

# -----------------------------------------------------------------------------
# Placement table: ref -> (x, y, rot)   board-relative mm, rot in degrees CCW
#
# Single-sided, so the placement is the routing plan (the PREROUTE tracks below fix
# its skeleton before FreeRouting fills in the rest):
#  * The module's left edge fans I_SENSE (IO4) and the four DRV8876 lines (IO5..IO8)
#    straight down into the driver's top row. VREF is boxed in between I_SENSE and
#    nFAULT, so R9/R10/R13 straddle the I_SENSE track (0805: a track fits between).
#  * +3V3 reaches module pin 1 from underneath (between the right pad row and the
#    ground pad), and from pin 1 loops around the EN/reset block, passing under SW3
#    between its pad pairs -- the switch's internal bridges carry EN and GND across.
#  * The main +3V3 track runs west under R1 (1206) and between the pad pairs of SW1
#    and SW2, whose bridges carry GND (and their signal) across it.
#  * USB-C needs two 0R hops: R14 (pad A6, boxed in by the two D- pads) and R16
#    (the ESD array's GND).
# -----------------------------------------------------------------------------
PLACE = {
    # ESP32-C3 module, antenna at the top edge
    "U1":  (44.0, 19.0, 0),
    # USB-C on the right edge, ESD array, CC pull-downs, D+ / GND hops, VBUS diode
    "J2":  (76.8, 19.75, 90),     # shell front overhangs the edge 0.5 mm so a plug seats fully
    "U4":  (63.8, 19.75, 180),
    "R14": (69.0, 19.5, 90),     # 0603: A7 (D-) runs between its pads
    "R16": (66.9, 18.75, 90),    # the D+ track runs between its pads
    "R4":  (68.5, 13.8, 90),
    "R3":  (67.1, 22.7125, -90), # 0805: VBUS runs between its pads
    "D5":  (69.3, 24.3625, 90),
    # status LED on IO0 (above the USB pair)
    "R6":  (60.5, 12.5, 0),
    "D3":  (60.5, 15.0, 0),
    # top-left: reset + EN RC + module decoupling inside the +3V3 loop
    "SW3": (14.0, 11.0, 0),
    "C9":  (20.5, 11.2, 90),
    "C11": (22.6, 10.0, -90),
    "C10": (24.8, 10.0, -90),
    "R5":  (27.2, 10.0, -90),
    # current sense and VREF: R9/R10/R13 straddle the I_SENSE track
    "R13": (18.0, 19.5, 0),
    "R9":  (18.0, 22.5, 0),
    "R10": (18.0, 25.5, 180),
    "C13": (15.5, 28.5, -90),
    "R12": (21.0, 29.5, 180),
    "R11": (20.0, 31.1, 180),
    # DRV8876, inputs on its top row facing the module, motor connector to the west
    "U2":  (25.0, 36.0, -90),
    "J3":  (13.0, 35.5, -90),
    "C14": (23.6, 41.8, 0),
    "C12": (26.4, 43.0, 90),
    "C15": (20.6, 43.0, 180),
    "R19": (29.4, 36.0, -90),
    # BOOT straddles the main +3V3 track; USER sits over the I2C lines
    "SW2": (35.5, 40.0, -90),
    "SW1": (60.0, 30.0, 0),
    # below the module: IO2 pull-up, VM sense divider, I2C header + pull-ups
    "R15": (49.0, 28.6, 0),
    "R2":  (52.5, 33.0, 90),
    "C3":  (52.5, 36.0, 90),
    "R1":  (51.5, 40.0, 90),
    "J4":  (61.0, 41.5, 0),
    "R7":  (59.0, 46.3, 0),
    "R8":  (61.0, 35.0, 90),
    # 12 V input along the bottom edge
    "J1":  (10.0, 52.5, -90),
    "F1":  (23.0, 56.5, 0),
    "D1":  (30.0, 59.5, 180),    # cathode (pad 1) east, on the +12 V feed
    "C2":  (35.5, 59.5, 0),
    "C16": (33.0, 51.5, 0),
    "C1":  (43.5, 56.5, 0),
    # 3.3 V buck, bottom right: VIN faces the VBUCK track on the east, SW/L1 west
    "U3":  (66.5, 50.0, 180),
    "C4":  (71.0, 45.5, 90),
    "C5":  (69.4, 51.5, 90),
    "C6":  (63.3, 50.5, 90),
    "D2":  (72.5, 52.5, -90),
    "L1":  (58.5, 50.5, 180),
    "C7":  (53.5, 50.5, -90),
    "C8":  (51.3, 50.5, -90),
}
HOLES = [(3.5, 3.5), (76.5, 3.5), (76.5, 58.5), (3.5, 24.0)]

# Skeleton tracks laid (and locked) before FreeRouting runs: net, width, polyline.
# A point is either (x, y) in board mm or (ref, pad) for that pad's centre.
PREROUTE = [
    # --- +3V3 ---------------------------------------------------------------
    # from module pin 1 round the EN/reset block (under SW3) and down past R13/R9
    ("+3V3", 0.5, [("U1", "1"), (29.0, 13.0), (29.0, 6.0), (14.0, 6.0), (14.0, 22.5)]),
    ("+3V3", 0.5, [(14.0, 19.5), ("R13", "1")]),
    ("+3V3", 0.5, [(14.0, 22.5), ("R9", "1")]),
    ("+3V3", 0.5, [(24.8, 6.0), ("C10", "1")]),
    ("+3V3", 0.5, [(22.6, 6.0), ("C11", "1")]),
    ("+3V3", 0.5, [(29.0, 9.17), ("R5", "1")]),
    # into pin 1 from under the module, then the main track west under SW2 and R1
    ("+3V3", 0.5, [("U1", "1"), (47.0, 13.0), (47.0, 40.0), (29.4, 40.0), ("R19", "2")]),
    ("+3V3", 0.5, [("U2", "16"), (29.4, 38.86)]),
    ("+3V3", 0.5, [(47.0, 28.6), ("R15", "1")]),
    # east: to the buck output, the I2C header and its pull-ups
    ("+3V3", 0.5, [(47.0, 40.0), (54.3, 40.0), (54.3, 47.3), (61.0, 47.3), ("R8", "1")]),
    ("+3V3", 0.5, [(54.3, 49.55), ("C7", "1")]),
    ("+3V3", 0.5, [(54.3, 47.3), (54.3, 49.55)]),
    ("+3V3", 0.5, [("C7", "1"), ("C8", "1")]),
    ("+3V3", 0.5, [(56.45, 47.3), ("L1", "2")]),
    ("+3V3", 0.5, [(58.175, 47.3), ("R7", "1"), (58.0, 45.5), ("J4", "1")]),
    # --- module left edge: I_SENSE and the four driver lines ----------------
    ("I_SENSE", 0.3, [("U1", "3"), (18.0, 16.0), (18.0, 29.5), ("R12", "2")]),
    ("M_nFAULT", 0.3, [("U1", "4"), ("U2", "4", "x", 17.5), ("U2", "4")]),
    ("M_nSLEEP", 0.3, [("U1", "5"), ("U2", "3", "x", 19.0), ("U2", "3")]),
    ("M_IN2", 0.3, [("U1", "6"), ("U2", "2", "x", 20.5), ("U2", "2")]),
    ("M_IN1", 0.3, [("U1", "7"), ("U2", "1", "x", 22.0), ("U2", "1")]),
    # --- module right edge: IO2 pull-up and VM sense out from under the module
    ("Net-(U1-IO2)", 0.3, [("U1", "16"), (49.83, 16.0), ("R15", "2")]),
    ("VM_SENSE", 0.3, [("U1", "15"), (51.0, 17.5), (51.0, 38.54), ("R1", "2")]),
    ("VM_SENSE", 0.3, [(51.0, 33.82), ("R2", "1")]),
    ("VM_SENSE", 0.3, [(51.0, 36.78), ("C3", "1")]),
    # --- I2C + USER under SW1 ------------------------------------------------
    ("Net-(U1-IO10)", 0.3, [("U1", "10"), (57.2, 25.0), (57.2, 32.25), (55.98, 32.25)]),
    ("SDA", 0.3, [("U1", "11"), (60.0, 23.5), ("J4", "2")]),
    ("SDA", 0.3, [("R7", "2"), (60.0, 46.3), (60.0, 44.5)]),
    ("SCL", 0.3, [("U1", "12"), (62.0, 22.0), ("J4", "3")]),
    ("SCL", 0.3, [("R8", "2"), (62.0, 34.175)]),
    # --- USB-C pad row: fan out, hop A6 over D- (R14), CC1 over VBUS (R3) ---
    ("Net-(J2-D+-PadB6)", 0.3, [("J2", "B6"), (70.9, 19.0), ("R14", "2"), ("U4", "3")]),
    ("Net-(J2-D+-PadA6)", 0.3, [("J2", "A6"), (69.3, 20.0)]),
    ("Net-(J2-D--PadA7)", 0.3, [("J2", "A7"), (68.1, 19.5), (68.1, 20.7), ("U4", "1")]),
    ("Net-(J2-D--PadA7)", 0.3, [("J2", "B7"), (70.4, 20.5), (69.8, 21.1), (68.5, 21.1), (68.1, 20.7)]),
    ("Net-(J2-CC1)", 0.3, [("J2", "A5"), (71.0, 21.0), (70.4, 21.6), (67.1, 21.6), ("R3", "1")]),
    ("Net-(J2-CC2)", 0.3, [("J2", "B5"), (70.6, 18.0), (70.6, 15.3), ("R4", "1")]),
    ("Net-(D5-A)", 0.5, [("J2", "A4"), (70.9, 22.2), (70.4, 22.7125), ("D5", "2")]),
    ("Net-(D5-A)", 0.3, [("D5", "2"), (63.8, 22.7125), (63.8, 19.75), ("U4", "5")]),
    ("USB_D+", 0.3, [("U4", "4"), ("U1", "14")]),
    ("USB_D-", 0.3, [("U4", "6"), ("U1", "13")]),
    ("Net-(U4-GND)", 0.3, [("U4", "2"), ("R16", "1")]),
    # --- EN, BOOT, the VREF pocket, current sense ----------------------------
    ("Net-(U1-EN)", 0.3, [("U1", "2"), (27.2, 14.5), ("R5", "2")]),
    ("Net-(U1-EN)", 0.3, [(27.2, 14.5), (20.5, 14.5), ("C9", "1")]),
    ("Net-(U1-EN)", 0.3, [(20.5, 14.5), (17.98, 14.5), (17.98, 13.25)]),
    ("Net-(U1-IO9)", 0.3, [("U1", "8"), (33.25, 23.5), (33.25, 36.02)]),
    ("M_nFAULT", 0.3, [("R13", "2"), (25.33, 19.5)]),
    ("Net-(U2-VREF)", 0.3, [("R9", "2"), (24.67, 22.5), ("U2", "5")]),
    ("Net-(U2-VREF)", 0.3, [("R10", "1"), (24.67, 25.5)]),
    ("Net-(U2-IPROPI)", 0.3, [("R11", "1"), (21.83, 31.1), ("R12", "1")]),
    ("Net-(U2-IPROPI)", 0.3, [("R12", "1"), (24.03, 29.5), ("U2", "6")]),
    # --- DRV8876: exposed pad joins its GND pins top and bottom -------------
    ("GND", 0.3, [("U2", "7"), (23.38, 34.8)]),
    ("GND", 0.3, [("U2", "9"), (22.72, 37.3)]),
    ("GND", 0.3, [("U2", "15"), (26.62, 37.3)]),
    # bottom row fans out in pin order: OUT2 west, VM/VCP to C14, CPH/CPL to C12
    ("Net-(J3-Pin_2)", 0.3, [("U2", "10"), (23.38, 40.0), (22.0, 40.0)]),
    ("Net-(J3-Pin_2)", 0.8, [(22.0, 40.0), (17.0, 40.0), (17.0, 37.3), (16.2, 36.5), ("J3", "2")]),
    ("+12V", 0.3, [("U2", "11"), (24.03, 40.7), ("C14", "1")]),
    ("+12V", 0.8, [("C14", "1"), ("C15", "1")]),
    ("Net-(U2-VCP)", 0.3, [("U2", "12"), (24.67, 40.7), ("C14", "2")]),
    ("Net-(U2-CPH)", 0.3, [("U2", "13"), (25.33, 43.825), ("C12", "1")]),
    ("Net-(U2-CPL)", 0.3, [("U2", "14"), ("C12", "2")]),
    # top-row OUT1 leaves north, necked between the 0.65 mm pins, then west to J3
    ("Net-(J3-Pin_1)", 0.3, [("U2", "8"), (22.72, 32.2), (22.2, 32.2)]),
    ("Net-(J3-Pin_1)", 0.8, [(22.2, 32.2), (18.2, 32.2), (16.6, 33.8), (15.6, 34.5), ("J3", "1")]),
    # --- 12 V to the VM-sense divider: from C16 along y = 45.5, so the ground
    # band south of it stays open from C16 to the buck output capacitors
    ("+12V", 0.8, [("C16", "1"), (30.3, 45.5), (51.5, 45.5), ("R1", "1")]),
    ("+12V", 0.8, [("C15", "1"), (21.38, 45.5), (30.3, 45.5)]),
    # the 12 V trunk: fuse -> C16 / TVS / C2 / C1, then along the south edge to D2
    ("+12V", 0.8, [("F1", "2"), (28.0, 54.2), (40.25, 54.2), ("C1", "1")]),
    ("+12V", 0.8, [("C16", "1"), (30.3, 54.2)]),
    ("+12V", 0.8, [(32.0, 54.2), ("D1", "1")]),
    ("+12V", 0.8, [(34.72, 54.2), ("C2", "1")]),
    ("+12V", 0.8, [("C1", "1"), (40.25, 58.9), (72.5, 58.9), ("D2", "2")]),
    ("I_SENSE", 0.3, [("C13", "1"), (18.0, 27.725)]),
    # --- buck feedback: from the L1 output round the south of U3 to FB -------
    ("+3V3", 0.5, [("L1", "2"), (56.45, 53.8), (67.64, 53.8), ("U3", "1")]),
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
        x, y, rot = PLACE[ref]
        fp.SetPosition(mm(x, y))
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            key = (ref, pad.GetNumber())
            if key in pad_net:
                pad.SetNet(netmap[pad_net[key]])
        # small parts: hide value text on silk to keep it clean
        fp.Value().SetVisible(False)
        fp.Reference().SetTextSize(VECTOR2I(FromMM(0.8), FromMM(0.8)))
        fp.Reference().SetTextThickness(FromMM(0.12))
        if ref[0] in "RCDLF" or ref in ("U2", "U3", "U4", "J4"):
            fp.Reference().SetLayer(pcbnew.F_Fab)      # keep the silkscreen clean; refs stay on F.Fab
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
    t.SetText("CURTAIN DRIVE v0.2")
    t.SetPosition(mm(64.0, 60.3))
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
    dsn = HW / "docs" / "curtain-drive.dsn"
    ses = HW / "docs" / "curtain-drive.ses"
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
