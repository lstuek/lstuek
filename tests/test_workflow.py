"""Static checks of the deliberately small YAML and its publish script (stdlib only)."""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/card.yml"
PUBLISH = ROOT / "scripts/publish_card.sh"


def block(text, name, indent=0):
    """Read a block by indentation; not a general YAML parser."""
    lines = text.splitlines()
    start = lines.index(" " * indent + name + ":") + 1
    result = []
    for line in lines[start:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        result.append(line)
    return "\n".join(result)


def test_workflow_triggers_and_paths():
    text = WORKFLOW.read_text()
    triggers = block(text, "on")
    assert re.findall(r"^  (\w+):", triggers, re.M) == [
        "schedule", "push", "workflow_dispatch"
    ]
    assert block(triggers, "schedule", 2).strip() == '- cron: "0 */6 * * *"'
    push = block(triggers, "push", 2)
    assert "    branches: [main]" in push
    assert re.findall(r"^      - (.+)$", block(push, "paths", 4), re.M) == [
        "data/pc.json", "data/stack.json", "data/shipped.json", "scripts/card.py"
    ]


def test_workflow_permissions_concurrency_and_token():
    text = WORKFLOW.read_text()
    assert block(text, "permissions").strip() == "contents: write"
    assert block(text, "concurrency").strip().splitlines() == [
        "group: card", "  cancel-in-progress: false"
    ]
    assert "secrets." not in text
    assert "runs-on: ubuntu-latest" in text
    assert "uses: actions/checkout@v4\n        with:\n          fetch-depth: 0" in text
    assert 'uses: actions/setup-python@v5\n        with:\n          python-version: "3.12"' in text
    assert "        env:\n          GH_TOKEN: ${{ github.token }}\n        run: bash scripts/publish_card.sh" in text


def test_publish_bound_and_render_order():
    text = PUBLISH.read_text()
    loop = text.split("for attempt in 1 2 3 4; do\n", 1)[1].split("\ndone", 1)[0]
    commands = ["git fetch origin main", "git reset --hard origin/main",
                "python scripts/card.py", "git add assets/card.svg",
                "git diff --cached --quiet -- assets/card.svg", "git commit", "git push origin HEAD:main"]
    offsets = [loop.index(command) for command in commands]
    assert offsets == sorted(offsets)
    assert text.count("python scripts/card.py") == 1
    assert "github-actions[bot]" in text
    assert "41898283+github-actions[bot]@users.noreply.github.com" in text
    assert text.rstrip().endswith("exit 1")
