#!/usr/bin/env python3
"""xTool F1 Ultra laser files for a single-sided (F.Cu) board.

    python3 tools/laser_export.py hardware-revB/curtain-drive-revB.kicad_pcb

Writes into <board dir>/production/laser/:
  <name>-ablate.dxf   the copper to REMOVE: board outline minus every pad, track and
                      poured zone on F.Cu, as closed R12 POLYLINEs on layer ABLATE.
                      Nested contours fill even-odd, so in XCS: import, Make compound,
                      check that removed copper is black and kept copper white, then run
                      the "Traces" preset (fill engrave, 100 %, 600 mm/s, 10 passes,
                      240 lines/cm, one-way, 30 kHz, cross hatch). Every hole is etched
                      out of its pad at drill size, as a mark to drill on
                      (--no-drill-marks leaves the pads solid).
  <name>-cut.dxf      board outline and every drilled/slotted hole as closed polylines
                      on layer CUT, for the "Cut/Drill" preset (vector, 100 mm/s, 160 passes).
  <name>-mask.dxf     solder-mask openings (pads) on layer MASK_OPEN, for the
                      "RemoveSolderMask" preset. Only needed on a solder-mask board. The
                      board outline is on layer REFERENCE, for alignment only: delete it
                      before running.
  <name>-preview.png  the ablate negative rendered black-on-white, to eyeball before a run.

All three DXFs share one frame: millimetres, origin at the board's top-left corner, and
each file's extents equal the board outline, so they import into XCS aligned. The copper
is F.Cu seen from above, so nothing is mirrored: etch with the copper side up, as drawn.

The file format follows ~/Projects/esp32-node/make_coupon.py (the coupon that proved
0.15 mm gaps and traces on this machine).
"""
import subprocess
import sys
from pathlib import Path

import pcbnew

pcbnew.SwigPyIterator.next = pcbnew.SwigPyIterator.__next__   # pcbnew on Python 3.14

MAX_ERR = pcbnew.FromMM(0.002)     # arc-to-segment error, far below the laser's line pitch
INSIDE = pcbnew.ERROR_INSIDE
DRILL_MARKS = "--no-drill-marks" not in sys.argv


def copper(board):
    """Every F.Cu shape on the board, merged into one polygon set."""
    cu = pcbnew.SHAPE_POLY_SET()
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            # NPTH (mounting holes, USB-C pegs) carry no copper; the cut pass makes them
            if pad.IsOnLayer(pcbnew.F_Cu) and pad.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                pad.TransformShapeToPolygon(cu, pcbnew.F_Cu, 0, MAX_ERR, INSIDE)
        for item in fp.GraphicalItems():
            if item.GetLayer() == pcbnew.F_Cu:
                item.TransformShapeToPolygon(cu, pcbnew.F_Cu, 0, MAX_ERR, INSIDE)
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA" and t.GetLayer() == pcbnew.F_Cu:
            t.TransformShapeToPolygon(cu, pcbnew.F_Cu, 0, MAX_ERR, INSIDE)
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.F_Cu:
            d.TransformShapeToPolygon(cu, pcbnew.F_Cu, 0, MAX_ERR, INSIDE)
    for z in board.Zones():
        if not z.GetIsRuleArea() and z.IsOnLayer(pcbnew.F_Cu):
            cu.Append(z.GetFilledPolysList(pcbnew.F_Cu))
    cu.Simplify()
    return cu


def mask_openings(board):
    m = pcbnew.SHAPE_POLY_SET()
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.IsOnLayer(pcbnew.F_Mask):
                pad.TransformShapeToPolygon(m, pcbnew.F_Mask, pad.GetSolderMaskExpansion(pcbnew.F_Mask),
                                            MAX_ERR, INSIDE)
    m.Simplify()
    return m


def holes(board):
    h = pcbnew.SHAPE_POLY_SET()
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetDrillSizeX() > 0:
                pad.TransformHoleToPolygon(h, 0, MAX_ERR, INSIDE)
    h.Simplify()
    return h


def contours(ps):
    """Every closed contour (outlines and their holes) as lists of (x, y) in mm."""
    out = []
    for i in range(ps.OutlineCount()):
        chains = [ps.Outline(i)] + [ps.Hole(i, j) for j in range(ps.HoleCount(i))]
        for c in chains:
            out.append([(pcbnew.ToMM(c.CPoint(k).x), pcbnew.ToMM(c.CPoint(k).y))
                        for k in range(c.PointCount())])
    return out


