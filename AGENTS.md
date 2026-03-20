# AGENTS.md — daxnoob.blog

## Overview

Personal technical blog at [daxnoob.blog](https://daxnoob.blog) covering Power BI, DAX, Microsoft Fabric, and data engineering topics. Built with **MkDocs + Material for MkDocs**, auto-deployed via GitHub Actions on push to `main`. 10k+ visitors.

**Owner:** Justin Martin (DAXNoobJustin)

## Tech Stack

- **Static site generator:** MkDocs with Material theme
- **Content:** Markdown with YAML frontmatter
- **Extensions:** Mermaid diagrams, code highlighting, admonitions, superfences, tabs, glightbox
- **Deploy:** GitHub Actions → GitHub Pages (automatic on `main` push)
- **Build:** `mkdocs build` / **Serve locally:** `mkdocs serve`

## Article Authoring Workflow

### 1. Create the Article

Create a new markdown file at:
```
docs/posts/{YYYY}/{slug}.md
```

**Required frontmatter:**
```yaml
---
title: "Article Title"
description: "SEO description for social sharing and search"
draft: false
date:
  created: YYYY-MM-DD
categories:
  - Category
tags:
  - Tag1
  - Tag2
authors:
  - justinmartin
slug: article-url-slug
image: assets/images/posts/{slug}/hero-image.png
---
```

**Key categories:** DevOps, Performance, Modeling, Fabric, DAX, Power BI

Add `<!-- more -->` after the opening paragraph to set the blog preview truncation point.

### 2. Images

Store images in a subfolder matching the article slug:
```
docs/assets/images/posts/{slug}/
```

Reference in markdown using relative paths:
```markdown
![Alt text](../../assets/images/posts/{slug}/image-name.png)
```

When drafting, use placeholder comments for images Justin will add later:
```markdown
<!-- IMAGE: Screenshot of the pipeline configuration panel -->
```

### 3. Demo Source Code

If the article includes a working demo or sample repo, add it to:
```
resources/{slug}/
```

Link to it from the article. These are standalone demo projects the community can clone and use.

### 4. Preview & Deploy

```bash
mkdocs serve          # Local preview at http://localhost:8000
mkdocs build          # Build static site to site/
```

Deploy is automatic — push to `main` triggers GitHub Actions which builds and deploys to GitHub Pages.

## Directory Structure

```
daxnoob.blog/
├── docs/
│   ├── posts/                    # Articles organized by year
│   │   ├── 2024/                 # 17 articles
│   │   ├── 2025/                 # 9 articles
│   │   └── 2026/                 # Latest articles
│   ├── assets/
│   │   └── images/
│   │       ├── posts/{slug}/     # Per-article images
│   │       └── shared/           # Logo, favicon, avatar
│   └── index.md                  # Home page
├── resources/                    # Demo repos accompanying articles
├── overrides/                    # Custom Material theme templates
├── includes/                     # Markdown snippets (auto-appended)
├── mkdocs.yml                    # Site configuration
└── .github/workflows/ci.yml     # Auto-deploy on push to main
```

## Conventions

- **Article filenames:** kebab-case matching the slug (e.g., `extending-fabric-cicd-with-pre-post-processing.md`)
- **URLs:** Flat structure with slug only — `daxnoob.blog/{slug}` (no dates in URLs)
- **Image folders:** Must match article slug exactly
- **Draft articles:** Set `draft: true` in frontmatter — they won't appear on the live site
- **Code blocks:** Always include language flag for syntax highlighting
- **Redirects:** Old WordPress URLs are mapped in `mkdocs.yml` under `redirects` plugin

## Agent Guidelines

- **Drafting articles:** Create the markdown structure and frontmatter. Write a draft of the content. Justin will review and rewrite in his voice. Use `<!-- IMAGE: description -->` placeholders.
- **Don't commit without review.** Always show the draft for approval first.
- **Cross-reference:** Blog articles often reference tools from the [fabric-toolbox](https://github.com/microsoft/fabric-toolbox) repo. Check if a `resources/` demo is needed.
- **Related repo:** The [brain](https://github.com/DAXNoobJustin/brain) repo tracks this project in `registry/projects.json`.
