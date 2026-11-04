"""Build the city banner: write tonight's numbers onto the base render and encode a looping WebP.

    python scripts/banner.py BASE_DIR CITY_JSON OUT.webp

BASE_DIR is the Blender base render (ref/banner-build.md, "Base render outputs"), N frames, all one size:
    beauty/0001.png ...           the street, sign faces dark
    wireframe/0001.png ...        the wireframe pass of the same frames
    masks/<area id>/0001.png ...  per text area, white where something in front covers the text
    rain/0001.png ...             the rain-only layer (RGBA), drawn above the text
    flicker.json                  the shared flicker curve, one value per frame
    spots.json                    the six text areas: corners top-left, top-right, bottom-right, bottom-left
CITY_JSON is the job's city data; only totals.tokens and totals.commits are read.
"""
import argparse
import functools
import json
import math
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import overlay

FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "BarlowCondensed-SemiBold.ttf")
CYAN = np.array([0.0, 1.0, 1.0], np.float32)
WORST = {"tokens": "104.2B TOKENS", "commits": "10,000 COMMITS"}
REFLECTION = 0.25
FILL_W, FILL_H = 0.92, 0.8


def read(path, mode):
    try:
        with Image.open(path) as image:
            return np.asarray(image.convert(mode), np.float32) / 255
    except FileNotFoundError:
        sys.exit(f"base render missing: {path}")


@functools.cache
def probe():
    return ImageFont.truetype(FONT, 100)


def edge(a, b):
    return float(np.hypot(b[0] - a[0], b[1] - a[1]))


def cell_size(corners):
    tl, tr, br, bl = corners
    return max(2, round(max(edge(tl, tr), edge(bl, br)))), max(2, round(max(edge(tl, bl), edge(tr, br))))


def fit_font(worst, size):
    width, height = size
    left, top, right, bottom = probe().getbbox(worst)
    scale = min(FILL_W * width / (right - left), FILL_H * height / (bottom - top))
    return ImageFont.truetype(FONT, max(1, int(100 * scale)))


def worst_case(area):
    if area["kind"] in WORST:
        return WORST[area["kind"]]
    shown = overlay.HOLOGRAMS if area["kind"] == "hologram" else overlay.PROJECTS
    return max(shown, key=probe().getlength)


def text_cell(area, text):
    size = cell_size(area["corners"])
    worst = worst_case(area)
    font = fit_font(worst, size)
    if font.getlength(text) > font.getlength(worst):
        sys.exit(f"text {text!r} does not fit the {area['id']} cell (sized for {worst!r})")
    cell = Image.new("L", size)
    ImageDraw.Draw(cell).text((size[0] / 2, size[1] / 2), text, fill=255, font=font, anchor="mm")
    return cell


def warp(cell, corners, frame_size):
    w, h = cell.size
    rows, rhs = [], []
    for (x, y), (u, v) in zip(corners, [(0, 0), (w, 0), (w, h), (0, h)]):
        rows += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        rhs += [u, v]
    coeffs = np.linalg.solve(np.array(rows, float), np.array(rhs, float))
    return cell.transform(frame_size, Image.Transform.PERSPECTIVE, tuple(coeffs), Image.Resampling.BICUBIC)


def blur(layer, radius):
    return layer.filter(ImageFilter.GaussianBlur(radius)) if radius > 0 else layer


def as_array(layer):
    return np.asarray(layer, np.float32) / 255


def box(corners, margin, frame_size):
    """Rows and columns around four corners, widened by the glow margin and clipped to the frame."""
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    m = math.ceil(margin)
    return (slice(max(0, math.floor(min(ys)) - m), min(frame_size[1], math.ceil(max(ys)) + m)),
            slice(max(0, math.floor(min(xs)) - m), min(frame_size[0], math.ceil(max(xs)) + m)))


