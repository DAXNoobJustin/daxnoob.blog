# DAX Noob Blog Migration — Task Tracker

> **Project:** Migrate daxnoob.blog from WordPress to Material for MkDocs + GitHub Pages  
> **Started:** 2025-06-15  
> **Last Updated:** 2025-06-15  
> **Status:** Phases 1-4 complete. Site builds and serves locally. Remaining: add images (3.18), git init & deploy (Phase 5-6), WordPress migration (Phase 7), polish (Phase 8).

---

## Phase 1: Project Setup

- [x] **1.1** Scaffold directory structure (docs, overrides, assets, .github, .devcontainer)
- [x] **1.2** Create `requirements.txt` with Python dependencies
- [x] **1.3** Create `.gitignore`
- [x] **1.4** Create `.devcontainer/devcontainer.json` for Codespaces/local dev container support

## Phase 2: MkDocs Configuration

- [x] **2.1** Create `mkdocs.yml` with site metadata (name, URL, author, description)
- [x] **2.2** Configure Material theme (palette, features, fonts)
- [x] **2.3** Configure blog plugin (post URL format, blog_dir, etc.)
- [x] **2.4** Configure markdown extensions (code highlighting, admonitions, tabs, etc.)
- [x] **2.5** Configure plugins (search, glightbox, RSS, etc.)
- [x] **2.6** Configure navigation (Blog, About, Privacy)
- [x] **2.7** Configure social links and footer
- [x] **2.8** Create `docs/.authors.yml` with author profile

## Phase 3: Theme & Styling

- [x] **3.1** Create `overrides/main.html` (base template with Open Graph/Twitter meta)
- [x] **3.2** Create `overrides/blog-post.html` (post template with hero image, sidebar)
- [x] **3.3** Create `overrides/404.html` (custom 404 page)
- [x] **3.4** Create `overrides/partials/post.html` (blog index card layout)
- [x] **3.5** Create `overrides/partials/post-header.html` (post header with description/divider)
- [x] **3.6** Create `overrides/partials/content.html` (content wrapper)
- [x] **3.7** Create `docs/assets/css/extra.css` (design system: tokens, typography, header, links, etc.)
- [x] **3.8** Create `docs/assets/css/blogCards.css` (blog index card styling)
- [x] **3.9** Create `docs/assets/css/blogIndex.css` (blog index/archive page styling)
- [x] **3.10** Create `docs/assets/css/posts.css` (post reading experience)
- [x] **3.11** Create `docs/assets/css/hero-image.css` (hero banner for posts)
- [x] **3.12** Create `docs/assets/css/codeblock.css` (code block refinements)
- [x] **3.13** Create `docs/assets/css/button.css` (button styles)
- [x] **3.14** Create `docs/assets/css/pages.css` (about/projects page layouts)
- [x] **3.15** Create `docs/assets/js/interactions.js` (scroll reveal, keyboard detection, progress bar)
- [x] **3.16** Create `docs/assets/js/hero-scroll.js` (hero image parallax on scroll)
- [x] **3.17** Create `docs/assets/js/lazy-images.js` (lazy loading for blog card images)
- [ ] **3.18** Add logo/avatar/favicon images to `docs/assets/images/`

## Phase 4: Content Pages

- [x] **4.1** Create `docs/index.md` (blog index landing page)
- [x] **4.2** Create `docs/about.md` (About page)
- [x] **4.3** Create `docs/privacy.md` (Privacy policy)
- [x] **4.4** Create a sample blog post to validate the full pipeline

## Phase 5: CI/CD & Deployment

- [x] **5.1** Create `.github/workflows/ci.yml` (GitHub Actions: build + deploy to gh-pages)
- [ ] **5.2** Initialize git repo locally
- [ ] **5.3** Create GitHub repository (`daxnoob.github.io`)
- [ ] **5.4** Push initial commit to GitHub
- [ ] **5.5** Configure GitHub Pages (deploy from `gh-pages` branch)
- [ ] **5.6** Verify site loads at `https://daxnoob.github.io`

## Phase 6: Custom Domain

- [ ] **6.1** Add `CNAME` file to `docs/` with `daxnoob.blog`
- [ ] **6.2** Configure DNS records (A records + CNAME) to point to GitHub Pages
- [ ] **6.3** Enable HTTPS in GitHub Pages settings
- [ ] **6.4** Verify `https://daxnoob.blog` loads correctly

## Phase 7: WordPress Migration

- [ ] **7.1** Export all WordPress posts (XML export or scrape)
- [ ] **7.2** Convert posts to Markdown with proper frontmatter
- [ ] **7.3** Fix/standardize categories and tags across all posts (see section below)
- [ ] **7.4** Download and migrate all post images to `docs/assets/images/blog/`
- [ ] **7.5** Update image references in all Markdown files
- [ ] **7.6** Verify all migrated posts render correctly
- [ ] **7.7** Set up redirects from old WordPress URLs (if needed)

## Phase 8: Polish & Launch

- [ ] **8.1** Test light/dark mode across all pages
- [ ] **8.2** Test responsive design (mobile/tablet)
- [ ] **8.3** Validate RSS feed
- [ ] **8.4** Validate Open Graph / Twitter card meta tags
- [ ] **8.5** Final review of all content
- [ ] **8.6** Go live — point domain, decommission WordPress

---

## Categories & Tags Cleanup (Task 7.3 Detail)

