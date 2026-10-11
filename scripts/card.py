#!/usr/bin/env python3
"""Draws the profile card: assets/card.svg (dark).

  python scripts/card.py                       data/*.json + the public contribution calendar (gh api)
  python scripts/card.py --offline DIR         fixture files in DIR only, no network, no gh

Python stdlib only. The SVG makes no external requests: icons are inlined as paths and the
fonts are base64 WOFF2 subsets (Basic Latin) with system-safe fallbacks. The font blobs, advance
widths and cap heights sit at the bottom of this file. They were cut from OFL-1.1 fonts
(fontsource files, subset with fontTools): Young Serif 400 for letters (U+0020-007E), Archivo
600/700 for every number (digits and , . : - % / B only), Figtree 500 for small text.
"""
import argparse
import datetime
import json
import math
import pathlib
import re
import subprocess
import sys
import urllib.request
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOGIN = "lstuek"
ICON_URL = "https://cdn.jsdelivr.net/npm/simple-icons@13.21.0/icons/{}.svg"
ICON_CACHE = ROOT / "tests" / "fixtures" / "card" / "icons"

W = 855
PAD = 26
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

LABEL_STYLE = "a"  # one-line pick for the small labels beside titles: a key of LABEL_STYLES
LABEL_STYLES = {
    "a": "Figtree uppercase, letter-spaced, grey; numbers in Archivo",
    "b": "Figtree sentence case, grey; numbers in Archivo",
    "c": "as b, minus labels that repeat the panel (23 tools, live sites, github.com/lstuek)",
}
DROP_IN_C = {"stack_count", "live_sites", "top_left"}
STYLE = LABEL_STYLE
FILES = {"disp": "young", "num": "arch7", "num6": "arch6", "sans5": "figtree5"}
DISP = "'Young Serif',Georgia,'Times New Roman',serif"
NUM = "Archivo,'Segoe UI',Arial,sans-serif"
SANS = "Figtree,'Segoe UI',Arial,sans-serif"
SUB_CSS = {"a": f"font:500 10.5px {SANS};letter-spacing:1.3px", "b": f"font:500 12px {SANS}", "c": f"font:500 12px {SANS}"}
C = {"bg": "#000000", "text": "#f4f6f8", "muted": "#9aa3b2", "light": "#b9c0cc", "bar": "#6b7685", "line": "#ffffff",
     "cyan": "#5cc8ff"}  # cyan marks only: lifetime number, top-3 bars, shipped count and bullets


# ---------------------------------------------------------------- data

def run_gh(args):
    done = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=120)
    if done.returncode:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {done.stderr.strip()[:200]}")
    return json.loads(done.stdout)


