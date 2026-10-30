"""City data (lstuek.github.io#2): schema guard, locked zone, ledgers per day, fetch failures.
Fixtures only: fake repo lists and fake ledgers; the GitHub CLI is never called."""
import collections
import datetime as dt
import json
import pathlib
import subprocess
import sys

import pytest

import update as u

NOW = dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)
KEYS = ["portfolio", "new-era", "bionic-wave", "ka-tech", "ka-ops", "aios", "crm", "systemselect"]
NAMES = ["owner/private-project", "owner/fake-site", "org/fake-ops"]


def landmark(**kw):
    return {"commits_total": 12, "commits_30d": 3, "pushed_this_week": True,
            "last_push_date": "2026-10-09", "language": "TypeScript", **kw}


def city(**kw):
    return {"generated_at": "2026-10-10T12:00:00Z",
            "totals": {"tokens": 1000, "commits": 40, "top_language": "TypeScript"},
            "landmarks": {k: landmark() for k in KEYS}, "locked": {"activity_30d": 5}, **kw}


def at(days_ago, hour=12):
    return NOW - dt.timedelta(days=days_ago) + dt.timedelta(hours=hour - 12)


# ---------- privacy guard ----------

def test_eight_landmark_keys_pass_even_when_a_repo_has_that_name():
    u.validate_upload("data/city.json", city(), NAMES + ["owner/aios", "owner/crm"])


def test_private_name_in_a_permitted_string_field_stops_the_job():
    u.validate_upload("data/city.json", city(), NAMES)
    leak = city(totals={"tokens": 1, "commits": 1, "top_language": "private-project"})
    with pytest.raises(SystemExit, match="repo name"):
        u.validate_upload("data/city.json", leak, NAMES)
    leak = city(landmarks={"crm": landmark(language="fake-site")})
    with pytest.raises(SystemExit, match="repo name"):
        u.validate_upload("data/city.json", leak, NAMES)
    # A landmark key is allowed only as a schema key, never as a value.
    leak = city(totals={"tokens": 1, "commits": 1, "top_language": "aios"})
    with pytest.raises(SystemExit, match="repo name"):
        u.validate_upload("data/city.json", leak, NAMES + ["owner/aios"])


@pytest.mark.parametrize("bad", [
    lambda c: c["landmarks"].update({"private-project": landmark()}),
    lambda c: c["landmarks"].update({"Portfolio": c["landmarks"].pop("portfolio")}),
    lambda c: c.update({"repos": {}}),
    lambda c: c["locked"].update({"fake-site": 2}),
    lambda c: c["landmarks"]["aios"].update({"repo": "x"}),
    lambda c: c["totals"].update({"by_repo": {}}),
])
def test_unknown_key_stops_the_job(bad):
    u.validate_upload("data/city.json", city(), NAMES)
    value = city()
    bad(value)
    with pytest.raises(SystemExit, match="privacy schema failed"):
        u.validate_upload("data/city.json", value, NAMES)


@pytest.mark.parametrize("field, value", [
    ("generated_at", "2026-10-10T12:00:00+02:00"), ("generated_at", "2026-10-10"),
    ("last_push_date", "2026-10-09T08:15:00Z"), ("last_push_date", "2026-10-09 08:15"),
])
def test_dates_have_no_clock_time_and_generated_at_is_utc(field, value):
    u.validate_upload("data/city.json", city(), NAMES)
    c = city()
    if field == "generated_at":
        c[field] = value
    else:
        c["landmarks"]["aios"][field] = value
    with pytest.raises(SystemExit, match="privacy schema failed"):
        u.validate_upload("data/city.json", c, NAMES)


def run_git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True,
                          creationflags=u.NO_WINDOW, check=True)


def test_city_file_is_on_the_staged_allowlist_and_unsafe_staged_files_stop(tmp_path, monkeypatch):
    run_git(tmp_path, "init", "--initial-branch=main")
    monkeypatch.setattr(u, "ROOT", str(tmp_path))
    path = tmp_path / "data/city.json"
    path.parent.mkdir()
    path.write_text(json.dumps(city()))
    run_git(tmp_path, "add", "data/city.json")
    u.validate_staged(NAMES)
    path.write_text(json.dumps(city(totals={"tokens": 1, "commits": 1, "top_language": "private-project"})))
    run_git(tmp_path, "add", "data/city.json")
    with pytest.raises(SystemExit, match="repo name"):
        u.validate_staged(NAMES)
    path.write_text(json.dumps(city()))
    (tmp_path / "landmarks.json").write_text(json.dumps({"aios": "owner/private-project"}))
    run_git(tmp_path, "add", "data/city.json", "landmarks.json")
    with pytest.raises(SystemExit, match="unexpected staged path: landmarks.json"):
        u.validate_staged(NAMES)


