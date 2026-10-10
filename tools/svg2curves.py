#!/usr/bin/env python3
"""Convert a plotter SVG (one <path id="curve-i"> per curve; M, relative c, l, Z) to a curves npz for fillrender.

Each cubic is sampled at `k` points. Coordinates are centred on the page and y is flipped (SVG y points down).
Usage: svg2curves.py in.svg out.npz [k]
"""
import re, sys
import numpy as np


def parse(d, k):
    toks = re.findall(r'[MmCcLlZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?', d)
    pts, i, cur, cmd = [], 0, np.zeros(2), None
    ts = np.linspace(0, 1, k + 1)[1:][:, None]
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in 'Zz':
                continue
            continue
        if cmd == 'M':
            cur = np.array([float(toks[i]), float(toks[i + 1])]); pts.append(cur.copy()); i += 2
        elif cmd == 'l':
            cur = cur + [float(toks[i]), float(toks[i + 1])]; pts.append(cur.copy()); i += 2
        elif cmd == 'c':
            v = np.array([float(x) for x in toks[i:i + 6]]).reshape(3, 2)
            p0, p1, p2, p3 = cur, cur + v[0], cur + v[1], cur + v[2]
            b = ((1 - ts) ** 3 * p0 + 3 * (1 - ts) ** 2 * ts * p1 + 3 * (1 - ts) * ts ** 2 * p2 + ts ** 3 * p3)
            pts.extend(b)
            cur = p3; i += 6
        else:
            raise ValueError(f'unhandled command {cmd}')
    return np.array(pts)


def main():
    src, out = sys.argv[1], sys.argv[2]
    k = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    s = open(src).read()
    vb = [float(x) for x in re.search(r'viewBox="([-\d.eE ]+)"', s).group(1).split()]
    cx, cy = vb[0] + vb[2] / 2, vb[1] + vb[3] / 2
    ds = sorted(re.findall(r'<path[^>]*\sid="curve-(\d+)"[^>]*\sd="([^"]*)"', s), key=lambda t: int(t[0]))
    curves = {}
    for i, d in ds:
        p = parse(d, k)
        curves[f'c{i}'] = np.stack([p[:, 0] - cx, cy - p[:, 1]], 1)
    np.savez(out, **curves)
    print(out, len(curves), 'curves', sum(len(v) for v in curves.values()), 'points')


if __name__ == '__main__':
    main()
