# learnterraform.day

A single-page, practical tour of Terraform for engineers who know some cloud but
haven't written much HCL. Core concepts, syntax, modules, state and backends,
the CLI, the gotchas, and example configs you can copy.

Live at **[learn-terraform.pages.dev](https://learn-terraform.pages.dev)**.

The page brands itself `learnterraform.day`. That domain is not registered yet —
point it at this Pages project as a custom domain if you pick it up.

## How this repo is put together

The page is designed in [Claude Design](https://claude.ai) and built from that
design — there is no framework and no dependency to install.

```
design/     Canvas sources (.dc.html artboards + the Nocturne design system)
scripts/    build.py       — turns the canvas source into the static site
            make-assets.py — renders favicon.png and the og.png share card
public/     Build output. This is what Cloudflare Pages serves.
```

`design/*.dc.html` render only inside the design editor: their runtime expects a
React host that nothing on the page provides. `scripts/build.py` lifts the markup
out, resolves the editor-only bindings, and re-implements the interactive parts
(reading progress, scroll-spy, example tabs, copy-to-clipboard) in plain
JavaScript. The output is a single self-contained HTML file.

## Building

```sh
python3 scripts/build.py
```

No arguments, no dependencies — Python 3 only. It writes `public/index.html`
alongside `robots.txt` and `sitemap.xml`, and fails loudly if the canvas source
grows a binding it doesn't know how to convert, so an edit in the design editor
can never silently drop content from the site.

The share card and favicon are generated separately, because rendering them needs
a browser and they change far less often than the page does:

```sh
python3 scripts/make-assets.py
```

That reads the brand colors and the header mark from the same values the page
uses and writes `public/favicon.png` and `public/og.png`. Re-run it after a brand
change and commit the result.

Preview locally:

```sh
python3 -m http.server 8899 --directory public
```

## Editing the content

Edit `design/Terraform in an Afternoon.dc.html` — in the Claude Design canvas or
by hand — then re-run the build and commit both the design and `public/`.

`design/Terraform in an Afternoon (Nocturne).dc.html` is a dark-theme variant of
the same page, built on the Nocturne design system in `design/_ds/`. It is not
what ships today; the build targets the light artboard.

## Deploying

Cloudflare Pages builds from this repo on every push to `main`: it runs
`python3 scripts/build.py` and publishes `public/`. Branches get preview
deployments. The connection is Cloudflare's GitHub integration, so there is no
API token stored in this repo.

This differs from `mysql-vs-postgres`, which deploys through a GitHub Actions
workflow using `cloudflare/wrangler-action` and a `CLOUDFLARE_API_TOKEN` secret.
Both land in the same place. The integration is used here because it needs no
long-lived credential, and because running the build on Cloudflare rather than
committing a pre-built directory means the published page cannot drift from the
design it was generated from.
