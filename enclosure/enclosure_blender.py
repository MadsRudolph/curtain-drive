# Curtain Drive enclosure -- native Blender build, v2 (80 x 62 mm single-sided SMD board)
#
# Run inside Blender (Scripting tab, or via the Blender MCP):
#     exec(open("/home/mads/Projects/curtain-drive/enclosure/enclosure_blender.py").read())
#     build_all()        # base, lid, servo, imported PCB model, materials
#     report()           # manifold / island / collision / cut-out checks
#     export_stls()      # stl/blender/curtain-drive-base.stl + -lid.stl (print orientation)
#     render()           # renders/blender_assembly.png
# 1 Blender unit = 1 mm (scene unit scale 0.001, lengths shown in mm).
#
# Box coordinates: x to the right, y from the FRONT wall (servo side) to the BACK wall
# (PCB / ESP32 antenna side), z up from the underside of the floor.
# Board coordinates are KiCad's: origin top-left, x right, y DOWN. The board's top edge
# (ky = 0, antenna end) faces the back wall. box_x = pcb_x0 + kx, box_y = pcb_y0 + pcb_l - ky.

import math
import os
import bpy
import bmesh
from mathutils import Vector, Matrix, Euler
from mathutils.bvhtree import BVHTree

# ---------------- PCB (hardware/curtain-drive.kicad_pcb, KiCad board coordinates) ----------------
pcb_glb = "/home/mads/Projects/curtain-drive/enclosure/pcb3d/curtain-drive-pcb.glb"
pcb_w, pcb_l, pcb_t = 80.0, 62.0, 1.6
pcb_holes = [(3.5, 3.5), (76.5, 3.5), (76.5, 58.5), (3.5, 24.0)]      # M2.5
standoff_h = 5.0
standoff_d = 6.0
standoff_hole_d = 2.2
part_h_max = 10.0            # C1 220 uF, 8 x 10 mm -- tallest part above the board top
# J1 barrel jack, left edge, mouth at kx = 0 facing -x, plug axis at ky = 52.5
jack_ky = 52.5
jack_body_h = 6.5            # body height above the board top
jack_axis_h = jack_body_h / 2    # ASSUMED plug-axis height above board (placeholder box model)
jack_open = (11.0, 11.0, 1.5)    # opening (y, z, corner r): room for the plug overmold
# J2 USB-C, right edge, mouth facing +x, centred at ky = 19.75, body 3.26 mm tall
usb_ky = 19.75
usb_body_h = 3.26
usb_open = (13.0, 7.5, 2.0)      # opening (y, z, corner r): room for the plug overmold
# J3 motor (JST-PH 2p, top entry, 6 mm) and J4 encoder (JST-PH 4p, top entry, 6 mm)
j3_kxy = (13.0, 35.5)
j4_kxy = (61.0, 39.75)          # body centre in the GLB (footprint origin is ky 41.5)
j3_slot = (8.0, 6.0, 1.5)        # left wall slot (y, z, r) -- passes a PHR-2 housing (5.95 x 4.5)
j4_slot = (12.0, 6.0, 1.5)       # right wall slot (y, z, r) -- passes a PHR-4 housing (9.95 x 4.5)
cable_slot_above = 7.0           # slot bottom this far above the board top (connector is 6 mm)
# lid holes over the buttons (PTS645, 4.3 mm tall) and the status LED
sw_kxy = [(14.0, 11.0), (35.5, 40.0), (60.0, 30.0)]     # SW3 RESET, SW2 BOOT, SW1 USER
led_kxy = (60.5, 15.0)                                  # D3
button_hole_d = 4.5
led_hole_d = 3.2

# ---------------- Servo: DM-S2000MD (datasheet values, NOT caliper-verified) ----------------
servo_l, servo_w, servo_h = 40.5, 20.2, 38.5
top_to_flange = 9.5
flange_t = 2.5
flange_span = 54.5
hole_dx, hole_dy = 49.0, 10.0
servo_screw_d = 2.6
shaft_from_end = 10.0
shaft_hole_d = 12.0

