# FreeCAD script: simple body STEP models for footprints KiCad ships no 3D model for.
# Run: freecadcmd tools/make_body_models.py   (from hardware/)
# Boxes follow each footprint's F.Fab outline (footprint coords, mm; model Y = -footprint Y)
# and a datasheet body height. Good enough for enclosure fitting, not for rendering.
import os
import FreeCAD, Part

OUT = os.path.join(os.getcwd(), "lib", "3dmodels")
BODIES = {
    # file: (lib dir, xmin, xmax, ymin, ymax, height)
    "USB_C_Receptacle_HRO_TYPE-C-31-M-12.step": ("Connector_USB", -4.52, 4.52, -3.7, 3.7, 3.26),
    "BarrelJack_CUI_PJ-036AH-SMT_Horizontal.step": ("Connector_BarrelJack", -4.55, 4.55, -4.55, 10.05, 6.5),
    "JST_PH_B2B-PH-SM4-TB_1x02-1MP_P2.00mm_Vertical.step": ("Connector_JST", -4.03, 4.03, -4.3, 0.8, 6.0),
    "JST_PH_B4B-PH-SM4-TB_1x04-1MP_P2.00mm_Vertical.step": ("Connector_JST", -6.03, 6.03, -4.3, 0.8, 6.0),
    "Fuse_1812_4532Metric.step": ("Fuse", -2.3, 2.3, -1.65, 1.65, 1.5),
    # rev B: radial PTC, datasheet body 7.1 x 3.0 mm, 11.3 mm tall above the seating plane
    "Fuse_Bourns_MF-RG300.step": ("Fuse", -1.0, 6.1, -0.9, 2.1, 11.3),
}
for name, (lib, x0, x1, y0, y1, h) in BODIES.items():
    d = os.path.join(OUT, lib + ".3dshapes")
    os.makedirs(d, exist_ok=True)
    box = Part.makeBox(x1 - x0, y1 - y0, h, FreeCAD.Vector(x0, -y1, 0))
    box.exportStep(os.path.join(d, name))
    print("wrote", name)