def load_calendars_online(now):
    years = run_gh(["api", "graphql", "-f",
                    f'query={{user(login:"{LOGIN}"){{contributionsCollection{{contributionYears}}}}}}'])
    years = years["data"]["user"]["contributionsCollection"]["contributionYears"]
    cal = "contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}"
    parts = []
    for y in years:
        end = min(f"{y}-12-31T23:59:59Z", now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        parts.append(f'y{y}:contributionsCollection(from:"{y}-01-01T00:00:00Z",to:"{end}"){{{cal}}}')
    data = run_gh(["api", "graphql", "-f", f'query={{user(login:"{LOGIN}"){{{" ".join(parts)}}}}}'])
    return [v["contributionCalendar"] for v in data["data"]["user"].values()]


def load_icon(slug, offline):
    """Path data (24x24 Simple Icons box) or None. Online: jsdelivr, cache dir as fallback."""
    if not slug:
        return None
    svg = None
    if not offline:
        try:
            with urllib.request.urlopen(ICON_URL.format(slug), timeout=15) as resp:
                svg = resp.read().decode("utf-8")
        except Exception:
            svg = None
    if svg is None:
        f = ICON_CACHE / f"logo-{slug.rstrip('0123456789')}.svg"  # css3 -> logo-css: media names carry no trailing number
        svg = f.read_text(encoding="utf-8") if f.exists() else None
    m = re.search(r'<path[^>]*\bd="([^"]+)"', svg or "")
    return m.group(1) if m else None


def flatten_days(calendars):
    days = {}
    for cal in calendars:
        for week in cal["weeks"]:
            for d in week["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
    return dict(sorted(days.items()))


def streaks(days):
    counts = list(days.values())
    best = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        best = max(best, run)
    cur = 0
    rest = counts[:-1] if counts and counts[-1] == 0 else counts  # today may not have happened yet
    for c in reversed(rest):
        if c <= 0:
            break
        cur += 1
    return cur, max(best, cur)


def next_round(billions):
    for step in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000):
        if step > billions:
            return step
    return int(billions) + 1


def gather(offline=None):
    """Everything the card shows, from DIR (offline) or data/ plus gh."""
    base = pathlib.Path(offline) if offline else ROOT / "data"
    read = lambda name: json.loads((base / name).read_text(encoding="utf-8"))
    pc, stack, shipped = read("pc.json"), read("stack.json"), read("shipped.json")
    if offline:
        cals = read("contributions.json")["calendars"]
    else:
        cals = load_calendars_online(datetime.datetime.now(datetime.timezone.utc))
    days = flatten_days(cals)
    cur, best = streaks(days)
    last31 = [(k, days[k]) for k in list(days)[-31:]]
    langs = pc["languages"]
    total_bytes = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:6]
    return {
        "updated": pc["updated"],
        "tokens": pc["tokens"],
        "stack": stack,
        "icons": {s["icon"]: load_icon(s["icon"], bool(offline)) for s in stack if s.get("icon")},
        "last31": last31,
        "month_total": sum(v for _, v in last31),
        "lifetime": sum(days.values()),
        "cur": cur,
        "best": best,
        "langs": [(n, b * 100 / total_bytes) for n, b in top],
        "shipped": shipped,
    }


# ---------------------------------------------------------------- text helpers

def tw(slot, text, size, ls=0.0):
    widths = FONT_WIDTHS[FILES[slot]]
    return sum(widths.get(c, 600) for c in text) * size / 1000 + ls * len(text)


def fit(slot, text, size, max_w, ls=0.0):
    while size > 8 and tw(slot, text, size, ls) > max_w:
        size -= 0.5
    return size


def clip_text(slot, text, size, max_w):
    if tw(slot, text, size) <= max_w:
        return text
    while text and tw(slot, text + "...", size) > max_w:
        text = text[:-1]
    return text + "..."


def fmt_int(n):
    return f"{int(n):,}"


def fmt_month(ym):
    y, m = ym.split("-")[:2]
    return f"{MONTHS[int(m) - 1]} {y}"


def t(x, y, text, cls, anchor=None, size=None):
    a = f' text-anchor="{anchor}"' if anchor else ""
    st = f' style="font-size:{size:.1f}px"' if size else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}"{a}{st}>{escape(str(text))}</text>'


def hline(y):
    return f'<line x1="0" y1="{y:.1f}" x2="{W}" y2="{y:.1f}" class="rule"/>'


def vline(x, y1, y2):
    return f'<line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}" class="rule"/>'


def cross(x, y, r=4):
    return f'<path d="M{x - r:.1f} {y:.1f}H{x + r:.1f}M{x:.1f} {y - r:.1f}V{y + r:.1f}" class="reg"/>'


def shown(key):
    return not (STYLE == "c" and key in DROP_IN_C)


def label(x, y, text, key, anchor=None):
    """Small grey label: Figtree, with every number run set in Archivo."""
    if not shown(key):
        return ""
    if STYLE == "a":
        text = text.upper()
    parts = re.split(r"(\d[\d,.:/-]*)", text)
    inner = "".join(f'<tspan class="nn">{escape(p)}</tspan>' if i % 2 else escape(p) for i, p in enumerate(parts))
    a = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" class="sub"{a}>{inner}</text>'


def panel_title(x, y, name, sub="", key=""):
    return t(x, y, name, "title") + (label(x + tw("disp", name, 13, 1.4) + 10, y, sub, key) if sub else "")


