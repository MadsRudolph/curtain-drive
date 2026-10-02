// Curtain Drive -- cord drive for a centre-opening curtain (rev C drive box).
//
// A winch drum on the servo shaft with TWO cord chambers: one cord end is tied in each
// chamber and they are wound in opposite directions, so one run winds on while the other
// pays out. The loop goes to the idler at the far end of the track and back. Each
// panel's lead runner is clamped to a different run, so the panels always move in
// opposite directions. Nothing can slip, so the motor stalls at the ends and the
// firmware's stall end stop works exactly as it did on the bench.
//
// Render one part:  openscad -D 'part="drum"' -o drum.stl curtain_pulley.scad
// parts: drum | spline_test | idler | idler_bracket | clamp | all
//
// ASSUMPTIONS (not measured -- check them, then adjust below):
//  * The servo (DM-S2000MD) has a standard 25T spline, ~5.9 mm OD, with an M3 centre screw.
//    The socket is a plain hole a little under the spline OD: press the metal spline in
//    (warm the drum with a hair dryer if it's tight) and it cuts its own teeth. Print
//    `spline_test` first and adjust `spline_d` until it's a firm press fit.
//  * The servo sits upside down in the box, its face on the 2.5 mm floor, and the spline
//    comes out through the 12 mm floor hole. The hub goes into that hole.
//  * Braided cord of about 1 mm, and about 1.2 m of travel per panel. At 25 mm core
//    diameter, one turn is ~80 mm of cord, so 1.2 m is ~15 turns. Each chamber holds
//    ~18 turns side by side and more in a second layer.

part = "all";
$fn = 96;

// ---------- drum ----------
core_d       = 24;     // cord winds on this (effective ~25 mm with 1 mm cord)
chamber_h    = 18;     // height of each cord chamber at the core
flange_d     = 38;     // flange outer diameter
flange_flat  = 1.6;    // flat part of each flange (the rest is a 45 deg cone underneath)
base_t       = 2.5;    // bottom flange (on the print bed, no cone)
hub_d        = 11.0;   // goes into the box's 12 mm floor hole
hub_h        = 2.0;    // floor is 2.5 mm: keeps 0.5 mm off the servo face
spline_d     = 5.7;    // press-fit socket for the ~5.9 mm 25T spline (tune with spline_test)
spline_depth = 6.0;
screw_d      = 3.4;    // M3 centre screw through the drum into the servo shaft
screw_floor  = 3.0;    // material under the screw head
access_d     = 7.0;    // bore from the bottom so a hex key reaches the M3 screw
knot_d       = 2.2;    // cord anchor holes through the flanges
knot_pocket  = [5, 3]; // dia, depth: the upper knot sits in this, the top flange is tight to the box floor

// ---------- idler ----------
idler_core_d   = 24;
idler_h        = 44;   // spans both runs (they leave the drum ~20 mm apart in height)
idler_bore     = 5.4;  // M5 bolt as the axle
bracket_t      = 5;
bracket_w      = 40;   // along the track
arm_len        = 46;
bolt_off       = 36;   // idler axis from the wall: flange (r 19) clears the 13 mm gussets by 4 mm
washer_gap     = 3.0;  // a 1 mm M5 washer each side + 1 mm play
slot_len       = 20;   // tensioning slots for the wall screws
wall_screw_d   = 4.5;

// ---------- clamp ----------
cord_d = 1.8;          // channel for ~1 mm cord (loose, the screw pinches it)

cone_h = (flange_d - core_d) / 2;          // 45 deg underside of a flange

module flange_up(z) {  // flange whose underside is a 45 deg cone (prints without support)
    translate([0, 0, z]) {
        cylinder(d1 = core_d, d2 = flange_d, h = cone_h);
        translate([0, 0, cone_h]) cylinder(d = flange_d, h = flange_flat);
    }
}

function drum_h() = base_t + chamber_h + cone_h + flange_flat + chamber_h + cone_h + flange_flat + hub_h;

module drum() {
    zA = base_t + chamber_h + cone_h + flange_flat;       // bottom of the upper chamber
    ztop = zA + chamber_h + cone_h + flange_flat;         // top face of the top flange
    difference() {
        union() {
            cylinder(d = flange_d, h = base_t);                     // bottom flange (bed)
            cylinder(d = core_d, h = ztop);                         // core
            flange_up(base_t + chamber_h);                          // middle flange
            flange_up(zA + chamber_h);                              // top flange
            translate([0, 0, ztop - 0.01]) cylinder(d = hub_d, h = hub_h + 0.01);  // hub
        }
        // spline socket from the top, M3 hole, hex-key access bore from the bottom
        translate([0, 0, drum_h() - spline_depth]) cylinder(d = spline_d, h = spline_depth + 1);
        translate([0, 0, -1]) cylinder(d = screw_d, h = drum_h() + 2);
        translate([0, 0, -1]) cylinder(d = access_d, h = drum_h() - spline_depth - screw_floor + 1);
        // cord anchors: lower chamber through the bottom flange, upper chamber through the
        // top flange; thread the cord out and knot it on the outside
        translate([core_d / 2 + knot_d / 2 + 0.3, 0, -1]) cylinder(d = knot_d, h = base_t + 2, $fn = 24);
        rotate([0, 0, 180]) translate([core_d / 2 + knot_d / 2 + 0.3, 0, zA + chamber_h - 1])
            cylinder(d = knot_d, h = cone_h + flange_flat + 2, $fn = 24);
        rotate([0, 0, 180]) translate([core_d / 2 + knot_d / 2 + 0.3, 0, ztop - knot_pocket[1]])
            cylinder(d = knot_pocket[0], h = knot_pocket[1] + 1, $fn = 32);
        // direction arrows on the bottom so the two windings go on opposite ways
        translate([0, -15.5, -0.01]) linear_extrude(0.6) mirror([1, 0, 0])
            text("A cw  B ccw", size = 2.4, halign = "center", valign = "center");
    }
}

