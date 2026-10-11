# PLAN: lstuek profile card

Now: slice 1 approved 2026-10-10. Done: #3 (PC upload, branch agent/3-pc-upload, 19 tests pass, real dry run 18.4B tokens), #4 (stack list, branch agent/4-stack). Running: #5 card (design). Done: #2 probe passed 2026-10-10 (Actions GITHUB_TOKEN: total 2,120, restricted 2,071; Oct 9 = 211 on both tokens), so the cloud reads contributions and UPLOAD_CONTRIBUTIONS stays False. Waiting: #6 cloud runner, #7 cutover.
- Known wrong on the live card until cutover: Codex tokens undercounted about 4x (summed last_token_usage gave 2.34B; total_token_usage advances give 9.79B on this PC, checked by an independent script). Audit A3 said "double count"; the measured direction is an undercount. Languages weight per repo, not per byte (A9).

## State (2026-10-10)
- The old updater works again: the clone moved from the deleted branch `agent/gitleaks-cli-2026-09-29` to `main` and into aios; task `lstuek-profile` re-registered at the new path. A local run without push passed (exit 0, 16 repos, 1,532 commits, Codex 33.7M tokens).
- Unproven: no window at the next scheduled run (18:00), and its push.
- Known broken: `scripts/test_update.py` fails with IndexError in the privacy-guard case. Hypothesis: a name in the test list has no `/`. Next test: run the case alone. Fixed in PRD task 1.

## Lincoln queue
- 2026-10-10: tell Claude if a window shows at the 18:00 run (State above).
