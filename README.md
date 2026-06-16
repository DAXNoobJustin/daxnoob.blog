# DAX Noob

Source for **[daxnoob.blog](https://daxnoob.blog/)** — my blog about Power BI, DAX, Microsoft Fabric, and the data-engineering rabbit holes I fall into along the way.

It's a static site built with [MkDocs](https://www.mkdocs.org/) and [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/), deployed to GitHub Pages.

[**Read the blog**](https://daxnoob.blog/) · [Presentations](https://daxnoob.blog/presentations/) · [Projects](https://daxnoob.blog/projects/) · [DAXing with DAX Noob](https://daxnoob.blog/daxing/) · [RSS](https://daxnoob.blog/feed_rss_created.xml) · [Subscribe](https://buttondown.com/daxnoob)

## Run it locally

You'll need Python 3.12+.

```bash
pip install -r requirements.txt   # one-time setup
mkdocs serve                      # live preview at http://127.0.0.1:8000
```

`mkdocs serve` hot-reloads as you edit, so changes show up instantly. Prefer not to install anything? Open the repo in VS Code or a Codespace and the dev container ([`.devcontainer/`](.devcontainer/)) sets it all up for you.

## How it's deployed

Nothing to deploy by hand. Every push to `main` triggers [`.github/workflows/ci.yml`](.github/workflows/ci.yml), which runs `mkdocs build` and publishes the output to GitHub Pages. Preview locally before pushing — a broken build means a broken site.

## Repo layout

```
docs/              # All site content
  posts/           # Blog posts — one .md per post, organized by year (YYYY/)
  assets/          # Images (per-post + shared), CSS, JS
  *.md             # Standalone pages: index, about, projects, presentations, daxing
resources/         # Downloadable code & notebooks that go with specific posts
includes/          # Shared markdown snippets
overrides/         # Material theme overrides
mkdocs.yml         # Site config — nav, theme, plugins, redirects
requirements.txt   # Python dependencies
```

Writing or editing a post? See **[AGENTS.md](AGENTS.md)** for the frontmatter template, file/image conventions, voice notes, and the redirect setup for retired WordPress URLs.

## Code from the posts

The [`resources/`](resources/) folder holds the scripts, notebooks, and sample projects referenced in articles. Each subfolder pairs with a post:

| Folder | What's in it | Article |
|---|---|---|
| [`fabric-semantic-model-starter/`](resources/fabric-semantic-model-starter/) | A full, anonymized reference for running production semantic models on Fabric — workspace layout, dev loop, CI/CD, monitoring, and an agentic layer. | [Open-source starter →](https://daxnoob.blog/starter) |
| [`agentic-power-query-development/`](resources/agentic-power-query-development/) | PowerShell wrappers and examples for iterating on Power Query (M) with an LLM via `PQTest`. | [Iterating on Power Query with an LLM](https://daxnoob.blog/agentic-power-query-development/) |
| [`extending-fabric-cicd/`](resources/extending-fabric-cicd/) | A lightweight framework for running custom pre/post-processing operations around `fabric-cicd` deployments. | [Extending fabric-cicd with Pre and Post-Processing Operations](https://daxnoob.blog/extending-fabric-cicd-with-pre-post-processing/) |
| [`remove-unused-measures/`](resources/remove-unused-measures/) | A notebook and Python script that strip unused report-level measures from a PBIP. | [Report Maintenance: Remove Unused Report Measures](https://daxnoob.blog/report-maintenance-remove-unused-report-measures/) |
| [`onelake-security-error-refresh/`](resources/onelake-security-error-refresh/) | A notebook that detects OneLake security errors on Direct Lake models and refreshes only the affected ones. | _Coming soon_ |

## Spotted a problem?

Found a typo, a broken link, or code that doesn't work? [Open an issue](https://github.com/DAXNoobJustin/daxnoob.blog/issues) or send a PR — much appreciated.
