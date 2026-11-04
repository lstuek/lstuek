"""Overlay plan for the city banner: what text shows in which area on every frame.

Pure logic, no images (ref/banner-build.md, "Overlay plan"). Every string it returns is a
formatted number with a fixed unit word or an approved project name; anything else stops the build.
"""
import collections
import json
import re
import sys

UNITS = {"tokens": "TOKENS", "commits": "COMMITS"}


def count(value):
    """A real positive total; a missing, partial or zero value never reaches a sign."""
    if type(value) is not int or value <= 0:
        sys.exit(f"city data missing: {value!r} is not a positive whole number")
    return value


def short(n):
    """23_400_000_000 -> 23.4B; the unit is picked after rounding, so 999.96M reads 1.0B."""
    for size, unit in ((10**9, "B"), (10**6, "M"), (10**3, "K")):
        tenths = (n * 10 + size // 2) // size  # half up, in whole numbers
        if tenths >= 10:
            return f"{tenths // 10}.{tenths % 10}{unit}"
    return str(n)


KINDS = {"tokens": 1, "commits": 1, "hologram": 3, "billboard": 1}  # six text areas
FIELDS = {"id", "kind", "corners", "color", "blur", "reflection"}


def quad_area(points):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))) / 2


def load_spots(path, size):
    """The spot file from the base render: six areas, each with four corners inside the frame."""
    width, height = size

    def require(ok, why):
        if not ok:
            sys.exit(f"spot file {path}: {why}")

    def quad(points, name):
        require(isinstance(points, list) and len(points) == 4 and all(
            isinstance(p, list) and len(p) == 2 and all(type(c) in (int, float) for c in p) for p in points),
            f"{name} needs four [x, y] corners")
        require(all(0 <= x <= width and 0 <= y <= height for x, y in points), f"{name} corner outside the frame")
        require(quad_area(points) >= 1, f"{name} has no area")

    with open(path, encoding="utf-8") as f:
        areas = json.load(f).get("areas")
    require(isinstance(areas, list) and len(areas) == sum(KINDS.values()), "needs six areas")
    for a in areas:
        require(isinstance(a, dict) and set(a) == FIELDS, f"each area needs exactly {sorted(FIELDS)}")
        require(a["kind"] in KINDS, f"unknown kind {a['kind']!r}")
        require(isinstance(a["color"], str) and re.fullmatch(r"#[0-9a-fA-F]{6}", a["color"]), "colour must be #rrggbb")
        require(type(a["blur"]) in (int, float) and a["blur"] >= 0, "blur must be a number >= 0")
        quad(a["corners"], a["id"])
        quad(a["reflection"], f"{a['id']} reflection")
    require(len({a["id"] for a in areas}) == len(areas), "ids must be unique")
    require(collections.Counter(a["kind"] for a in areas) == KINDS, f"kinds must be {KINDS}")
    return areas


def sign_text(kind, value):
    number = short(count(value)) if kind == "tokens" else f"{count(value):,}"
    return f"{number} {UNITS[kind]}"


# Lincoln's seven public project names, billboard order; New Era never appears (ref/banner-build.md, "Text").
PROJECTS = ("Portfolio", "Bionic Wave", "KA Tech", "KA Ops", "aios", "CRM", "SystemSelect")
HOLOGRAMS = ("Portfolio", "Bionic Wave", "KA Tech")
FPS = 24
FLICKER_FLOOR = 0.7  # neon dips go no deeper than 30%
NUMBER = {"tokens": r"[1-9]\d{0,3}(\.\d[KMB])?|[1-9]\d{0,2}", "commits": r"[1-9]\d{0,2}(,\d{3})*"}


def approved(text):
    """A formatted number with its unit word, or one approved project name; nothing else is drawn."""
    return text in PROJECTS or any(re.fullmatch(rf"(?:{NUMBER[k]}) {UNITS[k]}", text) for k in UNITS)


def frame_delays(frames):
    """41 or 42 ms per frame, rounded on the running total so the loop sums to frames / 24 seconds."""
    edges = [round(1000 * i / FPS) for i in range(frames + 1)]
    return [b - a for a, b in zip(edges, edges[1:])]


def slots(frames, count):
    """Slot start frames; slot lengths differ by at most one frame."""
    return [frames * k // count for k in range(count + 1)]


def sweep_window(edges):
    """About half a second (12 of 288 frames), centred in the longest billboard slot nearest the middle,
    so the sweep never shares a frame with a billboard switch and never touches frame 1."""
    frames = edges[-1]
    length = max(2, round(frames * 12 / 288))
    middle = (len(edges) - 1) // 2
    slot = max(range(len(edges) - 1), key=lambda k: (edges[k + 1] - edges[k], -abs(k - middle)))
    room = edges[slot + 1] - edges[slot]
    if room < length + 2:
        sys.exit(f"loop of {frames} frames is too short for a {length}-frame sweep inside one billboard slot")
    start = edges[slot] + (room - length) // 2
    return range(start, start + length)


def band(step, length):
    """The wireframe band [left, right] as fractions of the frame width: one wipe in, then one wipe out."""
    t = (step + 0.5) / length
    return [0.0, 2 * t] if t < 0.5 else [2 * t - 1, 1.0]


def plan(city, areas, frames, flicker, projects=PROJECTS, holograms=HOLOGRAMS):
    """Per frame: {"texts": {area id: text}, "flicker": {area id: level}, "sweep": [left, right] or None}."""
    totals = city.get("totals") if isinstance(city, dict) else None
    totals = totals if isinstance(totals, dict) else {}
    if not isinstance(flicker, list) or len(flicker) != frames:
        sys.exit(f"flicker curve needs exactly {frames} values")
    for text in (*projects, *holograms):
        if not approved(text):
            sys.exit(f"privacy check failed: {text!r} is not an approved name")
    fixed = {a["id"]: sign_text(a["kind"], totals.get(a["kind"])) for a in areas if a["kind"] in UNITS}
    fixed.update(zip((a["id"] for a in areas if a["kind"] == "hologram"), holograms, strict=True))
    billboard = [a["id"] for a in areas if a["kind"] == "billboard"]
    edges = slots(frames, len(projects))
    window = sweep_window(edges)
    out = []
    for i in range(frames):
        texts = dict(fixed, **{b: projects[next(k for k in range(len(projects)) if edges[k + 1] > i)] for b in billboard})
        for text in texts.values():
            if not approved(text):
                sys.exit(f"privacy check failed: {text!r} is not approved")
        level = 1.0 if i == 0 else min(1.0, max(FLICKER_FLOOR, float(flicker[i])))
        out.append({"texts": texts, "flicker": {a["id"]: level for a in areas},
                    "sweep": band(i - window.start, len(window)) if i in window else None})
    return out
