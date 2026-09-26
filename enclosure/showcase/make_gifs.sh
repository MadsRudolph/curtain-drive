#!/usr/bin/env bash
# Render the GIF frame sequences and turn them into palette-optimised looping GIFs.
# Run from anywhere; takes roughly 18 minutes on an RTX 3060.
# make_gifs.sh --encode-only rebuilds the GIFs from existing frames.
set -euo pipefail
cd "$(dirname "$0")/.."            # enclosure/

gif() {  # gif <frames dir> <output.gif> <width> <colours>
    # Light temporal denoise + a reduced palette keep each GIF near 4 MB.
    ffmpeg -y -loglevel error -framerate 12 -i "$1/%04d.png" \
        -filter_complex "[0:v]hqdn3d=0:0:10:10,scale=$3:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=$4:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
        -loop 0 "$2"
}

[ "${1:-}" = "--encode-only" ] || blender -b --python showcase/showcase.py -- gif room
gif showcase/frames-room showcase/curtains-motion.gif 600 96
cp showcase/frames-room/0061.png showcase/curtains-motion-poster.png

[ "${1:-}" = "--encode-only" ] || blender -b --python showcase/showcase.py -- gif drive
gif showcase/frames-drive showcase/drive-motion.gif 640 112
cp showcase/frames-drive/0028.png showcase/drive-motion-poster.png

ls -la showcase/*.gif showcase/*-poster.png