# ---------- AI ledgers: per-day prompt counts in the upload ----------

HOURLY = {"usage": {"2026-10-09": {"Opus": [500, 50]}, "2026-10-10": {"GPT (Codex)": [300, 30]}},
          "prompts": {"2026-10-09T08": 2, "2026-10-09T23": 1, "2026-10-10T14": 4}}
DAILY_PROMPTS = {"2026-10-09": 3, "2026-10-10": 4}


def test_uploaded_ledgers_hold_per_day_counts():
    daily = {"a" * 12: {**HOURLY, "prompts": DAILY_PROMPTS}}
    u.validate_upload("data/ai-abc.json", daily, NAMES)
    with pytest.raises(SystemExit, match="privacy schema failed"):
        u.validate_upload("data/ai-abc.json", {"a" * 12: HOURLY}, NAMES)


def test_ledger_migration_keeps_token_totals_and_moves_prompts_to_days():
    old, pruned, fresh = "a" * 12, "b" * 12, "c" * 12
    # Remote before migration: per-hour files from this PC and an older one; one session's logs are pruned.
    stored = {"mine": {old: HOURLY, pruned: HOURLY}, "older": {old: HOURLY}}
    before = u.pc_data(u.merge(*stored.values()), {}, collections.Counter(), NOW)["tokens"]
    assert before["total"] == 1760
    rebuilt = {old: HOURLY, fresh: {"usage": {}, "prompts": {"2026-10-10T09": 1}}}
    ledgers, everyone, _ = u.rebuild_ledgers(stored, rebuilt, "mine")
    for records in ledgers.values():
        u.validate_upload("data/ai-abc.json", records, NAMES)
        assert all(len(day) == 10 for r in records.values() for day in r["prompts"])
    assert ledgers["mine"][old]["prompts"] == ledgers["mine"][pruned]["prompts"] == DAILY_PROMPTS
    assert u.pc_data(everyone, {}, collections.Counter(), NOW)["tokens"] == before
    # Next run: the remote is per-day now and the logs are still per-hour; nothing doubles.
    ledgers2, everyone2, _ = u.rebuild_ledgers(ledgers, rebuilt, "mine")
    assert ledgers2 == ledgers
    assert u.pc_data(everyone2, {}, collections.Counter(), NOW)["tokens"] == before
    assert u.summarize(everyone2, "2026-10-10")[3] == 9


# ---------- city data from fake repo histories ----------

MAP = {"aios": "owner/fake-site", "crm": "org/fake-ops"}


def history():
    return {"owner/fake-site": [at(1), at(3), at(40)],
            "org/fake-ops": [at(20, hour=23)],
            "owner/private-project": [at(2), at(29), at(31)],
            "owner/other-private": [at(5)],
            "owner/empty": []}


def test_city_data_landmarks_totals_and_one_locked_number():
    snapshots = {"owner/fake-site": {"TypeScript": 900, "CSS": 50}, "org/fake-ops": {}}
    value = u.city_data(history(), {"Python": 5000, "TypeScript": 900}, snapshots, MAP, 1760, NOW)
    assert value == {
        "generated_at": "2026-10-10T12:00:00Z",
        "totals": {"tokens": 1760, "commits": 8, "top_language": "Python"},
        "landmarks": {
            "aios": {"commits_total": 3, "commits_30d": 2, "pushed_this_week": True,
                     "last_push_date": at(1).astimezone().date().isoformat(), "language": "TypeScript"},
            "crm": {"commits_total": 1, "commits_30d": 1, "pushed_this_week": False,
                    "last_push_date": at(20, hour=23).astimezone().date().isoformat(), "language": None}},
        "locked": {"activity_30d": 3}}
    u.validate_upload("data/city.json", value, list(history()))
    with pytest.raises(SystemExit, match="landmark map: ka-ops"):
        u.city_data(history(), {}, {}, {**MAP, "ka-ops": "org/renamed-away"}, 0, NOW)


def test_missing_landmark_map_means_no_landmarks(tmp_path, monkeypatch):
    monkeypatch.setattr(u, "ROOT", str(tmp_path))
    assert u.load_landmarks() == {}
    value = u.city_data(history(), {}, {}, u.load_landmarks(), 0, NOW)
    assert value["landmarks"] == {} and value["locked"] == {"activity_30d": 6}
    assert value["totals"]["top_language"] is None
    (tmp_path / "landmarks.json").write_text(json.dumps({"blog": "owner/fake-site"}))
    with pytest.raises(SystemExit, match="landmark map"):
        u.load_landmarks()


