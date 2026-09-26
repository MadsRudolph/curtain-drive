"""Curtain drive product showcase: room, track, curtains and the real enclosure meshes.

Illustrative renders only. The product is not built yet.

Run from /home/mads/Projects/curtain-drive/enclosure:
    blender -b --python showcase/showcase.py -- stills            # hero, drive-closeup, inside + .blend
    blender -b --python showcase/showcase.py -- stills --preview  # half size, few samples
    blender -b --python showcase/showcase.py -- gif room          # frames for curtains-motion.gif
    blender -b --python showcase/showcase.py -- gif drive         # frames for drive-motion.gif
Options: --only hero,inside   --frames 1,40,80   --samples N

Units: metres in the room. The drive, track, belt, carriers and pulleys are modelled in
millimetres in the enclosure's own box coordinates and sit under one empty scaled 0.001,
exactly like the surround-mount showcase. Box coordinates: x along the track (to the
right seen from the room), y from the box front towards the window wall, z up from the
underside of the box floor.
"""
import bpy, bmesh, math, sys, random
from pathlib import Path
from mathutils import Vector, Matrix
import numpy as np

HERE = Path(__file__).resolve().parent
ENCL = HERE.parent / 'enclosure.blend'
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
PREVIEW = '--preview' in argv
MODE = argv[0] if argv and not argv[0].startswith('--') else 'stills'


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


# ----------------------------------------------------------------------------------------
# Enclosure numbers (copied from enclosure_blender.py, all mm, box coordinates)
# ----------------------------------------------------------------------------------------
OUTER_X, OUTER_Y, OUTER_Z, LID_T = 86.0, 98.2, 42.5, 2.0
SERVO_CX, SERVO_CY = 43.0, 13.1
SERVO_L, SERVO_W, SERVO_H = 40.5, 20.2, 38.5
FLOOR_T, TOP_TO_FLANGE, FLANGE_T, FLANGE_SPAN = 2.5, 9.5, 2.5, 54.5
HOLE_DX, HOLE_DY = 49.0, 10.0
SHAFT_X, SHAFT_Y = 32.75, 13.1
LED_XY = (63.5, 80.2)
JACK = (0.0, 42.7, 12.35)            # barrel-jack opening centre, left wall
POSTS = [(4.5, 28.2), (81.5, 28.2), (4.5, 4.5), (81.5, 4.5)]
EAR_Y = OUTER_Y / 2

# ----------------------------------------------------------------------------------------
# Room placement (metres) and the track system (mm in box coordinates)
# ----------------------------------------------------------------------------------------
CEIL = 2.60                          # ceiling height
LID_GAP = 60.0                       # lid top to ceiling, mm
PLATE_T = 5.0                        # wall bracket plate thickness
WALL_Y_LOCAL = OUTER_Y + PLATE_T     # window wall face in box coordinates
PULLEY_WX = -1.36                    # world x of the drive pulley axis
HW_ORIGIN = Vector((PULLEY_WX - SHAFT_X / 1000, -WALL_Y_LOCAL / 1000, CEIL - (OUTER_Z + LID_T + LID_GAP) / 1000))
CEIL_LOCAL = OUTER_Z + LID_T + LID_GAP

YC = SHAFT_Y                         # track / belt centre line
X_P = SHAFT_X                        # drive pulley axis
X_I = (1.36 - HW_ORIGIN.x) * 1000    # idler axis (world x = +1.36)
TRACK_Z0, TRACK_Z1 = -28.0, -2.0     # track bottom / top
TRACK_X0, TRACK_X1 = X_P + 45.0, X_I - 45.0
BELT_Z0, BELT_Z1 = -13.0, -7.0       # 6 mm GT2 belt
R_PITCH = 20.0 / math.pi             # GT2 20T pitch radius, 2 mm pitch
R_BASE = 6.85                        # belt back-face (tooth root) radius around a pulley
R_TIP = 6.1                          # pulley outside radius == belt tooth tips
BELT_BACK = 0.63
TOOTH_H = 0.75
GLIDER_HALF = 6.0                    # glider bodies are 12 mm long; they touch when stacked
N_WAVES = 12                         # ripple-fold waves per panel
FABRIC_W = 2.64                      # flat fabric width per panel, metres
X0_LEFT = TRACK_X0 + 20.0            # first glider (fixed to the end stop), left panel
X0_RIGHT = TRACK_X1 - 20.0
SPAN_OPEN = N_WAVES * 12.0           # fully stacked panel, gliders touching
EDGE_CLOSED_L = (-0.005 - HW_ORIGIN.x) * 1000
SPAN_CLOSED = EDGE_CLOSED_L - X0_LEFT
TRAVEL = SPAN_CLOSED - SPAN_OPEN     # belt travel, mm
HOOK_Z = -37.0                       # fabric top edge, mm


def W(p):
    """box-coordinate mm -> world metres"""
    return HW_ORIGIN + Vector(p) / 1000.0


# ----------------------------------------------------------------------------------------
# Scene bootstrap: open the enclosure file read-only, keep Base, Lid, PCB
# ----------------------------------------------------------------------------------------
bpy.ops.wm.open_mainfile(filepath=str(ENCL))
old_scene = bpy.context.scene
for o in list(bpy.data.objects):
    if o.name in ('Servo', 'Floor', 'Camera', 'Key', 'Fill') or (o.users_collection and o.users_collection[0].name == 'Stage'):
        bpy.data.objects.remove(o, do_unlink=True)
SRC_BASE, SRC_LID, SRC_PCB = bpy.data.objects['Base'], bpy.data.objects['Lid'], bpy.data.objects['PCB']
scene = bpy.data.scenes.new('Room')
bpy.context.window.scene = scene
bpy.data.scenes.remove(old_scene)
for c in list(bpy.data.collections):
    if not c.users or c.name in ('Stage',):
        pass
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0

random.seed(7)


# ----------------------------------------------------------------------------------------
# Materials
# ----------------------------------------------------------------------------------------
def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree.nodes, m.node_tree.links, m.node_tree.nodes['Principled BSDF']


def mat(name, color, rough=.5, metal=0., bump=None, bump_strength=.15, spec=.5, sss=0.):
    m, n, l, p = new_mat(name)
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Metallic'].default_value = metal
    p.inputs['Specular IOR Level'].default_value = spec
    if sss:
        p.inputs['Subsurface Weight'].default_value = sss
        p.inputs['Subsurface Scale'].default_value = .002
    if bump:
        t = n.new('ShaderNodeTexNoise'); t.inputs['Scale'].default_value = bump; t.inputs['Detail'].default_value = 4
        b = n.new('ShaderNodeBump'); b.inputs['Strength'].default_value = bump_strength; b.inputs['Distance'].default_value = .001
        l.new(t.outputs['Fac'], b.inputs['Height']); l.new(b.outputs['Normal'], p.inputs['Normal'])
    m.diffuse_color = (*color, 1)
    return m


def pla(name, color, rough=.46, sss=.0):
    """Matte printed PLA: soft sheen, fine layer lines along object Z (mm), micro noise,
    rounded edges from a shader bevel so the real CAD meshes read as manufactured."""
    m, n, l, p = new_mat(name)
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Specular IOR Level'].default_value = .42
    p.inputs['Sheen Weight'].default_value = .15
    p.inputs['Sheen Roughness'].default_value = .4
    if sss:
        p.inputs['Subsurface Weight'].default_value = sss
        p.inputs['Subsurface Radius'].default_value = (1, .9, .75)
        p.inputs['Subsurface Scale'].default_value = .0008
    tc = n.new('ShaderNodeTexCoord')
    sep = n.new('ShaderNodeSeparateXYZ'); l.new(tc.outputs['Object'], sep.inputs[0])
    wave = n.new('ShaderNodeMath'); wave.operation = 'MULTIPLY'; wave.inputs[1].default_value = 2 * math.pi / .2
    l.new(sep.outputs['Z'], wave.inputs[0])
    sine = n.new('ShaderNodeMath'); sine.operation = 'SINE'; l.new(wave.outputs[0], sine.inputs[0])
    noise = n.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 1.6; noise.inputs['Detail'].default_value = 6
    l.new(tc.outputs['Object'], noise.inputs['Vector'])
    mix = n.new('ShaderNodeMath'); mix.operation = 'MULTIPLY_ADD'; mix.inputs[1].default_value = .35
    l.new(noise.outputs['Fac'], mix.inputs[0]); l.new(sine.outputs[0], mix.inputs[2])
    bevel = n.new('ShaderNodeBevel'); bevel.inputs['Radius'].default_value = .0006; bevel.samples = 8
    bump = n.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = .045; bump.inputs['Distance'].default_value = .00004
    l.new(mix.outputs[0], bump.inputs['Height']); l.new(bevel.outputs['Normal'], bump.inputs['Normal'])
    l.new(bump.outputs['Normal'], p.inputs['Normal'])
    # tiny roughness variation, like a matte print surface
    rr = n.new('ShaderNodeMapRange'); rr.inputs['To Min'].default_value = rough - .05; rr.inputs['To Max'].default_value = rough + .06
    l.new(noise.outputs['Fac'], rr.inputs['Value']); l.new(rr.outputs['Result'], p.inputs['Roughness'])
    m.diffuse_color = (*color, 1)
    return m


CHALK = pla('Chalk PLA (body)', (.74, .71, .655), .5, sss=.12)
GRAPHITE = pla('Graphite PLA (lid)', (.022, .024, .027), .58)
_gp = GRAPHITE.node_tree.nodes['Principled BSDF']
_gp.inputs['Specular IOR Level'].default_value = .16; _gp.inputs['Sheen Weight'].default_value = 0.
CHALK_FILL = mat('Chalk paint fill (label)', (.70, .68, .63), .6)
ALU = mat('Anodised aluminium', (.80, .80, .81), .28, 1., bump=900, bump_strength=.05)
ALU_TRACK = mat('Satin aluminium track', (.82, .82, .83), .33, 1.)
STEEL = mat('Stainless fasteners', (.62, .62, .63), .25, 1.)
BLACKOX = mat('Black oxide screw', (.02, .02, .022), .35, .6)
RUBBER = mat('GT2 belt rubber', (.008, .008, .009), .72, bump=600, bump_strength=.1, spec=.3)
NYLON = mat('White nylon gliders', (.80, .79, .76), .38, sss=.15)
SERVO_CASE = mat('Servo case ABS', (.016, .016, .018), .6, bump=300, bump_strength=.03, spec=.18)
LABEL = mat('Servo label foil', (.55, .56, .58), .35, .8)
INK = mat('Label print', (.01, .01, .012), .5)
WHITE_PVC = mat('White PVC cable', (.78, .77, .74), .42)
BRASS = mat('Brass spline', (.80, .55, .28), .3, 1.)
WIRE_COLS = [mat('Wire brown', (.12, .05, .02), .45), mat('Wire red', (.45, .02, .015), .45),
             mat('Wire orange', (.65, .20, .02), .45)]
JST = mat('JST housing', (.80, .78, .72), .45)

# LED light pipe: emission strength driven per frame
LEDM, _n, _l, _p = new_mat('Status LED light pipe')
_p.inputs['Base Color'].default_value = (.9, .9, .88, 1)
_p.inputs['Roughness'].default_value = .3
_p.inputs['Transmission Weight'].default_value = .4
_p.inputs['Emission Color'].default_value = (1., .78, .52, 1)
_p.inputs['Emission Strength'].default_value = 0.
LED_BSDF = _p

