# PRD: profile card, slice 1

Decisions live in [spec.md](spec.md). This slice ships the whole card once, end to end. Revised 2026-10-10 after the Codex audit (thread 01a12847; audit findings 1-10 below as A1-A10).

## Scope
0. **Probe first (code).** Before any other task: with Lincoln's profile setting on, run the calendar query in a throwaway workflow with `GITHUB_TOKEN` and compare one known private-commit day against the PC count (A4). If the counts match, the cloud reads contributions. If they do not, the PC upload also carries daily contribution counts (`contributions` in the shape below) and the cloud never reads them.
1. **PC upload (code, Codex worker).** `scripts/update.py` gains `--upload` and `--dry-run`:
   - Writes `data/pc.json` (shape below). The ledger `data/ai-<hash>.json` files stay.
   - Privacy: validates every upload file against an allowlist schema before it is written; commits with an explicit path list (`data/pc.json`, `data/ai-*.json`) and refuses when other files are staged (A1).
   - Codex tokens: counted from advances of `total_token_usage`, with repeats and counter resets handled, not by summing `last_token_usage` (A3: the current code double-counts). Existing ledger entries are rebuilt from the logs still on disk; entries for pruned logs keep their old value and are listed as an uncertain amount in the run log.
   - Claude tokens: one record per message and request id, keeping the last usage, not the first (A8). Formula unchanged: input + cache write + cache read + output.
   - Ledgers merge by session hash, so a session in two ledger files counts once (A7).
   - Languages: raw bytes summed across repos, percent computed after; when a repo read fails, the previous snapshot stays (A9).
   - Push: bounded retry with `pull --rebase`; a failed push keeps the ledger commit (A2: today `reset --keep HEAD~1` drops it).
   - Tests in `tests/` that pytest collects, with exact numeric expected totals; the old `scripts/test_update.py` is replaced (A10).
2. **Stack list (design).** Claude drafts `data/stack.json` from package files across Lincoln's repos (tool names only); Lincoln trims it on the preview.
3. **Card drawer (design).** `scripts/card.py` reads `data/pc.json`, `data/stack.json` and public GitHub data, and writes `assets/card.svg`: header, stack, contributions, totals, languages, open source, token spend. Own style, his panel grid. Fonts are embedded or system-safe, so the SVG renders the same on github.com.
4. **Cloud runner (code, Codex worker).** `.github/workflows/card.yml`: cron every 6 h, on push to `data/pc.json`, and manual. `permissions: contents: write`, a bot commit identity, `concurrency` with no cancel (A6, A2). It renders from the newest main: fetch, render, commit `assets/card.svg` and the cache-busted README, and on a rejected push it fetches, renders again and retries up to 3 times (A2).
5. **Cutover (code).** The current `--push` updater keeps running until the cloud runner passes its check. Then `scripts/install-task.ps1` registers `--upload`, the installer runs again, and the old SVG and README code leaves update.py (A5).

## Out of scope
Laptop upload, model split, time-of-day block, light theme, animation in the SVG.

## Data shape: `data/pc.json` (aggregates only)
```json
{
  "updated": "2026-10-10T18:00:00Z",
  "tokens": { "total": 0, "claude": 0, "codex": 0, "since": "2025-08" },
  "languages": { "TypeScript": 0, "Python": 0 },
  "contributions": { "2026-10-10": 0 }
}
```
`contributions` exists only if task 0 fails. `since` is the first day in the merged ledger. Totals and streaks use the last 365 days of the calendar; the bar chart shows 31 days.

Public data read in the cloud: contribution calendar (only if task 0 passes), merged PRs (search `author:lstuek type:pr is:merged`, then repo stars >= 50 and owner not lstuek or lbstuek).

## Acceptance checks
| Check | Command | Pass |
|---|---|---|
| Probe | `gh workflow run probe.yml; gh run watch <id>` | the private-commit day count equals the PC count, or task 1 adds `contributions` |
| Unit tests | `python -m pytest tests -q` | all pass, with exact totals for: Codex repeated and reset counters, a resumed `codex exec` rollout, Claude repeated message with growing output, two ledgers sharing a session, languages 1,000 B vs 10 B gives 99%/1% |
| Privacy | `python scripts/update.py --dry-run` | known-good aggregate passes; a test file with a private repo name and an extra staged file both block |
| Card renders | `python scripts/card.py --offline tests/fixtures` then a headless screenshot at 855 px | values on the card equal the fixture values; look is unproven until Lincoln sees it |
| Cloud run | `gh workflow run card.yml`, then `gh run watch <that run id>` | success, a new `assets/card.svg` commit on main rendered from that commit's `data/pc.json` |
| Race | push a `data/pc.json` change while a cloud run is mid-render | the final card shows the second upload's values |
| Cutover | `schtasks /query /tn lstuek-profile /v /fo list` after a fresh scheduled run | runs `pythonw.exe ... --upload`, a new log entry with exit 0, and a cloud run started by that upload |
| No window | the next scheduled run | Lincoln sees no window (only he can prove this) |

## Tasks (one issue each)
0. code: contributions probe.
1. code: PC upload + tests.
2. design: stack list draft.
3. design: card drawer + README, after 1 and 2.
4. code: cloud runner, after 3.
5. code: cutover, after 4 passes.

## Audit findings
All 10 taken. None dropped. A7 kept Lincoln's "all logs on record" choice and solved the double count with the session-hash merge.