def test_example_landmark_map_is_valid_and_fake():
    example = json.loads((pathlib.Path(__file__).resolve().parents[1] / "landmarks.example.json").read_text())
    assert set(example) == set(KEYS)
    assert all(v.startswith("example-owner/") for v in example.values())


def completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def test_city_repo_is_excluded_from_repo_list(monkeypatch):
    listed = [{"name": n, "isFork": False} for n in ("lstuek.github.io", "fake-site")]
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: completed(json.dumps(listed)))
    assert u.repos() == ["lstuek/fake-site", "lbstuek/fake-site"]


def test_full_repo_page_is_partial(monkeypatch):
    listed = [{"name": f"r{i}", "isFork": False} for i in range(200)]
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: completed(json.dumps(listed)))
    with pytest.raises(u.FetchError):
        u.repos()


@pytest.mark.parametrize("reply, expected", [
    (completed(stderr="gh: Git Repository is empty. (HTTP 409)", returncode=1), []),
    (completed('"2026-10-09T08:00:00Z"\n'), [dt.datetime(2026, 10, 9, 8, tzinfo=dt.timezone.utc)]),
    (completed(stderr="gh: API rate limit exceeded (HTTP 403)", returncode=1), u.FetchError),
    (completed('"2026-10-09T08:00:00Z"\n', returncode=1, stderr="HTTP 502 on page 2"), u.FetchError),
])
def test_empty_repo_is_zero_but_failed_or_partial_request_fails(monkeypatch, reply, expected):
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: reply)
    if expected is u.FetchError:
        with pytest.raises(u.FetchError):
            u.commit_history(["owner/fake-site"])
    else:
        assert u.commit_history(["owner/fake-site"]) == {"owner/fake-site": expected}


def fake_gh(fail=None):
    listed = json.dumps([{"name": "fake-site", "isFork": False}, {"name": "lstuek.github.io", "isFork": False}])
    def run(args, **kw):
        assert kw["creationflags"] == u.NO_WINDOW
        assert not any("lstuek.github.io" in a for a in args)
        if args[1:3] == ["repo", "list"]:
            return completed(listed if args[3] == "lstuek" else "[]")
        if "/commits" in " ".join(args):
            if fail:
                return completed('"2026-10-09T08:00:00Z"\n', returncode=1, stderr=fail)
            return completed('"2026-10-09T08:00:00Z"\n"2026-10-01T08:00:00Z"\n')
        return completed('{"TypeScript": 10}')
    return run


def run_main(tmp_path, monkeypatch, fail=None):
    monkeypatch.setattr(u, "ROOT", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "state"))
    monkeypatch.setattr(sys, "argv", ["update.py"])
    monkeypatch.setattr(u, "ASSETS", str(tmp_path / "assets"))
    monkeypatch.setattr(u, "scan_logs", lambda: {})
    monkeypatch.setattr(subprocess, "run", fake_gh(fail))
    u.main()


@pytest.mark.parametrize("fail", ["gh: API rate limit exceeded (HTTP 403)", "HTTP 502 on page 2"])
def test_failed_or_partial_request_keeps_previous_city_bytes(tmp_path, monkeypatch, fail):
    (tmp_path / "README.md").write_text("<!--AI:START--><!--AI:END--><!--UPDATED:START--><!--UPDATED:END-->")
    (tmp_path / "landmarks.json").write_text(json.dumps({"portfolio": "lstuek/fake-site"}))
    run_main(tmp_path, monkeypatch)
    path = tmp_path / "data/city.json"
    first = json.loads(path.read_text())
    assert first["landmarks"]["portfolio"]["commits_total"] == 2
    assert first["totals"]["commits"] == 2 and first["locked"] == {"activity_30d": 0}
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(SystemExit, match="fetch failed"):
        run_main(tmp_path, monkeypatch, fail)
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_failed_language_request_keeps_previous_city_bytes(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("<!--AI:START--><!--AI:END--><!--UPDATED:START--><!--UPDATED:END-->")
    (tmp_path / "landmarks.json").write_text(json.dumps({"portfolio": "lstuek/fake-site"}))
    run_main(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    ok = fake_gh()
    def run(args, **kw):
        if "/languages" in " ".join(args):
            return completed("", returncode=1, stderr="HTTP 502")
        return ok(args, **kw)
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(SystemExit, match="fetch failed"):
        u.main()
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
