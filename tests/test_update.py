import collections
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

import update as u

NOW = dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)
KEY = "a" * 12


def record(tokens, day="2026-10-10", family="GPT (Codex)"):
    return {"prompts": {}, "usage": {day: {family: [tokens, 0]}}}


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def event(kind, payload):
    return {"timestamp": "2026-10-10T12:00:00Z", "type": kind, "payload": payload}


def token(i, o):
    return event("event_msg", {"type": "token_count", "info": {
        "total_token_usage": {"input_tokens": i, "output_tokens": o},
        "last_token_usage": {"input_tokens": 999, "output_tokens": 999}}})


@pytest.mark.parametrize("pairs, expected", [([(100, 10), (100, 10), (150, 15), (20, 2), (30, 3)], 198),
                                           ([(100, 10), (100, 10), (160, 16)], 176)])
def test_codex_snapshots_reset_and_resumed_exec(tmp_path, monkeypatch, pairs, expected):
    monkeypatch.setattr(u, "HOME", str(tmp_path))
    path = tmp_path / ".codex/sessions/rollout-exec.jsonl"
    rows = [event("session_meta", {"id": "exec"}), event("turn_context", {"model": "gpt-6.1-sol"})]
    for pair in pairs:
        rows += [event("event_msg", {"type": "task_started"}), token(*pair)]
    jsonl(path, rows)
    assert u.summarize(u.scan_logs(), "")[4]["GPT (Codex)"] == expected


def test_claude_last_usage_and_request_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(u, "HOME", str(tmp_path))
    rows = []
    for output in [1, 5]:
        rows.append({"timestamp": "2026-10-10T12:00:00Z", "type": "assistant", "requestId": "r1",
                     "message": {"id": "m1", "model": "claude-opus-5", "usage": {
                         "input_tokens": 10, "cache_creation_input_tokens": 20,
                         "cache_read_input_tokens": 30, "output_tokens": output}}})
    jsonl(tmp_path / ".claude/projects/project/session.jsonl", rows)
    scanned = u.scan_logs()
    assert u.summarize(scanned, "")[:2] == (60, 5)
    rows.append({**rows[-1], "requestId": "r2"})
    jsonl(tmp_path / ".claude/projects/project/session.jsonl", rows)
    assert u.summarize(u.scan_logs(), "")[:2] == (120, 10)


def test_rebuild_overrides_every_ledger_and_pruned_is_uncertain(capsys):
    pruned = "b" * 12
    stored = {"mine": {KEY: record(100)}, "second": {KEY: record(100), pruned: record(7)}}
    ledgers, merged, uncertain = u.rebuild_ledgers(stored, {KEY: record(60)}, "mine")
    assert ledgers["mine"][KEY] == ledgers["second"][KEY] == record(60)
    assert u.summarize(merged, "")[4]["GPT (Codex)"] == 67
    assert merged[pruned] == record(7)
    assert uncertain == 7


def test_lifetime_since_and_empty():
    sessions = {KEY: record(100, "2025-08-01"), "b" * 12: record(60, "2026-10-10", "Opus")}
    assert u.pc_data(sessions, {}, collections.Counter(), NOW)["tokens"] == {
        "total": 160, "codex": 100, "claude": 60, "since": "2025-08"}
    assert u.pc_data({}, {}, collections.Counter(), NOW)["tokens"] == {
        "total": 0, "codex": 0, "claude": 0, "since": None}


def test_language_bytes_and_failed_repo_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    replies = {"repos/owner/big/languages": ['{"Python":1000}'], "repos/owner/small/languages": ['{"TypeScript":10}']}
    monkeypatch.setattr(u, "gh_lines", lambda *args: replies[args[-1]])
    shares = dict(u.language_shares(["owner/big", "owner/small"]))
    assert [round(100 * shares[k], 1) for k in ("Python", "TypeScript")] == [99.0, 1.0]
    replies["repos/owner/big/languages"] = []
    replies["repos/owner/small/languages"] = ['{"TypeScript":20}']
    assert u.language_bytes(["owner/big", "owner/small"]) == {"Python": 1000, "TypeScript": 20}
    assert json.loads((tmp_path / "lstuek-profile/languages.json").read_text())["owner/big"] == {"Python": 1000}