# PCB model: the KiCad glTF exports most plastics as metallic=1, roughness=1; fix that.
for m in bpy.data.materials:
    if m.name.startswith('mat_') and m.use_nodes:
        p = m.node_tree.nodes.get('Principled BSDF')
        if not p:
            continue
        c = p.inputs['Base Color'].default_value
        lum = .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
        metallic = p.inputs['Metallic'].default_value > .5
        greyish = abs(c[0] - c[1]) < .05 and abs(c[1] - c[2]) < .1
        if metallic and (lum < .15 or not greyish and c[1] > c[0]):
            p.inputs['Metallic'].default_value = 0.; p.inputs['Roughness'].default_value = .42
        elif metallic:
            p.inputs['Roughness'].default_value = .32
        elif lum < .3 and c[1] > c[0]:            # solder mask
            p.inputs['Roughness'].default_value = .35
            p.inputs['Base Color'].default_value = (.035, .16, .09, 1)

# Room materials
PLASTER = mat('Warm lime plaster', (.80, .78, .735), .9, bump=90, bump_strength=.12)
CEIL_PAINT = mat('Ceiling paint', (.84, .83, .80), .92, bump=60, bump_strength=.05)
OAK = mat('Oiled oak', (.36, .21, .10), .45, bump=30)
for wood, light, dark in [(OAK, (.46, .30, .15, 1), (.28, .15, .065, 1))]:
    n, l, p = wood.node_tree.nodes, wood.node_tree.links, wood.node_tree.nodes['Principled BSDF']
    tc = n.new('ShaderNodeTexCoord'); st = n.new('ShaderNodeVectorMath'); st.operation = 'MULTIPLY'
    st.inputs[1].default_value = (6, 90, 2)
    nz = n.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 2; nz.inputs['Detail'].default_value = 3
    l.new(tc.outputs['Object'], st.inputs[0]); l.new(st.outputs[0], nz.inputs['Vector'])
    ramp = n.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = .2; ramp.color_ramp.elements[0].color = dark
    ramp.color_ramp.elements[1].position = .8; ramp.color_ramp.elements[1].color = light
    l.new(nz.outputs['Fac'], ramp.inputs[0]); l.new(ramp.outputs[0], p.inputs['Base Color'])
WINDOW_PAINT = mat('Window frame paint', (.80, .79, .76), .4)
LINEN_CHAIR = mat('Oatmeal boucle', (.55, .50, .42), .95, bump=400, bump_strength=.4)
RUG = mat('Wool rug', (.46, .42, .36), 1., bump=250, bump_strength=.35)
TERRACOTTA = mat('Terracotta', (.42, .16, .07), .75, bump=150, bump_strength=.1)
CERAMIC = mat('Glazed ceramic', (.75, .72, .66), .22)
LEAF = mat('Olive leaves', (.06, .10, .03), .55, sss=.1)
STEM = mat('Stems', (.12, .08, .04), .7)
BLACK = mat('Soft black metal', (.015, .015, .017), .45, .3)
GRASS = mat('Garden', (.13, .19, .07), .95, bump=40, bump_strength=.3)
TREES = mat('Garden trees', (.07, .12, .05), .9, bump=3, bump_strength=.6)
for gm, dist in ((GRASS, 140.), (TREES, 110.)):
    n, l = gm.node_tree.nodes, gm.node_tree.links
    lpn = n.new('ShaderNodeLightPath'); ex = n.new('ShaderNodeMath'); ex.operation = 'MULTIPLY'; ex.inputs[1].default_value = -1 / dist
    l.new(lpn.outputs['Ray Length'], ex.inputs[0])
    e2 = n.new('ShaderNodeMath'); e2.operation = 'EXPONENT'; l.new(ex.outputs[0], e2.inputs[0])
    inv = n.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.; l.new(e2.outputs[0], inv.inputs[1])
    cam = n.new('ShaderNodeMath'); cam.operation = 'MULTIPLY'; l.new(inv.outputs[0], cam.inputs[0]); l.new(lpn.outputs['Is Camera Ray'], cam.inputs[1])
    em = n.new('ShaderNodeEmission'); em.inputs['Color'].default_value = (.70, .76, .82, 1); em.inputs['Strength'].default_value = .9
    mx = n.new('ShaderNodeMixShader'); l.new(cam.outputs[0], mx.inputs['Fac'])
    l.new(n['Principled BSDF'].outputs[0], mx.inputs[1]); l.new(em.outputs[0], mx.inputs[2])
    l.new(mx.outputs[0], n['Material Output'].inputs['Surface'])

# Linen: woven slub texture in UV space so it travels with the fabric, plus translucency
LINEN, n, l, p = new_mat('Oatmeal linen curtain')
p.inputs['Roughness'].default_value = .92
p.inputs['Sheen Weight'].default_value = .5
p.inputs['Sheen Roughness'].default_value = .45
p.inputs['Sheen Tint'].default_value = (1, .95, .88, 1)
uv = n.new('ShaderNodeUVMap')
sc = n.new('ShaderNodeMapping'); sc.inputs['Scale'].default_value = (FABRIC_W * 60, 2.45 * 6, 1)
l.new(uv.outputs['UV'], sc.inputs['Vector'])
slub = n.new('ShaderNodeTexNoise'); slub.inputs['Scale'].default_value = 1.0; slub.inputs['Detail'].default_value = 5
l.new(sc.outputs['Vector'], slub.inputs['Vector'])
ramp = n.new('ShaderNodeValToRGB')
ramp.color_ramp.elements[0].position = .25; ramp.color_ramp.elements[0].color = (.70, .65, .56, 1)
ramp.color_ramp.elements[1].position = .8; ramp.color_ramp.elements[1].color = (.84, .80, .72, 1)
sepuv = n.new('ShaderNodeSeparateXYZ'); l.new(uv.outputs['UV'], sepuv.inputs[0])
band = n.new('ShaderNodeMapRange'); band.interpolation_type = 'STEPPED'
head = n.new('ShaderNodeMath'); head.operation = 'GREATER_THAN'; head.inputs[1].default_value = .965
hem = n.new('ShaderNodeMath'); hem.operation = 'LESS_THAN'; hem.inputs[1].default_value = .025
l.new(sepuv.outputs['Y'], head.inputs[0]); l.new(sepuv.outputs['Y'], hem.inputs[0])
tint = n.new('ShaderNodeMix'); tint.data_type = 'RGBA'; tint.blend_type = 'MULTIPLY'
tint.inputs['B'].default_value = (.88, .86, .83, 1)
both = n.new('ShaderNodeMath'); both.operation = 'MAXIMUM'
l.new(head.outputs[0], both.inputs[0]); l.new(hem.outputs[0], both.inputs[1])
l.new(both.outputs[0], tint.inputs['Factor']); l.new(ramp.outputs[0], tint.inputs['A'])
l.new(slub.outputs['Fac'], ramp.inputs[0]); l.new(tint.outputs['Result'], p.inputs['Base Color'])
weave = n.new('ShaderNodeTexWave'); weave.inputs['Scale'].default_value = 1.
sc2 = n.new('ShaderNodeMapping'); sc2.inputs['Scale'].default_value = (FABRIC_W * 700, 2.45 * 700, 1)
l.new(uv.outputs['UV'], sc2.inputs['Vector']); l.new(sc2.outputs['Vector'], weave.inputs['Vector'])
bump = n.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = .35; bump.inputs['Distance'].default_value = .0006
add = n.new('ShaderNodeMath'); add.operation = 'MULTIPLY_ADD'; add.inputs[1].default_value = .5
l.new(weave.outputs['Fac'], add.inputs[0]); l.new(slub.outputs['Fac'], add.inputs[2])
l.new(add.outputs[0], bump.inputs['Height']); l.new(bump.outputs['Normal'], p.inputs['Normal'])
tr = n.new('ShaderNodeBsdfTranslucent'); l.new(ramp.outputs[0], tr.inputs['Color']); l.new(bump.outputs['Normal'], tr.inputs['Normal'])
mix = n.new('ShaderNodeMixShader'); mix.inputs['Fac'].default_value = .40
out = n['Material Output']
l.new(p.outputs[0], mix.inputs[1]); l.new(tr.outputs[0], mix.inputs[2]); l.new(mix.outputs[0], out.inputs['Surface'])


# ----------------------------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------------------------
def link(o, coll=None):
    (coll or scene.collection).objects.link(o)
    return o


def mesh_obj(name, bm, material, coll=None, parent=None, smooth=True, sharp_angle=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    for f in me.polygons:
        f.use_smooth = smooth
    if material:
        me.materials.append(material)
    o = link(bpy.data.objects.new(name, me), coll)
    if parent:
        o.parent = parent
    return o


def finish(o, bevel=0., segs=3, weighted=True):
    if bevel:
        b = o.modifiers.new('Soft manufactured edges', 'BEVEL')
        b.width = bevel; b.segments = segs; b.limit_method = 'ANGLE'; b.angle_limit = math.radians(40)
        b.harden_normals = True
    if weighted:
        w = o.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL'); w.keep_sharp = True
    return o


def box(name, mn, mx, material, bevel=0., coll=None, parent=None, segs=3):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    c = [(a + b) / 2 for a, b in zip(mn, mx)]; s = [b - a for a, b in zip(mn, mx)]
    for v in bm.verts:
        v.co = Vector((c[0] + v.co.x * s[0], c[1] + v.co.y * s[1], c[2] + v.co.z * s[2]))
    o = mesh_obj(name, bm, material, coll, parent, smooth=bool(bevel))
    return finish(o, bevel, segs, weighted=bool(bevel))


def cyl(name, center, r, z0, z1, material, verts=48, bevel=0., coll=None, parent=None, axis='Z', r2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r if r2 is None else r2, depth=z1 - z0)
    for v in bm.verts:
        v.co.z += (z0 + z1) / 2
    if axis == 'X':
        bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(math.pi / 2, 3, 'Y'))
    elif axis == 'Y':
        bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(-math.pi / 2, 3, 'X'))
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(center))
    o = mesh_obj(name, bm, material, coll, parent, smooth=True)
    return finish(o, bevel, 2)


def prism(name, pts, x0, x1, material, coll=None, parent=None, bevel=0.):
    """(y, z) polygon extruded along x."""
    bm = bmesh.new()
    a = [bm.verts.new((x0, y, z)) for y, z in pts]
    b = [bm.verts.new((x1, y, z)) for y, z in pts]
    bm.faces.new(list(reversed(a))); bm.faces.new(b)
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    o = mesh_obj(name, bm, material, coll, parent, smooth=bool(bevel))
    return finish(o, bevel, 2, weighted=bool(bevel))


def curve(name, pts, radius, material, coll=None, parent=None, res=12):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    cu.bevel_depth = radius; cu.bevel_resolution = 4; cu.resolution_u = res; cu.use_fill_caps = True
    s = cu.splines.new('BEZIER'); s.bezier_points.add(len(pts) - 1)
    for bp, p in zip(s.bezier_points, pts):
        bp.co = p; bp.handle_left_type = bp.handle_right_type = 'AUTO'
    cu.materials.append(material)
    o = link(bpy.data.objects.new(name, cu), coll)
    if parent:
        o.parent = parent
    return o


