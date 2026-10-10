#!/usr/bin/env python3
"""Region-fill rendering of a 23-Venn layout.

Stage 'curves' (GPU venv, has the plotter modules): expand a saved quotient state Z into 23 closed polygons (mm).
Stage 'render' (render venv, has PIL): rasterise each curve's interior with supersampling, build the 23-bit label of
every subpixel, colour it through a 2^23-entry lookup table, and box-filter down in linear light.

Colour of a region with label set S:
  v = sum_{j in S} exp(2 pi i j / 23)  ->  hue = arg v, chroma from |v|, lightness from rank |S|.
Rotating by one curve index turns every hue by 1/23 of a turn, so the 23-fold symmetry shows as a colour wheel.

Straight segments between crossings are used (no Bezier), so this pictures the straight-line drawing.
"""
import argparse, ctypes, hashlib, importlib.util, os, subprocess, sys, time
from pathlib import Path
import numpy as np

GPU = Path('/Users/dzoba/Developer/venn-diagram/research/n23-gpu-layout-20261006')
ROOT = GPU.parents[1]
CPU = ROOT / 'research/polar-calibration/plotter/plotter_svg.py'
GEO = GPU / 'geometry23-v2/validate.py'
THIN = GPU / 'profile23-diagnostic01/thin-primal.npz'
MESH = GPU / 'profile23-diagnostic01/prepared-mesh.npz'
N = 23


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def stage_curves(zfile, out, bezier=0, tension=1.0):
    sys.path.insert(0, str(CPU.parent))
    geo = module('geo', GEO)
    with np.load(zfile, allow_pickle=False) as d:
        Z = d['Z'].copy() if 'Z' in d.files else d['x'].copy()  # Tutte-stage files hold only the crossing orbits
    with np.load(MESH, allow_pickle=False) as d:
        norb = int(d['norb'])
    with np.load(THIN, allow_pickle=False) as d:
        P = geo.ThinPrimal(d)
    z = Z[:norb][P.orb] * P.lam ** P.kof
    curves = {}
    cpu = module('cpu_plotter', CPU) if bezier else None
    for b in range(P.n):
        pts = np.stack([z[P.cycles[b]].real, z[P.cycles[b]].imag], axis=1)
        if bezier:
            # Smoothed picture of the straight-line layout: centripetal Catmull-Rom cubics (plotter_svg.bezier_controls,
            # handles capped at 0.42 chord), each span sampled at `bezier` points.
            ctrl, _ = cpu.bezier_controls(pts, np.full(len(pts), tension), 0.42)
            pts = cpu.sample_bezier(ctrl, bezier).reshape(-1, 2)
        curves[f'c{b}'] = pts
    np.savez(out, **curves)
    print(f'wrote {out}: {P.n} curves, {sum(len(v) for v in curves.values())} vertices, '
          f'max |z| {np.abs(z).max():.1f} mm', flush=True)


