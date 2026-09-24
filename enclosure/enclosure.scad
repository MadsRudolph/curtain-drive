// Curtain Drive -- enclosure for the curtain-drive PCB + one DM-S2000MD servo
//
// Two printed parts: `base` (holds the servo and the PCB) and `lid`.
// Render one part or the assembly:
//   openscad -D 'part="base"'     -o base.stl enclosure.scad
//   openscad -D 'part="lid"'      -o lid.stl  enclosure.scad
//   openscad -D 'part="assembly"' -o view.png enclosure.scad
//
// Layout (top view, +x right, +y towards the servo):
//   back wall ----- PCB (70 x 48, antenna edge at the back wall) -----
//                   servo, output shaft pointing DOWN through the floor
//   The pulley sits below the box; the servo horn boss passes through `shaft_hole_d`.
// Print: base upside down is NOT needed -- both parts print flat, no supports.

part = "assembly";          // "base" | "lid" | "assembly"
$fn = 48;

// ---------------- PCB (from hardware/tools/pcb_layout.py) ----------------
pcb_w   = 70;
pcb_l   = 48;
pcb_t   = 1.6;
pcb_holes = [[3.5, 3.5], [66.5, 3.5], [3.5, 44.5], [66.5, 44.5]];   // M2.5
standoff_h = 5;
part_h_max = 11;           // tallest part on the PCB (8 mm electrolytic)
// connector positions on the PCB edges (board coordinates)
jack_y    = 33;   jack_w = 12;  jack_h = 12;     // barrel jack, left edge  (x = 0)
usb_y     = 12.5;   usb_w  = 10;  usb_h  = 4.5;    // USB-C, right edge       (x = 70)
sw_xy     = [[17, 6], [17, 14], [17, 22]];       // RESET, BOOT, USER tact switches
led_xy    = [8, 14];
button_hole_d = 4.5;
led_hole_d    = 3.2;

// ---------------- Servo: DM-S2000MD (standard size) -- MEASURE YOURS ----------------
servo_l   = 40.5;          // case length
servo_w   = 20.2;          // case width
servo_h   = 38.5;          // case height, shaft-side face to the far end (without shaft)
top_to_flange = 9.5;       // shaft-side face to the underside of the mounting flange
flange_t  = 2.5;
flange_span = 54.5;        // over both flanges
hole_dx   = 49;            // mounting hole spacing along the length
hole_dy   = 10;            // mounting hole spacing across
servo_screw_d = 2.6;       // pilot hole for M3 self tapping (the servo's own screws)
shaft_from_end = 10;       // shaft centre from the nearest end of the case
shaft_hole_d = 12;         // clearance in the floor for the horn / pulley boss

// ---------------- Box ----------------
wall     = 2;
floor_t  = 2.5;
lid_t    = 2;
clr      = 1;              // clearance around the PCB and the servo
gap      = 8;              // PCB to servo compartment (room for the side lid posts)
corner_r = 3;
post_d   = 6;              // lid screw posts, M2.5 self tapping
post_hole_d = 2.2;
ear_slot_w = 4.5;          // wall / track mounting slots on the two ears
ear_l    = 10;             // ear length beyond the wall
fuse     = 1;              // overlap between the shell and features unioned onto it

inner_x = max(pcb_w, flange_span) + 2 * clr;
inner_y = pcb_l + 2 * clr + gap + servo_w + 2 * clr;
inner_z = max(servo_h + 1.5, standoff_h + pcb_t + part_h_max + 1);
outer_x = inner_x + 2 * wall;
outer_y = inner_y + 2 * wall;
outer_z = floor_t + inner_z;

// positions inside the box (box origin = outer corner, floor level z = 0)
pcb_x0 = wall + clr + (inner_x - 2 * clr - pcb_w) / 2;
pcb_y0 = wall + clr;
servo_cx = wall + inner_x / 2;
servo_cy = wall + clr + pcb_l + clr + gap + clr + servo_w / 2;
shaft_x  = servo_cx - servo_l / 2 + shaft_from_end;

module rrect(x, y, r, h) {
    linear_extrude(h) offset(r) offset(-r) square([x, y]);
}

// Lid screw posts: two in the back corners (beside the servo flanges, which are
// shorter than the box) and two on the side walls in the gap between PCB and servo.
// The PCB corners are left free -- its own holes sit 3.5 mm from its edges.
gap_y = wall + clr + pcb_l + clr + gap / 2;
module lid_posts(h) {
    // posts sink `fuse`/2 into the walls so they merge with the shell instead of just touching it
    pi = wall + post_d/2 - fuse/2;
    for (p = [[pi, gap_y], [outer_x - pi, gap_y], [pi, outer_y - pi], [outer_x - pi, outer_y - pi]])
        translate([p[0], p[1], 0]) children();
}