def text(name, body, size, loc, rot, material, coll=None, parent=None, extrude=0.02, align='CENTER', bold=False):
    cu = bpy.data.curves.new(name, 'FONT'); cu.body = body; cu.size = size; cu.extrude = extrude
    cu.align_x = align; cu.align_y = 'CENTER'
    try:
        cu.font = bpy.data.fonts.load('/usr/share/fonts/liberation/LiberationSans-%s.ttf' % ('Bold' if bold else 'Regular'), check_existing=True)
    except Exception:
        pass
    cu.materials.append(material)
    o = link(bpy.data.objects.new(name, cu), coll)
    o.location = loc; o.rotation_euler = rot
    if parent:
        o.parent = parent
    return o


def empty(name, coll=None, parent=None):
    o = link(bpy.data.objects.new(name, None), coll)
    o.empty_display_size = 20
    if parent:
        o.parent = parent
    return o


# ----------------------------------------------------------------------------------------
# Enclosure meshes: sharp edges by angle + label paint fill on the engraved floor
# ----------------------------------------------------------------------------------------
def prep_enclosure_mesh(me, label=False):
    bm = bmesh.new(); bm.from_mesh(me)
    for e in bm.edges:
        if len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle() < math.radians(32)
    for f in bm.faces:
        f.smooth = True
        if label:
            c = f.calc_center_median()
            if f.normal.z > .9 and 1.2 < c.z < 1.6 and abs(c.x - 43) < 28 and abs(c.y - SERVO_CY) < 5:
                f.material_index = 1
    bm.to_mesh(me); bm.free()


SRC_BASE.data.materials.clear(); SRC_BASE.data.materials.append(CHALK)
prep_enclosure_mesh(SRC_BASE.data)
SRC_LID.data.materials.clear(); SRC_LID.data.materials.append(GRAPHITE); SRC_LID.data.materials.append(CHALK_FILL)
prep_enclosure_mesh(SRC_LID.data, label=True)
for o in (SRC_BASE, SRC_LID):
    o.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL').keep_sharp = True


def copy_tree(o, coll, parent):
    c = o.copy()
    link(c, coll)
    c.parent = parent
    c.matrix_parent_inverse = o.matrix_parent_inverse.copy() if o.parent else Matrix.Identity(4)
    c.matrix_basis = o.matrix_basis.copy()
    for ch in o.children:
        copy_tree(ch, coll, c)
    return c


# ----------------------------------------------------------------------------------------
# Servo DM-S2000MD, detailed but inside the datasheet envelope, mounted shaft-down
# ----------------------------------------------------------------------------------------
def build_servo(coll, parent):
    x0, x1 = SERVO_CX - SERVO_L / 2, SERVO_CX + SERVO_L / 2
    y0, y1 = SERVO_CY - SERVO_W / 2, SERVO_CY + SERVO_W / 2
    zf = FLOOR_T + TOP_TO_FLANGE
    parts = []
    parts.append(box('Servo gear cap', (x0, y0, FLOOR_T), (x1, y1, zf - .25), SERVO_CASE, .8, coll, parent))
    parts.append(box('Servo middle case', (x0, y0, zf), (x1, y1, FLOOR_T + 31), SERVO_CASE, .6, coll, parent))
    parts.append(box('Servo bottom cover', (x0 + .15, y0 + .15, FLOOR_T + 31.3), (x1 - .15, y1 - .15, FLOOR_T + SERVO_H), SERVO_CASE, .9, coll, parent))
    # mounting flanges with rubber-grommet style bosses and screws into the printed bosses
    for sx in (-1, 1):
        xa, xb = (SERVO_CX + sx * SERVO_L / 2, SERVO_CX + sx * FLANGE_SPAN / 2)
        box('Servo flange', (min(xa, xb) - (0.5 if sx < 0 else -.5), y0, zf), (max(xa, xb), y1, zf + FLANGE_T), SERVO_CASE, .6, coll, parent)
        for sy in (-1, 1):
            cx, cy = SERVO_CX + sx * HOLE_DX / 2, SERVO_CY + sy * HOLE_DY / 2
            cyl('Flange screw', (cx, cy, 0), 2.3, zf + FLANGE_T, zf + FLANGE_T + 1.6, STEEL, 24, .3, coll, parent)
            cyl('Flange screw socket', (cx, cy, 0), .9, zf + FLANGE_T + 1.3, zf + FLANGE_T + 1.65, BLACKOX, 6, 0, coll, parent)
    # corner screws of the bottom cover (the "bottom" faces up because the servo is inverted)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl('Case screw', (SERVO_CX + sx * (SERVO_L / 2 - 2.6), SERVO_CY + sy * (SERVO_W / 2 - 2.4), 0),
                1.1, FLOOR_T + SERVO_H - .2, FLOOR_T + SERVO_H + .25, STEEL, 16, .15, coll, parent)
    # seam grooves
    for z in (zf - .25, FLOOR_T + 31.15):
        box('Servo seam', (x0 - .05, y0 - .05, z - .05), (x1 + .05, y1 + .05, z + .05), BLACKOX, 0, coll, parent)
    # output boss and 25T spline, through the 12 mm floor hole, pointing down
    cyl('Servo output boss', (SHAFT_X, SHAFT_Y, 0), 4.8, .8, FLOOR_T, SERVO_CASE, 40, .3, coll, parent)
    bm = bmesh.new()
    pts = []
    for i in range(100):
        a = 2 * math.pi * i / 100
        r = 2.95 - .18 * (0.5 + 0.5 * math.cos(25 * a))
        pts.append(bm.verts.new((SHAFT_X + r * math.cos(a), SHAFT_Y + r * math.sin(a), -6.0)))
    top = [bm.verts.new((v.co.x, v.co.y, .8)) for v in pts]
    bm.faces.new(list(reversed(pts))); bm.faces.new(top)
    for i in range(100):
        j = (i + 1) % 100
        bm.faces.new((pts[i], pts[j], top[j], top[i]))
    mesh_obj('Servo 25T output spline', bm, BRASS, coll, parent, smooth=True)
    # label on the +y face (towards the PCB), text in two lines
    box('Servo label', (x0 + 3.5, y1, FLOOR_T + 14.5), (x1 - 3.5, y1 + .12, FLOOR_T + 29.5), LABEL, 0, coll, parent)
    rot = (math.pi / 2, 0, math.pi)       # text faces +y, reads right way up
    text('Servo label text', 'DM-S2000MD', 3.2, (SERVO_CX, y1 + .14, FLOOR_T + 25.2), (-math.pi / 2, math.pi, 0), INK, coll, parent, .03, bold=True)
    text('Servo label text 2', 'DIGITAL SERVO  6-8.4V  360°', 1.7, (SERVO_CX, y1 + .14, FLOOR_T + 20.5), (-math.pi / 2, math.pi, 0), INK, coll, parent, .03)
    text('Servo label text 3', '20 kg·cm   METAL GEAR', 1.7, (SERVO_CX, y1 + .14, FLOOR_T + 17.6), (-math.pi / 2, math.pi, 0), INK, coll, parent, .03)
    # three-wire lead from the case end to the J3 motor connector on the PCB
    j3 = Vector((17.75, 59.7, 15.15))
    box('J3 plug housing', (j3.x - 2.6, j3.y - 4.0, j3.z), (j3.x + 2.6, j3.y + 4.0, j3.z + 4.5), JST, .3, coll, parent)
    for k, wm in enumerate(WIRE_COLS):
        dy = (k - 1) * 1.05
        curve('Servo lead', [(x0 - .5, SERVO_CY + dy, FLOOR_T + 34.5), (x0 - 5, SERVO_CY + 4 + dy, FLOOR_T + 35),
                             (j3.x - .5, 34 + dy * .4, FLOOR_T + 32), (j3.x + dy * .8, j3.y - 1.5, j3.z + 10), (j3.x + dy * .8, j3.y, j3.z + 4.4)],
              .5, wm, coll, parent)
    box('Servo lead grommet', (x0 - 1.4, SERVO_CY - 2.2, FLOOR_T + 33), (x0, SERVO_CY + 2.2, FLOOR_T + 36), SERVO_CASE, .3, coll, parent)


def build_unit(coll, parent, lid_matrix=None, led_light=True):
    """Base + lid (real meshes) + PCB model + servo + screws + LED pipe, box coordinates."""
    base = link(bpy.data.objects.new('Drive base (enclosure.blend)', SRC_BASE.data), coll)
    base.parent = parent
    base.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL').keep_sharp = True
    lid_parent = empty('Lid pose', coll, parent)
    lid_parent.matrix_basis = lid_matrix if lid_matrix is not None else Matrix.Translation((0, 0, OUTER_Z))
    lid = link(bpy.data.objects.new('Drive lid (enclosure.blend)', SRC_LID.data), coll)
    lid.parent = lid_parent
    lid.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL').keep_sharp = True
    for (px, py) in POSTS:
        cyl('Lid screw', (px, py, 0), 2.45, LID_T - 1.2, LID_T - .35, BLACKOX, 24, .25, coll, lid_parent)
        cyl('Lid screw socket', (px, py, 0), .8, LID_T - .6, LID_T - .3, STEEL, 6, 0, coll, lid_parent)
    pipe = cyl('Status LED light pipe', (LED_XY[0], LED_XY[1], 0), 1.55, -1.95, LID_T - .15, LEDM, 24, .2, coll, lid_parent)
    if led_light:
        # soft spill on the ceiling above the lid (the pipe itself is emissive)
        ld = bpy.data.lights.new('Status LED glow', 'SPOT'); ld.energy = 0.; ld.shadow_soft_size = .004
        ld.spot_size = math.radians(150); ld.spot_blend = 1.; ld.color = (1., .80, .55)
        lo = link(bpy.data.objects.new('Status LED glow', ld), coll)
        lo.parent = lid_parent; lo.location = (LED_XY[0], LED_XY[1], LID_T + 1.0)   # points up (+z)
        lo.rotation_euler = (math.pi, 0, 0)
    pcb = copy_tree(SRC_PCB, coll, parent)
    build_servo(coll, parent)
    return base, lid, lid_parent, pcb


# ----------------------------------------------------------------------------------------
# ROOM
# ----------------------------------------------------------------------------------------
room = bpy.data.collections.new('Room'); scene.collection.children.link(room)
hwc = bpy.data.collections.new('Drive, track and carriers (mm)'); scene.collection.children.link(hwc)
curt = bpy.data.collections.new('Curtains'); scene.collection.children.link(curt)

RW, RD = 2.2, 5.2      # half width, depth
# floor boards along y (towards the window)
box('Floor base', (-RW, -RD, -.05), (RW, .3, -.012), OAK, coll=room)
x = -RW
row = 0
while x < RW - 1e-6:
    w = min(.19, RW - x)
    y = -RD - (row % 3) * .55
    while y < 0:
        L = random.choice([1.4, 1.8, 2.2])
        box('Oak floorboard', (x + .0015, max(y, -RD) + .0015, -.012), (x + w - .0015, min(y + L, 0) - .0015, 0), OAK, .0015, room, segs=2)
        y += L
    x += w; row += 1
