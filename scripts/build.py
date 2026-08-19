#!/usr/bin/env python3
"""Build the static site from the Claude Design canvas source.

The .dc.html artboards render only inside the design editor: their runtime
(support.js) expects a React host that nothing on the page provides. This
lifts the markup out and re-implements the handful of editor-only bindings
in plain JS, so the result is a static file Cloudflare Pages can serve.

Usage: python3 scripts/build.py
"""
import html
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "design" / "Terraform in an Afternoon.dc.html"
OUT = ROOT / "public" / "index.html"

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

    leftover = re.findall(r"\{\{[^}]*\}\}|<sc-[a-z]+", body)
    if leftover:
        fail("unconverted canvas bindings remain: %s" % ", ".join(sorted(set(leftover))))

    page = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<meta name="color-scheme" content="light">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta name="twitter:card" content="summary_large_image">
{head}
</head>
<body>
{body}
{runtime}
</body>
</html>
""".format(
        title=html.escape(TITLE),
        description=html.escape(DESCRIPTION),
        head=head,
        body=body.strip(),
        runtime=RUNTIME.strip(),
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print("wrote %s (%d bytes)" % (OUT.relative_to(ROOT), len(page.encode("utf-8"))))


if __name__ == "__main__":
    main()
