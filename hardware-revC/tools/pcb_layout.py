#!/usr/bin/env python3
"""Curtain Drive Rev C -- PCB build script (KiCad 10 pcbnew API).

Builds hardware-revC/curtain-drive-revC.kicad_pcb from the schematic netlist:
  * exports the netlist with kicad-cli, loads every footprint, assigns nets
  * places every part at hand-chosen coordinates (board-relative, mm)
  * draws the outline, mounting holes and the antenna keep-out under the module
  * optionally routes with FreeRouting (--route): GND is poured first so the router
    treats it as a plane, then the pour is refilled around the routed tracks

    python3 hardware-revC/tools/pcb_layout.py            # placement only
    python3 hardware-revC/tools/pcb_layout.py --route    # + FreeRouting + zone fill

Board: 90 x 72 mm (rev B's outline and mounting holes, so the enclosure still fits),
SINGLE-SIDED: every track on F.Cu, no vias. Made on the xTool F1 Ultra fiber laser.
The ESP32-WROOM-32 is the only SMD part and sits on the copper side; every other part
is a through-hole part from the DTU shop, body on the back, soldered on the copper.
On the copper side a THT part is just its pads, so every resistor, diode and disc cap
is also a free bridge that tracks run under.
"""
import subprocess
import sys
from pathlib import Path

import pcbnew
from pcbnew import VECTOR2I, FromMM

# KiCad 10 SWIG wrappers on Python 3.14: some container iterators still call .next()
pcbnew.SwigPyIterator.next = pcbnew.SwigPyIterator.__next__

HW = Path(__file__).resolve().parent.parent
SCH = HW / "curtain-drive-revC.kicad_sch"
PCB = HW / "curtain-drive-revC.kicad_pcb"
NET = HW / "docs" / "curtain-drive-revC.net"
FPLIB = Path("/usr/share/kicad/footprints")
PROJ_FPLIB = HW / "lib"                     # CurtainDrive.pretty: via-free variants
JAR = max(Path.home().glob(".freerouting/freerouting-*.jar"))   # whichever release is installed

W, H = 90.0, 72.0          # board size, mm
X0, Y0 = 100.0, 100.0      # board origin in sheet coordinates
CORNER = 2.0

# -----------------------------------------------------------------------------
# Rev C placement.
#
# The module sits at the top edge, antenna over the edge strip. Its left pins carry
# what goes to the motor side (I_SENSE, M_IN1, M_IN2), its right pins the UI side
# (LED, UART, I2C, USER, BOOT). Two nets cross underneath the module, where only its
# own pads are in the way: +3V3 comes in at the bottom-right corner and reaches VDD
# (pin 2) from inside, and VM_SENSE leaves pin 4 inside and exits bottom-left.
#
# The L298 (Multiwatt15, standing on the back) can only sit mirrored: with the odd
# pins on the right column (x = 30, facing the module) pin 1 is at the top.
#  * right column, from the right: IN1/IN2 straight in; Vss decoupled by C15;
#    SENSE_A (pin 1, top) goes up and left to R11 (1 ohm) and R12 (to I_SENSE);
#  * left column, from the left: OUT1, VS (+12V), EnA (+5V from the LM7805);
#  * the channel between the rows: EnA joins Vss, and OUT2 (pin 3) leaves through the
#    top end towards the motor header.
# The motor lines run to J3 on the left edge; the +12V trunk runs up the very edge,
# outside J3, so they never cross. The flyback diodes straddle the motor lines.
# -----------------------------------------------------------------------------
PLACE = {   # SMD parts on the copper side: ref -> (x, y, rot)
    "U1": (44.0, 16.0, 0),
}

