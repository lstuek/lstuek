# lstuek: GitHub profile card

Lincoln's GitHub profile (github.com/lstuek). README.md is the profile page itself. Decisions: [ref/spec.md](ref/spec.md). State: [PLAN.md](PLAN.md). Rules for all of personal: ../../index.md.

gate: `python -m pytest tests -q`
Map: read `index.md` first; `node ~/.claude/infra/index.mjs <repo root>` writes it, never edit it by hand.

- The PC job is Task Scheduler task `lstuek-profile`, registered by `scripts/install-task.ps1` (pythonw.exe, every 6 h). Rerun the installer after the repo moves or the arguments change.
- Every child process the PC job starts uses `creationflags=NO_WINDOW`. A call without it flashes a window on Lincoln's screen (2026-10-10: an old branch without the flag).
- The clone stays on `main`. The job pulls and pushes main; a feature branch left checked out stops every run (2026-10-10: 13 failed runs on a deleted branch).
- Only aggregates leave the PC: no repo, project or client names. The privacy guard in update.py checks every file it writes.
- The job writes `data/city.json` for the Commit City page (lstuek/lstuek.github.io#2): totals, the 8 landmark keys, one locked-zone 30-day number. The key-to-repo map is `landmarks.json` (gitignored, local only; shape in `landmarks.example.json`); no file means no landmarks. A failed, rate-limited or partial GitHub request exits before any write, so the previous city data stays. lstuek.github.io is excluded from all counts.
- Uploaded AI ledgers hold prompt counts per day; per-hour detail stays in the local logs.
- Never: store a GitHub access key as a repo secret (spec decision 5), copy code from krishhgg/krishhgg (no license).

allow: data/ — ledger and aggregate files the job uploads