@pytest.mark.parametrize("enabled", [False, True])
def test_contributions_flag_and_window(monkeypatch, enabled):
    monkeypatch.setattr(u, "UPLOAD_CONTRIBUTIONS", enabled)
    counts = collections.Counter({NOW.date(): 3, NOW.date() - dt.timedelta(days=364): 2,
                                  NOW.date() - dt.timedelta(days=365): 9})
    pc = u.pc_data({}, {}, counts, NOW)
    assert ("contributions" in pc) == enabled
    if enabled:
        assert len(pc["contributions"]) == 365
        assert sum(pc["contributions"].values()) == 5
    u.validate_upload("data/pc.json", pc, [])


@pytest.mark.parametrize("days, expected", [([1, 2, 3, 10, 11], (3, 3)), ([0, 1], (2, 2)), ([5], (0, 1)), ([], (0, 0))])
def test_streaks(days, expected):
    today = dt.date(2026, 9, 22)
    assert u.streaks({today - dt.timedelta(days=n) for n in days}, today) == expected


def test_legacy_family_merge_summarize_privacy():
    assert u.family("claude-opus-5-5") == "Opus"
    assert u.family("gpt-6-astra") == "GPT (Codex)"
    assert u.family("<synthetic>") is None
    with pytest.raises(SystemExit):
        u.check_private(["built for ka-tech"], ["ka-tech"])
    u.check_private(["lifelong learner"], ["life"])
    small = {"usage": {"2026-09-20": {"Opus": [10, 1]}}, "prompts": {"2026-09-20T14": 1}}
    big = {"usage": {"2026-09-20": {"Opus": [50, 5]}}, "prompts": {"2026-09-20T14": 3}}
    old = {"usage": {"2026-09-01": {"Fable": [100, 10]}}, "prompts": {"2026-09-01T09": 2}}
    assert u.merge({"a": small}, {"a": big, "b": small}) == {"a": big, "b": small}
    tin, tout, sess, prompts, models, times = u.summarize({"a": big, "o": old}, "2026-09-16")
    assert (tin, tout, sess, prompts, models["Opus"], models["Fable"], len(times)) == (50, 5, 1, 3, 55, 0, 5)


def run_git(path, *args, check=True):
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True,
                          creationflags=u.NO_WINDOW, check=check)


@pytest.fixture
def remote(tmp_path, monkeypatch):
    bare, local, other = [tmp_path / n for n in ("remote.git", "local", "other")]
    bare.mkdir()
    run_git(bare, "init", "--bare", "--initial-branch=main")
    run_git(tmp_path, "clone", str(bare), str(local))
    for repo in [local]:
        run_git(repo, "config", "user.email", "test@example.invalid")
        run_git(repo, "config", "user.name", "Test")
    (local / "seed.txt").write_text("base\n")
    run_git(local, "add", "seed.txt")
    run_git(local, "commit", "-m", "base")
    run_git(local, "push", "-u", "origin", "main")
    run_git(tmp_path, "clone", str(bare), str(other))
    run_git(other, "config", "user.email", "test@example.invalid")
    run_git(other, "config", "user.name", "Test")
    monkeypatch.setattr(u, "ROOT", str(local))
    return bare, local, other


def commit_file(local, name="data/ai-abc.json", content=None):
    path = local / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if content is not None else json.dumps({KEY: record(60)}), encoding="utf-8")
    run_git(local, "add", "--", name)
    run_git(local, "commit", "-m", "ledger")
    return run_git(local, "rev-parse", "HEAD").stdout.strip()


