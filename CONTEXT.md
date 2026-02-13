# DAX Noob Blog Migration — Session Context

> **Purpose:** Provide any new agent with full context to continue this project seamlessly.  
> **Last Updated:** 2025-06-15

---

## What We're Doing

Migrating Justin Martin's blog **daxnoob.blog** from WordPress to **Material for MkDocs** hosted on **GitHub Pages**. The goals are:

1. **Source-controlled blog** — all content in Git, hosted on GitHub
2. **Markdown-first authoring** — write posts in VS Code, commit, auto-deploy
3. **Modern, polished design** — inspired by Jake Duddy's blog (evaluationcontext.github.io)

## Key Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Static site generator | Material for MkDocs | Python-based, fast builds, excellent blog plugin, recommended by Jake Duddy |
| Hosting | GitHub Pages | Free, auto-deploy via GitHub Actions, custom domain support |
| GitHub repo name | `daxnoob.github.io` | User site — deploys to root URL |
| Custom domain | `daxnoob.blog` | Already owned, will point DNS to GitHub Pages |
| Accent color | Teal `#3CBCB4` | Matches the DAX Noob robot logo |
| Secondary color | Steel Blue `#5A7A94` | From logo background |
| Dark tone | Navy `#2D4356` | Dark mode base, from logo background |
| Fonts | IBM Plex Sans / JetBrains Mono / Space Grotesk | Same as Jake's site, easy to change later |
| Design inspiration | Jake Duddy's evaluationcontext.github.io | Forked approach — same architecture, our own colors/branding |

## Architecture (from Jake's repo)

```
daxnoob.blog/
├── .devcontainer/          # Dev container for local/Codespaces development
│   └── devcontainer.json
├── .github/workflows/
│   └── ci.yml              # GitHub Actions: build mkdocs → deploy to gh-pages
├── docs/
│   ├── .authors.yml        # Blog author profiles
│   ├── index.md            # Blog index (landing page)
│   ├── about.md            # About page
│   ├── privacy.md          # Privacy policy
│   ├── assets/
│   │   ├── css/            # Custom stylesheets (extra.css, blogCards.css, etc.)
│   │   ├── images/         # Logo, avatar, favicon, blog post images
│   │   └── js/             # Custom JavaScript (interactions, hero scroll, lazy images)
│   └── posts/
│       ├── 2024/           # Blog posts organized by year
│       ├── 2025/           # Each post in its own folder: YYYY-MM-DD-slug/post.md
│       └── 2026/
├── overrides/              # Material theme template overrides
│   ├── main.html           # Base template (OG meta, fonts)
│   ├── blog-post.html      # Blog post template (hero image, sidebar, metadata)
│   ├── 404.html            # Custom 404 page
│   └── partials/
│       ├── post.html       # Blog index card (how posts appear on the index)
│       ├── post-header.html # Post header (description + divider)
│       └── content.html    # Content wrapper
├── mkdocs.yml              # Main configuration file
├── requirements.txt        # Python dependencies
├── TASKS.md                # Task tracker (see companion file)
└── CONTEXT.md              # This file
```

## Blog Post Format

Each blog post is a Markdown file with YAML frontmatter:

```markdown
---
title: Post Title Here
description: A brief description for cards and meta tags
image: /assets/images/blog/2025/2025-03-03-slug/header.png
date: 2025-03-03
authors:
  - justinmartin
comments: true
categories:
  - DAX
  - Fabric
slug: posts/my-post-slug
---

Post content in Markdown here...
```

Posts live in `docs/posts/YYYY/YYYY-MM-DD-slug/post-name.md`.

## How Deployment Works

1. Author writes/edits Markdown in VS Code
2. Commits and pushes to `master` (or `main`) branch
3. GitHub Actions CI runs:
   - Checks out code
   - Installs Python + dependencies from `requirements.txt`
   - Runs `mkdocs gh-deploy --force` (builds HTML → pushes to `gh-pages` branch)
4. GitHub Pages serves the `gh-pages` branch
5. Custom domain (`daxnoob.blog`) points to GitHub Pages via DNS

## Color Palette

Derived from the DAX Noob logo (teal robot on steel-blue background):

| Token | Hex | Usage |
|-------|-----|-------|
| `--dn-teal` | `#3CBCB4` | Primary accent (links, highlights, hover) |
| `--dn-teal-dark` | `#2A9D8F` | Darker accent (link hover, active states) |
| `--dn-teal-light` | `#6ED4CB` | Light accent (underline animations, subtle highlights) |
| `--dn-teal-ghost` | `rgba(60, 188, 180, 0.08)` | Ghost backgrounds (tags, pills) |
| `--dn-steel` | `#5A7A94` | Secondary (subtle backgrounds) |
| `--dn-navy` | `#2D4356` | Dark mode base, dark backgrounds |
| `--dn-slate` | `#1A2B3C` | Deepest dark (code bg in dark mode) |

## WordPress Posts to Migrate

26 posts from January 2024 to November 2025. Full audit in TASKS.md.

Categories to standardize: DAX, Data Modeling, Power Query, Administration, Python, Visualization, Fabric, Video.

## Social Links

- Email: justin@daxnoob.blog
- LinkedIn: https://www.linkedin.com/in/daxnoobjustin/
- Twitter/X: https://twitter.com/dax_noob_justin

## Reference Repository

Jake Duddy's blog repo has been cloned locally for reference:
- Local path: `c:\Users\justinmartin\Projects\evaluationcontext.github.io`
- Remote: https://github.com/EvaluationContext/evaluationcontext.github.io
- Key files to reference: `mkdocs.yml`, `overrides/`, `docs/assets/css/`, `docs/assets/js/`

## Current Status

**Phases 1-4 complete.** All project files have been created and the site builds and serves locally (`mkdocs build` succeeds, `mkdocs serve` runs on port 8000). A sample blog post ("Welcome to the New DAX Noob") validates the full pipeline.

**Remaining work:**

- **3.18** — Add the DAX Noob logo/avatar/favicon images to `docs/assets/images/` (Justin needs to provide these)
- **Phase 5** — Initialize git, create GitHub repo (`daxnoob.github.io`), push, configure GitHub Pages
- **Phase 6** — Configure custom domain DNS for `daxnoob.blog`
- **Phase 7** — Export WordPress posts, convert to Markdown, standardize categories/tags, migrate images
- **Phase 8** — Final polish, test responsiveness, validate RSS/OG/Twitter, go live

See [TASKS.md](TASKS.md) for detailed progress tracking.
