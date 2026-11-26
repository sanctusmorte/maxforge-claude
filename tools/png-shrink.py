#!/usr/bin/env python3
"""Downscale PNG/JPG screenshots before an agent Reads them (token spend: ~1.6k tokens per 1280x900 image).

Usage: python3 ~/.claude/tools/png-shrink.py <file-or-dir>... [--max 1000] [--out <dir>]
Writes <name>.small.png next to each input (or into --out); prints the written paths. Never overwrites inputs.
"""
import argparse, pathlib, sys
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("paths", nargs="+")
ap.add_argument("--max", type=int, default=1000, help="longest side in px")
ap.add_argument("--out")
a = ap.parse_args()
files = []
for p in map(pathlib.Path, a.paths):
    files += sorted(x for x in p.rglob("*") if x.suffix.lower() in (".png", ".jpg", ".jpeg") and ".small." not in x.name) if p.is_dir() else [p]
if not files:
    sys.exit("no images")
for f in files:
    dst = (pathlib.Path(a.out) if a.out else f.parent) / f"{f.stem}.small.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(f)
    im.thumbnail((a.max, a.max * 4))  # width-bound; tall full-page shots keep their aspect
    im.save(dst, optimize=True)
    print(dst)
