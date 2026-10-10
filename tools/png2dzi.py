#!/usr/bin/env python3
"""Tile an existing PNG into a DZI pyramid. Usage: png2dzi.py IN.png OUTDIR NAME [quality]"""
import math, sys
from pathlib import Path
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
TILE = 256
src, outdir, name = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
q = int(sys.argv[4]) if len(sys.argv) > 4 else 85
im = Image.open(src).convert('RGB')
W, H = im.size
L = int(math.ceil(math.log2(max(W, H))))
files = outdir / f'{name}_files'
for lev in range(L, -1, -1):
    d = files / str(lev)
    d.mkdir(parents=True, exist_ok=True)
    w, h = im.size
    for r in range(math.ceil(h / TILE)):
        for c in range(math.ceil(w / TILE)):
            im.crop((c * TILE, r * TILE, min((c + 1) * TILE, w), min((r + 1) * TILE, h))).save(d / f'{c}_{r}.jpg', quality=q)
    im = im.resize((max(1, math.ceil(w / 2)), max(1, math.ceil(h / 2))), Image.LANCZOS)
(outdir / f'{name}.dzi').write_text(
    f'<?xml version="1.0" encoding="UTF-8"?>\n<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
    f'Format="jpg" Overlap="0" TileSize="{TILE}"><Size Width="{W}" Height="{H}"/></Image>\n')
print(name, W, H)
