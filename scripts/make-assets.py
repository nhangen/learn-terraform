#!/usr/bin/env python3
"""Render the favicon and the Open Graph card from the site's brand.

Both are generated rather than hand-drawn so they stay in step with the design:
the colors, the mark and the wordmark below are the ones the page header uses.
Rendered with headless Chrome, which is already the tool the build is verified
with. Run after changing the brand; the output is committed.

Usage: python3 scripts/make-assets.py
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "public"

ACCENT = "#6d28d9"
INK = "#0e0e10"
MUTED = "#5a5a63"

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">'
)

# The header mark: a wide accent bar over a narrow dark one. Scaled by --u so the
# same geometry renders at favicon size and at card size.
MARK = """
<span style="display:flex;flex-direction:column;align-items:center;gap:calc(2*var(--u))">
  <span style="width:calc(20*var(--u));height:calc(5*var(--u));border-radius:calc(1*var(--u));background:{accent}"></span>
  <span style="width:calc(5*var(--u));height:calc(15*var(--u));border-radius:calc(1*var(--u));background:{ink}"></span>
</span>
""".format(accent=ACCENT, ink=INK)

FAVICON = """<!DOCTYPE html><meta charset="utf-8">{fonts}
<style>
  html,body {{ margin:0; padding:0; background:transparent; }}
  body {{ --u:2.4px; width:64px; height:64px; display:grid; place-items:center; }}
</style>
{mark}
""".format(fonts=FONTS, mark=MARK)

OG = """<!DOCTYPE html><meta charset="utf-8">{fonts}
<style>
  html,body {{ margin:0; padding:0; }}
  body {{
    --u:1.9px;
    width:1200px; height:630px; background:#ffffff;
    font-family:'IBM Plex Sans',system-ui,sans-serif;
    display:flex; flex-direction:column; justify-content:center;
    padding:0 86px; box-sizing:border-box; position:relative; overflow:hidden;
  }}
  .glow {{
    position:absolute; top:-150px; right:-120px; width:760px; height:620px;
    background:radial-gradient(circle, rgba(124,58,237,.20), transparent 66%);
    filter:blur(30px);
  }}
  .brand {{
    display:flex; align-items:center; gap:16px;
    font-family:'Space Grotesk',sans-serif; font-weight:600; font-size:27px;
    letter-spacing:-.01em; color:{ink};
  }}
  .eyebrow {{
    font-family:'IBM Plex Mono',monospace; font-size:20px; letter-spacing:.16em;
    text-transform:uppercase; color:{accent}; margin:52px 0 22px;
  }}
  h1 {{
    font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:96px;
    line-height:1.02; letter-spacing:-.035em; color:{ink}; margin:0;
  }}
  .pills {{ display:flex; gap:13px; margin-top:46px; }}
  .pill {{
    font-family:'IBM Plex Mono',monospace; font-size:19px; color:{muted};
    border:1px solid #e4e4ec; border-radius:100px; padding:11px 24px;
  }}
</style>
<div class="glow"></div>
<span class="brand">{mark}<span><span style="color:{accent}">learn</span>terraform<span style="color:{accent}">.day</span></span></span>
<div class="eyebrow">Infrastructure as code &middot; A working reference</div>
<h1>Learn Terraform<br>in an <span style="color:{accent}">afternoon.</span></h1>
<div class="pills">
  <span class="pill">10 sections</span>
  <span class="pill">~40 min read</span>
  <span class="pill">Terraform 1.x / OpenTofu</span>
</div>
""".format(fonts=FONTS, mark=MARK, accent=ACCENT, ink=INK, muted=MUTED)


def chrome():
    for c in (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ):
        if pathlib.Path(c).exists():
            return c
    found = shutil.which("google-chrome") or shutil.which("chromium")
    if not found:
        sys.exit("make-assets.py: no Chrome/Chromium found to render with")
    return found


def render(html, width, height, out, transparent=False):
    binary = chrome()
    with tempfile.TemporaryDirectory() as tmp:
        page = pathlib.Path(tmp) / "page.html"
        page.write_text(html, encoding="utf-8")
        shot = pathlib.Path(tmp) / "shot.png"
        cmd = [
            binary, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--window-size=%d,%d" % (width, height),
            # Fonts come from Google Fonts, so give the fetch room before capture.
            "--virtual-time-budget=8000",
            "--screenshot=%s" % shot,
        ]
        if transparent:
            cmd.append("--default-background-color=00000000")
        cmd.append(page.as_uri())
        subprocess.run(cmd, check=True, capture_output=True)
        if not shot.exists():
            sys.exit("make-assets.py: Chrome produced no image for %s" % out.name)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(shot, out)
        print("wrote %s (%d bytes)" % (out.relative_to(ROOT), out.stat().st_size))


def main():
    render(FAVICON, 64, 64, OUT / "favicon.png", transparent=True)
    render(OG, 1200, 630, OUT / "og.png")


if __name__ == "__main__":
    main()