box('Ceiling', (-RW - .1, -RD - .1, CEIL), (RW + .1, .3, CEIL + .1), CEIL_PAINT, coll=room)
box('Left wall', (-RW - .15, -RD, 0), (-RW, .3, CEIL), PLASTER, coll=room)
box('Right wall', (RW, -RD, 0), (RW + .15, .3, CEIL), PLASTER, coll=room)
box('Back wall', (-RW, -RD - .15, 0), (RW, -RD, CEIL), PLASTER, coll=room)
WX, WZ0, WZ1, WT = .95, .52, 2.28, .30
box('Window wall left', (-RW, 0, 0), (-WX, WT, CEIL), PLASTER, coll=room)
box('Window wall right', (WX, 0, 0), (RW, WT, CEIL), PLASTER, coll=room)
box('Window wall below', (-WX, 0, 0), (WX, WT, WZ0), PLASTER, coll=room)
box('Window wall above', (-WX, 0, WZ1), (WX, WT, CEIL), PLASTER, coll=room)
box('Window sill', (-WX, 0, WZ0 - .03), (WX, .20, WZ0), WINDOW_PAINT, .004, room)
for xs, sgn in ((-RW, 1), (RW, -1)):
    box('Skirting', (min(xs, xs + sgn * .018), -RD, 0), (max(xs, xs + sgn * .018), 0, .085), WINDOW_PAINT, .003, room)
box('Skirting', (-RW, -.018, 0), (-WX - .001, 0, .085), WINDOW_PAINT, .003, room)
box('Skirting', (WX + .001, -.018, 0), (RW, 0, .085), WINDOW_PAINT, .003, room)
# window frame: outer frame, mullion, transom, glass
FY0, FY1 = .20, .26
fw = .065
box('Window frame L', (-WX, FY0, WZ0), (-WX + fw, FY1, WZ1), WINDOW_PAINT, .004, room)
box('Window frame R', (WX - fw, FY0, WZ0), (WX, FY1, WZ1), WINDOW_PAINT, .004, room)
box('Window frame B', (-WX, FY0, WZ0), (WX, FY1, WZ0 + fw), WINDOW_PAINT, .004, room)
box('Window frame T', (-WX, FY0, WZ1 - fw), (WX, FY1, WZ1), WINDOW_PAINT, .004, room)
box('Window mullion', (-.04, FY0 - .01, WZ0), (.04, FY1, WZ1), WINDOW_PAINT, .004, room)
box('Window transom', (-WX, FY0 - .005, 1.86), (WX, FY1, 1.915), WINDOW_PAINT, .004, room)
for sx in (-1, 1):
    box('Window handle', (sx * .055 - .006, FY0 - .045, 1.20), (sx * .055 + .006, FY0 - .01, 1.23), STEEL, .003, room)
GLASS, gn, gl, gp = new_mat('Window glass')
lp = gn.new('ShaderNodeLightPath'); lw = gn.new('ShaderNodeLayerWeight'); lw.inputs['Blend'].default_value = .15
glossy = gn.new('ShaderNodeBsdfGlossy'); glossy.inputs['Roughness'].default_value = .02
transp = gn.new('ShaderNodeBsdfTransparent')
mixg = gn.new('ShaderNodeMixShader')
mf = gn.new('ShaderNodeMath'); mf.operation = 'MULTIPLY'; mf.inputs[1].default_value = .35
gl.new(lw.outputs['Fresnel'], mf.inputs[0])
mf2 = gn.new('ShaderNodeMath'); mf2.operation = 'MULTIPLY'
gl.new(mf.outputs[0], mf2.inputs[0]); gl.new(lp.outputs['Is Camera Ray'], mf2.inputs[1])
gl.new(mf2.outputs[0], mixg.inputs['Fac']); gl.new(transp.outputs[0], mixg.inputs[1]); gl.new(glossy.outputs[0], mixg.inputs[2])
gl.new(mixg.outputs[0], gn['Material Output'].inputs['Surface'])
box('Window glass', (-WX, .228, WZ0), (WX, .232, WZ1), GLASS, coll=room)
# outside: a bright, soft, out-of-focus garden, like an interior photo exposed for the room.
# The backdrop is visible to the camera only, so the sun and sky still light the room.
BACK, bn, bl, bp = new_mat('Garden daylight backdrop (camera only)')
btc = bn.new('ShaderNodeTexCoord'); bsep = bn.new('ShaderNodeSeparateXYZ'); bl.new(btc.outputs['Generated'], bsep.inputs[0])
bnoise = bn.new('ShaderNodeTexNoise'); bnoise.inputs['Scale'].default_value = 2.2; bnoise.inputs['Detail'].default_value = 1.
bnoise.inputs['Roughness'].default_value = .3; bl.new(btc.outputs['Generated'], bnoise.inputs['Vector'])
# height of the soft foliage band varies along x
hb = bn.new('ShaderNodeMath'); hb.operation = 'MULTIPLY_ADD'; hb.inputs[1].default_value = .22; hb.inputs[2].default_value = .30
bl.new(bnoise.outputs['Fac'], hb.inputs[0])
d = bn.new('ShaderNodeMath'); d.operation = 'SUBTRACT'; bl.new(bsep.outputs['Z'], d.inputs[0]); bl.new(hb.outputs[0], d.inputs[1])
sm = bn.new('ShaderNodeMapRange'); sm.interpolation_type = 'SMOOTHSTEP'
sm.inputs['From Min'].default_value = -.10; sm.inputs['From Max'].default_value = .12
bl.new(d.outputs[0], sm.inputs['Value'])
green = bn.new('ShaderNodeMix'); green.data_type = 'RGBA'
green.inputs['A'].default_value = (.26, .38, .17, 1); green.inputs['B'].default_value = (.50, .60, .36, 1)
bl.new(bnoise.outputs['Color'], green.inputs['Factor'])
sky = bn.new('ShaderNodeMix'); sky.data_type = 'RGBA'; sky.inputs['B'].default_value = (.93, .95, .97, 1)
bl.new(sm.outputs['Result'], sky.inputs['Factor']); bl.new(green.outputs['Result'], sky.inputs['A'])
bem = bn.new('ShaderNodeEmission'); bem.inputs['Strength'].default_value = .95
bl.new(sky.outputs['Result'], bem.inputs['Color']); bl.new(bem.outputs[0], bn['Material Output'].inputs['Surface'])
backdrop = box('Garden backdrop', (-9, 4.5, -3.0), (9, 4.6, 7.0), BACK, coll=room)
for attr in ('visible_diffuse', 'visible_glossy', 'visible_transmission', 'visible_volume_scatter', 'visible_shadow'):
    setattr(backdrop, attr, False)

# furniture: lounge chair, side table, plant, rug, art
box('Wool rug', (-1.45, -3.3, 0), (1.25, -1.35, .012), RUG, .01, room)
CH = Matrix.Translation((1.05, -1.25, 0)) @ Matrix.Rotation(math.radians(-32), 4, 'Z')
chair = []
chair.append(box('Chair seat', (-.36, -.34, .30), (.36, .36, .46), LINEN_CHAIR, .06, room))
chair.append(box('Chair back', (-.36, .24, .40), (.36, .40, .86), LINEN_CHAIR, .07, room))
chair[-1].rotation_euler.x = math.radians(-10)
for sx in (-1, 1):
    chair.append(box('Chair oak arm', (sx * .40 - .03, -.36, .30), (sx * .40 + .03, .38, .58), OAK, .012, room))
    for sy in (-1, 1):
        chair.append(box('Chair leg', (sx * .40 - .02, sy * .30 - .02, 0), (sx * .40 + .02, sy * .30 + .02, .32), OAK, .008, room))
chair.append(box('Chair cushion', (-.2, .14, .46), (.2, .26, .78), TERRACOTTA, .05, room))
chair[-1].rotation_euler = (math.radians(-18), 0, math.radians(8))
bpy.context.view_layer.update()
for o in chair:
    o.matrix_world = CH @ o.matrix_world
cyl('Side table top', (.32, -.62, 0), .23, .52, .55, OAK, 64, .006, room)
cyl('Side table stem', (.32, -.62, 0), .025, .02, .52, BLACK, 24, 0, room)
cyl('Side table foot', (.32, -.62, 0), .17, 0, .02, BLACK, 48, .004, room)
cyl('Vase', (.30, -.60, 0), .055, .55, .80, CERAMIC, 48, .004, room, r2=.035)
cyl('Mug', (.42, -.70, 0), .038, .55, .64, TERRACOTTA, 32, .003, room)
for i in range(3):
    a = i * 2.1
    curve('Dry branch', [(.30, -.60, .74), (.30 + .06 * math.cos(a), -.60 + .05 * math.sin(a), 1.0), (.30 + .15 * math.cos(a), -.60 + .12 * math.sin(a), 1.25)], .003, STEM, room)
cyl('Plant pot', (1.78, -.55, 0), .20, 0, .42, TERRACOTTA, 64, .01, room, r2=.24)
random.seed(11)
for i in range(22):
    a = i * 2.39; h = random.uniform(.8, 1.7)
    tip = (1.78 + math.cos(a) * random.uniform(.18, .38), -.55 + math.sin(a) * random.uniform(.12, .3), h)
    curve('Plant stem', [(1.78, -.55, .40), (1.78 + math.cos(a) * .05, -.55 + math.sin(a) * .04, h * .7), tip], .005, STEM, room)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, location=tip)
    lf = bpy.context.object; lf.name = 'Plant leaf'; lf.scale = (.10, .012, .16); lf.rotation_euler = (.4, random.uniform(-.7, .7), a)
    lf.data.materials.append(LEAF)
    for f in lf.data.polygons:
        f.use_smooth = True
    for c in lf.users_collection:
        c.objects.unlink(lf)
    room.objects.link(lf)
# framed print on the left wall
box('Print frame', (-RW, -2.9, 1.15), (-RW + .03, -2.05, 1.75), OAK, .004, room)
ART, an, al, ap = new_mat('Print: abstract')
ap.inputs['Roughness'].default_value = .8
tcx = an.new('ShaderNodeTexCoord'); sepx = an.new('ShaderNodeSeparateXYZ'); al.new(tcx.outputs['Generated'], sepx.inputs[0])
rx = an.new('ShaderNodeValToRGB'); rx.color_ramp.interpolation = 'CONSTANT'
rx.color_ramp.elements[0].color = (.72, .68, .60, 1); rx.color_ramp.elements[1].position = .45; rx.color_ramp.elements[1].color = (.38, .15, .07, 1)
e = rx.color_ramp.elements.new(.62); e.color = (.13, .15, .12, 1)
e = rx.color_ramp.elements.new(.7); e.color = (.72, .68, .60, 1)
al.new(sepx.outputs['Z'], rx.inputs[0]); al.new(rx.outputs[0], ap.inputs['Base Color'])
box('Print', (-RW + .03, -2.85, 1.2), (-RW + .032, -2.1, 1.70), ART, coll=room)

# power outlet with a small white 12 V plug-in supply, left of the curtains
OUT_X = W((-37, 0, 0)).x
box('Wall socket plate', (OUT_X - .04, -.009, .26), (OUT_X + .04, 0, .34), WINDOW_PAINT, .004, room)
box('12 V plug-in supply', (OUT_X - .028, -.045, .262), (OUT_X + .028, -.009, .338), WINDOW_PAINT, .008, room)

# ----------------------------------------------------------------------------------------
# DRIVE + TRACK (mm, box coordinates)
# ----------------------------------------------------------------------------------------
HW = empty('Drive and track, mm (scaled 0.001)', hwc)
HW.matrix_world = Matrix.Translation(HW_ORIGIN) @ Matrix.Diagonal((.001, .001, .001, 1))
UNIT = build_unit(hwc, HW)
LED_LIGHT = bpy.data.objects['Status LED glow']

