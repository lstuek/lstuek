"""Regenerate the lstuek profile: stats SVGs + the AI-usage block in README.md.

Runs locally (uses the existing `gh` login and local Claude Code / Codex logs).
Only aggregates leave this machine: no repo, project, or client names.

    python scripts/update.py          # regenerate files
    python scripts/update.py --push   # regenerate, commit, push (skips if run < 5h ago; --force overrides)
"""
import collections
import datetime as dt
import glob
import hashlib
import json
import os
import platform
import re
import subprocess
import sys

USER = "lstuek"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
HOME = os.path.expanduser("~")
MIN_GAP_HOURS = 5  # scheduled runs closer together than this are skipped

BG, BORDER, TEXT, MUTED, ACCENT = "#0d1117", "#30363d", "#c9d1d9", "#8b949e", "#bc8cff"
FONT = 'font-family="Segoe UI, Ubuntu, sans-serif"'
LANG_COLORS = {
    "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "Python": "#3572a5",
    "PLpgSQL": "#336790", "HTML": "#e34c26", "CSS": "#8e5cd9",
    "PowerShell": "#5391fe", "Shell": "#89e051",
}


# ---------- GitHub (via gh CLI) ----------

def gh_lines(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    return r.stdout.splitlines() if r.returncode == 0 else []  # empty repos return 409


def repos():
    data = json.loads("\n".join(gh_lines("repo", "list", USER, "--limit", "200", "--json", "name,isFork")) or "[]")
    return [r["name"] for r in data if not r["isFork"] and r["name"] != USER]


def commit_times(names):
    out = []
    for n in names:
        for s in gh_lines("api", "--paginate", f"repos/{USER}/{n}/commits?per_page=100",
                          "--jq", '.[] | select(.author.type != "Bot") | .commit.author.date'):
            out.append(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone())
    return out


def language_shares(names):
    """Each repo counts equally, so one huge or generated-heavy repo can't dominate."""
    total = collections.Counter()
    for n in names:
        langs = json.loads("\n".join(gh_lines("api", f"repos/{USER}/{n}/languages")) or "{}")
        size = sum(langs.values())
        for k, v in langs.items():
            total[k] += v / size
    s = sum(total.values()) or 1
    return [(k, v / s) for k, v in total.most_common()]


# ---------- Local AI logs ----------

def family(model):
    m = (model or "").lower()
    for key, name in (("opus", "Opus"), ("fable", "Fable"), ("sonnet", "Sonnet"), ("haiku", "Haiku")):
        if key in m:
            return name
    return "GPT (Codex)" if m.startswith(("gpt", "codex")) else None


def read_jsonl(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()


def scan_logs():
    """Per-session aggregates from local logs: {session_hash: {"usage": {day: {family: [in, out]}}, "prompts": {"YYYY-MM-DDTHH": n}}}.
    Keyed by a hash of the log file name, so copies of the same session on two machines merge instead of double counting."""
    sessions, seen = {}, set()
    rec = lambda path: sessions.setdefault(hashlib.sha1(os.path.basename(path).encode()).hexdigest()[:12], {"usage": {}, "prompts": {}})

    def usage(path, t, fam, i, o):
        u = rec(path)["usage"].setdefault(t.date().isoformat(), {}).setdefault(fam, [0, 0])
        u[0] += i
        u[1] += o

    def prompt(path, t):
        p = rec(path)["prompts"]
        p[f"{t:%Y-%m-%dT%H}"] = p.get(f"{t:%Y-%m-%dT%H}", 0) + 1

    for path in glob.glob(os.path.join(HOME, ".claude", "projects", "*", "*.jsonl")):
        for d in read_jsonl(path):
            if "timestamp" not in d:
                continue
            t, msg = ts(d["timestamp"]), d.get("message") or {}
            if d.get("type") == "user" and not d.get("isMeta"):
                c = msg.get("content")
                if isinstance(c, str) or (isinstance(c, list) and any(x.get("type") == "text" for x in c)):
                    prompt(path, t)
            elif d.get("type") == "assistant" and msg.get("id") not in seen and family(msg.get("model")):
                seen.add(msg.get("id"))  # streamed chunks repeat the same message id
                u = msg.get("usage") or {}
                i = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                usage(path, t, family(msg.get("model")), i, u.get("output_tokens", 0))

    for path in glob.glob(os.path.join(HOME, ".codex", "sessions", "**", "*.jsonl"), recursive=True):
        model = None
        for d in read_jsonl(path):
            p, kind = d.get("payload") or {}, d.get("type")
            if kind == "turn_context":
                model = p.get("model")
            elif kind == "event_msg" and "timestamp" in d:
                t = ts(d["timestamp"])
                if p.get("type") == "task_started" and model != "codex-auto-review":  # Codex's own safety reviewer, not a prompt
                    prompt(path, t)
                elif p.get("type") == "token_count":
                    u = ((p.get("info") or {}).get("last_token_usage")) or {}
                    if u:
                        usage(path, t, "GPT (Codex)", u.get("input_tokens", 0), u.get("output_tokens", 0))
    return sessions


def weight(s):
    return sum(i + o for fams in s["usage"].values() for i, o in fams.values()) + sum(s["prompts"].values())


def merge(*maps):
    """Union of session maps; for a session seen more than once, keep the most complete copy (later maps win ties)."""
    out = {}
    for m in maps:
        for k, v in m.items():
            if k not in out or weight(v) >= weight(out[k]):
                out[k] = v
    return out


def summarize(sessions, since):
    """since: ISO date string. Returns (tokens_in, tokens_out, sessions, prompts, model_tokens, all_prompt_times)."""
    tin = tout = prompts = active = 0
    models, times = collections.Counter(), []
    for s in sessions.values():
        for day, fams in s["usage"].items():
            if day >= since:
                for fam, (i, o) in fams.items():
                    tin, tout = tin + i, tout + o
                    models[fam] += i + o
        recent = 0
        for hour, n in s["prompts"].items():
            times += [dt.datetime.strptime(hour, "%Y-%m-%dT%H")] * n
            recent += n if hour[:10] >= since else 0
        prompts, active = prompts + recent, active + (recent > 0)
    return tin, tout, active, prompts, models, times


# ---------- Stats ----------

def streaks(dates, today):
    days = set(dates)
    longest = run = 0
    for d in sorted(days):
        run = run + 1 if d - dt.timedelta(days=1) in days else 1
        longest = max(longest, run)
    cur, d = 0, today if today in days else today - dt.timedelta(days=1)  # today not over yet
    while d in days:
        cur, d = cur + 1, d - dt.timedelta(days=1)
    return cur, longest


def bar(frac, width=25):
    n = round(frac * width)
    return "█" * n + "░" * (width - n)


def table(rows, unit):
    total = sum(v for _, v in rows) or 1
    return "\n".join(f"{k:<14}{f'{v:,} {unit}':<22}{bar(v / total)}  {100 * v / total:5.1f} %" for k, v in rows)


def fmt(n):
    return f"{n / 1e9:.1f}B" if n >= 1e9 else f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.1f}K" if n >= 1e3 else str(n)


def ai_block(tin, tout, sessions, prompts, models, times):
    parts = [("🌞 Morning", range(6, 12)), ("🌆 Daytime", range(12, 18)), ("🌃 Evening", range(18, 24)), ("🌙 Night", range(0, 6))]
    tod = [(name, sum(t.hour in hrs for t in times)) for name, hrs in parts]
    week = [(day, sum(t.weekday() == i for t in times)) for i, day in
            enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])]
    owl = max(tod, key=lambda x: x[1])[0].split()[1]
    best = max(week, key=lambda x: x[1])[0]
    return f"""**🤖 AI Coding This Week**

```text
🔤 {fmt(tin)} input tokens · {fmt(tout)} output tokens
🧠 {sessions} sessions · {prompts} prompts

{table([(k, v) for k, v in models.most_common()], "tokens")}
```

**I'm a {owl} builder, most active on {best}** <sub>(commits + AI prompts on record)</sub>

```text
{table(tod, "events")}

{table(week, "events")}
```"""