# ---------------- Box ----------------
wall, floor_t, lid_t = 2.0, 2.5, 2.0
lip_h = 2.0                  # locating lip below the lid plate
clr = 1.0
gap = 8.0                    # servo compartment to PCB (room for the side lid posts)
corner_r = 3.0
post_d, post_hole_d = 6.0, 2.2
ear_slot_w, ear_l = 4.5, 10.0
fuse = 1.0
head_margin = 2.0            # free space above the tallest PCB part AND below the lid lip
FN = 48                      # segments per full circle (OpenSCAD $fn)

# ---------------- lid details ----------------
lip_clr = 0.3                # clearance of lid lip notches around posts / servo
label_text = "CURTAIN DRIVE"
label_w = 51.58              # width of the OpenSCAD text(size=5) in Liberation Sans
label_depth = 0.6
label_font = "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"
explode_gap = 30.0           # lid lifted this far above the base in the scene

# ---------------- derived ----------------
inner_x = max(pcb_w, flange_span) + 2 * clr
inner_y = clr + servo_w + clr + gap + clr + pcb_l + clr
inner_z = max(servo_h + 1.5,
              standoff_h + pcb_t + part_h_max + head_margin + lip_h)
outer_x = inner_x + 2 * wall
outer_y = inner_y + 2 * wall
outer_z = floor_t + inner_z
servo_cx = wall + inner_x / 2
servo_cy = wall + clr + servo_w / 2
shaft_x = servo_cx - servo_l / 2 + shaft_from_end
gap_y = wall + clr + servo_w + clr + gap / 2
pcb_x0 = wall + clr + (inner_x - 2 * clr - pcb_w) / 2
pcb_y0 = wall + clr + servo_w + clr + gap + clr          # box y of the board edge ky = pcb_l
pcb_z0 = floor_t + standoff_h                            # underside of the board
board_top = pcb_z0 + pcb_t
_pi = wall + post_d / 2 - fuse / 2
POSTS = [(_pi, gap_y), (outer_x - _pi, gap_y), (_pi, _pi), (outer_x - _pi, _pi)]


def bx(kx):
    return pcb_x0 + kx


def by(ky):
    return pcb_y0 + pcb_l - ky


# ======================= helpers =======================
def get_coll(name, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def _obj_from_bm(name, bm, coll):
    me = bpy.data.meshes.new(name)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def _prism(bm, pts, z0, z1, axis='Z'):
    """Extrude a 2D polygon from z0 to z1 along `axis` into a closed prism.
    pts are (x,y) for axis Z, (y,z) for axis X and (x,z) for axis Y."""
    # snap to 1e-9 mm: points that are mathematically ON another face (e.g. an ear-corner
    # arc vertex landing exactly on the wall at x = 0) must be exactly on it, otherwise the
    # EXACT solver keeps a 1e-16 mm sliver that slicers see as a non-manifold edge.
    pts = [(round(a, 9) + 0.0, round(b, 9) + 0.0) for a, b in pts]
    if axis == 'Z':
        m = lambda a, b, w: (a, b, w)
    elif axis == 'X':
        m = lambda a, b, w: (w, a, b)
    else:
        m = lambda a, b, w: (a, w, b)
    bot = [bm.verts.new(m(a, b, z0)) for a, b in pts]
    top = [bm.verts.new(m(a, b, z1)) for a, b in pts]
    bm.faces.new(list(reversed(bot)))
    bm.faces.new(top)
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bot[i], bot[j], top[j], top[i]))