module base() {
    difference() {
        union() {
            // shell
            difference() {
                rrect(outer_x, outer_y, corner_r, outer_z);
                translate([wall, wall, floor_t]) rrect(inner_x, inner_y, corner_r - wall, inner_z + 1);
            }
            // PCB standoffs
            for (h = pcb_holes)
                translate([pcb_x0 + h[0], pcb_y0 + h[1], floor_t - 0.01]) cylinder(d = 6, h = standoff_h);
            // servo flange bosses (the flange rests on these, screws go down into them)
            for (sx = [-1, 1], sy = [-1, 1])
                translate([servo_cx + sx * hole_dx / 2, servo_cy + sy * hole_dy / 2, floor_t - 0.01])
                    cylinder(d = 7, h = top_to_flange);
            // servo side cradles keep the case from rocking
            for (sy = [-1, 1])
                translate([servo_cx - servo_l/2 - 0.5, servo_cy + sy * (servo_w/2 + 1) - 1, floor_t - 0.01])
                    cube([servo_l + 1, 2, top_to_flange]);
            // lid screw posts
            lid_posts(inner_z) cylinder(d = post_d, h = floor_t + inner_z - 0.01);
            // mounting ears (wall / track screws), left and right
            for (sx = [0, 1])
                translate([sx ? outer_x - fuse : -ear_l, outer_y/2 - 12, 0]) rrect(ear_l + fuse, 24, 2, floor_t);
        }
        // servo screw pilot holes
        for (sx = [-1, 1], sy = [-1, 1])
            translate([servo_cx + sx * hole_dx / 2, servo_cy + sy * hole_dy / 2, floor_t + 1])
                cylinder(d = servo_screw_d, h = top_to_flange);
        // shaft / horn boss through the floor
        translate([shaft_x, servo_cy, -1]) cylinder(d = shaft_hole_d, h = floor_t + 2);
        // PCB standoff screw holes
        for (h = pcb_holes)
            translate([pcb_x0 + h[0], pcb_y0 + h[1], floor_t + 1]) cylinder(d = 2.2, h = standoff_h);
        // lid post holes
        lid_posts(0) translate([0, 0, outer_z - 8]) cylinder(d = post_hole_d, h = 9);
        // barrel jack cut-out, left wall
        translate([-1, pcb_y0 + jack_y - jack_w/2, floor_t + standoff_h - 1])
            cube([wall + 2, jack_w, jack_h]);
        // USB-C cut-out, right wall
        translate([outer_x - wall - 1, pcb_y0 + usb_y - usb_w/2, floor_t + standoff_h + pcb_t - 0.5])
            cube([wall + 2, usb_w, usb_h]);
        // encoder / spare cable slot, front wall (servo side)
        translate([servo_cx + servo_l/2 + 2, outer_y - wall - 1, floor_t + 2]) cube([8, wall + 2, 5]);
        // mounting ear slots
        for (sx = [0, 1])
            hull() for (dy = [-6, 6])
                translate([sx ? outer_x + ear_l/2 : -ear_l/2, outer_y/2 + dy, -1]) cylinder(d = ear_slot_w, h = floor_t + 2);
        // vent slots above the driver side
        for (i = [0 : 4])
            translate([wall + 8 + i * 6, -1, outer_z - 8]) cube([2.5, wall + 2, 6]);
    }
}

module lid() {
    difference() {
        union() {
            rrect(outer_x, outer_y, corner_r, lid_t);
            // locating lip
            translate([wall + 0.3, wall + 0.3, lid_t - 0.01])
                difference() {
                    rrect(inner_x - 0.6, inner_y - 0.6, corner_r - wall, 2);
                    translate([wall, wall, -1]) rrect(inner_x - 0.6 - 2 * wall, inner_y - 0.6 - 2 * wall, 1, 4);
                }
        }
        // lid screws
        lid_posts(0) translate([0, 0, -1]) cylinder(d = 2.8, h = lid_t + 4);
        lid_posts(0) translate([0, 0, -0.01]) cylinder(d = 5.5, h = 1.2);   // countersink-ish recess
        // button holes and LED window (lid is mirrored: box y == pcb y, x == pcb x)
        for (s = sw_xy) translate([pcb_x0 + s[0], pcb_y0 + s[1], -1]) cylinder(d = button_hole_d, h = lid_t + 4);
        translate([pcb_x0 + led_xy[0], pcb_y0 + led_xy[1], -1]) cylinder(d = led_hole_d, h = lid_t + 4);
        // label
        translate([outer_x/2, outer_y - 12, lid_t - 0.6]) linear_extrude(1)
            text("CURTAIN DRIVE", size = 5, halign = "center", valign = "center");
    }
}

module servo_model() {
    color("SteelBlue") {
        translate([servo_cx - servo_l/2, servo_cy - servo_w/2, floor_t]) cube([servo_l, servo_w, servo_h]);
        translate([servo_cx - flange_span/2, servo_cy - servo_w/2, floor_t + top_to_flange]) cube([flange_span, servo_w, flange_t]);
        translate([shaft_x, servo_cy, -6]) cylinder(d = 6, h = floor_t + 6);
    }
}

module pcb_model() {
    color("DarkGreen") translate([pcb_x0, pcb_y0, floor_t + standoff_h]) cube([pcb_w, pcb_l, pcb_t]);
}

if (part == "base") base();
else if (part == "lid") lid();
else {
    base();
    servo_model();
    pcb_model();
    // lid lifted and flipped so the assembly is readable
    translate([0, 0, outer_z + 22]) mirror([0, 0, 1]) color("Gainsboro", 0.6) translate([0, 0, -lid_t]) lid();
}

echo(str("outer box = ", outer_x, " x ", outer_y, " x ", outer_z + lid_t, " mm"));
