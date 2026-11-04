import itertools
import json

import pytest

import overlay as o


@pytest.mark.parametrize("tokens, expected", [(23_400_000_000, "23.4B TOKENS"), (23_449_999_999, "23.4B TOKENS"),
                                              (104_249_000_000, "104.2B TOKENS"), (999_960_000, "1.0B TOKENS"),
                                              (5_250_000, "5.3M TOKENS"), (12_300, "12.3K TOKENS")])
def test_tokens_read_as_one_decimal_and_a_unit(tokens, expected):
    assert o.sign_text("tokens", tokens) == expected


@pytest.mark.parametrize("commits, expected", [(1532, "1,532 COMMITS"), (10_000, "10,000 COMMITS"), (7, "7 COMMITS")])
def test_commits_read_with_thousands_separators(commits, expected):
    assert o.sign_text("commits", commits) == expected


@pytest.mark.parametrize("value", [None, 0, -5, "1532", 1.5, True])
def test_a_missing_value_stops_the_build_and_never_shows_zero(value):
    with pytest.raises(SystemExit, match="missing"):
        o.sign_text("commits", value)


SIZE = (240, 120)


def area(id, kind, x, y, w=40, h=16):
    return {"id": id, "kind": kind, "corners": [[x, y], [x + w, y + 2], [x + w, y + h], [x, y + h - 2]],
            "color": "#ff2bd6", "blur": 1.5, "reflection": [[x, 100], [x + w, 100], [x + w, 112], [x, 112]]}


def spots():
    return {"areas": [area("sign-tokens", "tokens", 5, 6, 72, 20), area("sign-commits", "commits", 82, 6, 72, 20),
                      area("holo-1", "hologram", 10, 40), area("holo-2", "hologram", 60, 40),
                      area("holo-3", "hologram", 110, 40), area("billboard", "billboard", 160, 8, 76, 30)]}


def write_spots(tmp_path, value):
    path = tmp_path / "spots.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_a_good_spot_file_gives_six_areas(tmp_path):
    areas = o.load_spots(write_spots(tmp_path, spots()), SIZE)
    assert [a["id"] for a in areas] == ["sign-tokens", "sign-commits", "holo-1", "holo-2", "holo-3", "billboard"]


def broken(change):
    value = spots()
    change(value["areas"])
    return value


@pytest.mark.parametrize("change", [
    lambda a: a.pop(),                                            # five areas
    lambda a: a[3].update(id="holo-1"),                           # duplicate id
    lambda a: a[0].update(kind="neon"),                           # unknown kind
    lambda a: a[1].update(kind="tokens"),                         # two token signs, no commit sign
    lambda a: a[2]["corners"][1].__setitem__(0, 241),             # corner past the right edge
    lambda a: a[2]["corners"][0].__setitem__(1, -1),              # corner above the frame
    lambda a: a[4].update(corners=[[5, 5], [20, 5], [35, 5], [50, 5]]),  # zero area
    lambda a: a[5]["reflection"][2].__setitem__(1, 130),          # reflection outside the frame
    lambda a: a[0].pop("color"),                                  # missing field
], ids=["five", "dup-id", "bad-kind", "kinds-count", "right", "top", "zero-area", "reflection", "no-color"])
def test_a_broken_spot_file_stops_the_build(tmp_path, change):
    with pytest.raises(SystemExit, match="spot file"):
        o.load_spots(write_spots(tmp_path, broken(change)), SIZE)


CITY = {"totals": {"tokens": 23_400_000_000, "commits": 1532, "top_language": "Python"}}
CALM = [1.0] * 24


def areas():
    return spots()["areas"]


def plan(frames=24, flicker=None, city=CITY, **names):
    return o.plan(city, areas(), frames, flicker or [1.0] * frames, **names)


def test_every_frame_shows_both_numbers_and_the_three_hologram_names():
    for frame in plan():
        assert frame["texts"]["sign-tokens"] == "23.4B TOKENS"
        assert frame["texts"]["sign-commits"] == "1,532 COMMITS"
        assert [frame["texts"][f"holo-{i}"] for i in (1, 2, 3)] == ["Portfolio", "Bionic Wave", "KA Tech"]


