"""Exercise the real shell loop with only local bare Git remotes."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
README = '<img src="https://raw.githubusercontent.com/lstuek/lstuek/main/assets/card.svg?t=123" />\n'

# The renderer reads the checkout's data. A post-commit hook invokes its second
# mode to land a competing upload strictly between render/commit and push.
RENDERER = '''import json
import os
from pathlib import Path
import subprocess
import sys

def git(*args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "-C", os.environ["RIVAL"], *args], env=env,
                   check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

state = Path(os.environ["RACE_STATE"])
if len(sys.argv) > 1:
    left = int(state.read_text())
    if left:
        rival = Path(os.environ["RIVAL"])
        git("pull", "--ff-only", "origin", "main")
        data = rival / "data/pc.json"
        value = json.loads(data.read_text())["value"] + 1
        data.write_text(json.dumps({"value": value}))
        git("add", "data/pc.json")
        git("commit", "-m", "Competing upload")
        git("push", "origin", "HEAD:main")
        state.write_text(str(left - 1))
else:
    value = json.loads(Path("data/pc.json").read_text())["value"]
    with Path(os.environ["RENDER_LOG"]).open("a") as log:
        log.write(str(value) + "\\n")
    if os.environ.get("FAIL_RENDER"):
        raise SystemExit(7)
    Path("assets").mkdir(exist_ok=True)
    Path("assets/card.svg").write_text("<svg>" + str(value) + "</svg>\\n")
'''


def run(args, cwd, env=None, check=True):
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True,
                            text=True, timeout=60, creationflags=NO_WINDOW)
    if check:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


def git(cwd, *args):
    return run(["git", *args], cwd).stdout.strip()


@pytest.fixture
def local_repo(tmp_path):
    remote = tmp_path / "remote.git"
    publisher = tmp_path / "publisher"
    rival = tmp_path / "rival"
    git(tmp_path, "init", "--bare", "--initial-branch=main", str(remote))
    git(tmp_path, "clone", str(remote), str(publisher))
    git(publisher, "config", "user.name", "Fixture")
    git(publisher, "config", "user.email", "fixture@example.invalid")
    (publisher / "data").mkdir()
    (publisher / "scripts").mkdir()
    (publisher / "data/pc.json").write_text(json.dumps({"value": 1}))
    (publisher / "README.md").write_text(README)
    (publisher / "scripts/card.py").write_text(RENDERER)
    shutil.copyfile(ROOT / "scripts/publish_card.sh", publisher / "scripts/publish_card.sh")
    git(publisher, "add", ".")
    git(publisher, "commit", "-m", "Fixture")
    git(publisher, "push", "origin", "HEAD:main")
    git(tmp_path, "clone", str(remote), str(rival))
    git(rival, "config", "user.name", "Uploader")
    git(rival, "config", "user.email", "uploader@example.invalid")
    state = tmp_path / "race-state"
    state.write_text("0")
    log = tmp_path / "renders"
    env = os.environ.copy()
    # Make `python` resolve to the interpreter running pytest on every platform.
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env["PATH"]
    env.update(RIVAL=rival.as_posix(), RACE_STATE=state.as_posix(),
               RENDER_LOG=log.as_posix(), RACE_RENDERER=(publisher / "scripts/card.py").as_posix())
    hook = publisher / ".git/hooks/post-commit"
    hook.write_text('#!/usr/bin/env bash\npython "$RACE_RENDERER" --compete\n', newline="\n")
    hook.chmod(0o755)
    return publisher, remote, state, log, env


def publish(repo):
    publisher, _, _, _, env = repo
    bash = shutil.which("bash")
    assert bash, "bash is required to verify publish_card.sh"
    return run([bash, "scripts/publish_card.sh"], publisher, env, check=False)


def assert_published_cards_match_data(remote):
    commits = git(remote, "log", "main", "--format=%H", "--grep=^Update profile card$").splitlines()
    assert commits
    for commit in commits:
        value = json.loads(git(remote, "show", f"{commit}:data/pc.json"))["value"]
        assert git(remote, "show", f"{commit}:assets/card.svg") == f"<svg>{value}</svg>"
        readme = git(remote, "show", f"{commit}:README.md")
        stamp = git(remote, "show", "-s", "--format=%ct", commit)
        assert re.search(r"card\.svg\?t=(\d+)", readme)[1] == stamp
        assert git(remote, "show", "-s", "--format=%an|%ae", commit) == (
            "github-actions[bot]|41898283+github-actions[bot]@users.noreply.github.com"
        )
    return commits


def test_competing_upload_forces_fetch_and_fresh_render(local_repo):
    _, remote, state, log, _ = local_repo
    state.write_text("1")
    result = publish(local_repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert log.read_text().splitlines() == ["1", "2"]
    assert len(assert_published_cards_match_data(remote)) == 1
    assert json.loads(git(remote, "show", "main:data/pc.json"))["value"] == 2
    assert "Push rejected on attempt 1" in result.stderr


def test_four_rejections_fail_without_publishing_stale_card(local_repo):
    _, remote, state, log, _ = local_repo
    state.write_text("4")
    result = publish(local_repo)
    assert result.returncode != 0
    assert log.read_text().splitlines() == ["1", "2", "3", "4"]
    assert state.read_text() == "0"
    assert "failed after 4 rejected pushes" in result.stderr
    assert git(remote, "log", "main", "--format=%H", "--grep=^Update profile card$") == ""
    assert json.loads(git(remote, "show", "main:data/pc.json"))["value"] == 5


def test_untracked_card_is_committed(local_repo):
    publisher, remote, _, log, _ = local_repo
    assert not (publisher / "assets/card.svg").exists()
    result = publish(local_repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert log.read_text().splitlines() == ["1"]
    assert len(assert_published_cards_match_data(remote)) == 1
    assert git(remote, "diff-tree", "--no-commit-id", "--name-only", "-r", "main").splitlines() == [
        "README.md", "assets/card.svg"
    ]


def test_unchanged_card_makes_no_commit(local_repo):
    assert publish(local_repo).returncode == 0
    _, remote, _, log, _ = local_repo
    before = git(remote, "rev-parse", "main")
    result = publish(local_repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Profile card unchanged" in result.stdout
    assert git(remote, "rev-parse", "main") == before
    assert log.read_text().splitlines() == ["1", "1"]
    assert len(assert_published_cards_match_data(remote)) == 1


def test_failed_render_does_not_commit_or_push(local_repo):
    _, remote, _, _, env = local_repo
    before = git(remote, "rev-parse", "main")
    env["FAIL_RENDER"] = "1"
    result = publish(local_repo)
    assert result.returncode == 7
    assert git(remote, "rev-parse", "main") == before