def dxf(path, layers, x0, y0, h):
    """Minimal R12 ASCII DXF, units mm, every contour a closed POLYLINE (as make_coupon.py).
    Board coordinates are shifted to the top-left corner and Y is flipped (DXF is y-up)."""
    o = ["0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
         "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER", "70", str(len(layers))]
    for i, name in enumerate(layers):
        o += ["0", "LAYER", "2", name, "70", "0", "62", str(i + 1), "6", "CONTINUOUS"]
    o += ["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    n = 0
    for name, polys in layers.items():
        for pts in polys:
            o += ["0", "POLYLINE", "8", name, "66", "1", "70", "1"]
            for x, y in pts:
                o += ["0", "VERTEX", "8", name, "10", f"{x - x0:.4f}", "20", f"{h - (y - y0):.4f}"]
            o += ["0", "SEQEND", "8", name]
            n += 1
    o += ["0", "ENDSEC", "0", "EOF"]
    Path(path).write_text("\n".join(o) + "\n")
    return n


def svg(path, polys, x0, y0, w, h):
    d = "".join("M" + "L".join(f"{x - x0:.4f},{y - y0:.4f}" for x, y in p) + "Z" for p in polys)
    Path(path).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w * 20:.0f}" height="{h * 20:.0f}" '
        f'viewBox="0 0 {w} {h}"><rect width="{w}" height="{h}" fill="#fff"/>'
        f'<path d="{d}" fill="#000" fill-rule="evenodd"/></svg>\n')


def main(pcb):
    pcb = Path(pcb).resolve()
    board = pcbnew.LoadBoard(str(pcb))
    if any(t.GetClass() == "PCB_VIA" for t in board.GetTracks()):
        sys.exit("board has vias: not a single-sided laser board")
    if any(t.GetLayer() != pcbnew.F_Cu for t in board.GetTracks()):
        sys.exit("board has copper off F.Cu")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())      # never export a stale fill

    outline = pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(outline, False):
        sys.exit("board outline is not closed")
    bb = outline.BBox()
    x0, y0 = pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY())
    w, h = pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())

    hl = holes(board)
    cu = copper(board)
    if DRILL_MARKS:
        cu.BooleanSubtract(hl)             # etch every hole inside its pad: a centre mark to drill on
    ablate = outline.CloneDropTriangulation()
    ablate.BooleanSubtract(cu)
    ablate.Simplify()
    cut = [contours(outline)[0]] + contours(hl)

    out = pcb.parent / "production" / "laser"
    out.mkdir(parents=True, exist_ok=True)
    stem = pcb.stem
    n_ab = dxf(out / f"{stem}-ablate.dxf", {"ABLATE": contours(ablate)}, x0, y0, h)
    n_cut = dxf(out / f"{stem}-cut.dxf", {"CUT": cut}, x0, y0, h)
    # the openings alone don't span the board, so the outline rides along on REFERENCE to
    # align the file; delete that layer in XCS before running
    n_mask = dxf(out / f"{stem}-mask.dxf", {"MASK_OPEN": contours(mask_openings(board)),
                                             "REFERENCE": [contours(outline)[0]]}, x0, y0, h) - 1
    svg(out / f"{stem}-preview.svg", contours(ablate), x0, y0, w, h)
    subprocess.run(["rsvg-convert", "-o", str(out / f"{stem}-preview.png"), str(out / f"{stem}-preview.svg")],
                   check=True)
    (out / f"{stem}-preview.svg").unlink()
    area = pcbnew.ToMM(pcbnew.ToMM(ablate.Area()))
    print(f"{stem}: {w:.1f} x {h:.1f} mm, ablate {n_ab} contours ({area:.0f} mm² of copper removed, "
          f"{100 * area / (w * h):.0f} % of the board), cut {n_cut} contours ({n_cut - 1} holes), "
          f"mask {n_mask} openings -> {out}")


if __name__ == "__main__":
    for p in [a for a in sys.argv[1:] if not a.startswith("--")] or sys.exit(__doc__):
        main(p)
