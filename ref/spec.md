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
| 11 | (2026-10-10, after the first preview) Two themes: light = cream background, grey text, navy accents; dark = black background, white text, sky-blue accents. The README serves the dark one to dark-mode visitors (`<picture>` with `prefers-color-scheme`). Replaces the orange print look. |
| 12 | Softer fonts than the first preview's high-contrast serif; Lincoln picks from a rendered board. |
| 13 | The open-source panel becomes "Shipped": live public sites Lincoln built, from a hand-kept list `data/shipped.json`. Replaces decision 7. Lincoln checks with partners before naming their sites. |
| 15 | (2026-10-10, after the font board) Dark only: black background, white and grey text; decision 11's light card is dropped. Letters in Young Serif (name, headings), every number in Nunito's lining figures, small text in Figtree. Cyan marks only what matters: core stack tools (`"core": true` in data/stack.json: TypeScript, Python, React, Claude Code, Codex, Supabase, Vercel), the current streak, and the token bar. Everything else is white or grey. |
| 16 | (2026-10-10, ship approval) Cyan only on: lifetime contributions number, the 3 highest bars of the 31 days, the Shipped count and bullets. Stack has no accents (no core flag); token bar and streak bar white; the "≈ N billion tokens" line is removed. Replaces decision 15's cyan list. |
| 17 | (2026-10-10) Token bar cyan again; the top language bar and the streak bar cyan with tick marks like the token bar; the token count uses a sharper font than Nunito (Lincoln picks from a strip). Ship after Lincoln approves the render. Amends decision 16. |
| 18 | (2026-10-10, token font strip) Every number on the card uses Archivo, not Nunito (the token count included). The small grey labels beside panel titles ("23 tools", "1,777 in the last 31 days") use Figtree uppercase with letter spacing, grey, numbers in Archivo (option a; Lincoln shipped it as shown and tweaks it live). Amends decisions 15 and 17. |
| 14 | Stack drops Next.js, Astro, Express, Drizzle, Docker and shadcn/ui (23 tools). |

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