def rrect_pts(x, y, r, x0=0.0, y0=0.0):
    """offset(r) offset(-r) square([x,y]) -- rounded rectangle, CCW."""
    if r <= 0:
        return [(x0, y0), (x0 + x, y0), (x0 + x, y0 + y), (x0, y0 + y)]
    seg = FN // 4
    pts = []
    centres = [(x0 + x - r, y0 + r, -90), (x0 + x - r, y0 + y - r, 0),
               (x0 + r, y0 + y - r, 90), (x0 + r, y0 + r, 180)]
    for cx, cy, a0 in centres:
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    out = []
    for p in pts:
        if not out or (abs(p[0] - out[-1][0]) > 1e-6 or abs(p[1] - out[-1][1]) > 1e-6):
            out.append(p)
    if abs(out[0][0] - out[-1][0]) < 1e-6 and abs(out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


def rrect(name, coll, x, y, r, h, loc=(0, 0, 0)):
    bm = bmesh.new()
    _prism(bm, rrect_pts(x, y, r, loc[0], loc[1]), loc[2], loc[2] + h)
    return _obj_from_bm(name, bm, coll)


def wall_hole(name, coll, axis, centre, size, depth_range):
    """Rounded-rect opening through a wall. axis 'X' (side walls): centre=(y,z), size=(w_y,h_z,r).
    axis 'Y' (front/back walls): centre=(x,z), size=(w_x,h_z,r)."""
    w, h, r = size
    bm = bmesh.new()
    _prism(bm, rrect_pts(w, h, r, centre[0] - w / 2, centre[1] - h / 2), depth_range[0], depth_range[1], axis)
    return _obj_from_bm(name, bm, coll)


def cyl(name, coll, d, h, loc):
    r = d / 2
    pts = [(loc[0] + r * math.cos(2 * math.pi * i / FN), loc[1] + r * math.sin(2 * math.pi * i / FN))
           for i in range(FN)]
    bm = bmesh.new()
    _prism(bm, pts, loc[2], loc[2] + h)
    return _obj_from_bm(name, bm, coll)


def cube(name, coll, size, loc):
    return rrect(name, coll, size[0], size[1], 0, size[2], loc)


def boolean(target, cutter_coll, op):
    """Apply an EXACT boolean between target and every object in cutter_coll."""
    m = target.modifiers.new(name=op.title(), type='BOOLEAN')
    m.operation = op
    m.solver = 'EXACT'
    m.operand_type = 'COLLECTION'
    m.collection = cutter_coll
    m.use_self = False
    m.use_hole_tolerant = False
    bpy.context.view_layer.objects.active = target
    with bpy.context.temp_override(object=target, active_object=target):
        bpy.ops.object.modifier_apply(modifier=m.name)


def clear_coll(coll):
    for ob in list(coll.objects):
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if me is not None and me.users == 0:
            if isinstance(me, bpy.types.Mesh):
                bpy.data.meshes.remove(me)
            elif isinstance(me, bpy.types.Curve):
                bpy.data.curves.remove(me)


def mesh_report(ob):
    """Manifold / island check with bmesh, plus the check a slicer effectively does."""
    from collections import Counter
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    nonman_e = sum(1 for e in bm.edges if not e.is_manifold)
    nonman_v = sum(1 for v in bm.verts if not v.is_manifold)
    seen, islands = set(), 0
    for f in bm.faces:
        if f.index in seen:
            continue
        islands += 1
        stack = [f]
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            for e in cur.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
    vol = bm.calc_volume(signed=True)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
    key = lambda v: tuple(round(c, 4) for c in v.co)
    ec = Counter()
    for f in bm.faces:
        vs = f.verts
        for i in range(3):
            ec[tuple(sorted((key(vs[i]), key(vs[(i + 1) % 3]))))] += 1
    stl_bad_edges = sum(1 for c in ec.values() if c != 2)
    shortest = min(e.calc_length() for e in bm.edges)
    bm.free()
    bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    dims = [max(v[i] for v in bb) - min(v[i] for v in bb) for i in range(3)]
    return dict(name=ob.name, verts=len(ob.data.vertices), faces=len(ob.data.polygons),
                nonmanifold_edges=nonman_e, nonmanifold_verts=nonman_v, islands=islands,
                stl_bad_edges=stl_bad_edges, shortest_edge_mm=round(shortest, 5),
                volume_mm3=round(vol, 1), bbox_mm=[round(d, 3) for d in dims])


# ======================= scene setup =======================
def setup_scene():
    sc = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    us = sc.unit_settings
    us.system = 'METRIC'
    us.scale_length = 0.001
    us.length_unit = 'MILLIMETERS'
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for sp in area.spaces:
                if sp.type == 'VIEW_3D':
                    sp.clip_start = 0.1
                    sp.clip_end = 10000
    enc = get_coll("Enclosure")
    get_coll("Base", enc)
    get_coll("Lid", enc)
    ref = get_coll("Reference")
    get_coll("PCB model", ref)
    get_coll("_work")


def material(name, rgba, rough=0.5, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = rgba
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    m.diffuse_color = rgba
    return m


def assign(ob, mat):
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    ob.color = mat.diffuse_color


# ======================= base =======================
def build_base():
    work = get_coll("_work")
    ears = get_coll("_base_ears", work)
    adds = get_coll("_base_adds", work)
    cuts = get_coll("_base_cuts", work)
    inner = get_coll("_base_inner", work)
    for c in (ears, adds, cuts, inner):
        clear_coll(c)
    old = bpy.data.objects.get("Base")
    if old:
        bpy.data.objects.remove(old, do_unlink=True)

    base = rrect("Base", get_coll("Base"), outer_x, outer_y, corner_r, outer_z)
    # mounting ears fused onto the solid block before hollowing (identical result, cleaner mesh)
    for sx in (0, 1):
        rrect(f"ear{sx}", ears, ear_l + fuse, 24, 2, floor_t,
              (outer_x - fuse if sx else -ear_l, outer_y / 2 - 12, 0))
    boolean(base, ears, 'UNION')
    rrect("inner", inner, inner_x, inner_y, corner_r - wall, inner_z + 1, (wall, wall, floor_t))
    boolean(base, inner, 'DIFFERENCE')

    # --- unions ---
    for i, (hx, hy) in enumerate(pcb_holes):
        cyl(f"standoff{i}", adds, standoff_d, standoff_h, (bx(hx), by(hy), floor_t - 0.01))
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(f"boss{sx}{sy}", adds, 7, top_to_flange,
                (servo_cx + sx * hole_dx / 2, servo_cy + sy * hole_dy / 2, floor_t - 0.01))
    for sy in (-1, 1):
        cube(f"cradle{sy}", adds, (servo_l + 1, 2, top_to_flange),
             (servo_cx - servo_l / 2 - 0.5, servo_cy + sy * (servo_w / 2 + 1) - 1, floor_t - 0.01))
    for i, (px, py) in enumerate(POSTS):
        cyl(f"post{i}", adds, post_d, floor_t + inner_z - 0.01, (px, py, 0))
    boolean(base, adds, 'UNION')

    # --- cuts ---
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(f"pilot{sx}{sy}", cuts, servo_screw_d, top_to_flange,
                (servo_cx + sx * hole_dx / 2, servo_cy + sy * hole_dy / 2, floor_t + 1))
    cyl("shaft_hole", cuts, shaft_hole_d, floor_t + 2, (shaft_x, servo_cy, -1))
    for i, (hx, hy) in enumerate(pcb_holes):
        cyl(f"standoff_hole{i}", cuts, standoff_hole_d, standoff_h, (bx(hx), by(hy), floor_t + 1))
    for i, (px, py) in enumerate(POSTS):
        cyl(f"post_hole{i}", cuts, post_hole_d, 9, (px, py, outer_z - 8))
    # J1 barrel jack -- left wall
    wall_hole("jack", cuts, 'X', (by(jack_ky), board_top + jack_axis_h), jack_open, (-1, wall + 1))
    # J2 USB-C -- right wall
    wall_hole("usb", cuts, 'X', (by(usb_ky), board_top + usb_body_h / 2), usb_open,
              (outer_x - wall - 1, outer_x + 1))
    # J3 motor cable -- left wall, J4 encoder cable -- right wall
    zc = board_top + cable_slot_above + j3_slot[1] / 2
    wall_hole("j3_slot", cuts, 'X', (by(j3_kxy[1]), zc), j3_slot, (-1, wall + 1))
    zc = board_top + cable_slot_above + j4_slot[1] / 2
    wall_hole("j4_slot", cuts, 'X', (by(j4_kxy[1]), zc), j4_slot, (outer_x - wall - 1, outer_x + 1))
    # spare cable slot, front wall (servo side), as in the .scad
    cube("spare_slot", cuts, (8, wall + 2, 5), (servo_cx + servo_l / 2 + 2, -1, floor_t + 2))
    # mounting ear slots (hull of two d=4.5 circles 12 apart == stadium)
    for sx in (0, 1):
        cxs = outer_x + ear_l / 2 if sx else -ear_l / 2
        rrect(f"ear_slot{sx}", cuts, ear_slot_w, 12 + ear_slot_w, ear_slot_w / 2, floor_t + 2,
              (cxs - ear_slot_w / 2, outer_y / 2 - 6 - ear_slot_w / 2, -1))
    # vent slots, back wall (PCB side, as in the .scad)
    for i in range(5):
        cube(f"vent{i}", cuts, (2.5, wall + 2, 6), (wall + 8 + i * 6, outer_y - wall - 1, outer_z - 8))
    boolean(base, cuts, 'DIFFERENCE')
    return base


# ======================= lid =======================
# Modelled in its ASSEMBLED pose, in box x/y coordinates: plate z 0..lid_t with the
# outside face on top, lip hanging down. Exported for printing rotated 180 deg about Y
# (outside face on the bed) -- a real rotation, not a mirror.
def make_label(coll):
    fnt = bpy.data.fonts.load(label_font, check_existing=True)
    cu = bpy.data.curves.new("label_curve", 'FONT')
    cu.body = label_text
    cu.font = fnt
    cu.size = 5
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    cu.extrude = 0.5
    cu.resolution_u = 6
    tmp = bpy.data.objects.new("label_tmp", cu)
    coll.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.curves.remove(cu)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    s = label_w / (max(xs) - min(xs))
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    for v in bm.verts:
        v.co.x = (v.co.x - cx) * s + outer_x / 2
        v.co.y = (v.co.y - cy) * s + servo_cy          # over the servo, clear of all holes
        v.co.z = v.co.z + 0.5 + lid_t - label_depth
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("label", me)
    coll.objects.link(ob)
    return ob


def build_lid():
    work = get_coll("_work")
    adds = get_coll("_lid_adds", work)
    cuts = get_coll("_lid_cuts", work)
    lipcut = get_coll("_lid_lipcut", work)
    notch = get_coll("_lid_notch", work)
    for c in (adds, cuts, lipcut, notch):
        clear_coll(c)
    old = bpy.data.objects.get("Lid")
    if old:
        bpy.data.objects.remove(old, do_unlink=True)

    lid = rrect("Lid", get_coll("Lid"), outer_x, outer_y, corner_r, lid_t)
    lip = rrect("lip", adds, inner_x - 0.6, inner_y - 0.6, corner_r - wall, lip_h,
                (wall + 0.3, wall + 0.3, -lip_h + 0.01))
    rrect("lip_in", lipcut, inner_x - 0.6 - 2 * wall, inner_y - 0.6 - 2 * wall, 1, lip_h + 2,
          (2 * wall + 0.3, 2 * wall + 0.3, -lip_h - 1))
    # notch the lip where it would hit the 4 lid posts and the top of the servo (front wall)
    for i, (px, py) in enumerate(POSTS):
        cyl(f"notch_post{i}", notch, post_d + 2 * lip_clr, lip_h + 1, (px, py, -lip_h - 0.5))
    cube("notch_servo", notch, (servo_l + 2 * lip_clr, wall + 2, lip_h + 1),
         (servo_cx - servo_l / 2 - lip_clr, wall - 0.7, -lip_h - 0.5))
    boolean(lip, lipcut, 'DIFFERENCE')
    boolean(lip, notch, 'DIFFERENCE')
    boolean(lid, adds, 'UNION')

    for i, (px, py) in enumerate(POSTS):
        cyl(f"screw{i}", cuts, 2.8, lid_t + lip_h + 2, (px, py, -lip_h - 1))
        cyl(f"recess{i}", cuts, 5.5, 1.2, (px, py, lid_t - 1.2 + 0.01))
    for i, (sx, sy) in enumerate(sw_kxy):
        cyl(f"button{i}", cuts, button_hole_d, lid_t + lip_h + 2, (bx(sx), by(sy), -lip_h - 1))
    cyl("led", cuts, led_hole_d, lid_t + lip_h + 2, (bx(led_kxy[0]), by(led_kxy[1]), -lip_h - 1))
    make_label(cuts)
    boolean(lid, cuts, 'DIFFERENCE')
    lid.location.z = outer_z + explode_gap
    return lid


# ======================= reference parts =======================
def import_pcb():
    """Import the KiCad GLB. glTF is Y-up metres; Blender's importer converts to Z-up and to
    the scene unit (mm here), so the board comes in as 80 x 62 mm, top-left corner at the
    origin, KiCad +y -> Blender -y, components on +z, substrate z 0..1.51."""
    coll = get_coll("PCB model", get_coll("Reference"))
    for ob in list(coll.all_objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    lc = bpy.context.view_layer.layer_collection.children["Reference"].children["PCB model"]
    bpy.context.view_layer.active_layer_collection = lc
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=pcb_glb)
    new = [o for o in bpy.data.objects if o not in before]
    roots = [o for o in new if o.parent is None]
    assert len(roots) == 1, roots
    root = roots[0]
    root.name = "PCB"
    # board edge ky = 0 (antenna end) towards the back wall; lowest point (bottom mask,
    # z = -0.05) resting on the standoff tops
    root.location = (pcb_x0, pcb_y0 + pcb_l, pcb_z0 + 0.05)
    bpy.context.view_layer.update()
    return root


def build_servo():
    ref = get_coll("Reference")
    old = bpy.data.objects.get("Servo")
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    servo = cube("Servo", ref, (servo_l, servo_w, servo_h),
                 (servo_cx - servo_l / 2, servo_cy - servo_w / 2, floor_t))
    sv_add = get_coll("_servo_adds", get_coll("_work"))
    clear_coll(sv_add)
    cube("flange", sv_add, (flange_span, servo_w, flange_t),
         (servo_cx - flange_span / 2, servo_cy - servo_w / 2, floor_t + top_to_flange))
    cyl("shaft", sv_add, 6, floor_t + 6 + 0.5, (shaft_x, servo_cy, -6))
    boolean(servo, sv_add, 'UNION')
    return servo


def apply_materials():
    assign(bpy.data.objects["Base"], material("Base PLA (warm white)", (0.78, 0.76, 0.72, 1), rough=0.45))
    assign(bpy.data.objects["Lid"], material("Lid PLA (teal)", (0.10, 0.36, 0.40, 1), rough=0.4))
    assign(bpy.data.objects["Servo"], material("Servo blue", (0.10, 0.25, 0.65, 1), rough=0.5))


def cleanup_work():
    work = bpy.data.collections.get("_work")
    if not work:
        return

    def rec(c):
        for ch in list(c.children):
            rec(ch)
        clear_coll(c)
        bpy.data.collections.remove(c)
    rec(work)


def build_all():
    setup_scene()
    build_base()
    build_lid()
    build_servo()
    import_pcb()
    apply_materials()
    cleanup_work()
    return [mesh_report(bpy.data.objects[n]) for n in ("Base", "Lid")]


# ======================= checks =======================
def _bvh(ob, extra=Matrix()):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(extra @ ob.matrix_world)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


def inter_vol(a, b):
    """Volume of the EXACT boolean intersection of two closed meshes (world space)."""
    c = a.copy()
    c.data = a.data.copy()
    bpy.context.scene.collection.objects.link(c)
    tmpc = get_coll("_tmp_int")
    clear_coll(tmpc)
    d = b.copy()
    d.data = b.data.copy()
    tmpc.objects.link(d)
    boolean(c, tmpc, 'INTERSECT')
    bm = bmesh.new()
    bm.from_mesh(c.data)
    bm.transform(c.matrix_world)
    v = abs(bm.calc_volume())
    bm.free()
    me = c.data
    bpy.data.objects.remove(c, do_unlink=True)
    bpy.data.meshes.remove(me)
    clear_coll(tmpc)
    bpy.data.collections.remove(tmpc)
    return round(v, 3)


def pcb_parts():
    root = bpy.data.objects["PCB"]
    return [o for o in root.children_recursive if o.type == 'MESH' and len(o.data.polygons)]


def part_of(o):
    """Name of the KiCad reference (J1, C1, ...) an imported mesh belongs to."""
    p = o
    while p.parent and p.parent.name != "PCB":
        p = p.parent
    return p.name


def _inside(pt, bvh_tree):
    # odd number of ray hits along +z == inside a closed solid
    n, o, d = 0, Vector(pt), Vector((0.0123, 0.0071, 1)).normalized()
    while True:
        hit = bvh_tree.ray_cast(o, d)
        if hit[0] is None:
            return n % 2 == 1
        n += 1
        o = hit[0] + d * 1e-4


def collisions(lid_closed=True):
    """Surface intersections (BVH overlap) plus 'inside' tests between the assembled parts."""
    base, lid, servo = (bpy.data.objects[n] for n in ("Base", "Lid", "Servo"))
    lid_shift = Matrix.Translation((0, 0, outer_z - lid.location.z)) if lid_closed else Matrix()
    T = {"Base": _bvh(base), "Lid(closed)": _bvh(lid, lid_shift), "Servo": _bvh(servo)}
    out = {}
    # closed solids: EXACT intersection volume (faces that merely touch give 0)
    z0 = lid.location.z
    if lid_closed:
        lid.location.z = outer_z
    for a, b in ((lid, base), (lid, servo), (servo, base)):
        out[f"{a.name}{'(closed)' if a is lid and lid_closed else ''} x {b.name} [mm3]"] = inter_vol(a, b)
    lid.location.z = z0
    hits = {}
    for o in pcb_parts():
        t = _bvh(o)
        for n in ("Base", "Lid(closed)", "Servo"):
            k = len(t.overlap(T[n]))
            # also catch a part sitting wholly inside a solid
            c = o.matrix_world @ (sum((Vector(v) for v in o.bound_box), Vector()) / 8)
            if k or _inside(c, T[n]):
                hits.setdefault(n, set()).add(part_of(o))
    for n in ("Base", "Lid(closed)", "Servo"):
        out[f"PCB model x {n}"] = sorted(hits.get(n, []))
    return out


def part_bbox(ref):
    root = bpy.data.objects[ref]
    mn, mx = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for d in [root] + list(root.children_recursive):
        if d.type == 'MESH':
            for c in d.bound_box:
                w = d.matrix_world @ Vector(c)
                mn = Vector(map(min, mn, w))
                mx = Vector(map(max, mx, w))
    return mn, mx


def cutout_check():
    """Where each wall opening sits relative to the IMPORTED connector body."""
    rows = []
    specs = [("J1 barrel", "J1", (by(jack_ky), board_top + jack_axis_h), jack_open, "left", 0.0),
             ("J2 USB-C", "J2", (by(usb_ky), board_top + usb_body_h / 2), usb_open, "right", outer_x),
             ("J3 motor", "J3", (by(j3_kxy[1]), board_top + cable_slot_above + j3_slot[1] / 2), j3_slot, "left", 0.0),
             ("J4 encoder", "J4", (by(j4_kxy[1]), board_top + cable_slot_above + j4_slot[1] / 2), j4_slot, "right", outer_x)]
    for label, ref, (yc, zc), (w, h, r), side, face in specs:
        mn, mx = part_bbox(ref)
        oy0, oy1, oz0, oz1 = yc - w / 2, yc + w / 2, zc - h / 2, zc + h / 2
        mouth_x = mn.x if side == "left" else mx.x
        inner_face = wall if side == "left" else outer_x - wall
        rows.append(dict(part=label, body_y=(round(mn.y, 2), round(mx.y, 2)), body_z=(round(mn.z, 2), round(mx.z, 2)),
                         open_y=(round(oy0, 2), round(oy1, 2)), open_z=(round(oz0, 2), round(oz1, 2)),
                         margin_y=(round(mn.y - oy0, 2), round(oy1 - mx.y, 2)),
                         margin_z=(round(mn.z - oz0, 2), round(oz1 - mx.z, 2)),
                         body_centre_offset_y=round((mn.y + mx.y) / 2 - yc, 3),
                         body_to_inner_wall=round(abs(mouth_x - inner_face), 2),
                         body_to_outer_face=round(abs(mouth_x - face), 2)))
    return rows


def report():
    return dict(meshes=[mesh_report(bpy.data.objects[n]) for n in ("Base", "Lid")],
                collisions=collisions(), cutouts=cutout_check(),
                outer_box=(outer_x, outer_y, outer_z, outer_z + lid_t))


# ======================= export =======================
STL_DIR = "/home/mads/Projects/curtain-drive/enclosure/stl/blender"


def _export_one(ob, path):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, global_scale=1.0,
                          use_scene_unit=False, ascii_format=False, apply_modifiers=True,
                          forward_axis='Y', up_axis='Z')


def export_stls(stl_dir=STL_DIR):
    """Base as modelled (floor on the bed). Lid rotated 180 deg about Y so its outside
    face lies on the bed and the lip points up -- a rigid rotation, so the printed lid
    is exactly the part shown on the model once flipped back over."""
    os.makedirs(stl_dir, exist_ok=True)
    _export_one(bpy.data.objects["Base"], os.path.join(stl_dir, "curtain-drive-base.stl"))
    lid = bpy.data.objects["Lid"]
    pr = lid.copy()
    pr.data = lid.data.copy()
    pr.name = "Lid_print"
    bpy.context.scene.collection.objects.link(pr)
    pr.matrix_world = Matrix.Translation((outer_x, 0, lid_t)) @ Matrix.Rotation(math.pi, 4, 'Y')
    _export_one(pr, os.path.join(stl_dir, "curtain-drive-lid.stl"))
    me = pr.data
    bpy.data.objects.remove(pr, do_unlink=True)
    bpy.data.meshes.remove(me)


# ======================= render =======================
RENDER_PATH = "/home/mads/Projects/curtain-drive/enclosure/renders/blender_assembly.png"


def setup_stage():
    sc = bpy.context.scene
    stage = get_coll("Stage")
    clear_coll(stage)
    for l in list(bpy.data.lights):
        if l.users == 0:
            bpy.data.lights.remove(l)
    cd = bpy.data.cameras.get("Camera") or bpy.data.cameras.new("Camera")
    cam = bpy.data.objects.new("Camera", cd)
    stage.objects.link(cam)
    sc.camera = cam
    cd.clip_start = 1
    cd.clip_end = 5000

    def sun(name, energy, rot, ang):
        ld = bpy.data.lights.new(name, 'SUN')
        ld.energy = energy
        ld.angle = math.radians(ang)
        ob = bpy.data.objects.new(name, ld)
        stage.objects.link(ob)
        ob.rotation_euler = Euler([math.radians(a) for a in rot])
    sun("Key", 4.0, (40, 0, -40), 4)
    sun("Fill", 1.2, (60, 0, 110), 10)
    me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=400)
    bm.to_mesh(me)
    bm.free()
    fl = bpy.data.objects.new("Floor", me)
    stage.objects.link(fl)
    fl.location = (outer_x / 2, outer_y / 2, -6.5)
    me.materials.append(material("Floor", (0.12, 0.125, 0.135, 1), rough=0.8))
    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.05, 0.055, 0.065, 1)
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1200
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = 'AgX'
    return cam


