# PLAN: lstuek profile card

Now: the card is live (PR #8 merged 2026-10-10, 2a0c803), shorter (985 px) with slow idle motion since PR #9 (74ca635; spec 19-20). Actions draws `assets/card.svg` every 6 h and after each PC upload. The PC task runs `update.py --upload` (re-registered 2026-10-10). Open: #7 rest of the cutover.
- #7 left: remove the legacy SVG and README code from update.py; archive assets/commits.svg, languages.svg and streak.svg to archive/<date>-old-svgs/. Code task, goes to a Codex worker.
- Unproven: the rejected-push retry on GitHub itself. The live race on 2026-10-10 did not collide (the dispatched run rendered before the upload landed and found the card unchanged); the retry is proven only against a local bare remote (tests/test_publish.py).
- Unproven: no window at the 00:00 run in upload mode.
- Unproven: reduced motion inside an `<img>`. Headless Chromium's emulated setting did not reach the image (the ring kept moving); the SVG opened as a document had 0 running animations. A real OS setting is untested.
- Known: the top-line time on the card is the PC upload time from data/pc.json, not the render time.
- Languages weight per repo, not per byte, until the language snapshot covers all repos (A9).

## Lincoln queue
- 2026-10-10: tell Claude if a window shows at a scheduled run (the 18:00 old-mode run passed with exit 0; 00:00 is the first upload-mode run).
- 2026-10-10: look at the live card on github.com/lstuek, motion included, and say what to tweak (spec decisions 18-20).
