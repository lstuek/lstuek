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
    low = [x.lower() for x in shown]  # the default label style is uppercase
    for want in expected:
        assert want.lower() in low, f"{want!r} missing from the card"
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
    # lifetime number, top-3 bars, shipped count, shipped bullets, and the three bar fills (token, top language, streak)
    assert sorted(r.strip() for r in cyan_rules) == sorted([".num.hot", ".bar.hot", ".bignum", ".sitedot", ".fill.hot", ".ring"])


def test_only_the_lifetime_number_is_cyan_and_the_stack_has_no_accent(tmp_path):
    svg = draw(tmp_path)
    nums = re.findall(r'<text [^>]*class="(num(?: hot)?)"[^>]*>([^<]+)</text>', svg)
    assert nums == [("num hot", "9,355"), ("num", "18"), ("num", "53")]
    assert svg.count('class="fill hot"') == 3 and svg.count('class="fill top"') == 0  # streak, top language, token bars
    stack = json.loads((FIX / "stack.json").read_text())
    assert not any("core" in item for item in stack) and "core" not in svg
    assert "billion tokens" not in svg and 'class="approx"' not in svg
    assert len(re.findall(r'class="icon"', svg)) == 22 and 'class="pill"' in svg


NUMERIC = {"num", "num hot", "bignum", "bigtok", "nlab", "peaklbl"}


def test_every_number_is_archivo_and_letters_use_young_serif_and_figtree(tmp_path):
    svg = draw(tmp_path)
    css = svg[svg.index("<style>"):svg.index("</style>")]
    assert re.search(r"\.name\{font:400 100px 'Young Serif'", css) and re.search(r"\.title\{font:400 13px 'Young Serif'", css)
    for cls, rule in ((".bigtok", "700 78px"), (".bignum", "700 76px"), (".num", "700 36px"), (".nlab", "600 12.5px"), (".peaklbl", "600 11.5px")):
        assert re.search(re.escape(cls) + r"\{font:" + re.escape(rule) + r" Archivo", css), cls
    assert re.search(r"\.nn\{font-family:Archivo", css) and re.search(r"\.lab\{font:500 12\.5px Figtree", css)
    fams = set(re.findall(r"@font-face\{font-family:'([^']+)'", css))
    assert fams == {"Young Serif", "Archivo", "Figtree"}
    assert "Nunito" not in svg and "DM Mono" not in svg and "Token" not in svg
    # structural: a digit sits in an Archivo class or in an inline `nn` span, never in plain Figtree or Young Serif text
    for el in ET.fromstring(svg).iter("{http://www.w3.org/2000/svg}text"):
        cls = el.get("class")
        if cls in NUMERIC:
            continue
        assert not re.search(r"\d", el.text or ""), (cls, el.text)
        for span in el:
            assert span.get("class") == "nn", (cls, span.text)
            assert not re.search(r"\d", span.tail or ""), (cls, span.tail)


def label_texts(svg):
    return [("".join(e.itertext())) for e in ET.fromstring(svg).iter("{http://www.w3.org/2000/svg}text") if e.get("class") == "sub"]


def test_label_styles(tmp_path):
    assert card.LABEL_STYLE == "a" and card.LABEL_STYLE in card.LABEL_STYLES
    d = card.gather(str(FIX))
    a, b, c = (label_texts(card.build(d, k)) for k in ("a", "b", "c"))
    assert "23 TOOLS" in a and "1,231 IN THE LAST 31 DAYS" in a and "ALL TIME" in a and "BY BYTES" in a and "LIVE SITES" in a
    assert "SINCE AUG 2026" in a and "GITHUB.COM/LSTUEK" in a and "SEP 10" in a and "TODAY" in a
    assert "23 tools" in b and "1,231 in the last 31 days" in b and "github.com/lstuek" in b and "live sites" in b
    assert set(b) - set(c) == {"23 tools", "live sites", "github.com/lstuek", "profile card, updated 2026-10-11 00:29 utc"}
    assert "23 tools" not in c and "live sites" not in c and "github.com/lstuek" not in c
    assert "1,231 in the last 31 days" in c and "all time" in c and "since Aug 2026" in c
    assert card.build(d) == card.build(d, "a") and card.STYLE == "a"  # the default is option a


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


def test_bars_with_ticks(tmp_path):
    svg = draw(tmp_path)
    fills = re.findall(r'<rect [^>]*class="(fill[^"]*)"', svg)
    assert fills.count("fill hot") == 3 and fills.count("fill") == 5  # 5 other language bars, no ticks on them
    # ticks: streak 18 of best 53 -> min(53, 20) = 19 cuts, top language 9 cuts, token 20B goal -> 19 cuts
    assert svg.count('class="tick"') == 19 + 9 + 19


def style_block(svg):
    return svg[svg.index("<style>"):svg.index("</style>")]


def test_motion_is_css_only_with_a_reduced_motion_block(tmp_path):
    svg = draw(tmp_path)
    css = style_block(svg)
    for name in ("rise", "grow", "shine", "ring", "pop"):
        assert f"@keyframes {name}" in css, name
    block = css[css.index("@media (prefers-reduced-motion:reduce)"):]
    for sel in (".bar", ".fill.hot", ".peaklbl", ".shine", ".ring"):
        assert sel in block.split("}")[0], sel
    assert "animation:none" in block
    assert "<script" not in svg and "<animate" not in svg and "<set " not in svg
    # one-shot rise, looping shimmer and rings with a 3-4 s cycle
    assert re.search(r"\.bar\{[^}]*animation:rise [^;}]*backwards", css) and "infinite" not in re.search(r"\.bar\{[^}]*\}", css).group(0)
    assert re.search(r"\.shine\{animation:shine 3\.6s ease-in-out [\d.]+s infinite\}", css)
    assert re.search(r"\.ring\{[^}]*animation:ring 3\.6s ease-out infinite", css)


def test_resting_state_is_the_finished_card(tmp_path):
    svg = draw(tmp_path)
    css = style_block(svg)
    # base styles carry no transform or hidden state outside the animations: bars at full height, dots plain, shine off the fill
    assert not re.search(r"\.(?:bar|fill)[^{}]*\{[^}]*transform:(?!none)", css.split("@keyframes")[0])
    assert re.search(r"\.ring\{[^}]*opacity:0", css)  # rings invisible at rest
    assert svg.count('class="sitedot"') == 6 and svg.count('class="ring"') == 6
    assert 'class="shine" x="' in svg and len(re.findall(r'<rect [^>]*class="bar[^"]*"[^>]*style="animation-delay:\d+ms"', svg)) == 31


def test_same_data_gives_byte_identical_svg(tmp_path):
    a = draw(tmp_path / "a")
    b = draw(tmp_path / "b")
    assert a == b
    d = card.gather(str(FIX))
    assert card.build(d) == card.build(d)


def test_card_is_shorter_than_before():
    h = int(re.search(r'<svg [^>]*height="(\d+)"', card.build(card.gather(str(FIX)))).group(1))
    assert h < 1080 and h == 985
