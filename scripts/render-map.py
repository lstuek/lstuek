"""Re-render assets/stack-map.svg from assets/stack-map.mmd (run after editing the map).
GitHub's live Mermaid can fail on mindmaps, so the profile embeds a pre-rendered image."""
import html, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROWSER = sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
BRANCH = ["#3178c6", "#8e5cd9", "#2f6f5e", "#b0572f"]  # one color per top-level branch
theme = {"fontFamily": "Segoe UI, Ubuntu, sans-serif", "primaryColor": "#6e40c9", "primaryTextColor": "#ffffff"}
for i, c in enumerate(BRANCH * 3):
    theme[f"cScale{i}"], theme[f"cScaleLabel{i}"] = c, "#ffffff"

src = open(os.path.join(ROOT, "assets", "stack-map.mmd"), encoding="utf-8").read()
page = f"""<!doctype html><meta charset="utf-8"><pre class="mermaid">{html.escape(src)}</pre>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{startOnLoad:true,theme:"base",htmlLabels:false,themeVariables:{theme}}})</script>"""
with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
    f.write(page)
dom = subprocess.run([BROWSER, "--headless=new", "--disable-gpu", "--virtual-time-budget=10000", "--dump-dom", "file:///" + f.name],
                     capture_output=True, text=True, encoding="utf-8").stdout
svg = re.search(r"<svg.*?</svg>", dom, re.S)[0]
x, y, w, h = (float(v) for v in re.search(r'viewBox="([^"]+)"', svg)[1].split())
x, y, w, h = x - 40, y - 15, w + 80, h + 30
svg = re.sub(r'<svg[^>]*?>', lambda m: re.sub(r'\s(width|style|viewBox)="[^"]*"', "", m[0])[:-1] +
             f' xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {w} {h}" width="850" height="{850 * h / w:.0f}">'
             f'<rect x="{x + .5}" y="{y + .5}" width="{w - 1}" height="{h - 1}" rx="8" fill="#0d1117" stroke="#30363d"/>', svg, count=1)
# Mermaid left-aligns the root label when htmlLabels is off; center it.
svg = re.sub(r'(mindmap-node section-root[^>]*>(?:(?!</g></g></g>).)*?<text)', r'\1 text-anchor="middle" font-weight="600"', svg, count=1, flags=re.S)
open(os.path.join(ROOT, "assets", "stack-map.svg"), "w", encoding="utf-8").write(svg)
print("ok", "foreignObject" not in svg)
