#!/usr/bin/env bash
# Export the populated board as GLB (for Blender) and STEP into enclosure/pcb3d/.
# KiCad's library has no 3D models for a few footprints on this board; their body
# boxes live in hardware/lib/3dmodels (tools/make_body_models.py). They are merged
# with the system library in a temporary model dir, so the board file keeps the
# stock model paths.
set -euo pipefail
HW="$(cd "$(dirname "$0")/.." && pwd)"
SYS=/usr/share/kicad/3dmodels
OUT="$HW/../enclosure/pcb3d"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
for d in "$SYS"/*.3dshapes; do ln -s "$d" "$TMP/$(basename "$d")"; done
for d in "$HW"/lib/3dmodels/*.3dshapes; do
    n="$(basename "$d")"; rm "$TMP/$n"; mkdir "$TMP/$n"
    ln -s "$SYS/$n"/* "$TMP/$n"/ 2>/dev/null || true
    ln -sf "$d"/* "$TMP/$n"/
done
# DRV8876: same body as the stock HTSSOP-16 EP model, stored under the mask variant's name
ln -s "$SYS/Package_SO.3dshapes/HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm.step" \
      "$TMP/Package_SO.3dshapes/HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm_Mask2.46x2.31mm.step" 2>/dev/null || {
    rm "$TMP/Package_SO.3dshapes"; mkdir "$TMP/Package_SO.3dshapes"; ln -s "$SYS/Package_SO.3dshapes"/* "$TMP/Package_SO.3dshapes"/
    ln -s "$SYS/Package_SO.3dshapes/HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm.step" \
          "$TMP/Package_SO.3dshapes/HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm_Mask2.46x2.31mm.step"; }
mkdir -p "$OUT"
export KICAD10_3DMODEL_DIR="$TMP"
# origin at the board's top-left corner (board sits at 100,100 mm on the sheet)
kicad-cli pcb export glb --subst-models --include-tracks --include-pads --include-zones \
    --include-silkscreen --include-soldermask --user-origin 100x100mm \
    -o "$OUT/curtain-drive-revB-pcb.glb" "$HW/curtain-drive-revB.kicad_pcb"
kicad-cli pcb export step --subst-models --user-origin 100x100mm \
    -o "$OUT/curtain-drive-revB-pcb.step" "$HW/curtain-drive-revB.kicad_pcb"
# board renders for the write-up
R="$HW/../enclosure/renders"
kicad-cli pcb render --side top --quality high --background opaque --width 1600 --height 1250 \
    -o "$R/pcb_revB_top.png" "$HW/curtain-drive-revB.kicad_pcb"
kicad-cli pcb render --side top --quality high --background opaque --perspective --floor \
    --rotate '-40,0,-30' --zoom 0.9 --width 1600 --height 1100 \
    -o "$R/pcb_revB_iso.png" "$HW/curtain-drive-revB.kicad_pcb"
# rev B's through-hole parts sit on the back: show that side too
kicad-cli pcb render --side bottom --quality high --background opaque --width 1600 --height 1250 \
    -o "$R/pcb_revB_bottom.png" "$HW/curtain-drive-revB.kicad_pcb"
kicad-cli pcb render --side bottom --quality high --background opaque --perspective --floor \
    --rotate '40,0,30' --zoom 0.9 --width 1600 --height 1100 \
    -o "$R/pcb_revB_bottom_iso.png" "$HW/curtain-drive-revB.kicad_pcb"
