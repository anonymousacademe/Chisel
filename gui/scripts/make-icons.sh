#!/usr/bin/env bash
# Regenerate every packaging icon from src/assets/logo.svg (needs rsvg-convert and Pillow).
set -euo pipefail
cd "$(dirname "$0")/.."
SVG=src/assets/logo.svg
OUT=src-tauri/icons
png() { rsvg-convert -w "$1" -h "$1" "$SVG" -o "$2"; }
png 32 $OUT/32x32.png; png 64 $OUT/64x64.png; png 128 $OUT/128x128.png; png 256 $OUT/128x128@2x.png
png 512 $OUT/icon.png
for s in 30 44 71 89 107 142 150 284 310; do png $s $OUT/Square${s}x${s}Logo.png; done
png 50 $OUT/StoreLogo.png
png 192 public/favicon.png
cp "$SVG" public/logo.svg
png 512 ../src/lorewrite/gui/icon.png
python3 - <<'PY'
from PIL import Image
im = Image.open("src-tauri/icons/icon.png").convert("RGBA")
im.save("src-tauri/icons/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
im.save("src-tauri/icons/icon.icns")
PY