def oklab_to_srgb(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    rgb = np.clip(np.stack([r, g, bb], axis=-1), 0, 1)
    return np.where(rgb <= 0.0031308, 12.92 * rgb, 1.055 * rgb ** (1 / 2.4) - 0.055)


PALETTE = np.array([(230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180),
                    (70, 240, 240), (240, 50, 230), (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255),
                    (170, 110, 40), (255, 250, 200), (128, 0, 0), (170, 255, 195), (128, 128, 0), (255, 215, 180),
                    (0, 0, 128), (128, 128, 128), (255, 255, 255), (60, 60, 60), (200, 120, 120), (120, 200, 200),
                    (90, 90, 200), (200, 200, 90), (150, 90, 150), (90, 150, 90), (230, 160, 90), (90, 160, 230),
                    (160, 230, 90), (230, 90, 160)], dtype=np.uint8)


def lut(scheme, N=N):
    labels = np.arange(1 << N, dtype=np.uint32)
    if scheme.startswith('subset:'):
        # Colour by membership in a chosen subset of curves only (a k-curve sub-diagram, itself a Venn diagram).
        sel = [int(c) for c in scheme.split(':', 1)[1].split(',')]
        code = np.zeros(labels.size, dtype=np.int64)
        for i, c in enumerate(sel):
            code |= ((labels >> np.uint32(c)) & 1).astype(np.int64) << i
        out = PALETTE[code % len(PALETTE)].copy()
        out[0] = (6, 7, 11)
        return out
    if scheme == 'rankbands':
        # Topographic: one band per rank, alternating light/dark so neighbouring ranks separate.
        rank = np.zeros(labels.size, dtype=np.int64)
        for j in range(N):
            rank += ((labels >> np.uint32(j)) & 1).astype(np.int64)
        t = rank / N
        L = 0.25 + 0.65 * t + np.where(rank % 2 == 0, 0.04, -0.04)
        hue = 2 * np.pi * (0.62 - 0.55 * t)
        rgb = oklab_to_srgb(L, 0.10 * np.cos(hue), 0.10 * np.sin(hue))
        out = (rgb * 255 + 0.5).astype(np.uint8)
        out[0] = (6, 7, 11)
        return out
    rank = np.zeros(labels.size, dtype=np.float32)
    v = np.zeros(labels.size, dtype=np.complex64)
    for j in range(N):
        bit = ((labels >> np.uint32(j)) & 1).astype(np.float32)
        rank += bit
        v += bit * np.complex64(np.exp(2j * np.pi * j / N))
    hue = np.angle(v)
    mod = np.abs(v)
    t = rank / N
    if scheme == 'wheel':
        L = 0.30 + 0.62 * t
        C = 0.035 + 0.11 * np.clip(mod / 4.0, 0, 1)
    elif scheme == 'relief':
        L = 0.18 + 0.78 * t
        C = 0.02 + 0.06 * np.clip(mod / 4.0, 0, 1)
    else:
        raise ValueError(scheme)
    C = np.where(mod < 1e-3, 0.0, C)  # all-ones (and any balanced label): hue undefined, draw neutral
    rgb = oklab_to_srgb(L, C * np.cos(hue), C * np.sin(hue))
    out = (rgb * 255 + 0.5).astype(np.uint8)
    out[0] = (6, 7, 11)  # outside every curve: background
    return out


def scanfill():
    src = Path(__file__).with_name('scanfill.cpp')
    tag = hashlib.sha256(src.read_bytes()).hexdigest()[:12]
    lib = Path(__file__).with_name(f'libscanfill-{tag}.dylib')
    if not lib.exists():
        subprocess.run(['clang++', '-O3', '-std=c++17', '-shared', '-fPIC', '-o', str(lib), str(src)], check=True)
    return ctypes.CDLL(str(lib))


def stage_render(curves_npz, out_png, px, ss, scheme, view, threads=12, save_labels=None):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    t0 = time.time()
    d = np.load(curves_npz)
    n = len(d.files)
    cs = [d[f'c{b}'] for b in range(n)]
    rad = max(float(np.hypot(c[:, 0], c[:, 1]).max()) for c in cs) * 1.01
    cx, cy, half = (0.0, 0.0, rad) if view is None else view
    W = px * ss
    scale = W / (2 * half)
    labels = np.zeros((W, W), dtype=np.uint32)
    xy = np.concatenate([np.stack([(c[:, 0] - (cx - half)) * scale, ((cy + half) - c[:, 1]) * scale], 1) for c in cs])
    offsets = np.cumsum([0] + [len(c) for c in cs]).astype(np.int64)
    lib = scanfill()
    lib.sf_fill(n, offsets.ctypes.data_as(ctypes.c_void_p), np.ascontiguousarray(xy).ctypes.data_as(ctypes.c_void_p),
                W, W, labels.ctypes.data_as(ctypes.c_void_p), threads)
    print(f'filled {W}x{W} {time.time() - t0:.0f}s', flush=True)
    if save_labels:
        # Exact subpixel label plane (row 0 = top, subpixel centres), plus the mapping needed to reproduce it.
        np.save(save_labels, labels)
        import json
        Path(str(save_labels) + '.json').write_text(json.dumps(dict(
            curves=str(curves_npz), curves_sha256=hashlib.sha256(Path(curves_npz).read_bytes()).hexdigest(),
            W=W, px=px, ss=ss, view=[cx, cy, half], scale=scale,
            pixel_to_xy='x = (c + 0.5) / scale + (cx - half); y = (cy + half) - (r + 0.5) / scale',
            bit='bit b set <=> inside curve b (even-odd fill of curves-*.npz key c<b>)',
            scanfill_sha256=hashlib.sha256(Path(__file__).with_name('scanfill.cpp').read_bytes()).hexdigest()), indent=1))
    table = lut(scheme, n)
    img = np.empty((px, px, 3), dtype=np.uint8)
    rows = max(1, 4096 // ss)
    for r0 in range(0, px, rows):
        r1 = min(px, r0 + rows)
        block = table[labels[r0 * ss:r1 * ss]].astype(np.float32) / 255.0
        lin = np.where(block <= 0.04045, block / 12.92, ((block + 0.055) / 1.055) ** 2.4)
        lin = lin.reshape(r1 - r0, ss, px, ss, 3).mean(axis=(1, 3))
        srgb = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * lin ** (1 / 2.4) - 0.055)
        img[r0:r1] = (srgb * 255 + 0.5).astype(np.uint8)
    Image.fromarray(img).save(out_png, compress_level=6)
    print(f'wrote {out_png} {time.time() - t0:.0f}s', flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=['curves', 'render'])
    p.add_argument('--z', type=Path)
    p.add_argument('--curves', type=Path, required=True)
    p.add_argument('--out', type=Path)
    p.add_argument('--px', type=int, default=2000)
    p.add_argument('--ss', type=int, default=3)
    p.add_argument('--scheme', default='wheel')
    p.add_argument('--view', type=float, nargs=3, metavar=('CX', 'CY', 'HALF'))
    p.add_argument('--bezier', type=int, default=0, help='curves stage: samples per span of a smoothing cubic (0 = straight)')
    p.add_argument('--tension', type=float, default=1.0)
    p.add_argument('--save-labels', type=Path, help='render stage: also save the uint32 subpixel label plane (.npy)')
    a = p.parse_args()
    if a.stage == 'curves':
        stage_curves(a.z, a.curves, a.bezier, a.tension)
    else:
        stage_render(a.curves, a.out, a.px, a.ss, a.scheme, a.view, save_labels=a.save_labels)


if __name__ == '__main__':
    main()
