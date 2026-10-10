# Venn inspector

Zoomable pictures of simple symmetric Venn diagrams with 7, 11, 13, 17, 19 and 23 curves:
**https://dzoba.github.io/venn-inspector/**

Each diagram has three layers:

- **All curves.** Every point is coloured by which curves contain it. Brightness shows how many curves contain the
  point; hue is the sum of one unit arrow per containing curve.
- **One curve.** Curve 0 alone, inside versus outside.
- **Three curves.** A three-curve sub-diagram, which is itself an 8-region Venn diagram.

The 17-, 19- and 23-curve diagrams were found in 2026. Paper: [arXiv:2609.26546](https://arxiv.org/abs/2609.26546).
Certificates, checkers and Lean proofs: [doi:10.5281/zenodo.23189412](https://doi.org/10.5281/zenodo.23189412) and
[dzoba/venn17](https://github.com/dzoba/venn17).

## How the site is built

- `tools/svg2curves.py` turns a plotter SVG into closed polylines, one per curve.
- `tools/build_dzi.py` renders the full-resolution image block by block and writes a Deep Zoom (DZI) tile pyramid.
  It uses a region-fill renderer: an even-odd scanline fill of every curve into a per-pixel membership label, a
  2^n-entry colour table, and a 2x2 supersample averaged in linear light.
- `docs/` is the static site (OpenSeadragon viewer), served by GitHub Pages.

Layouts:
- 7, 11 and 13: circle packing.
- 17 and 19: pressure relaxations checked for crossings and region labels when they were exported.
- 23: a weighted Tutte layout, independently checked with zero crossing violations and all 8,388,608 region labels
  read back correctly.