def light_layers(area, text, frame_size):
    """[(rows, columns, light, outline or None)]: the sign and its road reflection, each cropped to its box."""
    cell = text_cell(area, text)
    color = np.array([int(area["color"][i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255
    glow = 0.2 * cell.size[1] + area["blur"]
    shape = warp(cell, area["corners"], frame_size)
    rows, cols = box(area["corners"], 3 * glow + 2, frame_size)
    core, halo = as_array(blur(shape, area["blur"] * 0.5))[rows, cols], as_array(blur(shape, glow))[rows, cols]
    light = core[..., None] * (0.45 + 0.55 * color) + 1.6 * halo[..., None] * color
    edges = as_array(shape.filter(ImageFilter.MaxFilter(3))) - as_array(shape.filter(ImageFilter.MinFilter(3)))
    mirror_glow = glow * 0.6 + 1
    mirror_rows, mirror_cols = box(area["reflection"], 3 * mirror_glow + 2, frame_size)
    mirror = as_array(blur(warp(ImageOps.flip(cell), area["reflection"], frame_size), mirror_glow))
    return [(rows, cols, light, edges[rows, cols, None] * CYAN),
            (mirror_rows, mirror_cols, REFLECTION * mirror[mirror_rows, mirror_cols, None] * color, None)]


def load_base(base):
    beauty_dir = os.path.join(base, "beauty")
    try:
        names = sorted(n for n in os.listdir(beauty_dir) if n.endswith(".png"))
    except FileNotFoundError:
        sys.exit(f"base render missing: {beauty_dir}")
    if not names or names != [f"{i:04d}.png" for i in range(1, len(names) + 1)]:
        sys.exit(f"base render frames must be 0001.png .. in {beauty_dir}")
    with Image.open(os.path.join(beauty_dir, names[0])) as first:
        size = first.size
    with open(os.path.join(base, "flicker.json"), encoding="utf-8") as f:
        flicker = json.load(f)
    return names, size, flicker, overlay.load_spots(os.path.join(base, "spots.json"), size)


def build(base, city_path, out, quality=90):
    frame_names, size, flicker, areas = load_base(base)
    with open(city_path, encoding="utf-8") as f:
        city = json.load(f)
    frames = overlay.plan(city, areas, len(frame_names), flicker)
    layers = {}
    images = []
    for name, step in zip(frame_names, frames):
        lit, wire = read(os.path.join(base, "beauty", name), "RGB"), read(os.path.join(base, "wireframe", name), "RGB")
        if lit.shape[:2] != (size[1], size[0]) or wire.shape != lit.shape:
            sys.exit(f"base render frame {name} is not {size[0]}x{size[1]}")
        for area in areas:
            text = step["texts"][area["id"]]
            if layers.get(area["id"], (None,))[0] != text:
                layers[area["id"]] = (text, light_layers(area, text, size))
            mask = read(os.path.join(base, "masks", area["id"], name), "L")
            for rows, cols, light, outline in layers[area["id"]][1]:
                visible = 1 - mask[rows, cols, None]
                lit[rows, cols] += step["flicker"][area["id"]] * light * visible
                if outline is not None:
                    wire[rows, cols] += outline * visible
        if step["sweep"] is not None:
            left, right = (round(f * size[0]) for f in step["sweep"])
            lit[:, left:right] = wire[:, left:right]
            line = right if step["sweep"][0] == 0 else left
            lit[:, max(0, line - 1):line + 1] = 0.3 + 0.7 * CYAN
        rain = read(os.path.join(base, "rain", name), "RGBA")
        lit = lit * (1 - rain[..., 3:]) + rain[..., :3] * rain[..., 3:]
        images.append(Image.fromarray((np.clip(lit, 0, 1) * 255 + 0.5).astype(np.uint8)))
    images[0].save(out, "WEBP", save_all=True, append_images=images[1:], duration=overlay.frame_delays(len(images)),
                   loop=0, quality=quality, method=4)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write the numbers onto the base render and encode the banner.")
    parser.add_argument("base", help="base render folder")
    parser.add_argument("city", help="city data JSON")
    parser.add_argument("out", help="output .webp path")
    args = parser.parse_args(argv)
    start = time.perf_counter()
    build(args.base, args.city, args.out)
    print(f"banner: {args.out} in {time.perf_counter() - start:.1f} s")


if __name__ == "__main__":
    main()
