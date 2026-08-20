#!/usr/bin/env python3
"""Build the static site from the Claude Design canvas source.

The .dc.html artboards render only inside the design editor: their runtime
(support.js) expects a React host that nothing on the page provides. This
lifts the markup out and re-implements the handful of editor-only bindings
in plain JS, so the result is a static file Cloudflare Pages can serve.

Usage: python3 scripts/build.py
"""
import datetime
import html
from html.parser import HTMLParser
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "design" / "Terraform in an Afternoon.dc.html"
OUT = ROOT / "public" / "index.html"

BASE_URL = "https://learn-terraform.pages.dev"
TITLE = "Learn Terraform in an Afternoon"
DESCRIPTION = (
    "A single-page, practical tour of Terraform: core concepts, HCL syntax, "
    "modules, state and backends, CLI commands, gotchas, and worked example configs."
)

# The header brand mark is an enum prop. renderVals() reads
# `this.props.mark ?? 'bars'` and data-props declares default "bars", so the
# bars variant is the one the canvas actually renders. The other two go.
MARK = "bars"

RUNTIME = """
<script>
(function () {
  'use strict';

  // Reading-progress bar + nav scroll-spy. Lifted verbatim from the canvas
  // component; it was already framework-free.
  var progress = document.getElementById('tf-progress');
  function onScroll() {
    var h = document.documentElement;
    if (progress) {
      var denom = (h.scrollHeight - h.clientHeight) || 1;
      progress.style.width = Math.min(100, Math.max(0, (h.scrollTop / denom) * 100)) + '%';
    }
    var current = null;
    document.querySelectorAll('main > section').forEach(function (s) {
      if (s.getBoundingClientRect().top <= 140) current = s.id;
    });
    document.querySelectorAll('[data-spy]').forEach(function (a) {
      var on = a.getAttribute('data-spy') === current;
      a.style.color = on ? '#6d28d9' : '#5a5a63';
      a.style.fontWeight = on ? '600' : '400';
      var dot = a.querySelector('[data-dot]');
      if (dot) dot.style.opacity = on ? '1' : '0';
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // Example-config tabs. The canvas held the selection in component state and
  // re-rendered; here all three panels stay in the DOM and we toggle display.
  var ORDER = ['vpc', 'backend', 'module'];
  function paintTabs(active) {
    document.querySelectorAll('[data-ex]').forEach(function (panel) {
      panel.style.display = panel.getAttribute('data-ex') === active ? '' : 'none';
    });
    document.querySelectorAll('.expill').forEach(function (pill, i) {
      var on = ORDER[i] === active;
      pill.style.background = on ? '#6d28d9' : 'transparent';
      pill.style.color = on ? '#ffffff' : '#5a5a63';
    });
  }
  document.querySelectorAll('[data-pick]').forEach(function (input) {
    input.addEventListener('change', function () {
      paintTabs(input.getAttribute('data-pick'));
    });
  });
  paintTabs('vpc');

  // Copy-to-clipboard on each code block.
  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var block = btn.closest('[data-code]');
      var code = block && block.querySelector('code');
      if (!code) return;
      var label = btn.querySelector('[data-copy-label]');
      function done() {
        if (!label) return;
        var prev = label.textContent;
        label.textContent = 'Copied';
        setTimeout(function () { label.textContent = prev; }, 1200);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(code.innerText).then(done, done);
      } else {
        done();
      }
    });
  });

  // Sections fade in as they scroll into view. The fade is applied by JS, so with
  // scripting off nothing is ever hidden in the first place.
  if ('IntersectionObserver' in window && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
    var hidden = [];
    function reveal(el) {
      el.style.opacity = '1';
      el.style.transform = 'none';
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        reveal(en.target);
        io.unobserve(en.target);
      });
    }, { threshold: 0.06, rootMargin: '0px 0px -8% 0px' });
    document.querySelectorAll('main > section, main > footer').forEach(function (el) {
      if (el.getBoundingClientRect().top > window.innerHeight * 0.88) {
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition = 'opacity .6s ease, transform .6s cubic-bezier(.2,.7,.2,1)';
        hidden.push(el);
        io.observe(el);
      }
    });

    // Failsafe: a section must never stay invisible. The observer can miss its
    // callback in a prerenderer, a JS-executing crawler, or on a deep link that
    // lands past the section, which would publish the page as blank. After a
    // short grace period everything still hidden is shown unconditionally.
    setTimeout(function () {
      hidden.forEach(function (el) {
        io.unobserve(el);
        reveal(el);
      });
    }, 2000);
  }
})();
</script>
"""


