# DAX Noob Blog — Project Context

> **Last Updated:** 2026-02-13

---

## Overview

Justin Martin's blog **daxnoob.blog** built with **Material for MkDocs**, hosted on **GitHub Pages**. Migrated from WordPress.

- **Repo:** https://github.com/DAXNoobJustin/daxnoob.github.io
- **Live URL:** https://daxnoobjustin.github.io (pending custom domain setup)
- **Custom domain:** daxnoob.blog (not yet configured)

## Architecture

- **Static site generator:** Material for MkDocs (v1.6.1)
- **Hosting:** GitHub Pages via GitHub Actions (`.github/workflows/ci.yml`)
- **Theme:** Light only (dark mode removed), teal primary `#3CBCB4`
- **Blog plugin:** `blog_dir: .` (blog is root), post URL format: `"{slug}"`
- **Plugins:** search, glightbox, tags, blog, rss

## Design System

- **Body font:** Inter (0.92rem)
- **Code font:** JetBrains Mono (0.85rem)
- **Display font:** Space Grotesk (headings only)
- **Background:** Warm `#FAFAF7`
- **Accent:** Teal `#3CBCB4`
- **Nav tabs:** Pill-style highlight (background, not underline)
- **h2 styling:** 60px gradient underline (teal to transparent)
- **Card hover:** Left-border teal accent (not lift effect)
- **Footer:** 3px gradient stripe (teal to transparent)
- **Video embeds:** Responsive `.video-wrapper` class (16:9 aspect ratio)

## Navigation

- Blog (index.md)
- Presentations (presentations.md)
- Projects (projects.md)
- DAXing with DAX Noob (daxing.md)
- About (about.md)
- Privacy (privacy.md — footer link only, not in nav tabs)

## Content

- **26 blog posts** in `docs/posts/2024/` and `docs/posts/2025/`
- **132 images** migrated from WordPress in `docs/assets/images/blog/`
- **3 showcase pages** (Presentations, Projects, DAXing) with custom card layouts

## Categories (5)

DAX, Power Query, Data Modeling, Administration, Miscellaneous

## Tags

Performance, Optimization, Semantic Model, M Functions, Data Quality, Data Modeling, Python, Microsoft Fabric, Fabric Notebook, KQL, MCP, Open Source, Power BI, RLS, Video, Workspace Monitoring

## Key CSS Files

- `extra.css` — Design system (tokens, typography, nav, footer, video embeds)
- `pages.css` — About page, Connect cards, Showcase card grid
- `blogCards.css` — Blog index card styling
- `blogIndex.css` — Blog index sidebar logo
- `posts.css` — Post reading experience
- `hero-image.css` — Hero banner for posts
- `codeblock.css` — Code block font sizing

## Key Overrides

- `overrides/main.html` — Base template with Open Graph meta
- `overrides/blog-post.html` — Post template with hero image and sidebar
- `overrides/partials/content.html` — Conditionally includes post-header (only for posts with `date` in frontmatter)
- `overrides/partials/post.html` — Blog index card template
- `overrides/partials/post-header.html` — Description + divider below post title

## Deployment

1. Push to `main` branch
2. GitHub Actions builds with `mkdocs build`
3. Uploads site artifact and deploys via `actions/deploy-pages@v4`

## Social Links

- LinkedIn: https://www.linkedin.com/in/daxnoobjustin/
- YouTube: https://www.youtube.com/@DAXNoobJustin
- GitHub: https://github.com/daxnoob
- Email: justin@daxnoob.blog

## What's Left

See [TASKS.md](TASKS.md) — custom domain DNS setup and final polish before go-live.
