"""Regenerate the lstuek profile: stats SVGs + the AI-usage block in README.md.

Runs locally (uses the existing `gh` login and local Claude Code / Codex logs).
Only aggregates leave this machine: no repo, project, or client names.

    python scripts/update.py          # regenerate files
    python scripts/update.py --push   # regenerate, commit, push (skips if run < 5h ago; --force overrides)
    python scripts/update.py --upload # upload aggregates; keep the legacy renderer until cutover
    python scripts/update.py --dry-run # print pc.json without writing or pushing
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
OWNERS = (USER, "lbstuek")  # my account and my org; repos are read under whichever owns them
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
HOME = os.path.expanduser("~")
MIN_GAP_HOURS = 5  # scheduled runs closer together than this are skipped
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # pythonw has no console, so each child would open one
UPLOAD_CONTRIBUTIONS = False


def state_dir():
    return os.path.join(os.environ.get("LOCALAPPDATA", HOME), "lstuek-profile")

BG, BORDER, TEXT, MUTED, ACCENT = "#0d1117", "#30363d", "#c9d1d9", "#8b949e", "#bc8cff"
FONT = 'font-family="Segoe UI, Ubuntu, sans-serif"'
LANG_COLORS = {
    "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "Python": "#3572a5",
    "PLpgSQL": "#336790", "HTML": "#e34c26", "CSS": "#8e5cd9",
    "PowerShell": "#5391fe", "Shell": "#89e051",
}


# ---------- GitHub (via gh CLI) ----------

def gh_lines(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", creationflags=NO_WINDOW)
    return r.stdout.splitlines() if r.returncode == 0 else []  # empty repos return 409


def repos():
    """Non-fork repos as "owner/name"."""
    out = []
    for o in OWNERS:
        data = json.loads("\n".join(gh_lines("repo", "list", o, "--limit", "200", "--json", "name,isFork")) or "[]")
        out += [f"{o}/{r['name']}" for r in data if not r["isFork"] and r["name"] != o]
    return out


def commit_times(names):
    out = []
    for n in names:
        for s in gh_lines("api", "--paginate", f"repos/{n}/commits?per_page=100",
                          "--jq", '.[] | select(.author.type != "Bot") | .commit.author.date'):
            out.append(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone())
    return out


def language_bytes(names, dry_run=False, return_snapshots=False):
    """Keep private per-repo snapshots locally; publish only their byte sums."""
    path = os.path.join(state_dir(), "languages.json")
    snapshots = load_json(path)
    total = collections.Counter()
    for n in names:
        lines = gh_lines("api", f"repos/{n}/languages")
        if lines:
            langs = json.loads("\n".join(lines))
            if not isinstance(langs, dict) or any(not count(v) for v in langs.values()):
                raise ValueError("invalid language byte response")
            snapshots[n] = langs
        total.update(snapshots.get(n, {}))
    if not dry_run:
        os.makedirs(state_dir(), exist_ok=True)
        write_json(path, snapshots)
    return (dict(total), snapshots) if return_snapshots else dict(total)


def language_shares(names):
    total = collections.Counter(language_bytes(names))
    size = sum(total.values()) or 1
    return [(k, v / size) for k, v in total.most_common()]


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
    sessions = {}
    rec = lambda path: sessions.setdefault(hashlib.sha1(os.path.basename(path).encode()).hexdigest()[:12], {"usage": {}, "prompts": {}})

    def usage(path, t, fam, i, o):
        u = rec(path)["usage"].setdefault(t.date().isoformat(), {}).setdefault(fam, [0, 0])
        u[0] += i
        u[1] += o

    def prompt(path, t):
        p = rec(path)["prompts"]
        p[f"{t:%Y-%m-%dT%H}"] = p.get(f"{t:%Y-%m-%dT%H}", 0) + 1

    for path in glob.glob(os.path.join(HOME, ".claude", "projects", "**", "*.jsonl"), recursive=True):
        if "claude-mem-observer" in path:  # claude-mem's background summarizer, not my sessions
            continue
        sub = os.sep + "subagents" + os.sep in path  # subagent tokens count; their briefs are not my prompts
        rec(path)  # even an empty rebuilt log overrides its stored copy
        messages = {}
        for index, d in enumerate(read_jsonl(path)):
            if "timestamp" not in d:
                continue
            t, msg = ts(d["timestamp"]), d.get("message") or {}
            if d.get("type") == "user" and not d.get("isMeta") and not sub:
                c = msg.get("content")
                if isinstance(c, str) or (isinstance(c, list) and any(x.get("type") == "text" for x in c)):
                    prompt(path, t)
            elif d.get("type") == "assistant" and family(msg.get("model")):
                u = msg.get("usage") or {}
                i = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                key = (msg.get("id", index), d.get("requestId", d.get("request_id")))
                messages[key] = (t, family(msg.get("model")), i, u.get("output_tokens", 0))
        for args in messages.values():
            usage(path, *args)

    for path in glob.glob(os.path.join(HOME, ".codex", "sessions", "**", "*.jsonl"), recursive=True):
        model = None
        previous = (0, 0)
        rec(path)
        for d in read_jsonl(path):
            p, kind = d.get("payload") or {}, d.get("type")
            if kind == "turn_context":
                model = p.get("model")
            elif kind == "event_msg" and "timestamp" in d:
                t = ts(d["timestamp"])
                if p.get("type") == "task_started" and model != "codex-auto-review":  # Codex's own safety reviewer, not a prompt
                    prompt(path, t)
                elif p.get("type") == "token_count":
                    u = ((p.get("info") or {}).get("total_token_usage")) or {}
                    if u:
                        current = (u.get("input_tokens", 0), u.get("output_tokens", 0))
                        reset = any(a < b for a, b in zip(current, previous))
                        delta = current if reset else tuple(a - b for a, b in zip(current, previous))
                        usage(path, t, "GPT (Codex)", *delta)
                        previous = current
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
    for name in (n.rsplit("/", 1)[-1] for n in names):
        for t in texts:
            if re.search(rf"\b{re.escape(name)}\b", t, re.I):
                sys.exit(f"privacy check failed: repo name {name!r} found in output")


def git(*args, out=None):
    return subprocess.run(["git", "-C", ROOT, *args], stdout=out, stderr=out, creationflags=NO_WINDOW).returncode


def git_text(*args):
    result = subprocess.run(["git", "-C", ROOT, *args], capture_output=True,
                            text=True, encoding="utf-8", creationflags=NO_WINDOW)
    if result.returncode:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr}")
    return result.stdout


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, separators=(",", ":"), sort_keys=True)


def count(value):
    return type(value) is int and value >= 0


def validate_upload(path, value, names):
    """An allowlist, including nested keys: no arbitrary text can leave the PC."""
    def require(ok):
        if not ok:
            sys.exit(f"privacy schema failed: {path}")

    def day(key):
        return isinstance(key, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", key) and dt.date.fromisoformat(key)

    try:
        require(isinstance(value, dict))
        if path == "data/pc.json":
            require(set(value) in ({"updated", "tokens", "languages"}, {"updated", "tokens", "languages", "contributions"}))
            require(isinstance(value["updated"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value["updated"]))
            dt.datetime.fromisoformat(value["updated"].replace("Z", "+00:00"))
            tokens = value["tokens"]
            require(isinstance(tokens, dict) and set(tokens) == {"total", "claude", "codex", "since"})
            require(all(count(tokens[k]) for k in ("total", "claude", "codex")))
            require(tokens["total"] == tokens["claude"] + tokens["codex"])
            since = tokens["since"]
            require(since is None or isinstance(since, str) and re.fullmatch(r"\d{4}-\d{2}", since))
            if since is not None:
                dt.date.fromisoformat(since + "-01")
            require(isinstance(value["languages"], dict))
            require(all(isinstance(k, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9+# ._-]{0,79}", k) and count(v) for k, v in value["languages"].items()))
            if "contributions" in value:
                require(isinstance(value["contributions"], dict))
                require(all(day(k) and count(v) for k, v in value["contributions"].items()))
        else:
            require(re.fullmatch(r"data/ai-[0-9a-f]+\.json", path))
            for session, record in value.items():
                require(isinstance(session, str) and re.fullmatch(r"[0-9a-f]{12}", session))
                require(isinstance(record, dict) and set(record) == {"prompts", "usage"})
                require(isinstance(record["prompts"], dict) and isinstance(record["usage"], dict))
                for hour, n in record["prompts"].items():
                    require(isinstance(hour, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}", hour) and count(n))
                    dt.datetime.strptime(hour, "%Y-%m-%dT%H")
                for date, families in record["usage"].items():
                    require(day(date) and isinstance(families, dict))
                    for fam, pair in families.items():
                        require(fam in {"Opus", "Fable", "Sonnet", "Haiku", "GPT (Codex)"})
                        require(isinstance(pair, list) and len(pair) == 2 and all(count(n) for n in pair))
    except (ValueError, TypeError, KeyError):
        sys.exit(f"privacy schema failed: {path}")
    check_private([json.dumps(value)], names)


def rebuild_ledgers(stored, rebuilt, mine_path):
    ledgers = {path: {**records, **{k: v for k, v in rebuilt.items() if k in records}}
               for path, records in stored.items()}
    ledgers[mine_path] = {**ledgers.get(mine_path, {}), **rebuilt}
    everyone = merge(*ledgers.values())
    uncertain = sum(weight(v) - sum(v["prompts"].values()) for k, v in everyone.items() if k not in rebuilt)
    return ledgers, everyone, uncertain


def pc_data(everyone, languages, per_day, now):
    models = summarize(everyone, "")[4]
    codex = models["GPT (Codex)"]
    total = sum(models.values())
    days = [day for record in everyone.values() for day in record["usage"]]
    days += [hour[:10] for record in everyone.values() for hour in record["prompts"]]
    value = {"updated": now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "tokens": {"total": total, "claude": total - codex, "codex": codex,
                        "since": min(days)[:7] if days else None}, "languages": languages}
    if UPLOAD_CONTRIBUTIONS:
        today = now.date()
        value["contributions"] = {(today - dt.timedelta(days=i)).isoformat(): per_day[today - dt.timedelta(days=i)] for i in range(365)}
    return value


LEGACY_PATHS = {"README.md", "assets/languages.svg", "assets/streak.svg", "assets/commits.svg"}


def validate_staged(names, legacy=False):
    paths = git_text("diff", "--cached", "--name-only", "-z").split("\0")
    for path in filter(None, paths):
        if legacy and path in LEGACY_PATHS:
            check_private([git_text("show", f":{path}")], names)
        elif path == "data/pc.json" or re.fullmatch(r"data/ai-[0-9a-f]+\.json", path):
            try:
                value = json.loads(git_text("show", f":{path}"))
            except (ValueError, RuntimeError):
                sys.exit(f"privacy schema failed: {path}")
            validate_upload(path, value, names)
        else:
            sys.exit(f"unexpected staged path: {path}")


def push_retained(out=None):
    for attempt in range(4):
        if git("pull", "--rebase", "--autostash", out=out):
            git("rebase", "--abort", out=out)
            return False
        if not git("push", out=out):
            return True
        print(f"push attempt {attempt + 1}/4 failed", flush=True)
    return False


def main():
    dry_run = "--dry-run" in sys.argv
    upload = "--upload" in sys.argv
    push = ("--push" in sys.argv or upload) and not dry_run
    if push:  # scheduled runs have no console: log to a local file
        local = state_dir()
        os.makedirs(local, exist_ok=True)
        stamp_path = os.path.join(local, "last")
        if "--force" not in sys.argv and os.path.exists(stamp_path) and                 dt.datetime.now().timestamp() - os.path.getmtime(stamp_path) < MIN_GAP_HOURS * 3600:
            return  # ran recently (wake/catch-up duplicates): skip silently
        log = open(os.path.join(local, "run.log"), "a", encoding="utf-8")
        sys.stdout = sys.stderr = log
        print(f"--- {dt.datetime.now():%Y-%m-%d %H:%M} {platform.node()}", flush=True)

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
    mine_path = os.path.join(data_dir, f"ai-{hashlib.sha1(platform.node().encode()).hexdigest()[:8]}.json")
    stored = {p: load_json(p) for p in sorted(glob.glob(os.path.join(data_dir, "ai-*.json")))}
    ledgers, everyone, uncertain = rebuild_ledgers(stored, scan_logs(), mine_path)
    print(f"uncertain: {uncertain}", flush=True)
    languages, snapshots = language_bytes(names, dry_run=True, return_snapshots=True)
    pc = pc_data(everyone, languages, per_day, now)
    validate_upload("data/pc.json", pc, names)
    for path, records in ledgers.items():
        validate_upload("data/" + os.path.basename(path), records, names)
    if dry_run:
        print(json.dumps(pc, indent=2, sort_keys=True), flush=True)
        return
    if push:
        validate_staged(names, legacy=not upload)
    os.makedirs(data_dir, exist_ok=True)
    for path, records in ledgers.items():
        write_json(path, records)
    write_json(os.path.join(data_dir, "pc.json"), pc)
    os.makedirs(state_dir(), exist_ok=True)
    write_json(os.path.join(state_dir(), "languages.json"), snapshots)
    tin, tout, sess, prompts, models, ptimes = summarize(everyone, (today - dt.timedelta(days=6)).isoformat())

    if not upload:
        size = sum(languages.values()) or 1
        svgs = {"languages.svg": langs_svg([(k, v / size) for k, v in sorted(languages.items(), key=lambda item: -item[1])]),
                "streak.svg": streak_svg(len(commits), cur, longest),
                "commits.svg": commits_svg(last90)}
        block = ai_block(tin, tout, sess, prompts, models, commits + ptimes)
        readme_path = os.path.join(ROOT, "README.md")
        with open(readme_path, encoding="utf-8") as f:
            readme = f.read()
        stamp = f"<sub>Last updated {now:%Y-%m-%d %H:%M %Z}</sub>"
        readme = re.sub(r"(<!--AI:START-->).*?(<!--AI:END-->)", lambda m: f"{m[1]}\n{block}\n{m[2]}", readme, flags=re.S)
        readme = re.sub(r"(<!--UPDATED:START-->).*?(<!--UPDATED:END-->)", lambda m: f"{m[1]}{stamp}{m[2]}", readme, flags=re.S)
        check_private([readme, *svgs.values()], names)
        os.makedirs(ASSETS, exist_ok=True)
        for fn, svg in svgs.items():
            with open(os.path.join(ASSETS, fn), "w", encoding="utf-8") as f:
                f.write(svg)
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme)
    print(f"{len(names)} repos, {len(commits)} commits, streak {cur}/{longest}, "
          f"AI {sess} sessions {prompts} prompts ({len(everyone)} sessions on record)", flush=True)

    if push:
        paths = ["data/pc.json", *["data/" + os.path.basename(p) for p in ledgers]]
        if not upload:
            paths += sorted(LEGACY_PATHS)
        if git("add", "--", *paths, out=log):
            sys.exit("stage failed")
        validate_staged(names, legacy=not upload)
        diff = git("diff", "--staged", "--quiet")
        if diff not in (0, 1):
            sys.exit("staged diff failed")
        if diff == 1:
            if git("commit", "-m", "Update profile stats", out=log):
                sys.exit("commit failed")
        if not push_retained(out=log):
            sys.exit("push failed; commit retained for next run")
        open(stamp_path, "w").close()  # mark success; failures retry on the next trigger


if __name__ == "__main__":
    main()
