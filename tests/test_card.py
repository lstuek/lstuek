import json
import pathlib
import re
import xml.etree.ElementTree as ET

import card

FIX = pathlib.Path(__file__).parent / "fixtures" / "card"
SCRIPT = pathlib.Path(card.__file__)


def draw(tmp_path):
    out = tmp_path / "card.svg"
    assert card.main(["--offline", str(FIX), "--out", str(out)]) == 0
    return out.read_text(encoding="utf-8")


def texts(svg):
    """All text and title content of the card, in document order."""
    root = ET.fromstring(svg)
    return ["".join(e.itertext()) for e in root.iter() if e.tag.endswith(("text", "title"))]


def test_fixture_values_appear_on_the_card(tmp_path):
    svg = draw(tmp_path)
    shown = texts(svg)
    pc = json.loads((FIX / "pc.json").read_text())
    langs = pc["languages"]
    total = sum(langs.values())
    top6 = sorted(langs.items(), key=lambda kv: -kv[1])[:6]
    expected = [
        "LINCOLN STUEK",
        "23 tools",                      # stack fixture after the trim
        "1,231 in the last 31 days",     # contributions panel total
        "Sep 10", "today", "92",         # both end labels, peak bar
        "9,355",                         # lifetime contributions (two calendars)
        "18", "53", "18/53",             # current streak, best streak, bar label
        "18,433,327,072",                # token spend, full number
        "since Aug 2026", "18.4B/20B",
        "Codex",                         # null icon: text label
    ] + [n for n, _ in top6] + [f"{b * 100 / total:.1f}%" for _, b in top6]
    for want in expected:
        assert want in shown, f"{want!r} missing from the card"
    assert "56.6%" in shown and "19.5%" in shown and len(top6) == 6
    for gone in ("Next.js", "Astro", "Express", "Drizzle ORM", "Docker", "shadcn/ui"):
        assert gone not in svg


def bar_classes(svg):
    return re.findall(r'<rect [^>]*class="(bar[^"]*)"[^>]*><title>([^<]+)</title>', svg)


def test_bars_are_31_days_and_the_top_three_days_are_hot(tmp_path):
    bars = bar_classes(draw(tmp_path))
    assert len(bars) == 31
    hot = [title for cls, title in bars if cls == "bar hot"]
    assert hot == ["2026-09-19: 81", "2026-09-24: 92", "2026-10-03: 88"]
    assert all(cls in ("bar", "bar zero") for cls, _ in bars if _ not in hot)
    assert bars[-1][0] != "bar hot"  # today is a normal bar unless it is top 3


def test_equal_days_pick_the_earliest_first():
    d = card.gather(str(FIX))
    d["last31"] = [(f"2026-09-{n:02d}", 3) for n in range(1, 32)][:30] + [("2026-10-01", 3)]
    hot = [t for c, t in bar_classes(card.build(d)) if c == "bar hot"]
    assert hot == ["2026-09-01: 3", "2026-09-02: 3", "2026-09-03: 3"]


def test_no_hot_bar_on_a_quiet_month():
    d = card.gather(str(FIX))
    d["last31"] = [(f"2026-09-{n:02d}", 0) for n in range(1, 32)]
    assert not [c for c, _ in bar_classes(card.build(d)) if c == "bar hot"]


def test_shipped_panel_lists_the_sites(tmp_path):
    shown = texts(draw(tmp_path))
    shipped = json.loads((FIX / "shipped.json").read_text())
    assert "SHIPPED" in shown and "6" in shown and "live sites" in shown
    for row in shipped:
        assert row["site"] in shown and row["kind"] in shown
    assert len(shipped) == 6


def test_shipped_clips_long_names_and_caps_at_seven():
    d = card.gather(str(FIX))
    d["shipped"] = [{"site": "a-very-long-subdomain-name.example-company-site.com", "kind": "browser games"}] * 9
    card.build(d)
    shown = texts(card.build(d))
    assert "9" in shown and sum(1 for s in shown if s.endswith("...")) == 7


def test_dark_only_black_background_and_cyan_is_scarce(tmp_path):
    svg = draw(tmp_path)
    assert 'class="bg"' in svg and ".bg{fill:#000000}" in svg
    assert "#f6f1e4" not in svg and "#e8512a" not in svg
    css = svg[svg.index("<style>"):svg.index("</style>")]
    cyan_rules = re.findall(r"([^{}]+)\{[^{}]*#5cc8ff[^{}]*\}", css)
    # lifetime number, top-3 bars, shipped count, shipped bullets
    assert sorted(r.strip() for r in cyan_rules) == sorted([".num.hot", ".bar.hot", ".bignum", ".sitedot"])


def test_only_the_lifetime_number_is_cyan_and_the_stack_has_no_accent(tmp_path):
    svg = draw(tmp_path)
    nums = re.findall(r'<text [^>]*class="(num(?: hot)?)"[^>]*>([^<]+)</text>', svg)
    assert nums == [("num hot", "9,355"), ("num", "18"), ("num", "53")]
    assert svg.count('class="fill hot"') == 0 and svg.count('class="fill top"') >= 3  # streak, token and top language bars
    stack = json.loads((FIX / "stack.json").read_text())
    assert not any("core" in item for item in stack) and "core" not in svg
    assert "billion tokens" not in svg and 'class="approx"' not in svg
    assert len(re.findall(r'class="icon"', svg)) == 22 and 'class="pill"' in svg


def test_numbers_use_nunito_and_letters_use_young_serif(tmp_path):
    svg = draw(tmp_path)
    css = svg[svg.index("<style>"):svg.index("</style>")]
    assert re.search(r"\.name\{font:400 100px 'Young Serif'", css)
    assert re.search(r"\.bigtok\{font:700 96px Nunito", css) and re.search(r"\.num\{font:700 40px Nunito", css)
    assert re.search(r"\.nlab\{font:600 12\.5px Nunito", css)
    assert re.search(r"\.lab\{font:500 12\.5px Figtree", css) and "'DM Mono'" in css


def test_svg_is_self_contained_and_small(tmp_path):
    svg = draw(tmp_path)
    ET.fromstring(svg)  # well-formed
    urls = re.findall(r"https?://[^\s\"')<>]+", svg)
    assert urls == ["http://www.w3.org/2000/svg"], urls
    assert "href" not in svg and "@import" not in svg
    assert len(svg.encode("utf-8")) < 300 * 1024


def test_streaks_and_next_round():
    days = {"2026-01-01": 1, "2026-01-02": 2, "2026-01-03": 0, "2026-01-04": 5, "2026-01-05": 0}
    assert card.streaks(days) == (1, 2)          # today (a zero) does not break the current streak
    assert card.streaks({"a": 0}) == (0, 0)
    assert [card.next_round(b) for b in (0.4, 18.43, 20, 92, 100.5)] == [1, 20, 50, 100, 200]


def test_every_subprocess_hides_its_window():
    src = SCRIPT.read_text(encoding="utf-8")
    calls = len(re.findall(r"subprocess\.(?:run|Popen|call|check_output)\(", src))
    flags = src.count('creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)')
    assert calls >= 1 and calls == flags