### Current WordPress Categories
| Category | Post Count | Keep? | Rename To? |
|----------|-----------|-------|------------|
| Admin | ~4 | TBD | |
| DAX | ~15+ | TBD | |
| KQL | ~1 | TBD | |
| Modeling | ~5 | TBD | |
| Notebooks | ~3 | TBD | |
| Power Query/M | ~2 | TBD | |
| Python | ~3 | TBD | |
| Video | ~6 | TBD | |
| Visualization | ~2 | TBD | |

### Current WordPress Tags
`business-intelligence`, `custom-functions`, `data-analysis`, `DAX`, `m`, `microsoft-fabric`, `power-bi`, `power-bi-desktop`, `power-platform`, `power-query`

### Proposed Standardized Categories
> *To be finalized with Justin — decide on a clean, consistent set*

| Proposed Category | Covers |
|-------------------|--------|
| DAX | DAX measures, optimization, patterns |
| Data Modeling | Star schema, relationships, model design |
| Power Query | M functions, transformations, data prep |
| Administration | Capacity, monitoring, governance, workspace management |
| Python | Notebooks, automation, scripting |
| Visualization | Reports, visuals, design |
| Fabric | Fabric-specific features, toolbox |
| Video | Video walkthroughs, DAXing episodes |

### All Blog Posts — Category/Tag Audit
| # | Date | Title | Current Categories | Current Tags | Proposed Categories |
|---|------|-------|--------------------|--------------|---------------------|
| 1 | 2024-01-10 | Hello (Blogging) World | — | — | — |
| 2 | 2024-01-11 | Intro to Custom M Functions | — | — | Power Query |
| 3 | 2024-01-14 | Custom M Function #1: fxJoinAndExpandTable | — | — | Power Query |
| 4 | 2024-01-21 | Custom M Function #2: fxGenerateSurrogateKeyColumn | — | — | Power Query |
| 5 | 2024-01-28 | Underrated Power BI Feature: Measures as Visual Filters | — | — | DAX, Visualization |
| 6 | 2024-02-04 | Custom M Function #3: fxSplitCamelCaseText | — | — | Power Query |
| 7 | 2024-02-13 | Custom M Function #4: fxSetColumnTypesFromModel | — | — | Power Query |
| 8 | 2024-02-25 | Power Query Level Up: Exploring the Advanced Editor and the M Language | — | — | Power Query |
| 9 | 2024-03-02 | Custom M Function #5: fxCumulativeToIncremental | — | — | Power Query |
| 10 | 2024-03-19 | You Don't Know Until You Test It: DAX Optimization | — | — | DAX |
| 11 | 2024-03-31 | Custom M Function #6: fxSplitCamelCaseColumns | — | — | Power Query |
| 12 | 2024-04-13 | Custom M Function #7: fxReplaceWithDefaultValue | — | — | Power Query |
| 13 | 2024-04-29 | Enhancing Your Golden Semantic Model with User Input Tables | — | — | Data Modeling |
| 14 | 2024-05-17 | Reducing Semantic Model Size with Creative Solutions | — | — | Data Modeling, DAX |
| 15 | 2024-06-05 | Sometimes It's Good to Fail: Raising Errors with Data Quality Tests | — | — | Power Query |
| 16 | 2024-06-23 | Creating User-Driven Default Slicer Selections | — | — | DAX, Visualization |
| 17 | 2024-12-30 | Optimizing Rolling Distinct Count Measures | DAX, Modeling | business-intelligence, DAX, etc. | DAX, Data Modeling |
| 18 | 2025-03-03 | Fabric Toolbox: DAX Performance Testing | DAX, Notebooks, Python | — | DAX, Fabric, Python |
| 19 | 2025-03-12 | Fabric Toolbox: Semantic Model Audit | Admin, DAX, Modeling, Notebooks, Python, Visualization | — | DAX, Fabric, Administration |
| 20 | 2025-03-29 | DAXing with DAX Noob: Episode 1 | DAX, Video | — | DAX, Video |
| 21 | 2025-04-04 | DAXing with DAX Noob: Episode 2 | DAX, Video | — | DAX, Video |
| 22 | 2025-05-30 | Extracting Semantic Model Source Tables with Fabric Notebooks | Admin, Modeling, Notebooks, Power Query/M, Python | — | Administration, Python, Fabric |
| 23 | 2025-06-17 | DAXing with DAX Noob: Episode 3 | DAX, Video | — | DAX, Video |
| 24 | 2025-06-18 | Identifying Semantic Model Capacity Spikes Using Workspace Monitoring | Admin, DAX, KQL, Modeling, Visualization | — | Administration, DAX, Fabric |
| 25 | 2025-10-21 | MCP Server: DAX Performance Tuner | DAX, Video | — | DAX, Video |
| 26 | 2025-11-04 | Semantic Model Optimization: Theory, Tips and Tools | Admin, DAX, Modeling, Video | — | DAX, Data Modeling, Video |

> **Note:** Posts 1-16 did not have visible categories on the WordPress index — they will need categories assigned during migration.

---

## Notes

- Color palette derived from DAX Noob logo: **Teal accent** (`#3CBCB4`), **Steel blue** (`#5A7A94`), **Dark navy** (`#2D4356`)
- Fonts: IBM Plex Sans (body) + JetBrains Mono (code) + Space Grotesk (headings) — same stack as Jake's, easy to swap later
- GitHub repo will be `daxnoob.github.io` (user site)
- Custom domain: `daxnoob.blog` (already owned)
