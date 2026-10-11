# lstuek profile card: spec

Goal: one SVG card on github.com/lstuek in the layout of github.com/krishhgg (reference read 2026-10-10), in Lincoln's own style, that redraws itself on a schedule with no window on Lincoln's screen.

## Decisions (Lincoln 2026-10-10)
| # | Decision |
|---|---|
| 1 | Panels: header name, stack icons, contributions (31-day bars, total, current and best streak), languages by bytes, open source (merged PRs), token spend. No other panels: the model split and the time-of-day block are dropped. |
| 2 | Look: his panel grid, Lincoln's own font and colors (design realm). Not a copy of his look. |
| 3 | Header text: LINCOLN STUEK. |
| 4 | Runner is split like his: GitHub Actions draws the card every 6 h from public data; the PC job uploads only aggregates, and that upload starts a redraw. |
| 5 | Private data: Lincoln turns on "Include private contributions on my profile", so the public calendar carries his real daily counts. The PC job uploads language byte totals with the token totals. No access key is stored in the cloud. |
| 6 | Token spend: lifetime total of Claude Code and Codex tokens on this desktop, all logs on record, shown as "since <month year>". Codex `codex exec` workers count: they write rollouts to `~/.codex/sessions/` (checked 2026-10-10). |
| 7 | Open source: his rule, merged PRs to public repos with 50+ stars that Lincoln does not own. It shows 0 today (5 merged PRs, all to bionicwaveai/bionic-wave). |
| 8 | Stack: a hand-kept list. Claude drafts it from the repos' package files; Lincoln trims it once on the preview. |
| 9 | Home: personal/projects/lstuek (moved from C:\Users\Lincoln\lstuek 2026-10-10; task `lstuek-profile` re-registered there). |
| 10 | The PC job runs with pythonw.exe, and every child process uses CREATE_NO_WINDOW. |

## Constraints
- Only aggregates leave the PC: no repo, project or client names (update.py rule, kept).
- His repo has no license: we study it and write our own code; nothing is copied.
- The token ledger only grows: totals stay when Claude or Codex prune old logs.

## Assumptions (self-decided, shown to Lincoln once with the PRD)
- Token count = every token processed, cache reads included (Claude: input + cache write + cache read + output; Codex: input + output). This is how his 92B figure is counted.
- The existing per-machine ledger files `data/ai-<hash>.json` stay the ledger (per hashed session, per day, per model: [input, output]); the card total adds all of them. There are two today (`ai-93275191` is this desktop; `ai-15f99dc2` is an older machine), and its history counts toward the lifetime total.
- Languages include the `lbstuek` org's non-fork repos, as update.py does today.
- Redraw cadence: every 6 h plus on each PC upload.

## Open questions
| Item | What is unclear | Answer or assumption | State |
|---|---|---|---|
| Panels | which panels | all five of his, no extras | closed |
| Look | copy or own | own style, his layout | closed |
| Token source | which PCs | this desktop only | closed |
| Codex workers | are `codex exec` runs counted | yes, rollouts are in ~/.codex/sessions | closed |
| Home | folder | personal/projects/lstuek | closed |
| Runner | cloud or PC | split | closed |
| Private repos | how the cloud sees them | profile setting + PC upload | closed |
| PR panel | rule | 50+ stars, shows 0 today | closed |
| Name | header text | LINCOLN STUEK | closed |
| Stack | list source | Claude drafts, Lincoln trims | closed |
| Token number | lifetime or month | lifetime, all logs on record | closed |
