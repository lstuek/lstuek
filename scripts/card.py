#!/usr/bin/env python3
"""Draws the profile card: assets/card.svg (dark).

  python scripts/card.py                       data/*.json + the public contribution calendar (gh api)
  python scripts/card.py --offline DIR         fixture files in DIR only, no network, no gh

Python stdlib only. The SVG makes no external requests: icons are inlined as paths and the
fonts are base64 WOFF2 subsets (Basic Latin) with system-safe fallbacks. The font blobs, advance
widths and cap heights sit at the bottom of this file. They were cut from OFL-1.1 fonts
(fontsource files, subset with fontTools to U+0020-007E): Young Serif 400 for letters, Nunito
600/700 for every number, Figtree 500/700 for small text, DM Mono 400 for captions.
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

FILES = {"disp": "young", "num": "nunito7", "num6": "nunito6", "sans5": "figtree5", "sans7": "figtree7", "mono": "mono"}
DISP = "'Young Serif',Georgia,'Times New Roman',serif"
NUM = "Nunito,'Segoe UI',Arial,sans-serif"
SANS = "Figtree,'Segoe UI',Arial,sans-serif"
MONO = "'DM Mono',Consolas,'Courier New',monospace"
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


def panel_title(x, y, name, sub=""):
    out = [t(x, y, name, "title")]
    if sub:
        out.append(t(x + tw("disp", name, 13, 1.4) + 10, y, sub, "sub"))
    return "".join(out)


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
    out = [panel_title(PAD, y + 32, "STACK", f"{len(items)} tools")]
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
    out.append(panel_title(x0, y + 32, "CONTRIBUTIONS", f"{fmt_int(d['month_total'])} in the last 31 days"))
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
    out.append(t(x0, base + 22, f"{MONTHS[s.month - 1]} {s.day}", "cap"))
    out.append(t(x0 + aw, base + 22, "today", "cap", "end"))
    return "".join(out)


def p_totals(d, x, y, h, w):
    x0, out = x + PAD, []
    aw = w - 2 * PAD
    out.append(panel_title(x0, y + 32, "TOTALS", "all time"))
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
        out.append(f'<rect x="{x0}" y="{by}" width="{max(14, tw_ * frac):.1f}" height="14" rx="7" class="fill top"/>')
    out.append(t(x0 + aw, by + 12, f"{d['cur']}/{d['best']}", "nlab", "end"))
    return "".join(out)


def p_langs(d, x, y, h, w):
    x0, out = x + PAD, []
    aw = w - 2 * PAD
    out.append(panel_title(x0, y + 32, "LANGUAGES", "by bytes"))
    bx, bw = x0 + 108, aw - 108 - 52
    ry = y + 74
    for i, (name, pct) in enumerate(d["langs"]):
        out.append(t(x0, ry, clip_text("sans5", name, 13.5, 100), "row"))
        out.append(f'<rect x="{bx}" y="{ry - 11}" width="{bw}" height="12" rx="6" class="track"/>')
        out.append(f'<rect x="{bx}" y="{ry - 11}" width="{max(12, bw * pct / 100):.1f}" height="12" rx="6" class="{"fill top" if i == 0 else "fill"}"/>')
        out.append(t(x0 + aw, ry, f"{pct:.1f}%", "nlab", "end"))
        ry += 36
    return "".join(out)


def p_shipped(d, x, y, h, w):
    x0, out = x + PAD, []
    aw = w - 2 * PAD
    sites = d["shipped"][:7]
    big = str(len(d["shipped"]))
    out.append(panel_title(x0, y + 32, "SHIPPED", "live sites"))
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
    out = [panel_title(PAD, y + 32, "TOKEN SPEND", f"since {fmt_month(tk['since'])}")]
    full = fmt_int(total)
    size = min(96, fit("num", full, 96, 590, 0.5))
    out.append(t(PAD, y + 124, full, "bigtok", size=size))
    goal = next_round(total / 1e9)
    bx, bw, by = PAD, W - 2 * PAD - 92, y + 148
    out.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="20" rx="10" class="track"/>')
    out.append(f'<rect x="{bx}" y="{by}" width="{max(20, bw * total / (goal * 1e9)):.1f}" height="20" rx="10" class="fill top"/>')
    steps = min(goal, 20)
    for i in range(1, steps):
        out.append(f'<line x1="{bx + bw * i / steps:.1f}" y1="{by + 4}" x2="{bx + bw * i / steps:.1f}" y2="{by + 16}" class="tick"/>')
    out.append(t(W - PAD, by + 15, f"{total / 1e9:.1f}B/{goal}B", "nlab", "end"))
    return "".join(out)


# ---------------------------------------------------------------- page

def build(d):
    strip_h, head_h, contrib_h, lang_h, tok_h = 40, 172, 248, 276, 196
    y = 0
    body = []
    upd = datetime.datetime.fromisoformat(d["updated"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    body.append(t(PAD, 25, "github.com/lstuek", "cap2"))
    body.append(t(W - PAD, 25, f"profile card, updated {upd} utc", "cap2", "end"))
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
    fam = (("disp", "Young Serif", 400), ("num6", "Nunito", 600), ("num", "Nunito", 700),
           ("sans5", "Figtree", 500), ("sans7", "Figtree", 700), ("mono", "DM Mono", 400))
    faces = "".join(f"@font-face{{font-family:'{n}';font-weight:{w};src:url(data:font/woff2;base64,{FONT_B64[FILES[k]]}) format('woff2')}}"
                    for k, n, w in fam)
    return (faces +
            f".bg{{fill:{c['bg']}}}.frame{{fill:none;stroke:{c['line']};stroke-opacity:.3}}"
            f".rule{{stroke:{c['line']};stroke-opacity:.16;stroke-width:1}}.reg{{stroke:{c['line']};stroke-opacity:.45;stroke-width:1;fill:none}}"
            f".axis{{stroke:{c['line']};stroke-opacity:.4;stroke-width:1}}.hair{{stroke:{c['line']};stroke-opacity:.12}}"
            f".title{{font:400 13px {DISP};letter-spacing:1.4px;fill:{c['text']}}}.sub{{font:400 11.5px {MONO};fill:{c['muted']}}}"
            f".cap{{font:400 11.5px {MONO};fill:{c['muted']}}}.cap2{{font:400 11px {MONO};fill:{c['muted']}}}"
            f".name{{font:400 100px {DISP};letter-spacing:1px;fill:{c['text']}}}"
            f".num{{font:700 40px {NUM};fill:{c['text']}}}.num.hot{{fill:{c['cyan']}}}"
            f".bignum{{font:700 76px {NUM};fill:{c['cyan']}}}.bigtok{{font:700 96px {NUM};letter-spacing:.5px;fill:{c['text']}}}"
            f".nlab{{font:600 12.5px {NUM};fill:{c['text']}}}"
            f".lab{{font:500 12.5px {SANS};fill:{c['muted']}}}.row{{font:500 13.5px {SANS};fill:{c['text']}}}"
            f".site{{font:500 13px {SANS};fill:{c['text']}}}.kind{{font:500 12.5px {SANS};fill:{c['muted']}}}.sitedot{{fill:{c['cyan']}}}"
            f".peaklbl{{font:600 11.5px {NUM};fill:{c['text']}}}"
            f".pilltxt{{font:500 12.5px {SANS};fill:{c['light']}}}"
            f".pill{{fill:none;stroke:{c['light']};stroke-width:1.4}}"
            f".icon{{fill:{c['light']}}}.dot{{fill:{c['muted']};opacity:.7}}"
            f".bar{{fill:{c['bar']}}}.bar.hot{{fill:{c['cyan']}}}.bar.zero{{fill:{c['muted']};opacity:.5}}"
            f".track{{fill:{c['line']};fill-opacity:.1}}.fill{{fill:{c['bar']}}}.fill.top{{fill:{c['text']}}}"
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
        "dojX9YL3/s98TP0lUy+pcA"
    ),
    "figtree5": (
        "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"
        "IxchLeU/9aoRH8sf6XNwnnAA=="
    ),
    "figtree7": (
        "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"
    ),
    "nunito6": (
        "d09GMgABAAAAAB4AABAAAAAAQLwAAB2iAAOaHQAAAAAAAAAAAAAAAAAAAAAAAAAAGkIbn14cZAZgP1NUQVREAIEmEQgK1BjARQE2AiQDgwwLgU"
        "gABCAFgUIHIAwHGwk1sxFRT0XtXkQVJ7T4rw+4MQRqaL/hqE2IhBFa1aeFwboz/rZOv+5BfezlPUabEInNnxace89JiDv/fwwJESEhIq2BI2pH"
        "aOyTXKhoWtbsKtztSatw+pQyfIfIEzPhBsQMGSATYm5mQL+H57fZQ11YCL/4n6hhIBi0ZJhgACoWCnZsba3VZbh2fVG7XXgZzm1X5eK65PmP+9"
        "i59/9JLMAwsCaQfN043RbAhDKI4sTfYZuV7PoEuvtAAmvmJ0qSHj3Vx0vpF75VODUpgP/LOc9PKDmnS/yfMgyAsvRyzgntdn5CT2hgVRoBpuVv"
        "wvDP/9ym79y2DbUQ1zp4IoulYh7Sb1ipZELn/9b81+7s5jM5wBRIqA/KFISr2p2b2ezMwkt2P2yywQLl9f/AJ8gkhWzyCkTyVQFtikkJUZUtoa"
        "qsUZWyp0L2VLZC+r7275i2hiJPkcZ/15tlTdlWslOQQYJICCIiki3f+92ymlWhXbGTcSSIBxj77ZOMgQIsAjieWUKyQo7khFKEHqeGI3HwyiQJ"
        "i2CFnE8XjCILzDzSzVl3O0gSubObVwIEJ0PdrUBwG+xtBwLCwjSNHpG7LAGIIKfcg4VQ1svrS3qLLI7bfWEnUL7Eyp4V6cgE4zx+VnOrleTc9X"
        "ovfl4uj6BHTlNCqPZkTFZi2GnQH0A1SxDRXwX9oFDytX2FOCTFUgUphSyt6tEx8gK4lNF4T47vlnTSGYtiDSBeIcWmbrZSg+R6ICtqHoahko+k"
        "Xl0/6i9UqqULevg6KkfV+45HZn+jhIeKRMo4VhTSTNLfketpGahShfnRmEbsGYmm0kcZzXOeVKCxlnzmZFwqITs2t6sS3l+vV6kwHP2CncKYEO"
        "GlpKp4GRPe2E9fWJYy8JtX7uBOY0pk0hD4tb6BxTNoC5AMGjBn5nPWlUvFZvVTtFgTkFblJHX1Jf4f8ACahKNzAvYQQFUgLwOIjq3uljOJuVrv"
        "9W3VPza+qyjsIJul/HHenaJTnItIQmkF0YPWrdQgjnqjV7ANGSElXqmfajh27E6OPFZKOpXS96TBh5wx4VNOYZUWnGxGoxn8nVnZpQG2An/rA9"
        "aiOHwyZ+lSP1OF2PqCcLDq2CRVoxW9vzZTQblDKHeEvdJjJAjhHdmQ0MehjT2HAujAbbrCue++UxZeIsmUXSKIGB9SEmdFQ+AkO8M4hyHkAX1r"
        "8DoPEE1RwZ1bM8QzqEwHvO/kURGZFmXl617A+hZuxKCfRAQ8zeHCYSmZ1gOMBbUA8gU78JlHf0DiK+YDqz5ar9kisbz1ePhD6DaUqXbUF9WBul"
        "CjA2ZrBBbF6EFxLZK9DZOZCEDHyFqJ7NAtf8cCPpwFnS4QdsczSaP/3TcGOsrOVz8SpEk0f22VRfFNXt2gRSMgoDksfxTBGQjiBnAI3EHxvhRB"
        "Bc0SjrT72h8lVTc0Eb4Sc92NjR2IsEZsAUdjapNr0Xwzs0wLlY3H8tJU+8K7aSOVQhl9+1JM8bnz2C0FEQf6jKTMVoTQZTAiZ/lK3WhrOPY5oh"
        "5B5+/CxYS5dd4Orkae6e0wHMN/RTdJJDpU7GaxCM2Rq2//Xk/QM0pAghSqtkkHF4nab2eLzaYM6v9jQQLLEOxGdO3yQIZXw56I0EfWdM1En5zg"
        "iYHoUoJWqODICEZHIYon1X3Z0/Dp1cZGgsRMxr5OKTgNAcxqj5pOTdEwKQJBE2808ABf90BROsOfbhBwd4qVgI2fRfsTTcyiQQcjF6fuRzn+ZI"
        "0YVm3ZIIVxrH4U/4WwCDAkBfSDdCjlH5W8zwad92ejWqLZq1V/wXaunL+F47QvAJbpOqStmzApsxclAYB63gv0nsDbezjz89S0npTZf+Ze/i5H"
        "6F9vgPuNkYFZRkGyKw7QyXPke/KDRiYJGQurfAU8ikTImGOAU0pyFi4KOQroUO3MSpSyITFzR5eZhyJJLcFE8ibwUI7A9uSSNGKNiTaJLlGcKc"
        "s546JkNgF6EokZkOXbvwLOFli8DiAIdsWoQCvRaUX82yMklgywIwXZNA6wQ+QEYBbDSVZFssovlnA8o7rKjosAYQbciZ7mvD5LrCFEFAWzqqFw"
        "fWrOMtHIrLQQ5folfFm0GrpwgFpE93j4ZbZbwhWvRaAZaUzHZD3RWRF11/zF39rtVUMQCCS+xB/DF5U27QEVY0zdMPqjj4lA+/DCiQhL3SKsii"
        "olotQSuC8zHvB8oWwfM/xxPsP/BeEWwbOAa+3yy4uBQLJNEiM3sv/OAszrgVX3oJsLy+vdXzT2kgD8RQYjodKJOpttFAC347vwmJFjnggQOloV"
        "fgHURny6YY+aSbkaK62dRTAvk4ZZQNCqWQQ59CygaxJ9kAHbAKcAtwAPHEpkK1PDz6uAm0s5qzwWOWzsKgVUcPIpkqtYtXy1PEoVqkJis6gC8B"
        "0A/gDAT6D8Aeo/AFgGWAegh9tJOfYCTP0Dc3312u8y6x+GziJPgbxFLjnWJUCGB9CSR7IU8ditK2MpLTpaSI3lMWRcMk0AC7kQGY5OgMiJ0Vk0"
        "DiFMYbJVHLJwx1OwWCgmC8hxaNwKulpAlHMsYsnSBITofDtZ6XHkOK7IwHlqsnvqCmm5JNcVSprEa4WkBql3RVaodDKM3l5KC5aE+kMF8qLy/n"
        "6aVqmFrvdBZrlyzmY5V2Ju4BftCULi+cautHgB3CKTD0hDVqd4T7hRrrcJuzg7GpK18v8XPVALd2LA3VVHHGUAuDt5k8v+aeNdiXcaOCulLpyp"
        "fcTApX/Qw6Iymxs6jxdHx1OeUFhMjD+Axv8XlWK07Pln6oGEun1iy46Q4egxdCQ+UMMk39eO4RWKILIKR1QeUEhFUpUzu3QlZdPNlDKIUJGb3X"
        "NGyP51dfd/mOMCdeifaVFTyI6k2ymlbK3adlG7AC7RtkPGCxqJuFruXKSHxjbYEbgG7JdNwjEAiNvEr15+uF1gkhIaau7mnI+E1eHeKwmAnwXd"
        "BUCLViR2bJ+3Pu/Omdy/gvAeLVygrHGdrKZYWs2eI167ygBcrN+YkIPL59WH/6kTfXKeKKlWeJH+zDDFbJMqkjCjwGcmONvwL/wAGx0D3pS528"
        "eztw42dN003XnG09n1fkqq725M14ZEoAQFVnmsKIJs3/C5twYiqSkcpWG8xtFyYtoknAIjzzyT2YnFOZHhTFh+Sb5oD5KCkK0a5tN0J37X2av2"
        "kyKCwKVPNuZ6EO/1GtNtd4P+M8T3A/1xDFjTHB5gTI6sP9iVRSDVeFsCp2OlSOgl3klWiL+NgWIYfOnonZ/ceOxzakpiepRWLtDlmBxJBZTAyc"
        "DGCWhMnJ9/y87FcnVE/5YfID43Np1HVWvLyqw4Wp9NiLrzY1lXrn7zRjQSWajbZYMJOQhQcn5MTlCwIltBcZL9tlY+Fg7/7bDJKHyxYZhSysQL"
        "3PXuINqs99F69NBZZ4gfXNbfr1Bk7F8GOvKFbYtkt8JRLMzimEk2clAxD9M2l7ygJ7n88atjoNxhGti8QlNpW2uMZz8gttUr+QPkn6XMTMGh7b"
        "eSIMcTLMImLvAcwXioAz8gU4A1xHnfSHvV1TuG/Mans/yFo0Mvf/dUsRhK9d7Rg99T7eBOtDET1ZYcYSiwY1zdmywqsYprAOJmIIZPx7jRBkI2"
        "Lk1yFcKt2DQpXkIngkEYev0igXgjmKkyEMnxFmYraZxYMfiuIzW5NgW3HQX6DgRjUspWIAeiQpBsdhsSgE4p8ombIAkqqfwIwcQkQq8pm1gxcs"
        "kPdHF+TyE+BSplZP5mNPppex5jZMmw1aZwXcK6LdWw12zRvfNo3F6DpH50YzBAlS6pTDXtCKIUjavCuUyyFQcPz0Z3BiLYq4+B49z+vhSu68l9"
        "zDcAGVmrHca33xS9YF9Txa3IzM8puvM/ToQ6fajHOVPbx1bEeqgE1UuSGlm3yKO6MEM2Nib050tZ4uiKeAv0MGcxOOfrlw1sTB1BvUF3yGwe7q"
        "qLHGfpjiaEm1jzslPkvG67nB437Jk88czAuovLXgxfWF+hMWCtjCTkImFY551cDaM8dcN6Eg0GInDVuEQtU5yPUvdaXsTSohIjJidWCpibLfSA"
        "SxJ4yXaLmhG7WuSDkrdIV6vdOxhHhr9uRPkZsTAKbbEgAlgMrrJrb0huLkWUrfeV8zavrkuLm4ZIK0GYMTEWkg0WEyrSshh/DqGUHfVzATWKzp"
        "u5f9xXQoaatKnMvd7CTtILltDvpz3rJ+OWwfUQJ3sA2OtvIo4/bTFDaLhUVj4myB2gGoKqYRcuL+45e6+4EyHOm5flPtTTTS3IxuyTKt1gFjle"
        "4SgXME2t1EkIrOTW92RV3Y1OdEePVx0XOWPHRJN1r/a547g3lkSi2we80Nb4VEZ/5evvQ0P01Xqz3pIiBkH5v6yqY/RE36k3d0NoiOxFxVSMUd"
        "5T/+CUwTas89ehPW2Ax6/rOLp0GWyCNWJJw782I14Unu+ZfOrlkbOUvcCpvVvswhnxUvURschqQg/eFjnA+8cRvUhe+DeOOSJ21kp5QtaB2l3L"
        "Dj6ydyfrah894Bt1JySvhhTcuIrqtrymufbowXkYL8Y1rrwdu/VV9RNPiP0kA2OVyMU3/FsOMnaTGKtsLXpMZHWfstKWWW1Gm4Xat/PkQw/2eN"
        "CadlHMc/sxqvLtPXTh7GnUu2f/qTOSh/qm+iolYqoY5Avp0neTq/d9CUNf7jP3d9jgQbA9e+3T35z/0Da9rzeuZG94Y7BhXxhsKb7BKKweu++z"
        "60XKQo0p128iJ2RHF5dnV60Kdb7pfi7XqdHpnOrc5zwPurLVWVnwKroeBNtp2ef3nOgoThv1Va2VeLStnDUxl1uknzOWu2nivAaDYsDnUww2GP"
        "LEHjyLPitp3nZ/fQdP5aObvXz94QvejJGK0rH00infVksN12zm1FnHhkeGt9IGtqElCOpFzR+LMHs7tw0T3TOj3rVLULBJ9NcZZacPRAizIagd"
        "k3/ORUIIGka4y1XgED1HfJ7pzpL00dKq9ZIiXQ/75/eHmlec/KvZi8sLmo2KQd/Yms2r03yUddb7G5AQDNcil1Av+i/0ysLxHgSMibhAhOnnCe"
        "I8PWJrxLXkID1MHCI23bitccjR4emHABSdA0hCMuXzX6jsBv0AQczQb+hSSwoznqdP1tNnZp4KSoQ05buLVJrD+L0hA8o1UuB+DFn3vzEzgkEc"
        "AhvzTxIBwc+NSon1o+gABkZE20xrw/djaPvOJfc4Ufd2VqHYIN5Ga6LRhmhR2N2La1kUimHN/Uv4EuwOhkU7gDcRW1BI/OwhNhH3Cg2fVjJrwF"
        "DbswdYtFjvdoIRQrtLPSfai9NGvVVDkrzwLr9nGkaP+aoDc8octUb5kG9Dz/Zmiwyp9b2TjgRU0a8RP3Sv6qxvqIK7r39FHCJaLuXmWSxm+KGX"
        "ewkMLx/Q2776ZtrcfE+TWMjNqDn/bqqyD3JLnUkVaM7I3U5PObvKe2wHqEtjJ040zjrKxV2/EYeIgQt5+UajId+YdwHoSPfH5zO/+vpCDrz77z"
        "fq6FqvRydJOWqNb0ar4IpAQUZSvj0ryNIYWjnHX9mSTX0wpsmDSSQuVjgxtfDbJrQOCfqzMxJz7IpaJpCYEqCbR/tRtA9NwEi2N43N64itoB1n"
        "i8CVndjmGkxqQH9DVThQURlu6Hf/5nHiAH2wxjS8zgwqhb0wGlfTu2Y9ROvp+ceZ+JdreASDaipHY2tGHwYGYafHb4U2D7OwkfBz+sSXtWN9CB"
        "Ief17De0EfGkXpwwduh8f2YLQ9/deZ2NOsvjHgF7I789lvdKmfiGZ5u2HKxOxsNPeZ6NkJKrKbO/eJKPVr3bPc3WjCsXfeJJLeIJ69AtJFXKDr"
        "MfPvvsuUcZRy5eqLEP4iNLsWQkNg9s8Qs14JqlOT24bnJoUrhmgOr0GbQY5tHZmbQnsTzfb3KQ18gcyTnGYVKdvX0lszDOmu4nguK8mQntgdm9"
        "yj/knFtSVYlvXNL3/5tzteapLVJxR6bSR8JQ07iJuje0/9A/IwVZp+my7BD9Lwg3gTcQDHZwg87td1BqOlWi/vcOfLu2t0Zfmpt3n5al+O3yi8"
        "076FvLllgEVuq0HbXaDhVfxQzs9akYcse7neCbq/nWyaoL48Q1iUV+GksTpv93zmGHj590UwAJhqdIrufLeio0ZvMlUYfo3F5eab8IP4010pPf"
        "1bhSkpX3ibn6/25foNqbf4Cv+XifB06wydBXn6rhajXebmTjDLsqiZiMcgj5cy7aOpGSYRL1++tLSo1M22JMxFTyeoHr+PlWFgr/DzeHsWXALB"
        "xbD3NUFdMFS5/HOS3uv46Sr3VKkm+dMO1ApDNjTYLgMrXsoQuunuXudP4ZceK6DwHXaHvT76TrXRaAnqFK3ZKrZ/0sOXmKqMt6aKiRkafoDY1d"
        "3XM0gT3+ZlS3Nz/GbRbb5LmpfrB4PyanuU7K/M0mvyUhN9FtKmRnDAP8Zoud6Va7oni8/t44fp4/RD9ELzNB7Gy9nxDGYcmx3HZMSDpU9R2saS"
        "wDuJH+QvEzM4sZl4xpDicSdH9SR8C//6/1P5lAxHXHticUca9XJ+ePH5jNu3FqsjiDZNfXk24iEZ+JKCgnLfd/fAu9L1ydHv1Fw9SkOxTjITrI"
        "QSpu4oDd9MFJ2WF2u1+lz1h+SkgEGf5UxdYQM7H611/zXMSFTGXOtC6uj5rnAAGY4vA4MwR7tg2vXudHKa9dqufC0vYLCU8lXZ3tydBRpepcHc"
        "SpEJJYMP/ABh+4DSbOQ/9VulyWSuQeknU62zGCuNv8b9asycWMxXNs/fz6+xv641mlAYZq4w/XbKD+AnMfPuouLskAirPgDZMf8wvSWKYo1CSo"
        "M80xKrXf8lvgX8hLgCbnhlT9JndS+FnZQVCi+XrlNVQR8ZzbJ0ibVMoBXno0te6rf/WHtr7gpL4eARi1oLMsVZ9Ap7mxtg6AqFyYXab3VIpu6H"
        "6BqIGbP+mzT0IcUwVIL0faV4UQadWR/7CZowc+OhcfAr2gJRks8C6CscP0cnaf+Qqx15xnv0/QS+nz4lk9AO4t4XVX4tiFyKLuw9M9Jl3InBhW"
        "N7e5gHesaCKGQp6Do3Ov4b+FPoV+M7R3uqNiBQzcBwJ76xt7YLhjcUjfZio939kxTEmh7cOTq2gKALY1tXSres7FsAfh8KJcydm5MeeeGnwh4q"
        "vO3y6DnB2LnL2yAoBD7fz6ade/tz0JuAtj818RB/+0MXJ8ATD6g2PWjdL7r2YNCcLfUy9/eOd/4m/2XYOwnKQ0Nj6/WEGuJ/WA7BMjgd7mgIXI"
        "dDjNiUJMgGV3LHYHW4Yvm71Ip+/2fHp3uEWfCWh4jDxAb6Njp+mN401y5bEmD9x2D+y2J/y2R8B0SsWn/tyoD6WEdh0ep1jz7Qp57uKC705rvG"
        "JyZdw/l52cOTE9nj4FB6AEH70JWIfEfFnyd5TRfubfZFf0um1mKuzo3maQcjxUGM/P6b819GpvrEWVa1JSWblnN/B69s1f2JFl5Wdkgs8xpS6W"
        "5l0VOv3mAZeP/puGT1sC//dbGU92D0TCEmzjQzliSpc7KcNlo/ivTTNKLrUUkyi9IkdKEt909wmw7dP9rEzXKERPJCtYhjP34g1hXrrnIaNOVt"
        "GeCY8Gt4XRxxkxb/5jL+meNXIfQc/YoRD6NYGDfW4edzvw0yolYzgRJVB/ude4fKeQ/+1VhEpKWbeWKhMdttSTLTP2loJaNeuBgbwNymfnjx/5"
        "mnS4VKa1ClCFlt2vo2NbDh7S80HGwLJG/NrW6V2NMq2e2vNJdST9zHLQjP4NWKBsq8sWF5QbFQZqhSK0Jmq7qpXuMqFt7gmUQizrxQ+EKGSMQ3"
        "PQ9mBK0vGM4qSS7F+hG0H9uMnUGhzetS9BueWeFva5qu1CBNznNmLECm+Lwqi1ZT0iJyZVeyCdaK+a4fz1Id0b6aHMN0p640T6HbrdPr3Vp3gU"
        "eLd9qjy7elfYsIlDl6qzVbr1RlG8AfiKsMFqFB6JiQ3D1YXz01bLKpG1ex+vo8hkNuduBXp9zgm1NFfNONFOHzdUyU6gU+DwZclozJlLJYEH59"
        "YDA8uDTCwp9G34LUbAuLCbHYKUnYZCFtjNnZG8pgHT0Wg/EInMeXBgy8KZFU2jTrBudJSzNnIEXGz0p/ym99EhAq72/tuytnHkWTAhKRE8dEs9"
        "ycN2JXN3FkurJkiVPCoTXyvi8iC+M4Cc8BDGZH3OdIsHZ4L/+4peHL1VGZXVRqV+bqJTcsjdN5d99/a4OsPo6Lht+8f088PTf5+VVLTEVQp2lV"
        "1PPeY3VcfO/PL12yhjh5w4brYKXguzLGrmR3fPJkLNWEVPjTv59pjcePyk174KE/WbulHip0R06MTDG2PoPp2845ybSJWIoF8d5fEc4iWrgZGf"
        "qDc4gf+12+d6eYu+i5svw7mfrRJLBX3ZX0vI2mr2+7q9bnjWeCL6pfv2faq5uqcn99O3NjHj0fNP6gASrUD31E7YeoEgS+D3jx8fyEfWT+/vnl"
        "kcH8XR1SvNeRQ9uRuT3JMnnnwpv9hIm7jrLWaqGs46+lmfvfvHAXrLxP3H3yqX66mbOWss5ipa7lrsXH+zx5a1Jd947nrTMH35mxHfxn+PgGwb"
        "xwYX1CMoWa+Nn6hZR55Sa5E+6jUhwUMWLH5tnDR+hR9MMbOPOYHRGP1qP2wUBsoDG6wahiu5wNl4go4uIwe5gC/X0YgxyC5RsE8ym/1QAsSqBR"
        "a34TzisHlWCvgTZBHHgjtA3yUik+qOj9IshHoXohIDTjCiY2wpxMJ9BzIJdQE15K+YmgHH2N0v7bItnAV9fqI7rObt3RUJ3hRF/fCUNt35WKmt"
        "Od/oy1XrtGZ7TGrp8ImOVuX9CXreoOmg0Km2KafLEkCU6UC+bSU2K5bzMFPladpcq9aSq7rv1URWCmu8d3+qi/xdG1YvqbUwuab26Oi1bzhCap"
        "oFSt+CpTaM4QFCnVTCDA1ZimKlTxCUt7YtTNd5LyhZliV1GyKjdQYBcwzWb9+uUPvYC9lE22CgQlCOpPykR9nBx3TLD+e3IdArW+ac/Fp/pVBo"
        "+yMDVa9M4nw3Ol35jYMoemXJUSn4w8GPM08aF6CE98BWx+EgcI9q73grBlQDGHGqjVUjvoaJS+92QuvCv6ywqOVWljJHDpYc25erQcLg3karMC"
        "9Qpb5HcBagOCnpdA/DsNfPcTTQ2cB/7+LY9QOArNihTKxUa0Ggn4s9VqX0hqXhJRQ20AohosgB68Akmhp6lXLkErkJuELl2B+RDEh688CAmAr7"
        "nEOD9jz7w0iCQxHsTBMKiKb4bnsIdfvPaMFG7riw/T3q2/eeTRjkRYmwz+io880pEMq5MvxTfr36WF8dTCE0GZ7vvCKWwuDA79EsPh0OUEJOPu"
        "xK6CoQnb/DLRGeLfoCKZNHpnZVOHmwRfiP/G7h/vWgut+KxZc+w7OpnZde2ilF6Arjhw3rWffT8J1w5NrdscJqkn5oaKAt1hm7A6X6osrOgKW1"
        "Nq8mVKB3OdW5Kd7kztrZmT7oCaCwNd9QFUraSmhGwpNZr9kkdMEtd0Z8akOzMnwwkSt+p2b1dL9h5YviOHK/oCdQCs4gLkVhMwJnm9z6719vzq"
        "N38KDvRYuuDnj27tK7Q5ljC9/LVlk+Iio4AB/735/hvf7atO0P22PDLyHgB/aadvAgD/ftx2c/FOmjUzUgsAGQfA8JsMuhcR7sMX9+f2fM+vHP"
        "Yz7J5X1FM0/cHQ/Aql0g9dYTGeONxu0fzSEUVNKVkqlfQu02Uhc/gqnH6c2y6zdfNfP5bf6+LXYondLalVKC2RUgJI6ubMDal1s0CUJCCyRU57"
        "E6dfXPp9q1HBcilwLrWyZ50quMY466Z9gTv6FVHa5p+qga3LwdhSgFcMpI+0yby0OkR2ohpTKhO1Iz3KQEKUjTRIicS7NiPLAfwHqrXynMi8gM"
        "MFQYSLv1zbXWLMr5TxCMM0UbolT4tIvta5IzJN627X5WGavkAXGPhbSgQDJCgVKZDu56BeZkgBtVm7WiTwXbklnkQkjIyunXkjkq3RJX0MPGc6"
        "0fHWSIDCIyINeDNrKaiV314eiPFDgT7tmvTqwGU3WG5ft6A8TRo06sVVLKyNt2/RoVVIUaJBH9FgYpJfODxbr6DWVnW8tIOzQe2/7Turq5j+lP"
        "/O4thP1HYA"
    ),
    "nunito7": (
        "d09GMgABAAAAAB2UABAAAAAAQHAAAB00AAOaHQAAAAAAAAAAAAAAAAAAAAAAAAAAGkIbn1gcZAZgP1NUQVREAIEmEQgK03zAKAE2AiQDgwwLgU"
        "gABCAFgRoHIAwHG740IwPBxgGAIP06IPvrA9uY1nifgyd+udcyTzMaxWJfUQTVkm/vvy2/pnyU0N2kDa31qwGnXto4KaKcGSHJLDyPa+VLZrKQ"
        "hezNZWFuGY/mCkjywPi6ClOnKlSNqa8GVP1DNGcNXg48yW52N8nGCBZCAkQMYkQgJEQQC0G1UPtClQpXE6xCReRrDtyVqp4Z9W/v7iH++/uy73"
        "2/ZmgAU57ygKUCvm8efRzACE3KYxaMbnb+d01r5JSZtDVyjiWQ0EzZFRByQG32/rL3lx4F4t8b3g5k+hdQ0vM4TSyKMwz0YwsCiyDwhuYWnZQ/"
        "p49h5o4e21BeNtPtaaZCcOeou6Wex3+wqPk+Zb/ZbxG0DgrgAOS/AMD/P1evfS/Z+cCzW5IfWagCqerKGpncvMzbl5cMLyVLPEuZmS0snDNvYp"
        "ISkPqtyhaBLJCtAxSmzleoGsuqwqsuU9XCewgPsQTmOJO0137pD4m1x2VPk0mYxCBFghtcYV0pdd7X9feeZhTIgx7QAkqfMnRAOZTQMrSSGkUf"
        "jFZCqhJqnO2GiiILqPMonm9bGwFHsH9gdgL29dTWesB+KWlrBGw7uYYLMBgKAYkns7kv5+xmaJN6kQtSLUWXn9shCv/FfdaGqsMTXPth52vX3c"
        "IMmlcRYRrYI402HHi0brv4GmCnLYB4OI7bH78JwquCMbhcGCJL6rFLyBet3Fc5FrthMHImIJPVNmld0aolxOhCopDVNcILI5k5WBYK9n3gxEUj"
        "kPX6GXCXSCoftBDwYZ4lz+2Sr4V42XIPEp84P1qEG+9OFocVEwGRNOUJVTHpwnJU4jWNSEYwNT1SSWbhAYfQcDtRJgmwA4eHQR8EBzf5xwmYUD"
        "iX+ox4cCR3eYQ8x87kJkWDotww+YC9YRpBuDm6HyASTnSmd2BvmIKhb54lhWjhNuBoAfUYC8UM0NkAqmjaiKaM4d4mBMAHkgfRZMF9TzyCumOG"
        "2KOwtUcJHhdNE9hLaIzaAORMASCwjge0yEimdO7MJZNbopxj0cwFAdRAlxVeoJWHI/phVgMrlMQaYWvM7ipYgN3sek3BAGQOu3gXE7EyW0LlzI"
        "ZIiy1rJXL0A3zFI57bcqPGyAWML8PjSYEGURqogmcRHYXqqpqxx+KxZaO9kIeYatmPpmyk1JLbpBC3E1kMDOX+hfaiIL/JNVUTG15sp4HEd/Xt"
        "jgqdKfiRFW67ZlyP4kISrqKTZBKUQmMdMHwqFspDkjPQFNHcAsH6wFhingxZLpV5pClvHa6w6OHsJSWjEkLxTBQVkEs+3liKXwAtEh4oVUS2AM"
        "tl0WTBWwQ5pSpDxmZk6NJZAeXp43kmQsljY8zQIIun4i2oZfMhSBNFwKiaFfo0vW/ZZsgJJ+66kKyzVNDAkaOQnqxgdc77LKqoEHknwrcmHPR7"
        "2eIwYpkh+ztBTkwFcR0A6kLUoIiIBkqXLU6d6hylbOCcwRKGWjQ5geXjprX8wCwXs/rh8qqy0tfICn0uJXXcP4rZEh8RbTdvkjxEkpQcBPzJz2"
        "RcOpRYZHXYFL0n1m0bU6Kp3HpGg5tE2G/TcjkmGeUmFuwAk2gCTJLaXGSZZG6Sb20tLwiFYOmkomEawmKlLsu2bSxPIfEoEXBTKstVwEVymio4"
        "5n6gZcFzwdlFnOcV9oU+PiK25dhUfGmKweQAWgFO/o6zr6ACF+LzoYHKoo5O1LhdeSoAdyKRwGoIBA7x+twRURdU7YG9yHrnCO/1PPmfL+c7yF"
        "JgVsEHniJbTuZbareIBn1GODYp+ic54RpTkCZ6Xky3F3YvTRWMTLM+c4ED7y9kqgZlhTllwJf42ZNrbdnYte8GrQwWmew8pSgHIJE4cIOR0AOG"
        "K66fHjWnXDoelHf8dJQpRl9FIBDrKm3BxdOrbMmpytqxYyivLkOrCaXMQEYo1BTJNH4HaHPbCjywrBXLgUjFGjnu3ZmphTFYmihqaKPExQZowa"
        "rKSEBtfsyHFtB6fewaLcMaHDZkbHXjm3K2eaEhV74CXF7/4CmsyIM7rygtW6w6kFVS3mlwhHfubldPG/R1FERiVQXVmlfQPN4W7W3ZX+nXeXms"
        "KgFsmSkzo0xhkxKVOB9VSr7KL/aaOdfAH9khrS+hjYSN9GkG+q1zAR7Wl0udoRRzvQMF//vBrYKNOt6Pd/8phHvFVU9GfbUCOkGAUDvgP9Bg3O"
        "t9dZsHgH+JYXiomkIlk9za8zTKY+tiuMOaB+bQzAlQ7iMo0e/ZhrXzrsnnNk1nJOjYuOC6AiX+EwnSkO+QN2Q+yrAACbgCrtNzMsnjliOLhZVR"
        "Pi0zjTQ6qYoUKGSQzS6dQ7EMpTLlsnHxoCI5AGcA8Bn4gMIWpU8AAzABCO3h9DXlhSi8S65FyTao9b3LWZGiIQ78GCDt/YAUCBJAUY3MA4lcQi"
        "DMF/b3jw4LYGCJ9GCYTYimhwcT/EO2G4jwl8A4Eh1FoYnx4OginBvNDWYHB5ICWaiULRjejKAmxrGRWLaeygs0htJjk3EfYWQomR4YtNcHQoGV"
        "anFFB4oyvYOnG0IQkYhMDjEHS4JDgtLoQz8EMaFg8XIGZfkF+ZYG+QVmde9aj9X1nwr4+iRS0zuw46vuXWh2RqDV2bOjLjcmKCo/oPush8+scw"
        "EBX0vT7y+Y4C78TCKZjvzC6AchKNGFzu2atfNf9ZWqQTdU5RATCzvc0ok08AdMf9WjtcYLFi3HYg6ANSj4HzvZ63cHseYFiTHldGWUADYHTjoZ"
        "UM9e+chBIkdQ1FcUwsdCFUY1nFJAeDOzAywVxQogEW7aFjVHpmGYAFRdBcLWy+yvFvH8fgd9D+dpFfwRO9gOd45LY5QJoe1O+yKBZKu/A8W98+"
        "NOqBdYZVpgPxlCEWtjg0Vt74I+HNR5aM0K4ziNtJKsPbcjXzRNdagEnwma1XIBhe53UMI6iVBaq0dGzOgfos+6PUo2U6TEjjy5GyVPZeMXXIoZ"
        "lNatrR1TMoz3u+T0ssce/o4c+3FfjpDmUUQPDzppKu5J7oxmB3qYzOSBakfxqt5V+z/oi9I0AzqcJRIY5FKqx6QGs6oeNfZPEl16fPTYDaZV0E"
        "2HQdTpg1gfxkHQeNAUAeEOtpKQ0ikEYWhacL8OQMv6pLvtJSOIoBKn3ouiqelAL0joO0ocnpwQumC44dKrv9kIDJAGFtSVChzbtouVzwmVtmhG"
        "Lf544Oupun6NJoR4ov7QrJ236RuIF83bGjQ/QlBUPKUdhkgc3u1szg2d+WTLgd6I94RFS2fGAZBaQWHeohROiMMjQc5YhCLz8+9kK4CJGVH32y"
        "mt04oLM4BNjGesNqJBqfCskxcyMt68gKz7eBpxbC2udlFr2cukxgDEMwCdhf/uU5qAoZWUYLgvAQkF/zZayRICagEOqJnvkwGOKmbcQJ6uaeaS"
        "rZrWcvZ+RR1Z8T8+KXRtY2V5XaAKIpQWSW77ZWQZn+Q0jGE7lD2OzCjZEd4l6DsABct3q38on25695Z+yfuCvCZ6uUHBqm5O4wMQvczbGKhxpC"
        "VqFvDWi1hy2d9YJEpgV4XmL8VTSENmmPGEWbLlrB4LoruCUZWT3xUiAdE4kIOpsBzXvKDzsT7KcZGhTQsu4Ylg5ENLMtQOtYmU2MCTaOUbkx+F"
        "aTIlAgX3TzrqoZQQwxKm/+KAAuQlWZAkOvJFIiVjcWSekBWxI0glCCumnuxOgKZ/rzGR0QZdcOfBi0reE6LMm1rxNIxI5UhDkf5/OtY2a1gSvp"
        "MCCgt3dXU+LNrhkjnNK95ARhaiaggo5/7mZ5YBDSKgo9pacXbS2IjIWftselu3rwMl+/xhusPQ/lIKazJrI4jSTivQaSXlktEsymUfDkLr06al"
        "7XZtFkZyHVCrJKvXofXeeaWzzNGYjyAOS2ZBsEVmpNyG6XwMUGka7kzAxLMB6aquAtBT8EEcWDOCANnTYxy+zfBAkpV+VTodURggoE/SjL6Wzi"
        "tbGuFdk17m4LUjh6E3lActrCkIQ8lcxtTe+VwN6rLYqDRF3OvAsjX97VIuZFdov6hcyFeIkS8URlySVnLERU4bKwlyaMYLODA2Yh2CEP2KNzZj"
        "OTkgGThjh1Nhpu4rWa4MaaJJkmOXKuxOY4USFcebaq7KCAYdghU79V8YumBIJiO4QFKv5pp0Y0S1475VQmowMc9bJOsN2NaWlHjUMyqRIolkJI"
        "oVK9qdJDZ+eo6UDHxnT9JXZ4r+v5Rp/SebFBcniVW/blXumOXu0i61bz3i346/GqTJgGofIBhLNgFVcagSpvnmeccYaKkFn8oVY9G1jTJn3cDs"
        "6A/+MvBd6vfhoXhL/gvLU7RKo8hSPGNWaQWJQFrtSkzqnP+keTxzZxrj9AgMlMcW1eKPcJhtapiTbFrRmg0fLst7/b2mRjhLMhMe0hKyvPkbgV"
        "t5AvwRKGkRFkK2jE94sp8CQr4nHOQrpdGY3K+GWM3hjp/rFS09JSk6s1IzTTbn39Sv9FgHrXeZR+XyeFlM3mnGBQtDaam0cIkBMOXWrDRr7Jh2"
        "WDkSDcEmKUyxRdO0sltBy9hxlZbHNh/eps60thyNe0irJxiGzjTBZgzXdbtVW6uPQqTxxN27ZNLrT9G6VB0mezKio8YvGsTKrmgmPe+3/YUM/Z"
        "8BMogaY+jJNUn3ejAn37+2WTuTbSM+M944sMPN6QY5yTxAh5RGYdvtdBQcbl/WXiTghnGBw498xbnGzzhiJMPbg59g3JZ1BKb8ekq1xr7NnrJm"
        "5KS38mvzBsvSRWawfGAypNkTMpZWFSuySVWmnP+HmL6y5RldnZUtl9xHdO+Fone6IyWbNaqESYHXUbMZrLJxINexqckRPzfPNTvBLq7Bpprvts"
        "7XFH1nCIswlEgFDZlWQVOJ1MAxhXsVMtubD1GmN9LO87guHjx/dFcWf7YrbwEvr6umMzmfNkItTJ4+deq0zhZ3pALZSUZ2IbyLZLQXQXpR8jc8"
        "jSFLK1gC7mJq94IitHegD2VcC9R7EQPf6sAG2zfmOAabnPyuQldXQpakGcW/2t+c4yPLyiDw0ypkCU22/7TPaIuyhTQsuNeI7ITg7cjWl/f0HR"
        "TEOddCBIvAPfEMugeOe9B/r/t9wzJ0tT7vx7qP+Fsly6CP4P6B8ZhQn3nr0HneRTrAA9CfFG5ODl/l1c60HHkmfk8aPj7uqYsNgNX8+UItNkIh"
        "X2JyOJ6B+FuwJMJx9cMdrkxsGEVHMLAAygtKHvX/FOTisY/X6csUxw4hlOfUPMpNqvEGbkK3OpcVEwjNS+/MII8+Vd8boP5Fc+AvEdj9rnMMfU"
        "SeLCr1BTWXco4MD77rGEMe0V6ABVb25Dk2NTri5+a6pidkVK3NdQwmC7pyi++ZuUGdL+e3WKfUzilVFcj4zZmT67rg/wqnp4fib9o6JlZXd7S1"
        "HfoWf4u3rdelKuTyVLluPViz33P0ZLsu6xrv/8gs5cQ397xmuvgIN5arJUV1gowljOhrtWndR+ATGAZdKz8Z5sspfom/xWcOpOolUolekjoAUu"
        "TmBGag32G3VMYPsSdLYJHVkBTDinzaALkIhS6LINJqlJbTlIo66p4v+11ZXum69DAuT43w6Owv/fVQKdGdl87nZBjFFVQg6sF+KZfQEQQdQn3X"
        "JwMZQS9R8Legxd/UGJGeFtGUVsUIwfEQRmVxtsvhyHIVV1JEe8hVpZquORpQ7odF7fA27Vj9AaJe7/mdHftbxPaHGHSl/UjIBKDzw/z7Ry378z"
        "cK9rD7MCnqFLHvEZl8sv8ogXWMtPARSn+y/7a17zOGfe7f+xe8f6zvF1Duh3wxvv+eL37E+iD5Qia+/nD4U/ShTx9ek5DPEl9oFX/Hf1+/8Cjh"
        "O58zXtzTXh/egSRwTzofNY/ZL0Q9xYhe3x/6l3L43w+3IXTI74c/bYiZrwW1yHebdvl2+ESXUIZRdIiyns4Y3L3QO6qZMvRhHaaAV/5CexQvlS"
        "vq7MBqE4yCZFPA7yjjUTSDd481MeFUElUTpIq69j/aP5zbzhCWsTA2Llc/ho9SKC9x/oTS2U9Avn9yofK7HSZ8jEobw+34OI0WgnsHjhXIlepi"
        "pbDZahG2upWlroiJNL0wU2uRRLTKd5JVmwmYZrQkKyda5MxCtaqIKWOYw4if+wvZRyYUPiUxiByEk6Z3qknD9RO2EhW7f/YyhYF/VLmVwlaLVd"
        "jsVqqU+fKxAG9nH58dH6PRxnDL3u8KlOiZ/igFOiYrVS0Wc3JLo8qQZGfsp+VLw2fDaiPyf95eOidmG00v8LObM9NRVeDN9LcsxR9oRD4RbIQG"
        "8JVH7oHgtWQ7n1lVVVkyIVzQPK2A/XJ0jiAxYryCWAtDPeQshwqwb1E5YW70sDni+E9HLYEUrUalyvd/7VIoNCUKYYNJTMtdmskUJBcqbvUY8B"
        "AqbRyfNblj8rSoyIk0DS9Va5EJrD6VFXT6IXnVXsHOQpFcnh4bkat762MowD/p5jixSid9ogpa2Zf2jt7EePsT92Q00d/RHKxSnF7CYtvouB14"
        "d9uBnXL22KVu7kk8hEYbx/epomz2aK87Pjeio2ekxXPL3sR7KLqLE773eNLZb8I5D2GKj3DvUc9NKvCTv8PhKny0uuk7vDr2hFH3rRVURF66zA"
        "ZmWkDT7iqVOo6b9gocUpk8XfxLcFKBQiExxrJ6boARGv+HRMsViHXKB37AvhyrQqnxkdbt8LgQ19ykVLZGTrumgCmVcItUdECS0R/TeYo2jsfj"
        "4wM+ybL3daEyWeWOzY+nWKlWFijGAl/hIX2hRtKDy3gVMJavUBJvleQC5eu9FrCpiJ261z0THFzKOz3lqyc2pdZHvQAh79tku/JcehMfA++MLQ"
        "7L+jwU47X1U2tqMJP/EoN//qEs/IlKI+QnpRZFKLnm8MSfduYTt/j9tRgVvKKQTl0uC1cFaFJEphY7oKvOjo12ptxLis5sUsEIZwtqI/KZq/2W"
        "vyE+bPWyA2Mo8VufS2vAG5VWLidP+5b+fxotmP4+aTkvIUUnfbr/bzdNpaSO4eZnqU4p8AUx/Xd9c1fqjxh8ZM+8TFq3bfdlBFrjXD3YsssE/g"
        "WR7FrWMr/8HgIdGZhihqc72zdD0JHyaU7SVGvfdwTy2qSupS29JgQx9c7Ol87I65OCUm/oup/P4DX52v+S4OsQ/Nf5yb3cKb2jLyD4pB9pzQnJ"
        "4BUifAOGXozO2hwzc/PNUXD6go6lztWuSTq6pSsLBFoo3/1FfhszfAcUE2Z3zH7hqaP9Di+A4PlwFHRocctzPxPjCz8eWgCz9wYrKqrc/rdL9n"
        "cXEkdbtG8SkheaRHtLr6F/h9O86JarDpWvk6nB6WomS03HNSDWjjmn90+SbWy1OTpnHz/QLtvU4nRU61Qd8+appui06inYru4AA3nkzt5Am39L"
        "XpEb410543zMQru8OYx0DOVV2v4vCx1GQVcboYThHtfvvYi0RCV8p2BqwznYdxUzNmJ7aqkic1WcMCclBrWKbGdOXWJysJMoegoDVEUTsd2KW4"
        "0VrLSu9PAo7vG/mAkavkpFGUaQYUoSJ/cZg3dTFqEKrUS9sjoPxO6uoohNVVyRXR6D6zYsDDQEWF2GZGVBCx8MQAvFLZ9wEyXUxxW26C4JQmmM"
        "XgF1CEWHqAILHlr0SUL9LY8JBAobsKex592VXjJdOik25swHtkSrk9OP3Jh/NhTphQ3YCGbChlBkGPN+yViRFZGoLZWIyrWpyupWGUj1z5lmT+"
        "lvyo/qzihuFhi4+ei0zxsa9e9jCOdoMqswqs6WHtiaYLRyBMoiqbBCo5PVVivSK9hNjzmRj9xsduYvkZxfi8Fu4HvOY3Firg4bRtBhbA6GodCB"
        "FRhtKwvEam/jJeelJESZDfH3SP+aXRqF3NnATUtv4MqdCi7T9NdaYqp/tjstJTmvjWcrMxhEIpFBaNAbhSKRUZSqiJrygs7XiORytYgvUIvBe2"
        "MLIM6oz4yWJJpmKFzXXalOldXUKHS5U20pAxfWzqhnuwGjJqn4lyITTPdmLmTQFzBZ1XRGDVi03bxcTBmV3CKqWTuY9ClMVieXPHueRpLpesyi"
        "M44cg97+MJHbW4RPHyIYSNQOdmEE28zG0/gYwm6e82f3fJhgJOE/wmcNcwfDGR+4USqiZyEzq/hNRncNJT7FFZ1kSsChSfG/ZfhHBqkJo2YPsK"
        "MCtV1MKUHafNxHSMSjJW2+/imll2zIV/iquOKQ5UVdhaOo+lKKe0Kbb8lRIumIu83HP6XkogqNCV4V5w7huVcFgw4/OECELFhrDDEOBhHnQDnX"
        "ud/9UhJietzybKhZgnWnziGSYgzwlE5kVqlg8qHSc+WNQYR2OCMa/YyMmxHa4GYxdblwhBiZ2YkuFC+U3qsjarQD5FDsy/ANexw/jtgHRzfsdo"
        "CXlB+/cZxaOjpo/3HEsWcDvgw0PoJGSNAwdI80DJGyUJC4hJWHhlaELQ7Lqp5AZxh4uElZInrYlAYvT1wUpRo0Br3vn0GbFjxVrQ6Zik8lqfrf"
        "BxnBotNYTPuun6yiTr2K0qZCLy5VMqhwix81pZGXJywCfsmpO8a5GH05k15AJObTbZejLsr+lBngISJxGpFFFELn8ZX7MW9s30r8PCTUFMsWiU"
        "MwECf0WLnXc6g3evYuPYYMkQVHIy9G3VXz04mEdL7qbrTNJFgfc4t/QEHw79BSuJtI7IYNJw2bhSAxob5UH6RpQmXv2FM4CHoGg6lrwneSwk/w"
        "8nDi6zEi/LciLQQ/bHGvV7S2KteXVqRsnty+JaV80oHCkm0tOfzObJ1MqdFgv5C1BTpRZk5ZjknU4lYnC7VJh8K6auPgGiPjfHxMAL4OZXhhru"
        "Qi85xF+tKGwfy8rS1Nzg19zhpNLW0v5cfPVsro7Mg2Hmcf3S7iL+NyTjHMicIHgGt6Q7zMKWXGaMwEAnqKY4lJiE/PiZbbi+0GDlWrVjYE7TyC"
        "XUn6nS/pIaMDMRbIyTBagl3FTM51BDoAlDP17CShrJSfxv4+/pu7SecJa7iUeLUwk8w+wSIcuN9/cK1PFsycCJZ22jg+Ibe9FBNSgPCATpPyKn"
        "QetbgOHRUYP6afy6eoEh7cwCD+w6oaKJ+QV2SWSwurxKneyU7S6ah5UZzWjZW4+bf10x2e6ecNxASVUcJjnkivh4uJeflpMmlueZLGl51POg1i"
        "A5oCbRkkTSItoYMboMkwVAVtGIQq6cRKaHALVA0Ks0+Y6w/T667u4/ZkBWkJh0Blku/2D+jDj4ePJSd39OND7MN236U7b8fB7hrwZlq643Y83F"
        "jTq3wVdt13ge919IGBnhexObTrQ8L+/nHj7ZbOZY67bHKzFlwMDQv8Ae7ArM6Nju9B7Rwaq2fX8q7bUCz5eAJ3sPDQ4q79m5UHNndZgdFv+dDV"
        "pOTlzTOWDx8TWpY9qXcWTSzXRhdbEyU1bkXuMLGDTEHitDPYZAzOhG4GMlW9Owx9qCBudH+9MaPip19np62a0bvu8KphpAPSRlVPkl87r31Td5"
        "34R1WoQUbnecrgu/qGw1pb3eLVP21akYc/UCB43yktu4sbneKneHn9DPhSFf4Cvn5b9CHxrIeSoaCkaAAKv2vBDhmkwaNY3Zmzes9e/yzuAx73"
        "Dkl/QZY14oRNX0qGD3hc6EBpfu9tco1y1v4dl4VJehHa9yB7svhuSPhr9/qG/JKH1RuNu1Z4F2EYy7xzqeuhEaorp+HS4NmF99QmauOxw/Iaz7"
        "3G56e4PhpomzKt0o2qO5ctsLOf8cmYmdVayR0CyiMLpZnWHQx8PTbtMp69mxbgipULLMKRFtMGSwIcjzlXNrpCAPyz9zamhum6omnWUdL8iakO"
        "uVTvyVel8mQRt+brLwqrVO3K3nXeoZ/XOo5J+r7zRffChcUXVrRrrPwmycZBC0i8pirlAc7k83GTZ5iIfGspT3hRiz9Qetgt1TJ663gA8mbYI5"
        "L4/dSvB4N1g0W7RjXaNKG7bYo2rUqY1ahSrY1Gk3rlclQcNpi0Aa7/2pWxa9KgRCMvAMiNhir/U41vbsPFAAAA"
    ),
    "mono": (
        "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"
    ),
}
_CHARS = ' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~'
FONT_WIDTHS = {
    "young": dict(zip(_CHARS, [250, 373, 402, 760, 723, 883, 813, 214, 454, 454, 582, 600, 316, 511, 313, 500, 602, 397, 543, 529, 575, 537, 608, 572, 558, 608, 313, 316, 600, 600, 600, 540, 1042, 786, 719, 749, 790, 755, 694, 772, 898, 407, 525, 798, 699, 1036, 891, 822, 700, 822, 798, 723, 788, 808, 784, 1207, 853, 794, 745, 397, 500, 397, 600, 598, 600, 619, 609, 514, 619, 515, 402, 522, 681, 347, 303, 631, 347, 1036, 681, 574, 631, 625, 530, 542, 410, 659, 600, 932, 603, 578, 544, 456, 600, 456, 600])),
    "figtree5": dict(zip(_CHARS, [244, 302, 345, 629, 561, 793, 645, 212, 360, 360, 483, 626, 235, 414, 219, 401, 643, 416, 564, 547, 624, 576, 569, 542, 614, 569, 266, 271, 626, 626, 626, 506, 990, 687, 611, 722, 691, 591, 546, 756, 751, 276, 525, 625, 524, 849, 774, 779, 586, 782, 631, 612, 561, 706, 701, 967, 632, 616, 638, 329, 401, 329, 559, 437, 233, 516, 589, 542, 588, 548, 376, 591, 561, 240, 275, 500, 227, 857, 561, 580, 594, 581, 349, 466, 384, 561, 530, 798, 492, 540, 488, 388, 257, 388, 595])),
    "figtree7": dict(zip(_CHARS, [238, 312, 412, 631, 554, 813, 647, 245, 382, 382, 488, 632, 257, 408, 248, 432, 648, 422, 579, 556, 633, 581, 580, 556, 612, 580, 301, 305, 632, 632, 632, 513, 992, 714, 612, 725, 700, 589, 554, 743, 750, 289, 552, 666, 537, 857, 773, 787, 603, 789, 645, 607, 584, 704, 722, 985, 679, 647, 632, 344, 432, 344, 581, 434, 263, 533, 596, 546, 595, 554, 393, 601, 570, 262, 291, 538, 246, 872, 568, 581, 601, 592, 379, 466, 402, 568, 556, 835, 536, 576, 477, 394, 256, 394, 667])),
    "nunito6": dict(zip(_CHARS, [264, 237, 417, 600, 600, 937, 708, 231, 336, 336, 452, 600, 237, 429, 237, 297, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 237, 237, 600, 600, 600, 450, 948, 736, 682, 676, 751, 589, 554, 731, 767, 268, 338, 643, 552, 861, 743, 775, 642, 775, 677, 622, 611, 733, 700, 1107, 660, 606, 596, 333, 297, 333, 600, 500, 366, 537, 591, 467, 591, 537, 347, 594, 576, 243, 246, 516, 306, 866, 576, 565, 591, 591, 373, 484, 365, 569, 520, 846, 534, 520, 468, 370, 275, 370, 600])),
    "nunito7": dict(zip(_CHARS, [271, 248, 448, 600, 600, 945, 726, 243, 358, 358, 453, 600, 248, 434, 248, 313, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 248, 248, 600, 600, 600, 459, 950, 744, 688, 680, 762, 597, 562, 736, 773, 282, 354, 665, 562, 868, 748, 785, 652, 785, 686, 631, 621, 738, 713, 1113, 672, 618, 605, 354, 313, 354, 600, 500, 377, 547, 600, 472, 600, 542, 364, 604, 585, 255, 259, 536, 319, 877, 585, 576, 600, 600, 392, 488, 384, 579, 527, 853, 546, 526, 474, 391, 288, 391, 600])),
    "mono": dict(zip(_CHARS, [600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600, 600])),
}
FONT_CAP = {'young': 750, 'figtree5': 700, 'figtree7': 700, 'nunito6': 705, 'nunito7': 705, 'mono': 700}


if __name__ == "__main__":
    sys.exit(main())
