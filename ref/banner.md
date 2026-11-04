# Spec: City banner (looping video on the GitHub profile)

Decisions by Lincoln, 2026-11-02 and 2026-11-03 (record: aios plans/2026-10-27-commit-city/pivot-video.md; models: model-shortlist.md there). Revised after a Codex review and a design audit (both "revise"), 2026-11-03.

## Problem Statement

Lincoln wants his GitHub profile to show his work as a night, rainy cyberpunk city. A 3D page cannot run on github.com: a profile shows only pictures and text, so the interactive Commit City (archived as lstuek/commit-city-3d) never reached the profile. Today the profile is one stats card image. He wants something more striking that still shows his real numbers and projects, on the profile itself.

## Solution

A 12-second looping banner of a night city street in rain, rendered in Blender, shown at the top of the profile README as an animated image. The camera stays still while the scene lives: rain, steam, flickering neon, a passing car and a drone. Two neon signs show his all-time AI tokens and total commits. Holograms name three projects (Portfolio, Bionic Wave, KA Tech). A billboard cycles seven project names in large type. Once per loop a scan line sweeps the city into a cyan wireframe and back. Under the banner, plain text lists the seven projects with Lincoln's lines, plus a credits link. Every night the PC job writes fresh numbers onto the signs in seconds. The banner links to lincolnstuek.com. The stats card stays until Lincoln approves the finished banner.

## User Stories

1. As a profile visitor, I want a moving night city at the top of the profile that plays and loops by itself, so that the profile stands out at first glance.
2. As a profile visitor, I want the loop to repeat with no visible jump, so that it feels like a window onto a living street.
3. As a profile visitor, I want rain, wet reflections, steam, flickering neon, a passing car and a drone, so that the street feels real and alive.
4. As a profile visitor, I want to read Lincoln's all-time AI tokens and total commits on neon signs, so that I see how much he builds and ships.
5. As a profile visitor, I want holograms naming Portfolio, Bionic Wave and KA Tech, and a billboard cycling seven project names, so that I see what he works on.
6. As a profile visitor, I want a short wireframe scan once per loop, so that the city shows its digital side.
7. As a profile visitor on a phone, I want every number and name readable when the banner shrinks, so that it still means something there.
8. As a profile visitor, I want each project's one-line description as text under the banner, so that I can read every word at my own pace.
9. As a profile visitor, I want a click on the banner to take me to lincolnstuek.com, so that I can see his work and offers.
10. As a profile visitor, I want the banner to load quickly and never flash harshly, so that the profile is comfortable to open.
11. As a profile visitor using a screen reader, I want alt text with the numbers and project names, so that the banner's content reaches me.
12. As Lincoln, I want the numbers updated every night in seconds, so that the banner is never stale and my PC is not tied up.
13. As Lincoln, I want the token number to count Claude and Codex, all time, so that it shows my full usage.
14. As Lincoln, I want my approved lines used word for word and New Era left out, so that nothing public is put in my mouth.
15. As Lincoln, I want no unapproved names or private numbers in the banner, its text or its file data, so that nothing private leaks.
16. As Lincoln, I want to judge rendered stills before the full loop is made, so that a weak look is caught early.
17. As Lincoln, I want the scene built from artist-made models with every model credited, so that it looks real and the licenses are respected.
18. As Lincoln, I want a failed nightly run to keep yesterday's banner working, so that the profile never shows a broken image.
19. As Lincoln, I want the profile repo to stay small, so that nightly banners do not bloat its history.
20. As Lincoln, I want the stats card kept until the banner is approved, and its automation retired cleanly after, so that the profile is never empty and two jobs never fight over the README.
21. As Lincoln, I want a later upgrade path to a full nightly re-render, so that the numbers can one day get real reflections and rain on them.

Build and test decisions: [banner-build.md](banner-build.md).

## Out of Scope

Interaction on the profile (hover, clickable buildings, camera control); sound; New Era; per-repo numbers for private repos; the card's other stats (tool stack, contributions, streaks, languages); the archived 3D site; a full nightly 3D re-render.

## Further Notes

- Lincoln downloads the six models with his Sketchfab login; licenses come from the Sketchfab API and are checked again on download.
- Unknown until the playback proof: GitHub's image proxy size limit and cache time, iOS Safari and the GitHub app with 288 large frames, and whether a reduced-motion still can be served (the README sanitizer may strip it).
- Look references: brief.md "Look references" and its refs folder.
