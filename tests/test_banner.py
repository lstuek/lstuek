import json
import os
import pathlib

import numpy as np
import pytest
from PIL import Image

import banner
import overlay
from conftest import SIZE, spots

FRAMES = 24
REFS = pathlib.Path(__file__).parent / "fixtures" / "banner"
CITY = {"totals": {"tokens": 23_400_000_000, "commits": 1532, "top_language": "Python"}}
AMBER = (255, 190, 0)


def beauty(i):
    w, h = SIZE
    frame = np.zeros((h, w, 3), np.uint8)
    frame[...] = (8, 10, 24)
    frame[:, :, 2] += (np.arange(h) // 4).astype(np.uint8)[:, None]
    frame[70:76, 5 * i:5 * i + 6] = (90, 90, 110)  # a passing car, so no two frames are alike
    return frame


def wireframe():
    w, h = SIZE
    frame = np.zeros((h, w, 3), np.uint8)
    frame[...] = (30, 0, 40)
    frame[np.arange(h) % 8 < 2] = AMBER
    frame[:, np.arange(w) % 8 < 2] = AMBER
    return frame


def rain(i):
    w, h = SIZE
    y, x = np.mgrid[0:h, 0:w]
    streak = (x + 3 * i + y // 2) % 37 == 0
    layer = np.zeros((h, w, 4), np.uint8)
    layer[streak] = (180, 190, 210, 100)
    return layer


COMMITS_COVER = 118


def base_render(root, flicker=None):
    root.mkdir(parents=True, exist_ok=True)
    (root / "spots.json").write_text(json.dumps(spots()), encoding="utf-8")
    (root / "flicker.json").write_text(json.dumps(flicker or [0.5] + [1.0] * 4 + [0.75] + [1.0] * 18), encoding="utf-8")
    for folder in ["beauty", "wireframe", "rain"] + [f"masks/{a['id']}" for a in spots()["areas"]]:
        (root / folder).mkdir(parents=True, exist_ok=True)
    w, h = SIZE
    for i in range(FRAMES):
        name = f"{i + 1:04d}.png"
        Image.fromarray(beauty(i)).save(root / "beauty" / name)
        Image.fromarray(wireframe()).save(root / "wireframe" / name)
        Image.fromarray(rain(i)).save(root / "rain" / name)
        for a in spots()["areas"]:
            mask = np.zeros((h, w), np.uint8)
            if a["id"] == "sign-commits":
                mask[:, COMMITS_COVER:] = 255
            Image.fromarray(mask).save(root / "masks" / a["id"] / name)
    return root


def build(tmp_path, city=CITY):
    base = base_render(tmp_path / "base")
    (tmp_path / "city.json").write_text(json.dumps(city), encoding="utf-8")
    return banner.build(str(base), str(tmp_path / "city.json"), str(tmp_path / "banner.webp"))


def frames(path):
    with Image.open(path) as image:
        out = []
        for i in range(image.n_frames):
            image.seek(i)
            out.append((np.asarray(image.convert("RGB"), np.int16), image.info["duration"]))
        return out


def box(area_id, margin=4):
    corners = next(a["corners"] for a in spots()["areas"] if a["id"] == area_id)
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    return slice(max(0, min(ys) - margin), max(ys) + margin), slice(max(0, min(xs) - margin), max(xs) + margin)


def background(i):
    """What a frame looks like with no text: beauty under the fixture rain."""
    r = rain(i).astype(np.float32) / 255
    return beauty(i) * (1 - r[..., 3:]) + 255 * r[..., :3] * r[..., 3:]


def sweep_frames():
    plan = overlay.plan(CITY, spots()["areas"], FRAMES, [1.0] * FRAMES)
    return [i for i, f in enumerate(plan) if f["sweep"]], plan


def amber(pixels):
    return (pixels[..., 0] > 170) & (pixels[..., 1] > 120) & (pixels[..., 2] < 90)


def differing(patch, reference):
    """Share of pixels that differ visibly (summed channel difference over 60) from a reference patch."""
    return float((np.abs(patch - reference).sum(axis=-1) > 60).mean())


def wire_match(frame, columns):
    """Share of the fixture's wireframe lines in these columns that show amber in the frame."""
    lines = amber(wireframe().astype(np.int16)[:, columns])
    return float(amber(frame[:, columns])[lines].mean())


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return frames(build(tmp_path_factory.mktemp("banner")))


def test_the_build_is_a_webp_that_loops_forever_with_exact_delays(tmp_path):
    out = build(tmp_path)
    with Image.open(out) as image:
        assert image.format == "WEBP" and image.is_animated and image.n_frames == FRAMES
        assert image.size == SIZE and image.info["loop"] == 0
    delays = [d for _, d in frames(out)]
    assert set(delays) == {41, 42} and sum(delays) == 1000


REF_NAMES = {
    ("sign-tokens", 0): "sign-tokens-23-4b", ("sign-commits", 0): "sign-commits-1532",
    ("holo-1", 0): "hologram-portfolio", ("holo-2", 0): "hologram-bionic-wave", ("holo-3", 0): "hologram-ka-tech",
    ("billboard", 0): "billboard-portfolio", ("billboard", 4): "billboard-bionic-wave", ("billboard", 23): "billboard-systemselect",
}


@pytest.mark.parametrize("area_id, frame", list(REF_NAMES))
def test_each_area_shows_its_known_text(built, area_id, frame):
    patch = built[frame][0][box(area_id)]
    path = REFS / f"{REF_NAMES[area_id, frame]}.png"
    if os.environ.get("BANNER_WRITE_REFS"):
        REFS.mkdir(exist_ok=True)
        Image.fromarray(patch.astype(np.uint8)).save(path)
    reference = np.asarray(Image.open(path).convert("RGB"), np.int16)
    assert differing(patch, reference) < 0.01


def test_other_numbers_do_not_match_the_reference_patches(tmp_path):
    other = frames(build(tmp_path, {"totals": {"tokens": 98_700_000_000, "commits": 4321}}))[0][0]
    for area_id in ("sign-tokens", "sign-commits"):
        reference = np.asarray(Image.open(REFS / f"{REF_NAMES[area_id, 0]}.png").convert("RGB"), np.int16)
        assert differing(other[box(area_id)], reference) > 0.05


def test_text_is_hidden_where_the_mask_covers_it(built):
    rows, _ = box("sign-commits", margin=0)
    frame = built[0][0]
    covered = slice(COMMITS_COVER, 154)
    shown = slice(82, COMMITS_COVER)
    assert np.abs(frame[rows, covered] - background(0)[rows, covered]).mean() < 3
    assert np.abs(frame[rows, shown] - background(0)[rows, shown]).mean() > 15


def test_the_wireframe_shows_only_in_its_window_behind_the_scan_line(built):
    cyan = np.zeros((*SIZE[::-1], 3), np.int16)
    cyan[...] = (0, 255, 255)
    assert wire_match(cyan, slice(0, SIZE[0])) == 0
    assert wire_match(wireframe().astype(np.int16), slice(0, SIZE[0])) == 1
    window, plan = sweep_frames()
    assert window and 0 not in window
    for i, (frame, _) in enumerate(built):
        if i in window:
            left, right = (round(f * SIZE[0]) for f in plan[i]["sweep"])
            band, outside = slice(left + 2, right - 2), slice(right + 2, None) if left == 0 else slice(0, left - 2)
            assert wire_match(frame, band) > 0.8
            assert amber(frame[:, outside]).sum() == 0
        else:
            assert amber(frame).sum() == 0, f"wireframe leaked into frame {i + 1}"


def test_text_under_the_scan_line_turns_to_a_cyan_outline(built):
    window, plan = sweep_frames()
    i = next(i for i in window if plan[i]["sweep"][0] == 0)
    patch = built[i][0][box("sign-tokens", margin=0)]
    cyan = (patch[..., 0] < 110) & (patch[..., 1] > 150) & (patch[..., 2] > 150)
    magenta = (patch[..., 0] > 150) & (patch[..., 1] < 110) & (patch[..., 2] > 150)
    assert cyan.sum() > 20 and magenta.sum() == 0


def area(area_id):
    return next(a for a in spots()["areas"] if a["id"] == area_id)


@pytest.mark.parametrize("area_id, text", [("sign-tokens", "104.2B TOKENS"), ("sign-commits", "10,000 COMMITS"),
                                           ("holo-2", "Bionic Wave"), ("billboard", "SystemSelect")])
def test_worst_cases_fit_their_cell_without_touching_its_edge(area_id, text):
    ink = np.asarray(banner.text_cell(area(area_id), text)) > 0
    assert ink.any() and not (ink[0].any() or ink[-1].any() or ink[:, 0].any() or ink[:, -1].any())


@pytest.mark.parametrize("area_id, text", [("sign-tokens", "1000.0B TOKENS"), ("sign-commits", "100,000 COMMITS")])
def test_a_number_wider_than_its_worst_case_stops_the_build(area_id, text):
    with pytest.raises(SystemExit, match="does not fit"):
        banner.text_cell(area(area_id), text)


def test_the_command_builds_a_banner_from_a_folder_and_city_data(tmp_path, capsys):
    base = base_render(tmp_path / "base")
    (tmp_path / "city.json").write_text(json.dumps(CITY), encoding="utf-8")
    banner.main([str(base), str(tmp_path / "city.json"), str(tmp_path / "out.webp")])
    assert (tmp_path / "out.webp").stat().st_size > 0 and "banner:" in capsys.readouterr().out


def test_a_missing_base_render_file_stops_the_build(tmp_path):
    base = base_render(tmp_path / "base")
    (base / "masks" / "holo-2" / "0007.png").unlink()
    (tmp_path / "city.json").write_text(json.dumps(CITY), encoding="utf-8")
    with pytest.raises(SystemExit, match="base render missing"):
        banner.build(str(base), str(tmp_path / "city.json"), str(tmp_path / "out.webp"))


def test_the_glow_spreads_past_the_sign_edges(built):
    rows, cols = box("sign-tokens", margin=0)
    below = slice(rows.stop, rows.stop + 4)
    glow = built[0][0][below, cols] - background(0)[below, cols]
    assert glow.mean() > 8