# THT parts on the back: ref -> [(pad number, (x, y)), ...]. The first two targets fix
# position and orientation; a third disambiguates parts with paired pads (switches).
THT = {
    # reset / EN and 3V3 decoupling, top left. The module footprint's own antenna
    # keep-out spans x = 20..68 above y = 6.2, so the +3V3 line turns up at x = 19.3.
    "R5":  [("1", (8.0, 2.5)), ("2", (8.0, 10.12))],
    "C11": [("1", (12.0, 2.5)), ("2", (12.0, 7.5))],
    "C7":  [("1", (19.3, 6.5)), ("2", (15.8, 6.5))],      # 470 uF bulk on the module's 3V3
    "C9":  [("1", (13.0, 10.29)), ("2", (13.0, 12.29))],
    "SW3": [("1", (6.0, 20.0)), ("2", (6.0, 15.5)), ("1", (12.5, 20.0))],
    # current sense: I_SENSE comes down x = 23.68, SENSE_A comes up from pin 1
    "C13": [("1", (23.68, 17.0)), ("2", (18.68, 17.0))],
    "R12": [("1", (23.68, 21.88)), ("2", (23.68, 29.5))],
    "R11": [("1", (27.5, 27.0)), ("2", (55.44, 27.0))],
    # the driver
    "U2":  [("1", (30.0, 34.0)), ("2", (24.92, 35.27)), ("3", (30.0, 36.54))],
    "R13": [("1", (32.6, 35.5)), ("2", (40.22, 35.5))],
    "R14": [("1", (33.9, 38.8)), ("2", (41.52, 38.8))],
    "C15": [("1", (33.0, 44.16)), ("2", (33.0, 49.16))],
    # motor header, flyback diodes and VS decoupling; OUT2 runs at y = 32.3, OUT1 at 35.27
    "J3":  [("1", (3.5, 35.0)), ("2", (3.5, 32.46))],
    "D9":  [("1", (13.6, 32.3)), ("2", (13.6, 22.14))],
    "D7":  [("1", (9.0, 35.27)), ("2", (9.0, 25.11))],
    "D6":  [("2", (11.4, 35.27)), ("1", (11.4, 45.43))],
    "D8":  [("2", (15.9, 32.3)), ("1", (15.9, 42.46))],
    "C14": [("1", (19.0, 37.81)), ("2", (19.0, 30.19))],
    # 5 V for the L298 logic
    "U4":  [("1", (12.5, 50.0)), ("3", (17.58, 50.0))],
    "C5":  [("1", (8.0, 45.0)), ("2", (8.0, 50.0))],
    # VM sense divider on the VM_SENSE column (x = 36.7), R1 down to the +12V bus
    "C3":  [("1", (36.7, 44.0)), ("2", (41.7, 44.0))],
    "R2":  [("1", (36.7, 47.5)), ("2", (44.32, 47.5))],
    "R1":  [("2", (36.7, 51.0)), ("1", (36.7, 58.62))],
    # 12 V input, bottom left; the +12V bus runs along y = 58.62
    "J1":  [("1", (6.0, 60.5)), ("2", (6.0, 65.58))],
    "C1":  [("1", (17.0, 58.62)), ("2", (17.0, 63.62))],
    "C16": [("1", (27.0, 58.62)), ("2", (27.0, 62.12))],
    "C2":  [("1", (32.0, 58.62)), ("2", (32.0, 63.62))],
    "D1":  [("1", (13.0, 69.0)), ("2", (28.24, 69.0))],
    # UI side, right of the module
    "R6":  [("1", (57.0, 8.0)), ("2", (64.62, 8.0))],
    "D3":  [("2", (67.5, 8.0)), ("1", (70.04, 8.0))],
    "J5":  [("1", (85.5, 10.5)), ("2", (85.5, 13.04))],
    "J4":  [("4", (85.5, 20.0)), ("1", (85.5, 27.62))],
    "R8":  [("2", (80.0, 21.0)), ("1", (80.0, 28.62))],
    "R7":  [("2", (77.0, 24.0)), ("1", (77.0, 31.62))],
    "SW2": [("1", (57.5, 32.0)), ("2", (57.5, 36.5)), ("1", (64.0, 32.0))],
    "SW1": [("1", (59.0, 41.0)), ("2", (59.0, 45.5)), ("1", (65.5, 41.0))],
    # 3.3 V: LM317T, bottom right, standing in its 16 x 16 mm pin-mount heatsink. The
    # heatsink (and its two pin holes) sits behind the tab, towards the bottom edge,
    # over x = 64..80, y = 55.2..71.2; only copper runs under it.
    "U3":  [("1", (69.46, 52.0)), ("3", (74.54, 52.0))],
    "D2":  [("2", (52.0, 69.0)), ("1", (62.16, 69.0))],
    "R17": [("1", (78.0, 48.9)), ("2", (70.38, 48.9))],
    "R18": [("1", (67.5, 48.9)), ("2", (59.88, 48.9))],
    "D10": [("2", (81.8, 43.25)), ("1", (81.8, 53.41))],
    "C10": [("1", (74.0, 45.0)), ("2", (76.0, 45.0))],
    "C4":  [("1", (85.0, 52.0)), ("2", (87.0, 52.0))],
    "C8":  [("1", (85.0, 57.0)), ("2", (85.0, 62.0))],
    "R15": [("2", (57.5, 29.5)), ("1", (65.12, 29.5))],
}
HOLES = [(3.5, 3.5), (86.5, 3.5), (87.0, 69.0), (3.5, 45.0)]
TITLE_AT = (46.0, 66.0)

