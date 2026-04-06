# daxnoob.blog — Agent Context

> Public blog at [daxnoob.blog](https://daxnoob.blog). MkDocs + Material for MkDocs, deployed to GitHub Pages.

## Quick Start

```bash
pip install -r requirements.txt   # one-time setup
mkdocs serve                      # local preview at http://127.0.0.1:8000
```

**Always preview locally before pushing.** Every push to `main` triggers the GitHub Actions deploy workflow (`.github/workflows/ci.yml`) which builds and publishes to GitHub Pages.

## Project Structure

```
docs/
  posts/              # Blog posts, organized by year (YYYY/)
    2024/             # Each post is a single .md file named by slug
    2025/
    2026/
  assets/
    images/
      posts/<slug>/   # Images per post — folder name matches the post slug
      shared/         # Logo, favicon, avatar
    css/              # Custom stylesheets
    js/               # Custom JavaScript
  index.md            # Blog homepage
  about.md, projects.md, presentations.md, daxing.md
resources/            # Downloadable files referenced by posts (code samples, notebooks)
includes/             # MkDocs snippet includes
overrides/            # Material theme overrides
mkdocs.yml            # Site configuration — nav, plugins, theme, redirects
```

## Writing Posts

### Frontmatter template

```yaml
---
title: "Post Title"
description: "One-line description for SEO and social cards."
draft: false
date:
  created: YYYY-MM-DD
categories:
  - CategoryName
tags:
  - Tag1
  - Tag2
authors:
  - justinmartin
slug: post-slug-matching-filename
image: assets/images/posts/<slug>/hero-image.png
---
```

### Conventions

- **File location:** `docs/posts/YYYY/<slug>.md`
- **Images:** Place in `docs/assets/images/posts/<slug>/`. Reference with relative path `../../assets/images/posts/<slug>/image.png`.
- **Downloadable resources:** Place in `resources/<slug>/`. Link from the post.
- **Excerpt marker:** Use `<!-- more -->` to mark where the blog index preview cuts off.
- **WordPress redirects:** If the post replaces an old WordPress URL, add a redirect entry in `mkdocs.yml` under `plugins > redirects > redirect_maps`.

### Voice & Style

Justin writes in a conversational, approachable tone — like explaining to a colleague over coffee. Key traits:
- First person ("I", "we", "our team")
- Practical and example-driven — always show real code/DAX/M, not just theory
- Acknowledges complexity honestly ("it took us a while to adopt")
- Links to official docs and GitHub repos for further reading
- Uses admonitions, code blocks with annotations, and Mermaid diagrams
- Categories are broad topics (DevOps, DAX, Power Query); tags are specific technologies

**Before writing a post:** Read 2–3 recent posts to match the voice. Do not use corporate/marketing language.

## What Not to Touch

- `mkdocs.yml` plugin configuration — changes can break the build
- `overrides/` — theme customizations, rarely changed
- `site/` — build output, gitignored
- `.cache/` — MkDocs cache, gitignored