def test_privacy_staged_blob_not_worktree(remote):
    _, local, _ = remote
    path = local / "data/pc.json"
    path.parent.mkdir()
    path.write_text(json.dumps(u.pc_data({}, {"Python": 1000}, collections.Counter(), NOW)))
    ledger = local / "data/ai-def.json"
    ledger.write_text(json.dumps({KEY: record(60)}))
    run_git(local, "add", "data")
    u.validate_staged(["owner/private-project"])
    ledger.write_text(json.dumps({KEY: record(60, family="Opus")}))
    run_git(local, "add", "data/ai-def.json")
    with pytest.raises(SystemExit, match="repo name"):
        u.validate_staged(["owner/Opus"])
    # The second ledger's staged blob leaks, even when the worktree is clean.
    bad = record(60)
    bad["usage"]["2026-10-10"]["private-project"] = [1, 0]
    ledger.write_text(json.dumps({KEY: bad}))
    run_git(local, "add", "data/ai-def.json")
    ledger.write_text(json.dumps({KEY: record(60)}))
    with pytest.raises(SystemExit, match="privacy"):
        u.validate_staged(["owner/private-project"])
    run_git(local, "add", "data/ai-def.json")
    (local / "extra.txt").write_text("extra")
    run_git(local, "add", "extra.txt")
    with pytest.raises(SystemExit, match="unexpected staged path"):
        u.validate_staged([])


def rejecting_hook(bare, once=False):
    run_git(bare, "config", "core.hooksPath", str(bare / "hooks"))
    hook = bare / "hooks/pre-receive"
    hook.write_text('#!/bin/sh\n' + ('if [ ! -f rejected ]; then touch rejected; exit 1; fi\nexit 0\n' if once else 'echo rejected >&2\nexit 1\n'), encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    return hook


def test_push_rejected_then_success(remote, capsys):
    bare, local, _ = remote
    rejecting_hook(bare, once=True)
    head = commit_file(local)
    assert u.push_retained()
    assert run_git(bare, "rev-parse", "main").stdout.strip() == head
    assert capsys.readouterr().out.count("push attempt") == 1


def test_four_failures_keep_commit_then_no_change_run_pushes(remote, capsys, monkeypatch):
    bare, local, _ = remote
    hook = rejecting_hook(bare)
    head = commit_file(local)
    calls = []
    original = u.git
    def observed(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(u, "git", observed)
    assert not u.push_retained()
    assert calls == [("pull", "--rebase", "--autostash"), ("push",)] * 4
    assert capsys.readouterr().out.count("push attempt") == 4
    assert run_git(local, "rev-parse", "HEAD").stdout.strip() == head
    assert run_git(local, "status", "--porcelain").stdout == ""
    hook.unlink()
    assert u.push_retained()
    assert run_git(bare, "rev-parse", "main").stdout.strip() == head


def test_failed_rebase_aborts_and_keeps_commit(remote):
    bare, local, other = remote
    head = commit_file(local, "seed.txt", "local change\n")
    commit_file(other, "seed.txt", "remote change\n")
    run_git(other, "push")
    assert not u.push_retained()
    assert run_git(local, "rev-parse", "HEAD").stdout.strip() == head
    assert not (local / ".git/rebase-merge").exists()
    assert not (local / ".git/rebase-apply").exists()
    assert (local / "seed.txt").read_text() == "local change\n"


def test_main_dry_run_writes_nothing_and_prints_uncertain(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(u, "ROOT", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "state"))
    monkeypatch.setattr(sys, "argv", ["update.py", "--dry-run", "--push"])
    monkeypatch.setattr(u, "repos", lambda: ["owner/private-project"])
    monkeypatch.setattr(u, "commit_times", lambda names: [])
    monkeypatch.setattr(u, "gh_lines", lambda *args: ['{"Python":1000}'])
    monkeypatch.setattr(u, "scan_logs", lambda: {})
    data = tmp_path / "data"
    data.mkdir()
    (data / "ai-abc.json").write_text(json.dumps({KEY: record(7)}))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    u.main()
    after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after
    out = capsys.readouterr().out
    assert out.startswith("uncertain: 7\n")
    assert json.loads(out.split("\n", 1)[1])["tokens"]["codex"] == 7


def test_all_subprocess_entry_points_hide_windows(monkeypatch):
    calls = []
    def run(*args, **kwargs):
        calls.append(kwargs)
        assert kwargs["creationflags"] == u.NO_WINDOW
        return subprocess.CompletedProcess(args[0], 0, stdout="{}", stderr="")
    monkeypatch.setattr(subprocess, "run", run)
    u.gh_lines("api", "example")
    u.git("status")
    u.git_text("status")
    assert len(calls) == 3
