# PLAN: lstuek profile card

Now: PRD slice 1 ([ref/prd.md](ref/prd.md)) revised after the Codex audit (10 findings, all taken); waiting on Lincoln's approval.
- Known wrong today: the live card double-counts Codex tokens (audit A3) and weights languages per repo, not per byte (A9). Fixed in PRD task 1.

## State (2026-10-10)
- The old updater works again: the clone moved from the deleted branch `agent/gitleaks-cli-2026-09-29` to `main` and into aios; task `lstuek-profile` re-registered at the new path. A local run without push passed (exit 0, 16 repos, 1,532 commits, Codex 33.7M tokens).
- Unproven: no window at the next scheduled run (18:00), and its push.
- Known broken: `scripts/test_update.py` fails with IndexError in the privacy-guard case. Hypothesis: a name in the test list has no `/`. Next test: run the case alone. Fixed in PRD task 1.

## Lincoln queue
- 2026-10-10: turn on "Include private contributions on my profile" at github.com/settings/profile (ref/spec.md decision 5).
- 2026-10-10: tell Claude if a window shows at the 18:00 run (State above).