module spline_test() {  // hub + socket only: check the press fit and the reach into the box
    offs = [-0.2, 0, 0.2];
    for (i = [0 : 2]) translate([i * 16, 0, 0]) difference() {
        union() {
            cylinder(d = 14, h = 4);
            translate([0, 0, 3.99]) cylinder(d = hub_d, h = hub_h + 0.01);
        }
        translate([0, 0, 4 + hub_h - spline_depth]) cylinder(d = spline_d + offs[i], h = spline_depth + 1);
        translate([0, 0, -1]) cylinder(d = screw_d, h = 10);
        for (k = [0 : i]) rotate([0, 0, k * 30]) translate([6.2, 0, -0.01]) cylinder(d = 1.2, h = 0.6, $fn = 12);
    }
    // dots on the underside: 1 dot = spline_d - 0.2, 2 = spline_d, 3 = spline_d + 0.2
}

module idler() {
    difference() {
        union() {
            cylinder(d = flange_d, h = base_t);
            cylinder(d = idler_core_d, h = base_t + idler_h + cone_h + flange_flat);
            translate([0, 0, base_t + idler_h]) {
                cylinder(d1 = idler_core_d, d2 = flange_d, h = cone_h);
                translate([0, 0, cone_h]) cylinder(d = flange_d, h = flange_flat);
            }
        }
        translate([0, 0, -1]) cylinder(d = idler_bore, h = 100, $fn = 32);
    }
}

function idler_total_h() = base_t + idler_h + cone_h + flange_flat;

module idler_bracket() {
    // Side profile (plate + two arms + gussets) extruded `bracket_w`, printed lying on its
    // side so the arms are strong along the layers. Installed: the plate goes on the wall
    // at the far end of the track, arms horizontal, the M5 axle vertical through both arms.
    gap = idler_total_h() + washer_gap;
    plate_h = gap + 2 * bracket_t;
    g = 8;                                        // gusset leg
    difference() {
        linear_extrude(bracket_w) {
            square([bracket_t, plate_h]);                                        // wall plate
            square([arm_len, bracket_t]);                                        // lower arm
            translate([0, gap + bracket_t]) square([arm_len, bracket_t]);        // upper arm
            polygon([[bracket_t, bracket_t], [bracket_t + g, bracket_t], [bracket_t, bracket_t + g]]);
            polygon([[bracket_t, gap + bracket_t], [bracket_t + g, gap + bracket_t], [bracket_t, gap + bracket_t - g]]);
        }
        // M5 axle through both arms, `bolt_off` from the wall
        translate([bolt_off, -1, bracket_w / 2]) rotate([-90, 0, 0]) cylinder(d = idler_bore, h = plate_h + 2, $fn = 32);
        // tensioning slots in the plate, running along the track (the extrusion direction)
        for (y = [plate_h * 0.3, plate_h * 0.7])
            hull() for (z = [bracket_w / 2 - slot_len / 2, bracket_w / 2 + slot_len / 2])
                translate([-1, y, z]) rotate([0, 90, 0]) cylinder(d = wall_screw_d, h = bracket_t + 2, $fn = 24);
    }
}

module clamp() {
    // Cord runs through the channel; an M3 screw from the top pinches it (self-taps into
    // the 2.6 mm hole). Hang the curtain's lead runner/hook in the eye underneath.
    difference() {
        union() {
            translate([-9, -5, 0]) cube([18, 10, 9]);
            hull() {
                translate([-4, -5, 0]) cube([8, 10, 0.01]);
                translate([0, -3.01, -10]) rotate([90, 0, 0]) cylinder(d = 10, h = 4.02, center = true);
            }
        }
        translate([-10, 0, 3.2]) rotate([0, 90, 0]) cylinder(d = cord_d, h = 20, $fn = 24);   // cord
        translate([0, 0, 1]) cylinder(d = 2.6, h = 10, $fn = 24);                             // M3 pinch
        translate([0, -3, -10]) rotate([90, 0, 0]) cylinder(d = 5, h = 14, center = true);     // eye (flush with one face so it prints on the bed)
    }
}

module clamp_print() {  // eye flat on the bed for strength across the layers
    rotate([90, 0, 0]) clamp();
}

if (part == "drum") drum();
if (part == "spline_test") spline_test();
if (part == "idler") idler();
if (part == "idler_bracket") idler_bracket();
if (part == "clamp") clamp_print();
if (part == "all") {
    drum();
    translate([50, 0, 0]) idler();
    translate([-40, 30, 0]) idler_bracket();
    translate([-30, -35, 5]) clamp_print();
    translate([-5, -35, 5]) clamp_print();
    translate([20, -40, 0]) spline_test();
}