def fail(msg):
    sys.exit("build.py: " + msg)


def extract(pattern, text, what, flags=re.S):
    m = re.search(pattern, text, flags)
    if not m:
        fail("could not find %s in %s" % (what, SRC.name))
    return m


class _FlexTextAudit(HTMLParser):
    """Find flex containers holding both bare text and element children.

    Flex layout promotes every bare text run to an anonymous flex item, so the
    container's `gap` lands between words and `align-items` stretches inline
    code chips into tall boxes. The prose has to sit in one element to be one
    item. Shipped once already -- every bullet under "Best practices" and both
    open cert-check summaries were broken this way in the original design.
    """

    def __init__(self):
        HTMLParser.__init__(self)
        self.stack = []
        self.bad = []

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "img", "hr", "meta", "link", "input"):
            return
        style = dict(attrs).get("style") or ""
        flex = "display:flex" in style.replace(" ", "")
        if self.stack:
            self.stack[-1]["elements"] += 1
        # a new element closes whatever text run was accumulating
        if self.stack:
            self.stack[-1]["open_run"] = False
        self.stack.append(
            {"tag": tag, "flex": flex, "runs": [], "open_run": False, "elements": 0}
        )

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] != tag:
                continue
            frame = self.stack.pop(i)
            del self.stack[i:]
            # One trailing text run beside elements is a normal label -- the
            # side-nav's "01" + "Core concepts" is meant to have a gap. The
            # breakage is prose split into several runs by inline chips, so
            # every fragment becomes its own flex item.
            if frame["flex"] and len(frame["runs"]) > 1:
                self.bad.append("<%s> %r" % (tag, " / ".join(frame["runs"])[:70]))
            return

    def handle_data(self, data):
        if not self.stack or not data.strip():
            return
        frame = self.stack[-1]
        if frame["open_run"]:
            frame["runs"][-1] += data.strip()
        else:
            frame["runs"].append(data.strip())
            frame["open_run"] = True


def audit_flex_text(markup):
    a = _FlexTextAudit()
    a.feed(markup)
    if a.bad:
        fail(
            "flex container mixes bare text with elements -- wrap the prose in "
            "one span or the gap lands between words:\n    "
            + "\n    ".join(a.bad)
        )


def resolve_hover(markup):
    """Turn the canvas runtime's `style-hover` attribute into real CSS.

    `style-hover` is interpreted by the design editor's runtime, not by a
    browser, so it is inert in a plain page -- the hover states simply vanish.
    Each distinct declaration becomes one generated class, shared by every
    element that used it.
    """
    rules, classes = [], {}

    def replace(m):
        decl = m.group("decl").strip().rstrip(";")
        if decl not in classes:
            name = "hv-%d" % (len(classes) + 1)
            classes[decl] = name
            rules.append(".%s:hover { %s; }" % (name, decl))
        return ' class="%s"' % classes[decl]

    out, count = re.subn(
        r'\s+style-hover="(?P<decl>[^"]*)"', replace, markup
    )
    if count:
        print("  resolved %d style-hover attribute(s) into %d rule(s)" % (count, len(rules)))
    return out, "\n  ".join(rules)


def resolve_sc_if(markup):
    """Replace the editor's <sc-if> conditionals with static markup.

    Brand-mark variants collapse to the one the canvas renders. The three
    example-config blocks are tab panels, not variants -- all three must
    survive or the tab switcher has nothing to switch between.
    """
    panels = {"exVpc": "vpc", "exBackend": "backend", "exModule": "module"}
    marks = {"markBracket": "bracket", "markBars": "bars", "markTile": "tile"}
    seen = []

    def replace(m):
        name = m.group("name")
        inner = m.group("inner")
        seen.append(name)
        if name in panels:
            return '<div data-ex="%s">%s</div>' % (panels[name], inner)
        if name in marks:
            return inner if marks[name] == MARK else ""
        fail("unknown sc-if binding %r -- refusing to guess" % name)

    out, count = re.subn(
        r'<sc-if value="\{\{\s*(?P<name>\w+)\s*\}\}"[^>]*>(?P<inner>.*?)</sc-if>',
        replace,
        markup,
        flags=re.S,
    )
    if count != 6:
        fail("expected 6 sc-if blocks, resolved %d" % count)
    missing = (set(panels) | set(marks)) - set(seen)
    if missing:
        fail("sc-if blocks missing: %s" % ", ".join(sorted(missing)))
    return out


