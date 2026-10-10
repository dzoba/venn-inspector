#!/usr/bin/env python3
"""Render a Venn diagram (curves npz) straight into a Deep Zoom (DZI) tile pyramid.

The full-resolution level is rendered block by block with the region-fill renderer (fillrender.py: even-odd scanline
fill of every curve into a per-subpixel label, 2^n colour table, box filter in linear light), so no monolithic image
is ever held. Lower levels are built by 2x2 downsampling of the level above.

Usage: build_dzi.py CURVES.npz OUTDIR NAME SIZE [--ss 2] [--scheme wheel] [--outline W] [--quality 85]
"""
import argparse, ctypes, importlib.util, math, os, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

FILLRENDER = Path(__file__).resolve().with_name('fillrender.py')
spec = importlib.util.spec_from_file_location('fillrender', FILLRENDER)
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
TILE = 256
BG = (6, 7, 11)
# Colours for sub-diagram views, indexed by the membership bits of the chosen curves (bit i = inside chosen curve i).
# Index 0 (outside every chosen curve, but inside the diagram) is a dark slate so it reads as "none of them".
SUBSET_COLOURS = {
    1: [(38, 44, 62), (255, 196, 64)],
    3: [(38, 44, 62), (230, 70, 80), (70, 170, 240), (180, 90, 230),
        (250, 210, 60), (250, 140, 50), (90, 210, 120), (245, 245, 245)],
}


def subset_lut(scheme, n):
    sel = [int(c) for c in scheme.split(':', 1)[1].split(',')]
    labels = np.arange(1 << n, dtype=np.uint32)
    code = np.zeros(labels.size, dtype=np.int64)
    for i, c in enumerate(sel):
        code |= ((labels >> np.uint32(c)) & 1).astype(np.int64) << i
    out = np.array(SUBSET_COLOURS[len(sel)], dtype=np.uint8)[code]
    out[0] = BG                      # the unbounded outside region
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('curves'); ap.add_argument('outdir'); ap.add_argument('name'); ap.add_argument('size', type=int)
    ap.add_argument('--ss', type=int, default=2)
    ap.add_argument('--scheme', default='wheel')
    ap.add_argument('--outline', type=float, default=0.0, help='outline width in output pixels at full size (0 = none)')
    ap.add_argument('--quality', type=int, default=85)
    ap.add_argument('--block', type=int, default=2048)
    a = ap.parse_args()
    t0 = time.time()
    d = np.load(a.curves)
    n = len(d.files)
    cs = [d[f'c{b}'] for b in range(n)]
    pts = np.concatenate(cs)
    offsets = np.cumsum([0] + [len(c) for c in cs]).astype(np.int64)
    half = max(float(np.hypot(c[:, 0], c[:, 1]).max()) for c in cs) * 1.02
    lib = fr.scanfill()
    table = (subset_lut(a.scheme, n) if a.scheme.startswith('subset:') else fr.lut(a.scheme, n)).astype(np.float32) / 255.0
    lin_table = np.where(table <= 0.04045, table / 12.92, ((table + 0.055) / 1.055) ** 2.4).astype(np.float32)
    S = a.size
    L = int(math.ceil(math.log2(S)))
    files = Path(a.outdir) / f'{a.name}_files'
    top = files / str(L)
    top.mkdir(parents=True, exist_ok=True)
    scale = S / (2 * half)                       # output px per unit
    B, ss = a.block, a.ss
    for by in range(0, S, B):
        for bx in range(0, S, B):
            bw, bh = min(B, S - bx), min(B, S - by)
            W, H = bw * ss, bh * ss
            x0 = -half + bx / scale
            y0 = half - by / scale
            xy = np.empty((len(pts), 2))
            xy[:, 0] = (pts[:, 0] - x0) * scale * ss
            xy[:, 1] = (y0 - pts[:, 1]) * scale * ss
            lab = np.zeros((H, W), dtype=np.uint32)
            lib.sf_fill(n, offsets.ctypes.data_as(ctypes.c_void_p), xy.ctypes.data_as(ctypes.c_void_p),
                        W, H, lab.ctypes.data_as(ctypes.c_void_p), 12)
            lin = lin_table[lab].reshape(bh, ss, bw, ss, 3).mean(axis=(1, 3))
            srgb = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.power(np.maximum(lin, 0), 1 / 2.4) - 0.055)
            img = Image.fromarray((np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8))
            if a.outline > 0:
                dr = ImageDraw.Draw(img)
                for c in cs:
                    p = np.stack([(c[:, 0] - x0) * scale, (y0 - c[:, 1]) * scale], 1)
                    p = np.vstack([p, p[:1]])
                    dr.line([tuple(q) for q in p], fill=(250, 250, 250), width=max(1, int(round(a.outline))))
            for ty in range(0, bh, TILE):
                for tx in range(0, bw, TILE):
                    tile = img.crop((tx, ty, min(tx + TILE, bw), min(ty + TILE, bh)))
                    tile.save(top / f'{(bx + tx) // TILE}_{(by + ty) // TILE}.jpg', quality=a.quality)
        print(f'row {by // B + 1}/{math.ceil(S / B)} ({time.time() - t0:.0f}s)', flush=True)
    # lower levels
    w = S
    for lev in range(L, 0, -1):
        src = files / str(lev)
        dst = files / str(lev - 1)
        dst.mkdir(exist_ok=True)
        cols, rows = math.ceil(w / TILE), math.ceil(w / TILE)
        nw = max(1, math.ceil(w / 2))
        for r in range(math.ceil(nw / TILE)):
            for c in range(math.ceil(nw / TILE)):
                canvas = Image.new('RGB', (2 * TILE, 2 * TILE))
                for dy in range(2):
                    for dx in range(2):
                        cc, rr = 2 * c + dx, 2 * r + dy
                        if cc < cols and rr < rows:
                            canvas.paste(Image.open(src / f'{cc}_{rr}.jpg'), (dx * TILE, dy * TILE))
                tw = min(TILE, nw - c * TILE); th = min(TILE, nw - r * TILE)
                canvas = canvas.crop((0, 0, min(2 * TILE, w - 2 * c * TILE), min(2 * TILE, w - 2 * r * TILE)))
                canvas.resize((tw, th), Image.LANCZOS).save(dst / f'{c}_{r}.jpg', quality=a.quality)
        w = nw
    (Path(a.outdir) / f'{a.name}.dzi').write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
        f'Format="jpg" Overlap="0" TileSize="{TILE}"><Size Width="{S}" Height="{S}"/></Image>\n')
    print(f'done {a.name} {S}px ({time.time() - t0:.0f}s)', flush=True)


if __name__ == '__main__':
    main()