# wall bracket: plate on the wall behind the box, two arms under the ears
bracket = [box('Wall bracket plate', (-14, OUTER_Y, -6.5), (100, WALL_Y_LOCAL, 32), CHALK, 1.2, hwc, HW)]
for xa, xb in ((-12, 1.0), (85.0, 98)):
    bracket.append(box('Wall bracket arm', (xa, 34, -6.5), (xb, OUTER_Y + .5, 0), CHALK, 1.0, hwc, HW))
    bracket.append(box('Wall bracket gusset', ((xa + xb) / 2 - 2, 70, -6.5), ((xa + xb) / 2 + 2, OUTER_Y + .5, 14), CHALK, .8, hwc, HW))
for xs in (-5.0, 91.0):
    cyl('Ear screw head', (xs, EAR_Y, 0), 3.8, FLOOR_T, FLOOR_T + 2.4, STEEL, 32, .5, hwc, HW)
    box('Ear screw slot', (xs - .45, EAR_Y - 2.4, FLOOR_T + 2.2), (xs + .45, EAR_Y + 2.4, FLOOR_T + 2.5), BLACKOX, 0, hwc, HW)
    cyl('Ear washer', (xs, EAR_Y, 0), 5.0, FLOOR_T - .01, FLOOR_T + .6, STEEL, 32, .2, hwc, HW)
for xs, zs in ((-7, 24), (93, 24)):
    cyl('Wall screw head', (xs, OUTER_Y + .01, zs), 3.4, -1.2, 0, STEEL, 32, .4, hwc, HW, axis='Y')
# barrel plug + slim lead down the wall
cyl('DC plug overmold', (JACK[0] - 7.5, JACK[1], JACK[2]), 4.6, -6.5, 6.5, WHITE_PVC, 32, .8, hwc, HW, axis='X')
cyl('DC plug strain relief', (JACK[0] - 18, JACK[1], JACK[2]), 2.1, -4, 4, WHITE_PVC, 32, .5, hwc, HW, axis='X', r2=3.4)
cable_pts = [(JACK[0] - 21, JACK[1], JACK[2]), (-26, JACK[1] + 1, JACK[2] - .8), (-31, 52, 7), (-35, 70, -4),
             (-37, 90, -18), (-37, WALL_Y_LOCAL - 2.2, -34), (-37, WALL_Y_LOCAL - 2.2, -60), (-37, WALL_Y_LOCAL - 2.2, -300)]
curve('12 V lead (to bracket)', cable_pts, 1.9, WHITE_PVC, hwc, HW)
z_socket = (.338 - HW_ORIGIN.z) * 1000
curve('12 V lead (down the wall)', [(-37, WALL_Y_LOCAL - 2.2, -300), (-37, WALL_Y_LOCAL - 2.2, z_socket + 120),
                                    (-37, WALL_Y_LOCAL - 8, z_socket + 30), (-37, WALL_Y_LOCAL - 27, z_socket + 2)], 1.9, WHITE_PVC, hwc, HW)
for zc in np.arange(-150, z_socket + 150, -420):
    box('Cable clip', (-41, WALL_Y_LOCAL - 5, zc - 3), (-33, WALL_Y_LOCAL, zc + 3), WHITE_PVC, .8, hwc, HW)

# track: aluminium C-profile, closed top, bottom slot for the glider stems
tp = [(3.5, 0), (15, 0), (15, 26), (-15, 26), (-15, 0), (-3.5, 0), (-3.5, 1.5), (-13.5, 1.5), (-13.5, 24.5), (13.5, 24.5),
      (13.5, 1.5), (3.5, 1.5)]
tp = [(YC + y, TRACK_Z0 + z) for y, z in tp]
prism('Curtain track (aluminium)', tp, TRACK_X0, TRACK_X1, ALU_TRACK, hwc, HW, bevel=.5)


def ring_cap(name, x0, x1, material):
    outer = box(name, (x0, YC - 16.5, TRACK_Z0 - 1.5), (x1, YC + 16.5, TRACK_Z1 + 1.5), material, 1.2, hwc, HW)
    cut = box(name + ' cut', (x0 - 1, YC - 13.5, TRACK_Z0 + 1.5), (x1 + 1, YC + 13.5, TRACK_Z1 - 1.5), None, 0, hwc, HW)
    slot = box(name + ' slot', (x0 - 1, YC - 3.5, TRACK_Z0 - 3), (x1 + 1, YC + 3.5, TRACK_Z0 + 2), None, 0, hwc, HW)
    for c in (cut, slot):
        c.hide_render = True; c.hide_viewport = True
        m = outer.modifiers.new('cut', 'BOOLEAN'); m.object = c; m.solver = 'EXACT'
        outer.modifiers.move(len(outer.modifiers) - 1, 0)
    return outer


ring_cap('Track end cap, drive end', TRACK_X0 - 6, TRACK_X0 + 4, CHALK)
ring_cap('Track end cap, idler end', TRACK_X1 - 4, TRACK_X1 + 6, CHALK)
# end clamps (stops) inside the track at both ends, with a knurled thumb screw on the front face
for xs in (X0_LEFT - GLIDER_HALF - 5, X0_RIGHT + GLIDER_HALF + 5):
    box('End clamp block', (xs - 5, YC - 13.3, TRACK_Z0 + 1.6), (xs + 5, YC + 13.3, TRACK_Z1 - 1.6), GRAPHITE, .6, hwc, HW)
    cyl('End clamp thumb screw', (xs, YC - 15, TRACK_Z0 + 13), 3.2, -3.5, 0, GRAPHITE, 24, .4, hwc, HW, axis='Y')
# lead-carrier end stops: a graphite block at belt height inside the track (the gliders run
# underneath it), fixed by a knurled thumb screw on the track front. The lead carrier's belt
# clamp runs into it: that is the stall the drive detects.
E_OPEN_L, E_OPEN_R = X0_LEFT + SPAN_OPEN, X0_RIGHT - SPAN_OPEN
for x0, x1, y0, y1 in ((E_OPEN_L - 15.5, E_OPEN_L - 5.5, YC - 13.3, YC - 8.2), (E_OPEN_R + 5.5, E_OPEN_R + 15.5, YC + 8.2, YC + 13.3)):
    box('Carrier end stop', (x0, y0, BELT_Z0 - 2.5), (x1, y1, TRACK_Z1 - 1.6), GRAPHITE, .5, hwc, HW)
    cyl('Carrier end stop thumb screw', ((x0 + x1) / 2, YC - 15, BELT_Z0 + 2), 3.4, -4.0, 0, GRAPHITE, 24, .4, hwc, HW, axis='Y')
    cyl('Carrier end stop screw shank', ((x0 + x1) / 2, YC - 15, BELT_Z0 + 2), 1.4, 0, 1.6, STEEL, 16, 0, hwc, HW, axis='Y')
# idler block: top and bottom plates, back wall, axle
IB = (TRACK_X1 + 6, X_I + 16)
box('Idler block top plate', (IB[0] - 2, YC - 16.5, -5.3), (IB[1], YC + 16.5, TRACK_Z1 + 1.5), CHALK, 1.0, hwc, HW)
box('Idler block bottom plate', (IB[0] - 2, YC - 16.5, -18.5), (IB[1], YC + 16.5, -14.7), CHALK, 1.0, hwc, HW)
box('Idler block end wall', (IB[1] - 4, YC - 16.5, -18.5), (IB[1], YC + 16.5, TRACK_Z1 + 1.5), CHALK, 1.0, hwc, HW)
cyl('Idler axle screw', (X_I, YC, 0), 3.2, TRACK_Z1 + 1.5, TRACK_Z1 + 3.5, STEEL, 32, .4, hwc, HW)
# ceiling drop rods with saddles and rosettes
ROD_X = [X_I - 20, (0 - HW_ORIGIN.x) * 1000, (-.83 - HW_ORIGIN.x) * 1000, (.83 - HW_ORIGIN.x) * 1000]
for i, rx in enumerate(ROD_X):
    zb = TRACK_Z1 + 1.5 if i else TRACK_Z1 + 3.5
    if i:
        box('Track saddle', (rx - 7, YC - 16.6, TRACK_Z1 - 7), (rx + 7, YC + 16.6, TRACK_Z1 + 2), ALU_TRACK, .8, hwc, HW)
        cut = box('Saddle cut', (rx - 8, YC - 15.01, TRACK_Z1 - 8), (rx + 8, YC + 15.01, TRACK_Z1), None, 0, hwc, HW)
        cut.hide_render = cut.hide_viewport = True
        sd = [o for o in hwc.objects if o.name.startswith('Track saddle')][-1]
        m = sd.modifiers.new('cut', 'BOOLEAN'); m.object = cut; m.solver = 'EXACT'
        sd.modifiers.move(len(sd.modifiers) - 1, 0)
    cyl('Ceiling drop rod', (rx, YC, 0), 3.0, zb + (0.5 if i else 0), CEIL_LOCAL - 2.5, ALU_TRACK, 32, 0, hwc, HW)
    cyl('Ceiling rosette', (rx, YC, 0), 13, CEIL_LOCAL - 3.0, CEIL_LOCAL, ALU_TRACK, 48, .8, hwc, HW)


# ---- pulleys (GT2 20T, aluminium) with grooves aligned to the belt's teeth --------------
def gt2_pulley(name, cx, phase, hub=True):
    root = empty(name, hwc, HW)
    root.location = (cx, YC, 0)
    bm = bmesh.new()
    N = 20 * 14
    ring0, ring1 = [], []
    for i in range(N):
        a = 2 * math.pi * i / N
        d = min(abs(((a - phase) % (2 * math.pi / 20)) - math.pi / 20), 1)
        # groove centred between teeth: groove where the belt tooth sits
        g = (a - phase) % (2 * math.pi / 20)
        g = min(g, 2 * math.pi / 20 - g)            # angular distance to groove centre
        w = .55 / R_TIP
        depth = TOOTH_H * (1 - min(1, max(0, (g - w * .55) / (w * .6)))) if g < w * 1.15 else 0
        r = R_TIP - depth
        ring0.append(bm.verts.new((r * math.cos(a), r * math.sin(a), BELT_Z0 - .2)))
        ring1.append(bm.verts.new((r * math.cos(a), r * math.sin(a), BELT_Z1 + .2)))
    bm.faces.new(list(reversed(ring0))); bm.faces.new(ring1)
    for i in range(N):
        j = (i + 1) % N
        bm.faces.new((ring0[i], ring0[j], ring1[j], ring1[i]))
    teeth = mesh_obj(name + ' teeth', bm, ALU, hwc, root, smooth=False)
    cyl(name + ' lower flange', (0, 0, 0), 8.0, BELT_Z0 - 1.2, BELT_Z0 - .2, ALU, 64, .3, hwc, root)
    cyl(name + ' upper flange', (0, 0, 0), 8.0, BELT_Z1 + .2, BELT_Z1 + 1.2, ALU, 64, .3, hwc, root)
    if hub:
        cyl(name + ' hub', (0, 0, 0), 5.5, BELT_Z1 + 1.2, -.8, ALU, 64, .4, hwc, root)
        cyl(name + ' set screw', (5.0, 0, -3.3), 1.35, -.6, .6, BLACKOX, 12, 0, hwc, root, axis='X')
        cyl(name + ' set screw', (0, 5.0, -3.3), 1.35, -.6, .6, BLACKOX, 12, 0, hwc, root, axis='Y')
        cyl(name + ' centre screw', (0, 0, 0), 2.6, BELT_Z0 - 2.4, BELT_Z0 - 1.2, BLACKOX, 32, .3, hwc, root)
        box(name + ' hex socket', (-1.1, -1.1, BELT_Z0 - 2.5), (1.1, 1.1, BELT_Z0 - 2.3), STEEL, 0, hwc, root)
        box(name + ' index mark', (5.7, -.5, BELT_Z1 + 1.21), (7.6, .5, BELT_Z1 + 1.26), GRAPHITE, 0, hwc, root)
    else:
        cyl(name + ' bearing', (0, 0, 0), 2.5, BELT_Z1 + 1.2, -5.3, STEEL, 32, .2, hwc, root)
        box(name + ' index mark', (5.7, -.5, BELT_Z1 + 1.21), (7.6, .5, BELT_Z1 + 1.26), GRAPHITE, 0, hwc, root)
    return root