@pytest.mark.parametrize("frames", [24, 288, 100])
def test_the_billboard_shows_seven_names_in_order_with_even_slots(frames):
    names = [frame["texts"]["billboard"] for frame in plan(frames)]
    slots = [(name, sum(1 for _ in group)) for name, group in itertools.groupby(names)]
    assert [name for name, _ in slots] == ["Portfolio", "Bionic Wave", "KA Tech", "KA Ops", "aios", "CRM", "SystemSelect"]
    assert max(n for _, n in slots) - min(n for _, n in slots) <= 1
    assert "New Era" not in names


def test_the_288_frame_loop_has_41_or_42_frame_slots():
    names = [frame["texts"]["billboard"] for frame in plan(288)]
    assert {sum(1 for _ in g) for _, g in itertools.groupby(names)} == {41, 42}


def test_flicker_never_dips_below_70_percent_and_is_shared():
    curve = [1.0, 0.2, 0.5, 0.95, 1.3, 0.0] * 4
    values = [set(frame["flicker"].values()) for frame in plan(flicker=curve)]
    assert all(len(v) == 1 for v in values)
    assert [v.pop() for v in values][1:6] == [0.7, 0.7, 0.95, 1.0, 0.7]


def test_frame_one_is_calm_even_when_the_curve_dips_there():
    first = plan(flicker=[0.3] + [1.0] * 23)[0]
    assert set(first["flicker"].values()) == {1.0} and first["sweep"] is None
    assert first["texts"]["billboard"] == "Portfolio"


@pytest.mark.parametrize("frames, length", [(24, 2), (288, 12)])
def test_one_sweep_of_about_half_a_second_per_loop_away_from_billboard_switches(frames, length):
    frames_plan = plan(frames)
    window = [i for i, frame in enumerate(frames_plan) if frame["sweep"] is not None]
    assert len(window) == length and window == list(range(window[0], window[0] + length)) and window[0] > 0
    names = [frame["texts"]["billboard"] for frame in frames_plan]
    assert len({names[i] for i in range(window[0] - 1, window[-1] + 2)}) == 1
    bands = [frames_plan[i]["sweep"] for i in window]
    assert bands[0][0] == 0 and bands[-1][1] == 1 and all(0 <= a < b <= 1 for a, b in bands)


def test_a_flicker_curve_of_the_wrong_length_stops_the_build():
    with pytest.raises(SystemExit, match="flicker"):
        plan(flicker=[1.0] * 23)


@pytest.mark.parametrize("city", [{}, {"totals": {"tokens": 5}}, {"totals": {"tokens": 0, "commits": 3}}])
def test_missing_city_numbers_stop_the_build(city):
    with pytest.raises(SystemExit, match="missing"):
        plan(city=city)


@pytest.mark.parametrize("names", [
    {"holograms": ("Portfolio", "Bionic Wave", "New Era")},
    {"projects": ("Portfolio", "Bionic Wave", "KA Tech", "KA Ops", "aios", "CRM", "acme-client-portal")},
    {"projects": ("Portfolio", "Bionic Wave", "KA Tech", "KA Ops", "aios", "CRM", "SystemSelect", "New Era")},
], ids=["hologram", "billboard", "new-era"])
def test_an_unapproved_name_is_refused(names):
    with pytest.raises(SystemExit, match="privacy"):
        plan(**names)


@pytest.mark.parametrize("text", ["23.4B TOKENS", "1,532 COMMITS", "KA Ops", "SystemSelect"])
def test_approved_strings_pass(text):
    assert o.approved(text)


@pytest.mark.parametrize("text", ["New Era", "23.4B COMMITS", "1532 COMMITS", "0x1F TOKENS", "kaops", "aios-private",
                                  "1,532 COMMITS\n", "23.4T TOKENS"])
def test_anything_else_is_not_approved(text):
    assert not o.approved(text)


@pytest.mark.parametrize("frames, total", [(288, 12000), (24, 1000), (12, 500)])
def test_frame_delays_are_41_or_42_ms_and_sum_to_the_loop(frames, total):
    delays = o.frame_delays(frames)
    assert len(delays) == frames and set(delays) == {41, 42} and sum(delays) == total
