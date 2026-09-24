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

Board: 70 x 48 mm, 2 layers, all parts on the top side.
"""
import json
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
JAR = Path.home() / ".freerouting/freerouting-2.4.1.jar"

W, H = 70.0, 48.0          # board size, mm
X0, Y0 = 100.0, 100.0      # board origin in sheet coordinates
CORNER = 2.0

# -----------------------------------------------------------------------------
# Placement table: ref -> (x, y, rot)   board-relative mm, rot in degrees CCW
# -----------------------------------------------------------------------------
PLACE = {
    # left edge: DC jack (opens to -x), buttons, LED
    "J1":  (10.2, 33.0, 0),     # overhangs x=0 on purpose; silk exception in curtain-drive.kicad_dru
    "SW3": (17.0, 6.0, 0),      # RESET
    "SW2": (17.0, 14.0, 0),     # BOOT
    "SW1": (17.0, 22.0, 0),     # USER
    "D3":  (8.0, 14.0, 90),     # status LED
    "R6":  (8.0, 17.5, 90),
    "R5":  (23.5, 8.0, 90),     # EN pull-up
    "C9":  (23.5, 11.5, 90),    # EN delay
    "C10": (24.3, 14.5, 0),     # 3V3 decoupling (clear of SW2 courtyard)
    "C11": (24.3, 17.0, 0),
    # ESP32-C3 module, antenna towards the top edge
    "U1":  (40.0, 19.5, 0),
    # DRV8876 and its passives
    "U2":  (40.0, 33.0, 0),
    "C12": (45.5, 31.5, 90),    # CPH-CPL
    "C14": (45.5, 34.5, 90),    # VCP-VM
    "C15": (48.5, 33.0, 90),    # VM bypass
    "C16": (54.0, 33.0, 0),     # VM bulk 100uF
    "R13": (33.0, 30.0, 0),     # nFAULT pull-up
    "R9":  (33.0, 34.0, 0),     # VREF divider
    "R10": (33.0, 36.0, 0),
    "R11": (33.0, 38.0, 0),     # IPROPI 1k
    "R12": (36.0, 39.5, 0),     # ADC series
    "C13": (39.0, 39.5, 0),     # ADC filter
    "J3":  (42.0, 44.0, 0),     # motor
    # 12 V input chain along the bottom-left
    "F1":  (17.0, 44.0, 0),
    "D1":  (24.5, 44.0, 0),
    "C1":  (23.0, 31.0, 0),     # 220uF bulk
    "C2":  (31.5, 44.0, 0),
    "R1":  (24.0, 40.0, 0),     # VM sense
    "R2":  (27.0, 40.0, 0),
    "C3":  (30.0, 40.0, 0),
    # right edge: USB-C (opens to +x), ESD, CC, 5 V diode, buck
    "J2":  (65.5, 12.5, 90),
    "R3":  (58.0, 8.0, 90),
    "R4":  (58.0, 11.5, 90),
    "U4":  (58.0, 15.5, 0),
    "D5":  (58.0, 19.5, 0),
    "D2":  (58.0, 25.0, 90),    # 12 V -> VBUCK
    "U3":  (63.0, 22.0, 0),
    "C4":  (67.0, 21.0, 90),
    "C5":  (67.0, 25.1, 90),
    "C6":  (63.0, 25.5, 0),     # BST
    "L1":  (63.0, 30.5, 0),
    "C7":  (67.0, 35.0, 90),
    "C8":  (67.0, 38.5, 90),
    # encoder header on the bottom edge with its pull-ups
    "J4":  (52.0, 44.0, 0),
    "R7":  (56.0, 38.0, 0),
    "R8":  (59.0, 38.0, 0),
}
HOLES = [(3.5, 3.5), (66.5, 3.5), (3.5, 44.5), (66.5, 44.5)]
POWER_NETS = ("+12V", "/VBUCK", "Net-(F1-Pad1)", "Net-(J3-Pin_1)", "Net-(J3-Pin_2)", "Net-(U3-SW)", "+3V3")
THT_REFS = ("J1", "J2", "J3", "J4")


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
        ls.addLayer(pcbnew.B_Cu)
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


def build():
    comps, nets = load_netlist()
    board = pcbnew.BOARD()
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    ds.m_MinClearance = FromMM(0.15)
    ds.m_TrackMinWidth = FromMM(0.2)
    ds.m_ViasMinSize = FromMM(0.5)
    ds.m_MinThroughDrill = FromMM(0.2)
    ds.m_CopperEdgeClearance = FromMM(0.3)
    try:
        dnc = ds.m_NetSettings.GetDefaultNetclass()
        dnc.SetClearance(FromMM(0.15)); dnc.SetTrackWidth(FromMM(0.25))
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
        fp = pcbnew.FootprintLoad(str(FPLIB / f"{lib}.pretty"), name)
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
        if ref[0] in "RCDLF" or ref in ("U3", "U4"):
            fp.Reference().SetLayer(pcbnew.F_Fab)      # keep the silkscreen clean; refs stay on F.Fab
        if ref in THT_REFS:
            fp.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_THERMAL)   # hand-solderable THT pins
        board.Add(fp)
        fps[ref] = fp

    outline(board)
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
    add_zone(board, None, pcbnew.F_Cu, [(25.5, 0.0), (54.5, 0.0), (54.5, 12.5), (25.5, 12.5)], rule_area=True)

    # silkscreen title
    t = pcbnew.PCB_TEXT(board)
    t.SetText("CURTAIN DRIVE v0.1")
    t.SetPosition(mm(9.5, 27.5))
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(VECTOR2I(FromMM(0.9), FromMM(0.9)))
    t.SetTextThickness(FromMM(0.15))
    board.Add(t)

    board.SetFileName(str(PCB))
    pcbnew.SaveBoard(str(PCB), board)
    ensure_netclasses()
    print("wrote", PCB, "with", len(fps), "footprints,", len(nets), "nets")
    return board


def ensure_netclasses():
    """Power netclass in the .kicad_pro so the DSN export (and FreeRouting) use 0.6 mm tracks."""
    pro = HW / "curtain-drive.kicad_pro"
    d = json.loads(pro.read_text())
    ns = d.setdefault("net_settings", {})
    classes = [c for c in ns.get("classes", []) if c.get("name") != "Power"]
    default = next(c for c in classes if c.get("name") == "Default")
    default.update({"clearance": 0.15, "track_width": 0.25, "via_diameter": 0.7, "via_drill": 0.35})
    power = dict(default)
    power.update({"name": "Power", "track_width": 0.6, "clearance": 0.2, "via_diameter": 0.8, "via_drill": 0.4,
                  "priority": 0})
    ns["classes"] = classes + [power]
    ns["netclass_assignments"] = {n: "Power" for n in POWER_NETS}
    ns["netclass_patterns"] = [{"netclass": "Power", "pattern": n} for n in POWER_NETS]
    pro.write_text(json.dumps(d, indent=2))


def widen_power(board):
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetNetname() in POWER_NETS:
            t.SetWidth(FromMM(0.6))


def route():
    dsn = HW / "docs" / "curtain-drive.dsn"
    ses = HW / "docs" / "curtain-drive.ses"
    board = pcbnew.LoadBoard(str(PCB))
    ok = pcbnew.ExportSpecctraDSN(board, str(dsn))
    print("dsn export:", ok)
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
    # FreeRouting necks traces down to squeeze between fine-pitch pads; lift any such
    # stub back up to the board minimum so DRC's track_width rule holds.
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetWidth() < board.GetDesignSettings().m_TrackMinWidth:
            t.SetWidth(board.GetDesignSettings().m_TrackMinWidth)
    gnd = board.FindNet("GND")
    m = 0.5
    rect = [(m, m), (W - m, m), (W - m, H - m), (m, H - m)]
    add_zone(board, gnd, pcbnew.F_Cu, rect)
    add_zone(board, gnd, pcbnew.B_Cu, rect)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(str(PCB), board)
    print("routed + filled, saved", PCB)


if __name__ == "__main__":
    build()
    if "--route" in sys.argv:
        route()