# belt path, pitch-line parameter s (mm)
D = X_I - X_P
S_TOTAL = 2 * D + 2 * math.pi * R_PITCH
S_IDLER = D
S_PULLEY = 2 * D + math.pi * R_PITCH
PHASE_P = math.pi / 2 + (1 - S_PULLEY) / R_PITCH      # groove angle offsets (see notes in README)
PHASE_I = -math.pi / 2 + (1 - S_IDLER) / R_PITCH
PULLEY = gt2_pulley('Drive pulley GT2 20T', X_P, PHASE_P)
IDLER = gt2_pulley('Idler pulley GT2 20T', X_I, PHASE_I, hub=False)


def belt_samples():
    fine = .25
    out = []
    s = 0.
    def dens(s):
        near_drive = s < 900 or s > S_TOTAL - 900 - math.pi * R_PITCH
        near_idler = abs(s - (D + math.pi * R_PITCH / 2)) < 120
        return fine if (near_drive or near_idler) else 8.
    while s < S_TOTAL - 1e-9:
        out.append(s)
        s += dens(s)
    return np.array(out)


BELT_S = belt_samples()
BELT_FINE = np.diff(np.append(BELT_S, S_TOTAL)) < 1


def belt_frame(s):
    """base-line point and outward normal (numpy, vectorised)"""
    P = np.zeros((len(s), 2)); N = np.zeros((len(s), 2))
    a = s < D
    P[a, 0] = X_P + s[a]; P[a, 1] = YC - R_BASE; N[a] = (0, -1)
    b = (s >= D) & (s < D + math.pi * R_PITCH)
    th = -math.pi / 2 + (s[b] - D) / R_PITCH
    P[b, 0] = X_I + R_BASE * np.cos(th); P[b, 1] = YC + R_BASE * np.sin(th); N[b, 0] = np.cos(th); N[b, 1] = np.sin(th)
    c = (s >= D + math.pi * R_PITCH) & (s < S_PULLEY + 1e-9)
    c = (s >= D + math.pi * R_PITCH) & (s < 2 * D + math.pi * R_PITCH)
    P[c, 0] = X_I - (s[c] - D - math.pi * R_PITCH); P[c, 1] = YC + R_BASE; N[c] = (0, 1)
    d = s >= 2 * D + math.pi * R_PITCH
    th = math.pi / 2 + (s[d] - S_PULLEY) / R_PITCH
    P[d, 0] = X_P + R_BASE * np.cos(th); P[d, 1] = YC + R_BASE * np.sin(th); N[d, 0] = np.cos(th); N[d, 1] = np.sin(th)
    return P, N


BELT_P, BELT_N = belt_frame(BELT_S)


def tooth_profile(q):
    """q = phase in [0, 1) of a 2 mm pitch; tooth centred on 0.5"""
    d = np.abs(q - .5)
    return TOOTH_H * np.clip((.30 - d) / .08, 0, 1)


def build_belt():
    n = len(BELT_S)
    me = bpy.data.meshes.new('GT2 belt loop')
    verts = np.zeros((n * 4, 3))
    faces = []
    for i in range(n):
        j = (i + 1) % n
        a, b = 4 * i, 4 * j
        # 0 outer-top, 1 outer-bottom, 2 inner-bottom, 3 inner-top
        faces += [(a, b, b + 1, a + 1), (a + 1, b + 1, b + 2, a + 2), (a + 2, b + 2, b + 3, a + 3), (a + 3, b + 3, b, a)]
    me.from_pydata(verts.tolist(), [], faces)
    me.uv_layers.new(name='UVMap')
    me.materials.append(RUBBER)
    o = link(bpy.data.objects.new('GT2 belt loop', me), hwc)
    o.parent = HW
    return o


BELT = build_belt()
# per-loop belt position (mm) with the loop seam unwrapped, and a height coordinate that is
# 0..1 on the smooth outer face and -1 on the toothed inner face
_li = np.zeros(len(BELT.data.loops), dtype=np.int64); BELT.data.loops.foreach_get('vertex_index', _li)
_face_of_loop = np.arange(len(BELT.data.loops)) // 4          # every face is a quad
_first_sample = _li[_face_of_loop * 4] // 4
_samp = _li // 4
_wrap = (_samp == 0) & (_first_sample == len(BELT_S) - 1)
LOOP_S = BELT_S[_samp] + np.where(_wrap, S_TOTAL, 0.)
LOOP_V = np.array([1., 0., -1., -1.])[_li % 4]
# print pattern: short pale dashes every 30 mm, like the lot print on a real belt
_n, _l = RUBBER.node_tree.nodes, RUBBER.node_tree.links
_uv = _n.new('ShaderNodeUVMap'); _sep = _n.new('ShaderNodeSeparateXYZ'); _l.new(_uv.outputs['UV'], _sep.inputs[0])
_w = _n.new('ShaderNodeMath'); _w.operation = 'WRAP'; _w.inputs[1].default_value = 0; _w.inputs[2].default_value = 30
_l.new(_sep.outputs['X'], _w.inputs[0])
_d1 = _n.new('ShaderNodeMapRange'); _d1.interpolation_type = 'STEPPED'
_m1 = _n.new('ShaderNodeMath'); _m1.operation = 'LESS_THAN'; _m1.inputs[1].default_value = 5.
_m2 = _n.new('ShaderNodeMath'); _m2.operation = 'COMPARE'; _m2.inputs[1].default_value = 8.5; _m2.inputs[2].default_value = 1.2
_l.new(_w.outputs[0], _m1.inputs[0]); _l.new(_w.outputs[0], _m2.inputs[0])
_or = _n.new('ShaderNodeMath'); _or.operation = 'MAXIMUM'; _l.new(_m1.outputs[0], _or.inputs[0]); _l.new(_m2.outputs[0], _or.inputs[1])
_vb = _n.new('ShaderNodeMath'); _vb.operation = 'COMPARE'; _vb.inputs[1].default_value = .5; _vb.inputs[2].default_value = .17
_l.new(_sep.outputs['Y'], _vb.inputs[0])
_mk = _n.new('ShaderNodeMath'); _mk.operation = 'MULTIPLY'; _l.new(_or.outputs[0], _mk.inputs[0]); _l.new(_vb.outputs[0], _mk.inputs[1])
_mc = _n.new('ShaderNodeMix'); _mc.data_type = 'RGBA'
_mc.inputs['A'].default_value = (.008, .008, .009, 1); _mc.inputs['B'].default_value = (.55, .55, .52, 1)
_l.new(_mk.outputs[0], _mc.inputs['Factor']); _l.new(_mc.outputs['Result'], _n['Principled BSDF'].inputs['Base Color'])


def update_belt(b):
    q = ((BELT_S - b) % 2.0) / 2.0
    th = np.where(BELT_FINE, tooth_profile(q), TOOTH_H * .45)
    P, N = BELT_P, BELT_N
    outer = P + N * BELT_BACK
    inner = P - N * th[:, None]
    v = np.zeros((len(BELT_S), 4, 3))
    v[:, 0, :2] = outer; v[:, 0, 2] = BELT_Z1
    v[:, 1, :2] = outer; v[:, 1, 2] = BELT_Z0
    v[:, 2, :2] = inner; v[:, 2, 2] = BELT_Z0
    v[:, 3, :2] = inner; v[:, 3, 2] = BELT_Z1
    BELT.data.vertices.foreach_set('co', v.reshape(-1))
    uvs = np.stack([LOOP_S - b, LOOP_V], 1).astype(np.float32)
    BELT.data.uv_layers['UVMap'].data.foreach_set('uv', uvs.reshape(-1))
    BELT.data.update()


# ---- gliders and master carriers ---------------------------------------------------------
def glider(name, material=NYLON):
    root = empty(name, hwc, HW)
    box(name + ' body', (-GLIDER_HALF, YC - 5.5, TRACK_Z0 + 1.6), (GLIDER_HALF, YC + 5.5, TRACK_Z0 + 8.5), material, .9, hwc, root)
    box(name + ' stem', (-1.8, YC - 1.8, TRACK_Z0 - 4), (1.8, YC + 1.8, TRACK_Z0 + 1.7), material, .4, hwc, root)
    bpy.ops.mesh.primitive_torus_add(major_radius=3.0, minor_radius=.9, major_segments=32, minor_segments=10,
                                     location=(0, YC, TRACK_Z0 - 6.2), rotation=(0, 0, 0))
    t = bpy.context.object; t.name = name + ' eyelet'; t.rotation_euler = (0, math.pi / 2, 0)
    t.data.materials.append(material)
    for c in t.users_collection:
        c.objects.unlink(t)
    hwc.objects.link(t); t.parent = root
    for f in t.data.polygons:
        f.use_smooth = True
    # stainless hook from the eyelet to the heading tape
    curve(name + ' hook', [(0, YC, TRACK_Z0 - 7), (0, YC - 1.5, TRACK_Z0 - 9.5), (0, YC - 2.5, HOOK_Z + 3), (0, YC - 1.5, HOOK_Z - 2)], .45, STEEL, hwc, root)
    return root


def master(name, side):
    """side -1: left panel (clamps the front belt run), +1: right panel (back run)"""
    root = empty(name, hwc, HW)
    xa, xb = (-GLIDER_HALF, 4.0) if side < 0 else (-4.0, GLIDER_HALF)
    box(name + ' body', (xa, YC - 12, TRACK_Z0 + 1.6), (xb, YC + 12, TRACK_Z0 + 12), GRAPHITE, .8, hwc, root)
    fy = (YC - 11.5, YC - 4.6) if side < 0 else (YC + 4.6, YC + 11.5)
    box(name + ' belt clamp', (xa + .5, fy[0], BELT_Z0 - 1.2), (xb - .5, fy[1], BELT_Z1 + 1.5), GRAPHITE, .5, hwc, root)
    box(name + ' stem', (xa + 1, YC - 1.8, TRACK_Z0 - 4), (xb - 1, YC + 1.8, TRACK_Z0 + 1.7), GRAPHITE, .4, hwc, root)
    # the visible drop arm that carries the leading edge of the panel
    box(name + ' drop arm', (xa, YC - 3.2, HOOK_Z - 6), (xb, YC + 3.2, TRACK_Z0 - 3.5), GRAPHITE, 1.0, hwc, root)
    # overlap arm: wraps under the track and up its front face; this is the part that
    # runs into the end-stop thumb screw when the panel is fully open
    box(name + ' arm under track', (xa, YC - 17.6, TRACK_Z0 - 4.5), (xb, YC + 1, TRACK_Z0 - 2.2), GRAPHITE, .7, hwc, root)
    box(name + ' front tab', (xa, YC - 17.6, TRACK_Z0 - 4.5), (xb, YC - 15.4, TRACK_Z1 - 10.5), GRAPHITE, .7, hwc, root)
    return root