def aim(cam, loc, target, lens=50):
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens


def render(path=RENDER_PATH, loc=None, target=None, lens=42):
    sc = bpy.context.scene
    cam = sc.camera if (sc.camera and sc.camera.name in bpy.data.objects) else setup_stage()
    aim(cam, loc or (-100, -115, 215), target or (outer_x / 2, outer_y / 2 + 8, 18), lens)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


RENDER_DIR = os.path.dirname(RENDER_PATH)


def render_views(out_dir=RENDER_DIR):
    """blender_assembly.png (exploded), blender_open.png (no lid, ~45 deg from above),
    blender_closed.png (lid on, barrel-jack / left wall in view). 1600 x 1200."""
    setup_stage()
    lid = bpy.data.objects["Lid"]
    z_expl = outer_z + explode_gap
    paths = []
    lid.location.z = z_expl
    lid.hide_render = False
    paths.append(render(os.path.join(out_dir, "blender_assembly.png")))
    lid.hide_render = True
    paths.append(render(os.path.join(out_dir, "blender_open.png"),
                        loc=(outer_x / 2 - 95, outer_y / 2 - 120, 175),
                        target=(outer_x / 2, outer_y / 2 + 4, 10), lens=42))
    lid.hide_render = False
    lid.location.z = outer_z
    paths.append(render(os.path.join(out_dir, "blender_closed.png"),
                        loc=(-150, outer_y / 2 - 95, 95),
                        target=(outer_x / 2 - 8, outer_y / 2 + 4, 16), lens=45))
    lid.location.z = z_expl
    return paths