def ticks(x, y, w, h, steps):
    """Tick marks across a bar: `steps` equal parts, cut in the background color."""
    return "".join(f'<line x1="{x + w * i / steps:.1f}" y1="{y + h * 0.2:.1f}" x2="{x + w * i / steps:.1f}" y2="{y + h * 0.8:.1f}" class="tick"/>'
                   for i in range(1, steps))


# ---------------------------------------------------------------- panels

def p_header(d, y, h):
    name = "LINCOLN STUEK"
    size = min(130, fit("disp", name, 130, W - 2 * PAD - 8, 1))
    cap = FONT_CAP[FILES["disp"]] / 1000
    return t(PAD, y + h / 2 + cap * size / 2, name, "name", size=size)


def p_stack(d, y):
    items = d["stack"]
    icon_w, gap, ggap, pill_pad = 30, 20, 40, 11
    widths = [icon_w if d["icons"].get(i.get("icon")) else tw("sans5", i["name"], 12.5) + 2 * pill_pad for i in items]
    groups = []
    for it, w in zip(items, widths):
        if groups and groups[-1][0] == it["group"]:
            groups[-1][1].append((it, w))
        else:
            groups.append((it["group"], [(it, w)]))
    gw = [sum(w for _, w in g[1]) + gap * (len(g[1]) - 1) for g in groups]
    total = sum(gw) + ggap * (len(gw) - 1)
    nrows = max(1, -(-int(total) // (W - 2 * PAD - 20)))
    rows, cur, curw = [], [], 0
    target = total / nrows
    for g, w in zip(groups, gw):
        if cur and curw + ggap + w / 2 > target and len(rows) < nrows - 1:
            rows.append((cur, curw))
            cur, curw = [], 0
        curw += (ggap if cur else 0) + w
        cur.append((g, w))
    rows.append((cur, curw))
    out = [panel_title(PAD, y + 32, "STACK", f"{len(items)} tools", "stack_count")]
    ry = y + 52
    for row, rw in rows:
        x = (W - rw) / 2
        for gi, (g, w) in enumerate(row):
            if gi:
                out.append(f'<circle cx="{x - ggap / 2:.1f}" cy="{ry + 15}" r="2" class="dot"/>')
            for it, iw in g[1]:
                path = d["icons"].get(it.get("icon"))
                name = escape(it["name"])
                if path:
                    s = icon_w * 0.8 / 24
                    out.append(f'<g><title>{name}</title><path transform="translate({x + icon_w * 0.1:.1f} {ry + 3:.1f}) '
                               f'scale({s:.3f})" d="{path}" class="icon"/></g>')
                else:
                    out.append(f'<rect x="{x:.1f}" y="{ry + 2}" width="{iw:.1f}" height="26" rx="13" class="pill"/>'
                               + t(x + iw / 2, ry + 19.5, it["name"], "pilltxt", "middle"))
                x += iw + gap
            x += ggap - gap
        ry += 46
    return "".join(out), ry + 4 - y


def p_contrib(d, y, h, w):
    x0, out = PAD, []
    out.append(panel_title(x0, y + 32, "CONTRIBUTIONS", f"{fmt_int(d['month_total'])} in the last 31 days", "month"))
    bars = d["last31"]
    aw = w - 2 * PAD
    pitch = aw / 31
    bw = pitch * 0.68
    base = y + h - 46
    top = y + 66
    mx = max(v for _, v in bars) or 1
    order = sorted(range(len(bars)), key=lambda i: (-bars[i][1], i))  # ties: earliest first
    peak_i = order[0]
    top3 = {i for i in order[:3] if bars[i][1] > 0}
    out.append(f'<line x1="{x0}" y1="{base + 1}" x2="{x0 + aw}" y2="{base + 1}" class="axis"/>')
    for i, (date, v) in enumerate(bars):
        bh = 2 if v == 0 else max(3, (base - top) * v / mx)
        bx = x0 + i * pitch + (pitch - bw) / 2
        cls = "bar hot" if i in top3 else ("bar zero" if v == 0 else "bar")
        out.append(f'<rect x="{bx:.1f}" y="{base - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="1.5" class="{cls}"><title>{date}: {v}</title></rect>')
        if i == peak_i:
            out.append(t(bx + bw / 2, base - bh - 7, v, "peaklbl", "middle"))
    s = datetime.date.fromisoformat(bars[0][0])
    out.append(label(x0, base + 22, f"{MONTHS[s.month - 1]} {s.day}", "axis"))
    out.append(label(x0 + aw, base + 22, "today", "axis", "end"))
    return "".join(out)


def p_totals(d, x, y, h, w):
    x0, out = x + PAD, []
    aw = w - 2 * PAD
    out.append(panel_title(x0, y + 32, "TOTALS", "all time", "all_time"))
    rows = [(fmt_int(d["lifetime"]), "contributions"),
            (fmt_int(d["cur"]), "day streak, current"),
            (fmt_int(d["best"]), "day streak, best")]
    ry = y + 82
    for num, lab in rows:
        out.append(t(x0, ry, num, "num hot" if lab == "contributions" else "num", size=fit("num", num, 40, 98)))
        out.append(t(x0 + 108, ry - 5, lab, "lab"))
        ry += 50
    by = ry - 12
    tw_ = aw - 62
    frac = min(1, d["cur"] / d["best"]) if d["best"] else 0
    out.append(f'<rect x="{x0}" y="{by}" width="{tw_}" height="14" rx="7" class="track"/>')
    if frac > 0:
        out.append(f'<rect x="{x0}" y="{by}" width="{max(14, tw_ * frac):.1f}" height="14" rx="7" class="fill hot"/>')
        out.append(ticks(x0, by, tw_, 14, min(d["best"], 20)))
    out.append(t(x0 + aw, by + 12, f"{d['cur']}/{d['best']}", "nlab", "end"))
    return "".join(out)


def p_langs(d, x, y, h, w):
    x0, out = x + PAD, []
    aw = w - 2 * PAD
    out.append(panel_title(x0, y + 32, "LANGUAGES", "by bytes", "bytes"))
    bx, bw = x0 + 108, aw - 108 - 52
    ry = y + 74
    for i, (name, pct) in enumerate(d["langs"]):
        out.append(t(x0, ry, clip_text("sans5", name, 13.5, 100), "row"))
        out.append(f'<rect x="{bx}" y="{ry - 11}" width="{bw}" height="12" rx="6" class="track"/>')
        out.append(f'<rect x="{bx}" y="{ry - 11}" width="{max(12, bw * pct / 100):.1f}" height="12" rx="6" class="{"fill hot" if i == 0 else "fill"}"/>')
        if i == 0:
            out.append(ticks(bx, ry - 11, bw, 12, 10))
        out.append(t(x0 + aw, ry, f"{pct:.1f}%", "nlab", "end"))
        ry += 36
    return "".join(out)


def p_shipped(d, x, y, h, w):
    x0, out = x + PAD, []
    aw = w - 2 * PAD
    sites = d["shipped"][:7]
    big = str(len(d["shipped"]))
    out.append(panel_title(x0, y + 32, "SHIPPED", "live sites", "live_sites"))
    out.append(t(x0, y + 100, big, "bignum"))
    tx = x0 + tw("num", big, 76) + 22
    out.append(t(tx, y + 78, "live sites" if len(d["shipped"]) != 1 else "live site", "row"))
    out.append(t(tx, y + 97, "built by me, public today", "lab"))
    ry = y + 134
    for i, s in enumerate(sites):
        kind = s["kind"]
        kw = tw("sans5", kind, 12.5)
        out.append(f'<circle cx="{x0 + 3}" cy="{ry - 4.5}" r="3" class="sitedot"/>')
        out.append(t(x0 + 16, ry, clip_text("sans5", s["site"], 13, aw - 16 - kw - 14), "site"))
        out.append(t(x0 + aw, ry, kind, "kind", "end"))
        if i < len(sites) - 1:
            out.append(f'<line x1="{x0}" y1="{ry + 8}" x2="{x0 + aw}" y2="{ry + 8}" class="hair"/>')
        ry += 22
    return "".join(out)


def p_tokens(d, y, h):
    tk = d["tokens"]
    total = tk["total"]
    out = [panel_title(PAD, y + 32, "TOKEN SPEND", f"since {fmt_month(tk['since'])}", "since")]
    full = fmt_int(total)
    size = min(96, fit("num", full, 96, 590))
    out.append(t(PAD, y + 124, full, "bigtok", size=size))
    goal = next_round(total / 1e9)
    bx, bw, by = PAD, W - 2 * PAD - 92, y + 148
    out.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="20" rx="10" class="track"/>')
    out.append(f'<rect x="{bx}" y="{by}" width="{max(20, bw * total / (goal * 1e9)):.1f}" height="20" rx="10" class="fill hot"/>')
    out.append(ticks(bx, by, bw, 20, min(goal, 20)))
    out.append(t(W - PAD, by + 15, f"{total / 1e9:.1f}B/{goal}B", "nlab", "end"))
    return "".join(out)


# ---------------------------------------------------------------- page

def build(d, label_style=None):
    global STYLE
    STYLE = label_style or LABEL_STYLE
    strip_h, head_h, contrib_h, lang_h, tok_h = 40, 172, 248, 276, 196
    y = 0
    body = []
    upd = datetime.datetime.fromisoformat(d["updated"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    body.append(label(PAD, 25, "github.com/lstuek", "top_left"))
    body.append(label(W - PAD, 25, f"{'updated' if STYLE == 'c' else 'profile card, updated'} {upd} utc", "updated", "end"))
    y += strip_h
    rules = [y]
    body.append(p_header(d, y, head_h))
    y += head_h
    rules.append(y)
    stack_svg, stack_h = p_stack(d, y)
    body.append(stack_svg)
    y += stack_h
    rules.append(y)
    split = 560
    body.append(p_contrib(d, y, contrib_h, split))
    body.append(p_totals(d, split, y, contrib_h, W - split))
    vsplit1 = (split, y, y + contrib_h)
    y += contrib_h
    rules.append(y)
    half = W / 2
    body.append(p_langs(d, 0, y, lang_h, half))
    body.append(p_shipped(d, half, y, lang_h, W - half))
    vsplit2 = (half, y, y + lang_h)
    y += lang_h
    rules.append(y)
    body.append(p_tokens(d, y, tok_h))
    y += tok_h
    H = y
    lines = [hline(r) for r in rules] + [vline(*vsplit1), vline(*vsplit2)]
    marks = [cross(vsplit1[0], vsplit1[1]), cross(vsplit1[0], vsplit1[2]), cross(vsplit2[0], vsplit2[1]), cross(vsplit2[0], vsplit2[2])]
    summary = (f"Profile card for Lincoln Stuek: {fmt_int(d['lifetime'])} contributions, "
               f"{d['cur']} day streak, {fmt_int(d['tokens']['total'])} tokens, {len(d['shipped'])} live sites shipped.")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(summary)}">'
            f'<title>{escape(summary)}</title><style>{css()}</style>'
            f'<defs><clipPath id="card"><rect width="{W}" height="{H}" rx="16"/></clipPath></defs>'
            f'<g clip-path="url(#card)"><rect width="{W}" height="{H}" class="bg"/>'
            + "".join(lines) + "".join(marks) + "".join(body) +
            f'</g><rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="15.5" class="frame"/></svg>')


def css():
    c = C
    fam = (("disp", "Young Serif", 400), ("num6", "Archivo", 600), ("num", "Archivo", 700), ("sans5", "Figtree", 500))
    faces = "".join(f"@font-face{{font-family:'{n}';font-weight:{w};src:url(data:font/woff2;base64,{FONT_B64[FILES[k]]}) format('woff2')}}"
                    for k, n, w in fam)
    return (faces +
            f".bg{{fill:{c['bg']}}}.frame{{fill:none;stroke:{c['line']};stroke-opacity:.3}}"
            f".rule{{stroke:{c['line']};stroke-opacity:.16;stroke-width:1}}.reg{{stroke:{c['line']};stroke-opacity:.45;stroke-width:1;fill:none}}"
            f".axis{{stroke:{c['line']};stroke-opacity:.4;stroke-width:1}}.hair{{stroke:{c['line']};stroke-opacity:.12}}"
            f".title{{font:400 13px {DISP};letter-spacing:1.4px;fill:{c['text']}}}.sub{{{SUB_CSS[STYLE]};fill:{c['muted']}}}.nn{{font-family:{NUM};font-weight:600}}"
            f".name{{font:400 100px {DISP};letter-spacing:1px;fill:{c['text']}}}"
            f".num{{font:700 40px {NUM};fill:{c['text']}}}.num.hot{{fill:{c['cyan']}}}"
            f".bignum{{font:700 76px {NUM};fill:{c['cyan']}}}.bigtok{{font:700 96px {NUM};fill:{c['text']}}}"
            f".nlab{{font:600 12.5px {NUM};fill:{c['text']}}}"
            f".lab{{font:500 12.5px {SANS};fill:{c['muted']}}}.row{{font:500 13.5px {SANS};fill:{c['text']}}}"
            f".site{{font:500 13px {SANS};fill:{c['text']}}}.kind{{font:500 12.5px {SANS};fill:{c['muted']}}}.sitedot{{fill:{c['cyan']}}}"
            f".peaklbl{{font:600 11.5px {NUM};fill:{c['text']}}}"
            f".pilltxt{{font:500 12.5px {SANS};fill:{c['light']}}}"
            f".pill{{fill:none;stroke:{c['light']};stroke-width:1.4}}"
            f".icon{{fill:{c['light']}}}.dot{{fill:{c['muted']};opacity:.7}}"
            f".bar{{fill:{c['bar']}}}.bar.hot{{fill:{c['cyan']}}}.bar.zero{{fill:{c['muted']};opacity:.5}}"
            f".track{{fill:{c['line']};fill-opacity:.1}}.fill{{fill:{c['bar']}}}.fill.hot{{fill:{c['cyan']}}}"
            f".tick{{stroke:{c['bg']};stroke-width:1.5}}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--offline", metavar="DIR", help="draw from fixture files in DIR only")
    ap.add_argument("--out", default=str(ROOT / "assets" / "card.svg"))
    args = ap.parse_args(argv)
    svg = build(gather(args.offline))
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8", newline="\n")
    print(f"{out} {len(svg.encode('utf-8'))} bytes")
    return 0


# ---- font data (generated; see the module docstring) ----
FONT_B64 = {
    "young": (
        "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"
        "wJ7Sl+ktb4iS+/Ye+J76SrlrB6Cg=="
    ),
    "figtree5": (
        "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"
        "fhPfWvJSrBH+t/cYdwLgAAAA=="
    ),
    "arch7": (
        "d09GMgABAAAAAAbUABAAAAAADNAAAAZ3AAIAQgAAAAAAAAAAAAAAAAAAAAAAAAAAGhQbg24cKgZgP1NUQVRaAFwRCAqNGIpeATYCJANICyYABC"
        "AFgUYHIAwHG1YKo6J2UE6xQP5x4JQtnde5ZlQtKHA9gqTYp0KeNCE58k+h1VmyXgUf337s78zuw9UyHiqlkDKHqDnxZY/HTf+yOQ/aMtF6QjVI"
        "KqopVMR1ruybKA+ft/f/BqOAMwibcFCQBULdFXdpop2tpd195HpgVyMwvsKRMLh3PMX9KgJ2DEJVVyhiByQMkVCVNbpOVQhRG+aMlXRO5QLxyW"
        "ttESjCGVquCTVKFJAGWp9SE0GWpx0nGqS3kHSMpHPkkQ8EgYgvkvPiuOUItKseUwmAPpzdos97VOmLfehD5Frwh/qkcUxvQPrt/+rloKrGkBWA"
        "XVApBGW5hYS9THLvViAT5csT5BArZQWKFcnTYSXZ+aLPzzDfLLUpAjDPSgk4RfnA7G6GmC3edxTHNlkLeI0b0WvCL44oX+i0u9jDMBwbJTHxEG"
        "f1AgTw4DdAm0AkTwBVAhji4zE9GsPgZYlOxwD9nenNsEtYjgotBBy1PAJEUPMPIDBHIwACYJSdIlcb7YFxAaOtu42at2Dj/x9E15Cxb///DaQX"
        "SZyugs3MVsXKFCklykXOagEqCHdVd8AjeV0AHHMha1u67iyS0pTOzmrgQ6sKGFUVEuSstDIuxZZmMo85R1iRaVnpQlGGtrwnwBLSImHEYZonYq"
        "ZsVffqFRQvPyJg4/HzELGYIUR1V7GSxV0GA1s895awkitZIbWvsQ0reR1QDk6TioWBvo5F+TWFw2r3xQDFrw4KMXSYgW09mxmiiADlkF+C3L3X"
        "Xy+vW+32PGB09qazxaiet9Qb354+w6KGQBiGoPg5vMyQ8aB6KS9HfHPRvnw7oOEqFsbEbgqKRahfzJ4XkPqW2lxGRsAoNBgqXrmP6h6uodXda7"
        "enzwj9WMCku/buFjaHWNw3CgxVtOt+JlbSPKwV1u2tYZKce8sUyeq3sGRiLNivGKAyrhDquHuUmpkn1rufne2R/OLe8RkUP/ere4rSHzcQ7QS6"
        "+bqoffseW8ywIR7h2/TMZdDdFkPghU3tLWEMDL3A7wS812rIQ9mis/UoDkX7FsS3gDzJohuc1S/DJFIUNnPa/2V/jKJn/rt77wm5m/69yO/Qfd"
        "OcFl1ZrSNUpRw1Vd9X/fOIaE7Rim+i5xmgavBzzuucL8lL2ulyz9LvXLZSPK88hT8EVWQSQJh4yFaFhctWmmhW4SamfvgZQTQ8LJVIZD/p8XHk"
        "e+wgOxN7dvD7JPk9O9Ae/K99B+HJ4x0T9CHhBRFBmJj2JIMmwZWzL7DU1W+0M+RaqZ3RnSU4f9QrEJVH2Cx7i4BUrr2FN+F/zkaBr+Csb+lq8i"
        "Sp4UG+ZR6oIzpFU9/PiF11mhzR01nRUv5TQdY4xkj61oyCXPVNGZmPu2QlKy7qGdBxPFvbWHUD2kD54R/fHgmyoi2RkShJAB6d2kkJljUGPac9"
        "mpaUYqgoDV+u9Y/XJ1udTFiWZiLvJO9OUEMuqTrGETY1+KQRrsjaVlMeZyhcCt4ayJe8nN+fp8LonaJccKNASjfUyd4oJlEPdJBpMG7prFAcEK"
        "PQZCYM4pg6hesKgs2qcEGPPB+kAsCip05M2Abr8cMsbE0i43Wc4jj/ZSoSGf9xCIkMAs9kQce5Up9lE118k87/10PVNsQsXjNdJtdEG1SRKFlT"
        "x1ffQMct6x81J4GetjCGcnSIpnSFegLS+esqbTcDfR3fZE2vWO0JPrWupb1O8Se0NblFPF4wj+/G4wWBPHIK16VCzKpxqlue/4NUIJjX1N3i2A"
        "bpCiLM7IwjEnRsTUMULZwV+3BYsJJxNEciEiciJDjE/xlnh2b8B+dNLU3gMG1QJisnbYu6lxirOlopQ2ChILn50Awo5suyoHBNUH6e+28u3P54"
        "IeyTBZ67tgOu5GxhoeTioKitY694xiJk/3MHlXaSLTN775LShDqbHD8yrUo8cGwyB+XYK3dY4/TlERO/KM+TLIhg46wgSaNfTxw+/AXA86/0Cg"
        "DfDx25FUiiUOj3SQ4DEH5zmoQTIF8DDDevyDpO+eIS1BNB0oRhzWoyvZBJxSSmMA/UU6pVQ5Nz9wschitBQYI6KuWxcxiosOEoAOGz8jw7TDUf"
        "aQMCS1RtbQVF+iA/UWBqZJ4WrlWvQANSH9ykkQI3zKUKEy1GpiTyLkVIiNiiMF74WbZIhIcoXUhHXjHCpYOLvDpVghCfay/9rDpGGA8JS6WJDu"
        "OoUjyklh/6v+I9NgAAAAA="
    ),
    "arch6": (
        "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"
        "axSOicTAZL802UbaKXfE8c4AYA"
    ),
}
_CHARS = ' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~'
FONT_WIDTHS = {
    "young": dict(zip(_CHARS, [250, 373, 402, 760, 723, 883, 813, 214, 454, 454, 582, 600, 316, 511, 313, 500, 602, 397, 543, 529, 575, 537, 608, 572, 558, 608, 313, 316, 600, 600, 600, 540, 1042, 786, 719, 749, 790, 755, 694, 772, 898, 407, 525, 798, 699, 1036, 891, 822, 700, 822, 798, 723, 788, 808, 784, 1207, 853, 794, 745, 397, 500, 397, 600, 598, 600, 619, 609, 514, 619, 515, 402, 522, 681, 347, 303, 631, 347, 1036, 681, 574, 631, 625, 530, 542, 410, 659, 600, 932, 603, 578, 544, 456, 600, 456, 600])),
    "figtree5": dict(zip(_CHARS, [244, 302, 345, 629, 561, 793, 645, 212, 360, 360, 483, 626, 235, 414, 219, 401, 643, 416, 564, 547, 624, 576, 569, 542, 614, 569, 266, 271, 626, 626, 626, 506, 990, 687, 611, 722, 691, 591, 546, 756, 751, 276, 525, 625, 524, 849, 774, 779, 586, 782, 631, 612, 561, 706, 701, 967, 632, 616, 638, 329, 401, 329, 559, 437, 233, 516, 589, 542, 588, 548, 376, 591, 561, 240, 275, 500, 227, 857, 561, 580, 594, 581, 349, 466, 384, 561, 530, 798, 492, 540, 488, 388, 257, 388, 595])),
    "arch7": dict(zip(_CHARS, [196, 301, 456, 600, 556, 973, 764, 253, 364, 364, 407, 641, 307, 333, 307, 300, 595, 596, 596, 596, 597, 595, 596, 596, 596, 595, 335, 335, 641, 641, 641, 613, 1001, 724, 722, 733, 739, 683, 622, 802, 754, 301, 603, 725, 591, 872, 754, 793, 681, 793, 730, 679, 641, 748, 694, 964, 706, 699, 653, 350, 300, 350, 641, 518, 228, 580, 608, 573, 608, 584, 325, 607, 602, 267, 264, 570, 267, 891, 602, 613, 608, 608, 380, 556, 342, 601, 547, 798, 572, 547, 519, 393, 253, 393, 641])),
    "arch6": dict(zip(_CHARS, [200, 292, 444, 583, 541, 966, 729, 246, 357, 357, 407, 636, 300, 333, 300, 298, 575, 576, 576, 576, 577, 575, 576, 576, 576, 575, 336, 336, 636, 636, 636, 613, 998, 709, 706, 721, 728, 672, 609, 794, 732, 282, 585, 695, 570, 844, 732, 782, 670, 782, 717, 667, 619, 724, 671, 954, 686, 677, 634, 339, 298, 339, 636, 507, 209, 556, 592, 547, 592, 561, 307, 591, 584, 252, 250, 543, 252, 861, 584, 598, 592, 592, 362, 541, 314, 583, 529, 758, 546, 529, 509, 394, 245, 394, 636])),
}
FONT_CAP = {'young': 750, 'figtree5': 700, 'arch7': 686, 'arch6': 686}


if __name__ == "__main__":
    sys.exit(main())