GLIDERS_L = [glider('Left glider %02d' % k) for k in range(N_WAVES)]
GLIDERS_R = [glider('Right glider %02d' % k) for k in range(N_WAVES)]
MASTER_L = master('Left master carrier', -1)
MASTER_R = master('Right master carrier', +1)


# ---- curtains: ripple-fold panels, rebuilt per frame from the carrier positions -----------
NU, NV = 1500, 64
FAB_TOP = W((0, 0, HOOK_Z)).z
FAB_BOT = .014
rng = np.random.default_rng(5)
FOLD_VAR = {s: 1 + .10 * rng.standard_normal(N_WAVES) for s in (-1, 1)}
FOLD_PHASE = {s: rng.uniform(0, 6.28, N_WAVES) for s in (-1, 1)}


def panel_mesh(name):
    me = bpy.data.meshes.new(name)
    verts = np.zeros((NU * NV, 3))
    faces = [(j * NU + i, j * NU + i + 1, (j + 1) * NU + i + 1, (j + 1) * NU + i) for j in range(NV - 1) for i in range(NU - 1)]
    me.from_pydata(verts.tolist(), [], faces)
    uvl = me.uv_layers.new(name='UVMap')
    uvs = np.zeros((len(me.loops), 2))
    li = np.zeros(len(me.loops), dtype=np.int64); me.loops.foreach_get('vertex_index', li)
    uu = (li % NU) / (NU - 1); vv = (li // NU) / (NV - 1)
    uvs[:, 0] = uu; uvs[:, 1] = vv
    uvl.data.foreach_set('uv', uvs.reshape(-1))
    for f in me.polygons:
        f.use_smooth = True
    me.materials.append(LINEN)
    o = link(bpy.data.objects.new(name, me), curt)
    tx = bpy.data.textures.get('Linen wrinkles') or bpy.data.textures.new('Linen wrinkles', 'CLOUDS')
    tx.noise_scale = .035; tx.noise_depth = 3
    dp = o.modifiers.new('Soft wrinkles', 'DISPLACE'); dp.texture = tx; dp.texture_coords = 'UV'
    dp.strength = .007; dp.mid_level = .5
    so = o.modifiers.new('Linen thickness', 'SOLIDIFY'); so.thickness = .0008; so.offset = 0
    return o


PANEL_L, PANEL_R = panel_mesh('Linen curtain, left panel'), panel_mesh('Linen curtain, right panel')


def panel_shape(span_m, side):
    """Serpentine ripple fold: n waves of two semicircles joined by straight runs.
    span_m: panel width along the track (m). side -1 left (grows +x), +1 right."""
    L = FABRIC_W
    Lw = L / N_WAVES
    lam = span_m / N_WAVES
    r = lam / 4
    u = np.linspace(0, L, NU)
    k = np.minimum((u / Lw).astype(int), N_WAVES - 1)
    s_nom = u - k * Lw
    zs = np.linspace(FAB_TOP, FAB_BOT, NV)
    zn = (zs - FAB_BOT) / (FAB_TOP - FAB_BOT)                 # 1 at top
    X = np.zeros((NV, NU)); Y = np.zeros((NV, NU))
    h0 = max((Lw - math.pi * lam / 2) / 4, 0.)
    for j in range(NV):
        relax = 1 + .10 * (1 - zn[j]) ** 1.5                    # folds open slightly towards the hem
        wob = 1 + .05 * np.sin(FOLD_PHASE[side][k] + 5 * zn[j])
        h = h0 * FOLD_VAR[side][k] * relax * wob
        segs = np.stack([h, np.full_like(h, math.pi * r), 2 * h, np.full_like(h, math.pi * r), h], 1)
        tot = segs.sum(1)
        s = s_nom * tot / Lw
        c = np.cumsum(segs, 1)
        x = np.zeros(NU); y = np.zeros(NU)
        m0 = s < c[:, 0]
        x[m0] = 0; y[m0] = s[m0]
        m1 = (s >= c[:, 0]) & (s < c[:, 1])
        ph = (s[m1] - c[m1, 0]) / r
        x[m1] = r - r * np.cos(ph); y[m1] = h[m1] + r * np.sin(ph)
        m2 = (s >= c[:, 1]) & (s < c[:, 2])
        x[m2] = 2 * r; y[m2] = h[m2] - (s[m2] - c[m2, 1])
        m3 = (s >= c[:, 2]) & (s < c[:, 3])
        ph = (s[m3] - c[m3, 2]) / r
        x[m3] = 3 * r - r * np.cos(ph); y[m3] = -h[m3] - r * np.sin(ph)
        m4 = s >= c[:, 3]
        x[m4] = 4 * r; y[m4] = -h[m4] + (s[m4] - c[m4, 3])
        X[j] = k * lam + x
        Y[j] = y
    return X, Y, zs


LED_GLOW = .015


def set_state(b, led=0.):
    """b: belt travel from fully open (mm). Moves belt, pulleys, carriers and fabric."""
    b = float(np.clip(b, 0, TRAVEL))
    update_belt(b)
    ang = b / R_PITCH
    PULLEY.rotation_euler.z = ang
    IDLER.rotation_euler.z = ang
    span = SPAN_OPEN + b                     # mm
    lam = span / N_WAVES
    for k, g in enumerate(GLIDERS_L):
        g.location = (X0_LEFT + k * lam, 0, 0)
    for k, g in enumerate(GLIDERS_R):
        g.location = (X0_RIGHT - k * lam, 0, 0)
    MASTER_L.location = (X0_LEFT + span, 0, 0)
    MASTER_R.location = (X0_RIGHT - span, 0, 0)
    yc_w = W((0, YC, 0)).y
    for side, obj, x0 in ((-1, PANEL_L, X0_LEFT), (1, PANEL_R, X0_RIGHT)):
        X, Y, zs = panel_shape(span / 1000, side)
        xw = W((x0, 0, 0)).x + (X if side < 0 else -X)
        yw = yc_w - 0.004 + Y * (1 if side < 0 else -1) * -1
        co = np.zeros((NV, NU, 3))
        co[..., 0] = xw; co[..., 1] = yw; co[..., 2] = zs[:, None]
        obj.data.vertices.foreach_set('co', co.reshape(-1))
        obj.data.update()
    LED_BSDF.inputs['Emission Strength'].default_value = 60. * led
    LED_LIGHT.data.energy = LED_GLOW * led
    bpy.context.view_layer.update()


# ----------------------------------------------------------------------------------------
# Lights, world, render settings
# ----------------------------------------------------------------------------------------
def aim(o, target):
    o.rotation_euler = (Vector(target) - o.location).to_track_quat('-Z', 'Y').to_euler()


world = bpy.data.worlds.new('Overcast-bright sky'); scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes['Background']
sky_grad = world.node_tree.nodes.new('ShaderNodeTexGradient')
wtc = world.node_tree.nodes.new('ShaderNodeTexCoord')
wsep = world.node_tree.nodes.new('ShaderNodeSeparateXYZ')
wr = world.node_tree.nodes.new('ShaderNodeValToRGB')
world.node_tree.links.new(wtc.outputs['Generated'], wsep.inputs[0])
world.node_tree.links.new(wsep.outputs['Z'], wr.inputs[0])
wr.color_ramp.elements[0].position = .5; wr.color_ramp.elements[0].color = (.85, .82, .74, 1)
wr.color_ramp.elements[1].position = .75; wr.color_ramp.elements[1].color = (.42, .56, .80, 1)
world.node_tree.links.new(wr.outputs[0], bg.inputs['Color'])
bg.inputs['Strength'].default_value = 3.0

sun_d = bpy.data.lights.new('Sun', 'SUN'); sun_d.energy = 4.2; sun_d.angle = math.radians(1.5); sun_d.color = (1., .93, .82)
sun = link(bpy.data.objects.new('Low afternoon sun', sun_d), room)
sun.rotation_euler = Vector((-.45, -.78, -.50)).to_track_quat('-Z', 'Y').to_euler()
portal_d = bpy.data.lights.new('Window portal', 'AREA'); portal_d.shape = 'RECTANGLE'
portal_d.size = 2 * WX; portal_d.size_y = WZ1 - WZ0; portal_d.cycles.is_portal = True
portal = link(bpy.data.objects.new('Window portal', portal_d), room)
portal.location = (0, WT - .01, (WZ0 + WZ1) / 2); portal.rotation_euler = (math.radians(-90), 0, 0)
fill_d = bpy.data.lights.new('Warm room bounce', 'AREA'); fill_d.size = 2.5; fill_d.energy = 110; fill_d.color = (1., .92, .82)
fill = link(bpy.data.objects.new('Warm room bounce (behind camera)', fill_d), room)
fill.location = (0, -4.6, 2.3); aim(fill, (0, 0, 1.2))

scene.render.engine = 'CYCLES'
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 8
scene.cycles.diffuse_bounces = 4
scene.cycles.glossy_bounces = 3
scene.cycles.transmission_bounces = 4
scene.cycles.transparent_max_bounces = 8
scene.cycles.sample_clamp_indirect = 8
scene.view_settings.view_transform = 'AgX'
scene.view_settings.exposure = .55
try:
    scene.view_settings.look = 'AgX - Medium High Contrast'
except Exception:
    pass
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_depth = '8'


def use_gpu(sc):
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for t in ('OPTIX', 'CUDA'):
        try:
            prefs.compute_device_type = t
            prefs.get_devices()
            ok = [d for d in prefs.devices if d.type == t]
            if ok:
                for d in prefs.devices:
                    d.use = d.type == t
                sc.cycles.device = 'GPU'
                print('GPU', t, [d.name for d in ok], flush=True)
                return t
        except Exception as e:
            print('GPU try failed', t, e)
    return 'CPU'


use_gpu(scene)


def camera(name, loc, target, lens, sc=None, coll=None):
    cd = bpy.data.cameras.new(name); cd.lens = lens; cd.clip_start = .005; cd.clip_end = 200
    o = link(bpy.data.objects.new(name, cd), coll or scene.collection)
    o.location = loc; aim(o, target)
    return o


def arch_camera(name, loc, look_x, lens, shift_y, shift_x=0.):
    """Level camera (vertical lines stay vertical), framed with lens shift."""
    o = camera(name, loc, (look_x, 0, loc[2]), lens)
    o.data.shift_y = shift_y; o.data.shift_x = shift_x
    return o


import os
_hc = [float(v) for v in os.environ.get('HERO_CAM', '-1.55,-2.45,1.38,-.45,0,1.78,22').split(',')]
CAM_HERO = camera('01 hero, room', tuple(_hc[:3]), tuple(_hc[3:6]), _hc[6])
CAM_CLOSE = camera('02 drive close-up', W((-165, -215, 138)), W((60, 32, -6)), 48)
CAM_ROOMGIF = arch_camera('04 curtains GIF', (-1.50, -3.05, 1.32), .60, 20, .03)
CAM_DRIVEGIF = camera('05 drive GIF', W((152, -228, -40)), W((137, 20, -24)), 29)
for c in (CAM_CLOSE, CAM_DRIVEGIF):
    c.data.dof.use_dof = True
    c.data.dof.aperture_fstop = 11
CAM_CLOSE.data.dof.focus_distance = (CAM_CLOSE.location - W((30, 20, 10))).length
CAM_DRIVEGIF.data.dof.focus_distance = (CAM_DRIVEGIF.location - W((130, 0, -15))).length
CAM_DRIVEGIF.data.dof.aperture_fstop = 8
CEILING = bpy.data.objects['Ceiling']
kd = bpy.data.lights.new('Close-up soft key', 'AREA'); kd.shape = 'DISK'; kd.size = .30; kd.energy = 3.5; kd.color = (1., .95, .88)
CLOSE_KEY = link(bpy.data.objects.new('Close-up soft key (close-ups only)', kd), hwc)
CLOSE_KEY.location = W((-320, -330, 60)); aim(CLOSE_KEY, W((60, 40, 0)))
CLOSE_KEY.visible_camera = False


def ceiling_visible(v):
    """Close-ups look down at the lid from above ceiling height, product-photo style:
    the ceiling still lights and shadows the scene but is hidden from the camera."""
    CEILING.visible_camera = v
    CLOSE_KEY.hide_render = v
    scene.view_settings.exposure = .55 if v else .15
    for o in hwc.objects:
        if o.name.startswith('Ceiling rosette'):
            o.visible_camera = v


# ----------------------------------------------------------------------------------------
# INSIDE scene: table-top product shot, lid lifted off
# ----------------------------------------------------------------------------------------
def build_inside():
    """Table-top product shot. Everything in box coordinates (mm) under one empty; the
    table top is at z = -6.5 because the base stands on its wall bracket's arms."""
    sc = bpy.data.scenes.new('Inside (table top)')
    sc.unit_settings.system = 'METRIC'
    col = bpy.data.collections.new('Inside'); sc.collection.children.link(col)
    sc.render.engine = 'CYCLES'
    sc.cycles.use_denoising = True
    sc.cycles.sample_clamp_indirect = 8
    sc.view_settings.view_transform = 'AgX'
    try:
        sc.view_settings.look = 'AgX - Medium High Contrast'
    except Exception:
        pass
    use_gpu(sc)
    wd = bpy.data.worlds.new('Studio daylight'); wd.use_nodes = True
    wd.node_tree.nodes['Background'].inputs[0].default_value = (.60, .58, .55, 1)
    wd.node_tree.nodes['Background'].inputs[1].default_value = .25
    sc.world = wd
    E = empty('Drive, mm', col)
    E.matrix_world = Matrix.Diagonal((.001, .001, .001, 1))
    T = -6.5
    desk = mat('Warm grey desk linoleum', (.34, .32, .29), .6, bump=40, bump_strength=.04)
    box('Desk top', (-700, -500, T - 30), (800, 520, T), desk, 3, col, E)
    box('Plaster wall', (-1500, 520, T - 500), (1500, 650, 1500), PLASTER, 0, col, E)
    lidm = Matrix.Translation((-92, 92, T + 2.0)) @ Matrix.Rotation(math.radians(8), 4, 'Z') @ Matrix.Translation((-43, -49, 0))
    base, lid, lidp, pcb = build_unit(col, E, lidm, led_light=False)
    for o in list(bracket):
        c = o.copy(); col.objects.link(c); c.parent = E
    for xs in (-5.0, 91.0):
        cyl('Ear screw head', (xs, EAR_Y, 0), 3.8, FLOOR_T, FLOOR_T + 2.4, STEEL, 32, .5, col, E)
        cyl('Ear washer', (xs, EAR_Y, 0), 5.0, FLOOR_T - .01, FLOOR_T + .6, STEEL, 32, .2, col, E)
    # spare pulley, hub up, and a belt loop lying on the table
    P2 = empty('Pulley (loose)', col, E)
    P2.matrix_basis = Matrix.Translation((-38, -40, T + 15.5)) @ Matrix.Rotation(.4, 4, 'Z')
    for o in PULLEY.children:
        c = o.copy(); col.objects.link(c); c.parent = P2
    th = np.linspace(0, 2 * math.pi, 17)[:-1]
    pts = [(-78 + 30 * math.cos(t), -18 + 11 * math.sin(t) + 2 * math.sin(2 * t), T + 3) for t in th]
    bl = curve('GT2 belt (spare loop)', pts, 0, RUBBER, col, E)
    bl.data.bevel_depth = 0; bl.data.extrude = 3.0
    bl.data.splines[0].use_cyclic_u = True
    so = bl.modifiers.new('thickness', 'SOLIDIFY'); so.thickness = 1.4
    for i, (xs, ys) in enumerate([(-8, -62), (6, -58)]):
        cyl('Spare M4 screw', (xs, ys + i * 3, T + 2.2), 2.1, -8, 0, STEEL, 24, .3, col, E, axis='X')
        cyl('Spare M4 screw head', (xs, ys + i * 3, T + 3.6), 3.6, 0, 2.6, STEEL, 32, .4, col, E, axis='X')
    kd = bpy.data.lights.new('Window softbox', 'AREA'); kd.shape = 'RECTANGLE'; kd.size = .9; kd.size_y = .6; kd.energy = 55
    kd.color = (1., .95, .88)
    k = link(bpy.data.objects.new('Window softbox', kd), col); k.location = (-.45, .30, .45); aim(k, (.0, .03, 0))
    rd = bpy.data.lights.new('Rim', 'AREA'); rd.size = .4; rd.energy = 14; rd.color = (1, .9, .8)
    r = link(bpy.data.objects.new('Rim', rd), col); r.location = (.45, .45, .35); aim(r, (.06, .04, .02))
    fd = bpy.data.lights.new('Fill', 'AREA'); fd.size = 1.2; fd.energy = 16; fd.color = (.95, .97, 1.)
    f = link(bpy.data.objects.new('Fill', fd), col); f.location = (.25, -.75, .45); aim(f, (.05, 0, 0))
    cam = camera('03 inside', (.215, -.255, .235), (.010, .030, .004), 58, coll=col)
    cam.data.dof.use_dof = True; cam.data.dof.aperture_fstop = 9
    cam.data.dof.focus_distance = (cam.location - Vector((.045, .03, .02))).length
    sc.camera = cam
    return sc


INSIDE = build_inside()
bpy.context.window.scene = scene
scene.camera = CAM_HERO


# ----------------------------------------------------------------------------------------
# Render
# ----------------------------------------------------------------------------------------
def render_to(sc, cam, path, size, samples):
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = size
    sc.render.resolution_percentage = 50 if PREVIEW else 100
    sc.cycles.samples = int(opt('--samples', 0)) or (max(16, samples // 8) if PREVIEW else samples)
    sc.render.filepath = str(path)
    bpy.context.window.scene = sc
    import time
    t = time.time()
    bpy.ops.render.render(write_still=True, scene=sc.name)
    print('RENDERED', path, '%.1fs' % (time.time() - t), flush=True)
    bpy.context.window.scene = scene


def ease(t):
    return t * t * (3 - 2 * t)


def move_profile(t, t0, t1, ramp=.35):
    """0..1 over [t0, t1]: short motor ramp-up, constant speed, hard stop (stall)."""
    if t <= t0:
        return 0.
    if t >= t1:
        return 1.
    T = t1 - t0; x = t - t0
    v = 1 / (T - ramp / 2)
    if x < ramp:
        return v * x * x / (2 * ramp)
    return min(1., v * (ramp / 2 + (x - ramp)))


def room_state(t):
    """6.5 s loop: open, close, pause, open (time-lapse, about 14x real speed)."""
    c = move_profile(t, .50, 2.50)
    o = move_profile(t, 4.00, 6.00)
    b = TRAVEL * (c - o)
    led = 1. if (.45 <= t < 2.65 or 3.95 <= t < 6.15) else 0.
    return b, led


def drive_state(t):
    """6 s loop at the drive: master arrives at the stack and stalls, pause, leaves again."""
    far = 175.0                                    # mm of travel shown
    a = move_profile(t, .25, 2.55, ramp=.3)       # opening: b goes far -> 0, stall at 0
    d = t - 4.0
    if d <= 0:
        back = 0.
    elif d >= 1.8:
        back = 1.
    else:
        back = ease(d / 1.8)                      # closing again, gentle stop off-frame
    b = far * (1 - a) + far * back
    led = 1. if (.2 <= t < 2.75 or 3.95 <= t < 5.85) else 0.
    return b, led


if MODE == 'stills':
    only = (opt('--only') or 'hero,closeup,inside').split(',')
    set_state(TRAVEL * .42, led=1.)
    ceiling_visible(True)
    scene.camera = CAM_HERO
    bpy.ops.wm.save_as_mainfile(filepath=str(HERE / 'curtain_showcase.blend'), check_existing=False)
    sfx = '-preview' if PREVIEW else ''
    if 'hero' in only:
        render_to(scene, CAM_HERO, HERE / ('hero%s.png' % sfx), (2000, 1400), 384)
    if 'closeup' in only:
        set_state(TRAVEL * .42, led=1.)
        ceiling_visible(False)
        render_to(scene, CAM_CLOSE, HERE / ('drive-closeup%s.png' % sfx), (1800, 1500), 384)
        ceiling_visible(True)
    if 'inside' in only:
        render_to(INSIDE, INSIDE.camera, HERE / ('inside%s.png' % sfx), (1800, 1400), 384)

elif MODE == 'gif':
    which = argv[1]
    fps = 12
    if which == 'room':
        n, fn, cam, size, out = 78, room_state, CAM_ROOMGIF, (720, 504), HERE / 'frames-room'
        ceiling_visible(True)
    else:
        n, fn, cam, size, out = 72, drive_state, CAM_DRIVEGIF, (720, 600), HERE / 'frames-drive'
        ceiling_visible(True)
        CLOSE_KEY.hide_render = False
        LED_GLOW = .0
        scene.render.use_motion_blur = True
        scene.render.motion_blur_shutter = .5
    out.mkdir(exist_ok=True)
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.cycles.samples = int(opt('--samples', 0)) or (24 if PREVIEW else 80)
    scene.render.use_persistent_data = True
    frames = [int(f) for f in opt('--frames').split(',')] if opt('--frames') else range(1, n + 1)
    import time
    t0 = time.time()
    for f in frames:
        t = (f - 1) / fps
        # motion blur needs the neighbouring sub-frame state: render with state at t,
        # and give Blender keyframes at f-0.5/f+0.5 is overkill; blur only the pulley.
        b, led = fn(t)
        set_state(b, led)
        if which == 'drive':
            # motion blur for the spinning pulley only: key its angle half a frame either side
            PULLEY.animation_data_clear()
            for df in (-.5, .5):
                bb, _ = fn(t + df / fps)
                PULLEY.rotation_euler.z = min(max(bb, 0), TRAVEL) / R_PITCH
                PULLEY.keyframe_insert('rotation_euler', index=2, frame=f + df)
        scene.frame_set(f)
        scene.render.filepath = str(out / ('%04d.png' % f))
        bpy.ops.render.render(write_still=True)
        print('FRAME', f, 'b=%.1f' % b, 'led', led, '%.1fs' % (time.time() - t0), flush=True)
    print('GIF_FRAMES_DONE', which, len(list(frames)), '%.1fs' % (time.time() - t0), flush=True)
