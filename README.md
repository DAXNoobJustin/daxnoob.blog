# DAX Noob

Source and companion code for **[daxnoob.blog](https://daxnoob.blog/)** — Justin Martin's blog about Power BI, DAX, Microsoft Fabric, and the data-engineering rabbit holes in between.

Here to read? It's all on the blog:

[**Read the blog**](https://daxnoob.blog/) · [Presentations](https://daxnoob.blog/presentations/) · [Projects](https://daxnoob.blog/projects/) · [DAXing with DAX Noob](https://daxnoob.blog/daxing/) · [RSS](https://daxnoob.blog/feed_rss_created.xml) · [Subscribe](https://buttondown.com/daxnoob)

## What's in here

This repo is the blog's source (a static site published to [daxnoob.blog](https://daxnoob.blog/)) plus the code that ships with individual posts:

- **`docs/`** — the blog itself: every post (one Markdown file, filed by year) and the standalone pages.
- **`resources/`** — downloadable scripts, notebooks, and sample projects that go with specific articles.

So there are really two reasons to be here: to read the writing (do that on the [blog](https://daxnoob.blog/)), or to grab the code from a post (below).

## Code from the posts

Each `resources/` folder pairs with an article:

| Resource | What it is | Article |
|---|---|---|
| [`fabric-semantic-model-starter/`](resources/fabric-semantic-model-starter/) | An anonymized, end-to-end reference for running production semantic models on Fabric. | [Open-source starter →](https://daxnoob.blog/starter) |
| [`agentic-power-query-development/`](resources/agentic-power-query-development/) | Tooling and examples for iterating on Power Query (M) with an LLM. | [Iterating on Power Query with an LLM](https://daxnoob.blog/agentic-power-query-development/) |
| [`extending-fabric-cicd/`](resources/extending-fabric-cicd/) | A framework for custom pre/post-processing around `fabric-cicd` deployments. | [Extending fabric-cicd with Pre and Post-Processing Operations](https://daxnoob.blog/extending-fabric-cicd-with-pre-post-processing/) |
| [`remove-unused-measures/`](resources/remove-unused-measures/) | A notebook and script that strip unused report-level measures from a PBIP. | [Report Maintenance: Remove Unused Report Measures](https://daxnoob.blog/report-maintenance-remove-unused-report-measures/) |
| [`onelake-security-error-refresh/`](resources/onelake-security-error-refresh/) | A notebook that detects OneLake security errors on Direct Lake models and refreshes the affected ones. | _Coming soon_ |

## Notes

- Working in the repo — writing a post or adding a resource? See [AGENTS.md](AGENTS.md).
- Spotted a typo, a broken link, or code that doesn't work? [Open an issue](https://github.com/DAXNoobJustin/daxnoob.blog/issues) or send a PR.
