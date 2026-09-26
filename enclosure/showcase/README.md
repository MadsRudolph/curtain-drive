# Curtain drive: product showcase

**These are illustrative renders. The curtain drive has not been built yet.** They show
how the finished product is meant to look and work in a home. They are not photos, and
they do not prove fit, strength, speed or reliability.

The scene is a living-room window wall. A ceiling-hung curtain track spans the window, and
two linen panels part from the centre. The drive box sits at the left end of the track on a
small wall bracket. Its pulley pulls a GT2 belt loop to an idler at the far end. One carrier
of each panel is clamped to opposite runs of the belt, so the panels always move in opposite
directions. When a carrier reaches its end stop the motor stalls, the drive reads that from
the motor current and stops, and the status LED goes out.

| File | What it is |
| --- | --- |
| `hero.png` | 2000 × 1400. Window corner of the room, curtains partly open, drive at the track end on the upper-left third. |
| `drive-closeup.png` | 1800 × 1500. The mounted drive: lid, label, LED window, pulley, belt, track end, power lead. |
| `inside.png` | 1800 × 1400. Table-top shot: base with the real KiCad PCB model and servo, lid beside it, spare pulley and belt. |
| `curtains-motion.gif` | 600 × 420, 6.5 s loop at 12 fps (78 frames): open, close, pause, open. Daylight in the room changes with the curtains. |
| `drive-motion.gif` | 640 × 533, 6 s loop at 12 fps (72 frames): pulley and belt turn, the lead carrier arrives and stops against the end-stop screw, the motor stalls and the LED goes out, pause, then it leaves again. |
| `*-poster.png` | Still frame of each GIF, for reduced-motion users. |
| `curtain_showcase.blend` | The whole scene: room, drive, track, curtains, cameras, and a second scene for the table-top shot. |
| `showcase.py` | Builds everything headless and renders the stills or the GIF frames. |
| `make_gifs.sh` | Renders both frame sequences and makes the GIFs and posters. |

## Regenerating

Run from `enclosure/`. Blender 5.2 with Cycles; it uses OptiX if it can, then CUDA, then the CPU.

```sh
blender -b --python showcase/showcase.py -- stills             # hero, drive-closeup, inside + .blend
blender -b --python showcase/showcase.py -- stills --preview   # half size, fewer samples, *-preview.png
blender -b --python showcase/showcase.py -- stills --only hero # just one still
showcase/make_gifs.sh                                          # both GIFs and their posters
```

`make_gifs.sh` runs `showcase.py -- gif room` and `-- gif drive`, which write numbered
720-pixel-wide frames into `frames-room/` and `frames-drive/`. It then builds each GIF with
the surround-mount showcase's palettegen/paletteuse command, plus a light temporal denoise,
a 96–112 colour palette, 12 fps and a slightly smaller width. The daylight change touches
every pixel of every moving frame, so at 720 px and 16 fps with a full palette the room GIF
came out at 15 MB:

```sh
ffmpeg -y -framerate 12 -i showcase/frames-room/%04d.png -filter_complex "[0:v]hqdn3d=0:0:10:10,scale=600:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" -loop 0 showcase/curtains-motion.gif
```

`make_gifs.sh --encode-only` rebuilds the GIFs from frames that are already rendered.

`--frames 1,40,80` renders only some frames, and `--samples N` overrides the sample count.

## What is taken from the design, and what is made up

From the design, unchanged:

- The `Base` and `Lid` meshes are read from `enclosure.blend` and shown as they are.
  `enclosure.blend`, the STLs and the hardware files are never written to. The script only
  scales mm to metres through a parent empty. It marks sharp edges and gives the engraved
  "CURTAIN DRIVE" label a paint fill, but those changes exist only in the showcase file.
- The populated PCB is the KiCad glTF model already inside `enclosure.blend`. Its materials
  are adjusted, because KiCad exports plastic parts as rough metal.
- The servo keeps the DM-S2000MD datasheet size (40.5 × 20.2 × 38.5 mm, flanges, hole
  pattern and shaft position) and sits shaft-down through the 12 mm floor hole.
- The ear slots, barrel-jack side, USB-C side, LED window and button holes are where the
  CAD puts them.

Illustrative, not designed yet:

- **Wall bracket.** A chalk-coloured plate with two arms under the ears. The CAD has ears
  but no bracket.
- **Track.** A 30 × 26 mm aluminium C-profile with a bottom slot, hung from the ceiling on
  aluminium drop rods. The belt runs inside the upper part of the track. Because the servo
  shaft points down, the box has to sit above the track, so the top of the track hangs about 0.11 m
  below the ceiling. A track screwed straight onto the ceiling would leave no room for the box.
- **Pulleys.** GT2 20-tooth (12.7 mm pitch diameter) with 16 mm flanges, pushed onto the
  servo's output spline. The idler is the same size. The real pulley bore, the spline
  adaptor and how the belt is tensioned have not been designed.
- **Belt, carriers, gliders, end stops and end caps.** Generic parts drawn for the picture.
  Each lead carrier clamps to the belt inside the track and has a graphite arm that wraps
  under the track and up its front face. An end stop at belt height, held by a knurled
  thumb screw on the track front, stops that arm when the panel is fully open, and the
  motor stalls there. The white gliders run underneath the stop. The belt's smooth back has
  pale printed dashes, like the lot print on a real belt, so its movement can be seen.
- **Curtains.** A procedural ripple-fold (a serpentine curve with 12 folds per panel,
  2.64 m of fabric per panel), rebuilt every frame from the glider positions. There is no
  cloth simulation.
- **Speed.** `curtains-motion.gif` is a time-lapse: a panel crosses in 2 s (about 14×), where
  the real drive would take roughly 28 s at the servo's about 60 rpm. `drive-motion.gif`
  runs at roughly 1.9× real speed. The pulley turns in step with the belt in both, at
  1 turn per 40 mm of belt.
- **LED.** The light pipe glows while the motor runs. A very faint warm spill on the ceiling
  is used in the room shots only.
- **Close-up camera.** The camera for `drive-closeup.png` sits a little above ceiling
  height, and the ceiling is hidden from that camera only, so the lid can be seen from
  above. The ceiling still casts its light and shadows.
- **Garden.** The view outside is a soft, out-of-focus gradient that only the camera sees,
  like an interior photo exposed for the room. The sun and sky light the room on their own.
- The room, furniture and lighting are made up. No outside models or images are used.
- `drive-closeup.png` and `inside.png` come from the first round. Since then the wall
  plaster and linen have been made lighter, so rendering them again now gives a slightly
  lighter wall and curtain behind the drive in the close-up.

## Palette and materials

- Body and bracket: "chalk" matte PLA, a warm off-white (linear RGB 0.74 / 0.71 / 0.655),
  with a slight sheen and soft subsurface scatter. The shader adds fine 0.2 mm layer lines,
  a matte micro-texture and about 0.6 mm of edge rounding.
- Lid, lead carriers, end clamps: "graphite" matte PLA, near black (0.022 / 0.024 / 0.027),
  with low specular so it reads as matte plastic and not as painted metal.
- Label: the engraved lettering is filled with a chalk-coloured paint.
- Status LED: a frosted light pipe with a warm white glow (1.0 / 0.78 / 0.52).
- Track, drop rods and pulleys: satin anodised aluminium. Belt: matte black rubber.
  Gliders: white nylon. Power lead and plug: white PVC.
- Curtains: oatmeal linen with a woven slub texture, heading tape and hem bands, soft
  wrinkles and some translucency, so closed curtains glow when the sun is on them.
- Rendering: Cycles on the GPU with denoising and AgX (Medium High Contrast look).