# ---------- SVGs ----------

def card(w, h, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{title}">'
            f'<title>{title}</title><rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="8" fill="{BG}" stroke="{BORDER}"/>'
            f'<text x="20" y="30" fill="{ACCENT}" font-size="14" font-weight="600" {FONT}>{title}</text>{body}</svg>')


def langs_svg(shares):
    top = shares[:6]
    rest = 1 - sum(v for _, v in top)
    if rest > 0.005:
        top.append(("Other", rest))
    x, body = 20.0, []
    for k, v in top:  # stacked bar
        body.append(f'<rect x="{x:.1f}" y="46" width="{v * 360:.1f}" height="8" fill="{LANG_COLORS.get(k, MUTED)}"/>')
        x += v * 360
    for i, (k, v) in enumerate(top):
        cx, cy = 20 + (i % 2) * 185, 80 + (i // 2) * 22
        body.append(f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{LANG_COLORS.get(k, MUTED)}"/>'
                    f'<text x="{cx + 16}" y="{cy}" fill="{TEXT}" font-size="12" {FONT}>{k} <tspan fill="{MUTED}">{100 * v:.1f}%</tspan></text>')
    return card(400, 165, "".join(body), "Languages across my repos")


def streak_svg(total, cur, longest):
    cols = [(total, "Total commits"), (cur, "Current streak"), (longest, "Longest streak")]
    body = "".join(
        f'<text x="{70 + i * 130}" y="95" fill="{ACCENT if i == 1 else TEXT}" font-size="30" font-weight="700" text-anchor="middle" {FONT}>{v:,}</text>'
        f'<text x="{70 + i * 130}" y="122" fill="{MUTED}" font-size="12" text-anchor="middle" {FONT}>{label}{" (days)" if i else ""}</text>'
        for i, (v, label) in enumerate(cols))
    return card(400, 165, body, "Commit streak")


def commits_svg(counts):
    """counts: list of (date, n) for consecutive days."""
    W, H, L, R, T, B = 850, 240, 45, 20, 50, 30
    cw, ch, n = W - L - R, H - T - B, len(counts)
    top = max(max(c for _, c in counts), 1)
    x = lambda i: L + i * cw / (n - 1)
    y = lambda v: T + ch - v / top * ch
    grid = "".join(f'<line x1="{L}" y1="{y(v):.1f}" x2="{W - R}" y2="{y(v):.1f}" stroke="#21262d"/>'
                   f'<text x="{L - 8}" y="{y(v) + 4:.1f}" fill="{MUTED}" font-size="11" text-anchor="end" {FONT}>{v}</text>'
                   for v in sorted({round(top * k / 4) for k in range(5)}))
    labels = "".join(f'<text x="{x(i):.1f}" y="{H - 8}" fill="{MUTED}" font-size="11" text-anchor="middle" {FONT}>{counts[i][0]:%b %d}</text>'
                     for i in range(0, n, 15))
    pts = " ".join(f"{x(i):.1f},{y(c):.1f}" for i, (_, c) in enumerate(counts))
    area = f"{L},{T + ch} {pts} {W - R},{T + ch}"
    body = (f'{grid}{labels}<polygon points="{area}" fill="{ACCENT}" fill-opacity="0.15"/>'
            f'<polyline points="{pts}" fill="none" stroke="{ACCENT}" stroke-width="2" stroke-linejoin="round"/>')
    return card(W, H, body, f"Commits per day · last {n} days")


# ---------- Main ----------

def check_private(texts, names):
    """Hard stop if any repo name leaks into a public file."""
    for name in names:
        for t in texts:
            if re.search(rf"\b{re.escape(name)}\b", t, re.I):
                sys.exit(f"privacy check failed: repo name {name!r} found in output")


def git(*args, out=None):
    return subprocess.run(["git", "-C", ROOT, *args], stdout=out, stderr=out).returncode


def main():
    push = "--push" in sys.argv
    if push:  # scheduled runs have no console: log to a local file
        local = os.environ.get("LOCALAPPDATA", HOME)
        stamp_path = os.path.join(local, "lstuek-profile.last")
        if "--force" not in sys.argv and os.path.exists(stamp_path) and                 dt.datetime.now().timestamp() - os.path.getmtime(stamp_path) < MIN_GAP_HOURS * 3600:
            return  # ran recently (wake/catch-up duplicates): skip silently
        log = open(os.path.join(local, "lstuek-profile.log"), "a", encoding="utf-8")
        sys.stdout = sys.stderr = log
        print(f"--- {dt.datetime.now():%Y-%m-%d %H:%M} {platform.node()}", flush=True)
        if git("pull", "--rebase", "--autostash", out=log):
            git("rebase", "--abort", out=log)
            sys.exit("pull failed; will retry next run")

    now = dt.datetime.now().astimezone()
    today = now.date()
    names = repos()
    if not names:
        sys.exit("no repos returned; is `gh` logged in?")  # never overwrite the profile with empty stats
    commits = commit_times(names)
    per_day = collections.Counter(t.date() for t in commits)
    last90 = [(today - dt.timedelta(days=89 - i), per_day[today - dt.timedelta(days=89 - i)]) for i in range(90)]
    cur, longest = streaks(per_day, today)

    # This machine's sessions, kept even after the local logs are pruned; other machines' files merge in.
    data_dir = os.path.join(ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)
    mine_path = os.path.join(data_dir, f"ai-{hashlib.sha1(platform.node().encode()).hexdigest()[:8]}.json")
    load = lambda p: json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    mine = merge(load(mine_path), scan_logs())
    with open(mine_path, "w", encoding="utf-8") as f:
        json.dump(mine, f, separators=(",", ":"), sort_keys=True)
    everyone = merge(*(load(p) for p in sorted(glob.glob(os.path.join(data_dir, "ai-*.json")))))
    tin, tout, sess, prompts, models, ptimes = summarize(everyone, (today - dt.timedelta(days=6)).isoformat())

    svgs = {"languages.svg": langs_svg(language_shares(names)),
            "streak.svg": streak_svg(len(commits), cur, longest),
            "commits.svg": commits_svg(last90)}
    block = ai_block(tin, tout, sess, prompts, models, commits + ptimes)

    readme_path = os.path.join(ROOT, "README.md")
    with open(readme_path, encoding="utf-8") as f:
        readme = f.read()
    stamp = f"<sub>Last updated {now:%Y-%m-%d %H:%M %Z}</sub>"
    readme = re.sub(r"(<!--AI:START-->).*?(<!--AI:END-->)", lambda m: f"{m[1]}\n{block}\n{m[2]}", readme, flags=re.S)
    readme = re.sub(r"(<!--UPDATED:START-->).*?(<!--UPDATED:END-->)", lambda m: f"{m[1]}{stamp}{m[2]}", readme, flags=re.S)

    check_private([readme, *svgs.values(), json.dumps(mine)], names)
    os.makedirs(ASSETS, exist_ok=True)
    for fn, svg in svgs.items():
        with open(os.path.join(ASSETS, fn), "w", encoding="utf-8") as f:
            f.write(svg)
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)
    print(f"{len(names)} repos, {len(commits)} commits, streak {cur}/{longest}, "
          f"AI {sess} sessions {prompts} prompts ({len(everyone)} sessions on record)", flush=True)

    if push:
        git("add", "README.md", "assets", "data", out=log)
        if git("diff", "--staged", "--quiet"):
            git("commit", "-m", "Update profile stats", out=log)
            if git("push", out=log):  # e.g. the other machine pushed first: drop our commit, next run regenerates
                git("reset", "--keep", "HEAD~1", out=log)
                sys.exit("push failed; will retry next run")
        open(stamp_path, "w").close()  # mark success; failures retry on the next trigger


if __name__ == "__main__":
    main()
