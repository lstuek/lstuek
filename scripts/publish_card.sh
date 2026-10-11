#!/usr/bin/env bash
set -euo pipefail

git config user.name 'github-actions[bot]'
git config user.email '41898283+github-actions[bot]@users.noreply.github.com'

for attempt in 1 2 3 4; do
    echo "Profile card attempt ${attempt}/4"
    git fetch origin main
    git reset --hard origin/main
    python scripts/card.py
    git add assets/card.svg
    if git diff --cached --quiet -- assets/card.svg; then
        echo 'Profile card unchanged'
        exit 0
    fi

    timestamp=$(date +%s)
    python - "$timestamp" <<'PY'
import pathlib
import re
import sys

readme = pathlib.Path("README.md")
text = readme.read_text(encoding="utf-8")
text, count = re.subn(
    r'(https://raw\.githubusercontent\.com/lstuek/lstuek/main/assets/card\.svg\?t=)\d+',
    lambda match: match[1] + sys.argv[1],
    text,
)
if count != 1:
    raise SystemExit("Expected exactly one profile card URL in README.md")
readme.write_text(text, encoding="utf-8", newline="\n")
PY
    git add README.md
    GIT_AUTHOR_DATE="@$timestamp +0000" GIT_COMMITTER_DATE="@$timestamp +0000" \
        git commit -m 'Update profile card'
    if git push origin HEAD:main; then
        exit 0
    fi
    echo "Push rejected on attempt ${attempt}; next attempt renders current main" >&2
done

echo 'Profile card publish failed after 4 rejected pushes' >&2
exit 1
