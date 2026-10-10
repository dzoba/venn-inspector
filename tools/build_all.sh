#!/bin/bash
# Build every tile pyramid for the site.
set -e
cd /Users/dzoba/Developer/venn-inspector
PY=/Users/dzoba/.venvs/render/bin/python
CP=/Users/dzoba/Developer/venn-diagram/research/polar-calibration/FOUND-23/circlepack
FR=/Users/dzoba/Developer/venn-diagram/research/polar-calibration/FOUND-23/fill-render
cp -n $CP/cp7-curves.npz work/curves7.npz|| true; cp -n $CP/cp11-curves.npz work/curves11.npz|| true; cp -n $CP/cp13-curves.npz work/curves13.npz || true
cp -n $FR/curves-ranktutte-p0.50.npz work/curves23.npz || true
b() { $PY tools/build_dzi.py "work/curves$1.npz" "docs/tiles/v$1" "$2" "$3" "${@:4}" | tail -1; }
rm -rf docs/tiles
b 7 fill 4096 --outline 3
b 7 one 4096 --scheme subset:0 --outline 3
b 7 three 4096 --scheme subset:0,2,4 --outline 3
b 11 fill 8192 --outline 2
b 11 one 4096 --scheme subset:0
b 11 three 4096 --scheme subset:0,4,7
b 13 fill 8192 --outline 2
b 13 one 4096 --scheme subset:0
b 13 three 4096 --scheme subset:0,4,9
b 17 fill 16384
b 17 one 8192 --scheme subset:0
b 17 three 8192 --scheme subset:0,6,11
b 19 fill 16384
b 19 one 8192 --scheme subset:0
b 19 three 8192 --scheme subset:0,6,13
b 23 fill 32768
b 23 one 16384 --scheme subset:0
b 23 three 16384 --scheme subset:0,8,16
du -sh docs/tiles/*
du -sh docs