# Skeleton tracks laid (and locked) before FreeRouting runs: net, width, polyline.
# A point is (x, y) in board mm, (ref, pad) for that pad's centre, or
# (ref, pad, "x", y) for that pad's x at the given y.
PREROUTE = [
    # --- module left edge ------------------------------------------------------
    ("I_SENSE", 0.3, [("U1", "5"), (23.68, 12.83), ("C13", "1"), ("R12", "1")]),
    ("M_IN1", 0.3, [("U1", "8"), (32.6, 16.64), (32.6, 39.08), ("U2", "5")]),
    ("M_IN2", 0.3, [("U1", "9"), (33.9, 17.91), (33.9, 41.62), ("U2", "7")]),
    ("Net-(U2-SENSE_A)", 0.8, [("U2", "1"), (30.0, 29.5), ("R12", "2")]),
    ("Net-(U2-SENSE_A)", 0.8, [(27.5, 29.5), ("R11", "1")]),
    # --- inside the module: VM_SENSE out at the bottom-left corner, 3V3 in at the right
    ("VM_SENSE", 0.3, [("U1", "4"), (36.7, 11.56), (36.7, 26.5), ("R1", "2")]),
    ("+3V3", 0.5, [("U1", "2"), (37.6, 9.02), (40.0, 11.4), (47.5, 11.4), (51.1, 15.0), (51.1, 43.25), (72.0, 43.25), ("U3", "2")]),
    # --- the L298 channel ------------------------------------------------------
    ("+3V3", 0.8, [("U1", "2"), (19.3, 9.02), (19.3, 2.5), ("R5", "1")]),     # wide: C7's Wi-Fi peaks
    ("Net-(U1-EN)", 0.3, [("U1", "3"), ("R5", "2", "x", 10.29), ("R5", "2")]),
    ("Net-(U1-EN)", 0.3, [("R5", "2"), (6.0, 12.1), ("SW3", "2")]),
    # --- module right edge: UART, I2C, buttons, LED ------------------------------
    ("LED", 0.3, [("U1", "37"), (55.0, 9.02), ("R6", "1")]),
    ("TXD0", 0.3, [("U1", "35"), (84.0, 11.56), ("J5", "1")]),
    ("RXD0", 0.3, [("U1", "34"), (83.5, 12.83), ("J5", "2")]),
    ("SCL", 0.3, [("U1", "33"), (80.0, 14.10), ("R8", "2"), (80.0, 22.54), ("J4", "3")]),
    ("SDA", 0.3, [("U1", "31"), (77.0, 16.64), ("R7", "2"), (77.0, 25.08), ("J4", "2")]),
    ("USER", 0.3, [("U1", "26"), (59.0, 22.99), (59.0, 41.0)]),     # the switch pads come in pairs:
    ("BOOT", 0.3, [("U1", "25"), (57.5, 24.26), (57.5, 32.0)]),     # name the pad by position
    ("+3V3", 0.5, [(72.0, 43.25), ("D10", "2"), (84.5, 43.25), (84.5, 33.5), (77.0, 33.5), ("R7", "1")]),
    ("+3V3", 0.5, [(80.0, 33.5), ("R8", "1")]),
    ("+3V3", 0.5, [(84.5, 33.5), (85.5, 32.5), ("J4", "1")]),
    ("+5V", 0.4, [("U2", "6"), (27.46, 40.35), (27.46, 44.16), ("U2", "9")]),
    ("+5V", 0.4, [("U2", "9"), ("C15", "1")]),
    ("/MOTOR_B", 0.8, [("U2", "3"), (27.46, 36.54), (27.46, 32.3), ("J3", "2", "x", 32.3), ("J3", "2")]),
    ("/MOTOR_A", 0.8, [("U2", "2"), (4.6, 35.27), ("J3", "1")]),
    # --- left column feeds -----------------------------------------------------
    ("+5V", 0.5, [("U4", "3"), (17.58, 40.35), ("U2", "6")]),
    ("+12V", 0.8, [("J1", "1"), (1.4, 60.5), (1.4, 37.81), ("U2", "4")]),
    ("+12V", 0.8, [("J1", "1"), (6.0, 58.62), (52.0, 58.62), ("D2", "2")]),
]
POWER_NETS = ("+12V", "/MOTOR_A", "/MOTOR_B", "Net-(U2-SENSE_A)")   # 0.8 mm
SUPPLY_NETS = ("+3V3", "+5V", "Net-(D10-K)")                          # 0.5 mm


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
        if ref in THT:
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
    ux, uy = PLACE["U1"][0], PLACE["U1"][1]
    ya = uy - 9.8                                   # antenna ends 9.8 mm above the module origin
    add_zone(board, None, pcbnew.F_Cu, [(ux - 14.5, 0.0), (ux + 14.5, 0.0), (ux + 14.5, ya), (ux - 14.5, ya)], rule_area=True)

    # silkscreen title
    t = pcbnew.PCB_TEXT(board)
    t.SetText("CURTAIN DRIVE rev C")
    t.SetPosition(mm(*TITLE_AT))
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

    A tact switch's two leg pairs are joined inside the switch; KiCad knows (jumper pad
    groups), FreeRouting does not and would try to join them with a track. For the route
    only, the second pad of each pair loses its net. Returns what restore_jumpered_pads()
    needs to put the netlist back.
    """
    locked = [t for t in board.GetTracks() if t.IsLocked()]

    def skeleton_ends_on(pad):
        return any(pad.HitTest(t.GetStart()) or pad.HitTest(t.GetEnd()) for t in locked)

    saved = []
    for fp in board.GetFootprints():
        if fp.GetReference().startswith("SW"):
            groups = {}
            for pad in fp.Pads():
                groups.setdefault(pad.GetNumber(), []).append(pad)
            for pads in groups.values():
                # keep the leg the skeleton lands on (else the first); the rest lose their net
                keep = next((pd for pd in pads if skeleton_ends_on(pd)), pads[0])
                for pad in pads:
                    if pad.m_Uuid != keep.m_Uuid:
                        saved.append((pad, pad.GetNetCode())); pad.SetNetCode(0)
    return saved


def restore_jumpered_pads(board, saved):
    for pad, code in saved:
        pad.SetNetCode(code)
    prune_jumper_runs(board, [pad for pad, _ in saved])


def prune_jumper_runs(board, dup_pads):
    """The DSN names pins by number, so FreeRouting still joins a switch's second leg
    of each pair with a track of its own. The switch joins them already: delete the
    routed tracks that reach a second leg, then any unlocked stub left dangling."""
    def touches(t, pad):
        sh = pad.GetEffectiveShape(pcbnew.F_Cu)
        return sh.Collide(t.GetEffectiveShape(pcbnew.F_Cu), 0)

    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and not t.IsLocked()]
    gone = [t for t in tracks if any(touches(t, pad) for pad in dup_pads)]
    while gone:
        ids = {t.m_Uuid.AsString() for t in gone}
        for t in gone:
            board.Remove(t)
        tracks = [t for t in tracks if t.m_Uuid.AsString() not in ids]
        alltr = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
        pads = [pd for fp in board.GetFootprints() for pd in fp.Pads()
                if all(pd.m_Uuid != d.m_Uuid for d in dup_pads)]
        gone = []
        for t in tracks:
            for end in (t.GetStart(), t.GetEnd()):
                linked = any(o.m_Uuid != t.m_Uuid and o.GetNetCode() == t.GetNetCode() and o.HitTest(end, 0)
                             for o in alltr)
                linked = linked or any(pd.GetNetCode() == t.GetNetCode() and pd.HitTest(end) for pd in pads)
                if not linked:
                    gone.append(t)
                    break


def check_dsn_one_layer(text):
    """The DSN must offer FreeRouting exactly one copper layer: with nowhere to put a
    via it cannot make one. (An injected (autoroute_settings (vias off) ...) scope, the
    FreeRouting 1.9 trick, makes 2.4 see zero routable pins, so it is not used.)"""
    import re
    layers = re.findall(r"\(layer\s+([^\s()]+)\s*\(type\s+(?:signal|power)\)", text)
    if layers != ["F.Cu"]:
        sys.exit(f"DSN has copper layers {layers}, expected only F.Cu")


def route():
    dsn = HW / "docs" / "curtain-drive-revC.dsn"
    ses = HW / "docs" / "curtain-drive-revC.ses"
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
    if REUSE_SES and ses.exists():
        print("reusing", ses)                  # same placement: skip the slow router run
    else:
        if ses.exists():
            ses.unlink()
        cmd = ["java", "-Djava.awt.headless=true", "-jar", str(JAR), "-de", str(dsn), "-do", str(ses),
               "-mp", "100", "-mt", "6", "--gui.enabled=false"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
        print(r.stdout[-600:])
    if not ses.exists():
        sys.exit("freerouting produced no .ses")
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


REUSE_SES = "--reuse-ses" in sys.argv     # re-import the last .ses (placement unchanged)
PLANE_GND = "--gnd-traces" not in sys.argv     # default: GND is a pour, not routed as tracks


if __name__ == "__main__":
    build()
    if "--route" in sys.argv:
        route()