def source_date():
    """Last commit date of the design source, as the sitemap's lastmod.

    Anchoring to the content's own history rather than to the clock keeps the
    build reproducible: a rebuild that changes nothing rewrites nothing.
    """
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(SRC)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=10,
        )
        stamp = out.stdout.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
            return stamp
    except (OSError, subprocess.SubprocessError):
        pass
    return datetime.date.today().isoformat()


def write_robots():
    path = OUT.parent / "robots.txt"
    path.write_text(
        "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % BASE_URL,
        encoding="utf-8",
    )
    print("wrote %s" % path.relative_to(ROOT))


def write_sitemap():
    path = OUT.parent / "sitemap.xml"
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url>\n"
        "    <loc>%s/</loc>\n"
        "    <lastmod>%s</lastmod>\n"
        "  </url>\n"
        "</urlset>\n" % (BASE_URL, source_date()),
        encoding="utf-8",
    )
    print("wrote %s" % path.relative_to(ROOT))


def main():
    if not SRC.exists():
        fail("missing canvas source: %s" % SRC)
    raw = SRC.read_text(encoding="utf-8")

    body = extract(r"<x-dc>(.*)</x-dc>", raw, "the <x-dc> block").group(1)
    helmet = extract(r"<helmet>(.*?)</helmet>", body, "the <helmet> block").group(1)
    body = body.replace(extract(r"<helmet>.*?</helmet>", body, "the <helmet> block").group(0), "")

    # The helmet carries the font links and the page stylesheet; the viewport
    # meta is re-declared in the head we build, so drop the duplicate.
    head = re.sub(r'<meta name="viewport"[^>]*>\s*', "", helmet).strip()

    body = resolve_sc_if(body)

    # Editor bindings become data attributes the runtime above binds to.
    body = body.replace('onClick="{{ copyCode }}"', "data-copy")
    for fn, value in (("pickVpc", "vpc"), ("pickBackend", "backend"), ("pickModule", "module")):
        body = body.replace('onChange="{{ %s }}"' % fn, 'data-pick="%s"' % value)

    body, hover_css = resolve_hover(body)

    # Anything the canvas runtime interprets is inert in a plain page. Catching
    # attributes as well as tags and bindings is deliberate: `style-hover`
    # shipped silently once, dropping every hover state on the page.
    leftover = re.findall(
        r"\{\{[^}]*\}\}|<sc-[a-z]+|\bstyle-(?:hover|active|focus)=|\bhint-[a-z-]+=", body
    )
    if leftover:
        fail("unconverted canvas constructs remain: %s" % ", ".join(sorted(set(leftover))))

    audit_flex_text(body)

    page = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<meta name="color-scheme" content="light">
<meta name="theme-color" content="#ffffff">
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="canonical" href="{base}/">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{base}/">
<meta property="og:image" content="{base}/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<meta name="twitter:image" content="{base}/og.png">
{head}
<style>
  /* Generated from the design's style-hover attributes. */
  {hover_css}
  /* The example-switcher radios are visually hidden, so without this a
     keyboard user tabbing into the control sees no focus indicator at all. */
  label:has(input:focus-visible) .expill {{ outline:2px solid #6d28d9; outline-offset:2px; }}
</style>
</head>
<body>
{body}
{runtime}
</body>
</html>
""".format(
        title=html.escape(TITLE),
        description=html.escape(DESCRIPTION),
        base=BASE_URL,
        hover_css=hover_css,
        head=head,
        body=body.strip(),
        runtime=RUNTIME.strip(),
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print("wrote %s (%d bytes)" % (OUT.relative_to(ROOT), len(page.encode("utf-8"))))

    write_robots()
    write_sitemap()


if __name__ == "__main__":
    main()
