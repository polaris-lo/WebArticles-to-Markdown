# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CLI tool that converts web articles from Chinese social media and content platforms into structured Markdown files with YAML frontmatter (suitable for Obsidian).

**Supported platforms**: WeChat (微信公众号), Weibo (微博), Xiaohongshu (小红书), Twitter/X, Reddit.

## Running the Tool

```bash
# Install core dependencies
pip3 install -r requirements.txt

# Platform-specific optional installs
pip3 install wechat-article-to-markdown   # WeChat
pip3 install xreach                        # Twitter/X
pip3 install playwright && playwright install firefox  # Xiaohongshu
pip3 install easyocr                       # OCR for Xiaohongshu/Weibo images (downloads ~1GB model)
pip3 install pytesseract pillow            # Lightweight OCR alternative (requires system Tesseract + chi_sim)

# LLM post-processing (optional)
export DEEPSEEK_API_KEY=sk-...             # or: ~/.config/webarticles/deepseek_api_key
export ANTHROPIC_API_KEY=sk-ant-...       # if using Claude provider

# Basic usage
python3 convert.py <URL>

# Common options
python3 convert.py <URL> -o ./output --cookies cookies/twitter.txt
python3 convert.py <URL> --dry-run            # Print to terminal, don't save
python3 convert.py <URL> --force-jina         # Skip platform parser, use Jina Reader
python3 convert.py <URL> --no-jina            # Disable Jina fallback entirely
python3 convert.py <URL> --no-images -v       # Skip image download, verbose logging
python3 convert.py <URL> --comments           # Include Reddit comments
python3 convert.py <URL> --print-frontmatter  # Print only YAML frontmatter
python3 convert.py <URL> --config my.yaml     # Use custom config file
```

There is no test suite.

## Architecture

**Data flow**: `convert.py` → `cli.py` (arg parsing, config) → `dispatcher.py` (URL routing) → platform extractor → [optional LLM post-processing] → `frontmatter.py` → `markdown_writer.py` → `output/YYYY-MM-DD-{slug}.md`

**Dispatcher** (`converter/dispatcher.py`): Routes URLs to platform classes via `_ROUTES` regex patterns. Falls back to Jina Reader for unmatched URLs or when a platform extractor fails.

**Platform extractors** (`converter/platforms/`): Each platform uses a tiered fallback strategy:

| Platform | Tier 1 | Tier 2 | Tier 3 |
|----------|--------|--------|--------|
| WeChat | `wechat-article-to-markdown` CLI | HTTP + BeautifulSoup | — |
| Weibo | `$render_data` JSON | HTML parsing | — |
| Reddit | JSON API | Jina Reader | — |
| Twitter | `xreach` CLI | Jina Reader | Nitter mirrors |
| Xiaohongshu | Playwright JS rendering | `__NEXT_DATA__` JSON | HTML parsing |

**Base class** (`converter/platforms/base.py`): All extractors implement `BasePlatform.extract()` returning a dict with keys: `title`, `author`, `date`, `platform`, `source_url`, `body_html` or `body_md`, `tags`, `categories`, `summary`, `extra`.

**Output format**: YAML frontmatter + Markdown body converted from HTML via `markdownify`.

```yaml
---
title: "Article Title"
source: "https://..."
platform: "wechat"
author: "Author Name"
published: "2026-03-18"
created: "2026-03-18T14:23:45"
tags:
  - "tag1"
categories:
  - "Account Name"
description: "First 100 chars of summary..."
language: "zh"               # auto-detected (CJK % > 15% → zh)
status: "unread"
extra:                       # platform-specific engagement metrics
  likes: 123
  comments: 45
---
```

## Optional Features

### OCR (Xiaohongshu & Weibo)

Images embedded in posts are OCR-scanned and appended as text. Two backends:

- **easyocr** (default): Pure Python, supports Chinese+English. `pip install easyocr`. Downloads ~1 GB model on first use.
- **pytesseract**: Lighter alternative, requires system `tesseract` binary + `chi_sim` language pack.

Engine selected by `config.yaml → platforms.xiaohongshu.ocr.engine: auto|easyocr|pytesseract`.

### LLM Post-Processing

When `llm.enabled: true` in `config.yaml`, the following passes run after extraction:

1. **Restructure** — removes ads/QR code text, splits long paragraphs, adds section headers, converts lists to Markdown. Platform-specific prompts per source.
2. **Summarize** — generates a 3–5 sentence Chinese summary. First sentence (≤100 chars) → frontmatter `description`; full summary → `## 摘要` body section.
3. **OCR cleanup** — fixes garbled/repeated text from OCR, normalizes lists and formatting.
4. **Reading guide** — extracts up to 5 questions from the article's own core ideas, placed after `## 摘要` as `## 导读` to help readers read with intent.
5. **Skill analyses** (optional, configured via `llm.skills`):
   - **Critical reading (五问法)** — Q1 logical boundary, Q2 hidden assumptions, Q3 applicability, Q4 debate positioning, Q5 missing voices. Q4/Q5 are omitted if not substantive.
   - **Domain map (三问法)** — Q1 expert consensus (core mental models), Q2 fundamental disagreements. Appended after the article body.

**Output order**: `## 摘要` → `## 导读` → article body → skill analysis sections.

Providers: `deepseek` (default, `deepseek-chat`) or `claude` (`claude-haiku-4-5-20251001`). API keys via env vars or `~/.config/webarticles/deepseek_api_key`.

## Configuration

`config.yaml` — full structure:

```yaml
output_dir: "./output"

images:
  download: true          # download CDN images locally (WeChat only)
  subdir: "assets"

comments:
  include: true           # include comments (Reddit)
  max_top_level: 3

jina:
  enabled: true
  timeout: 30

llm:
  enabled: false
  provider: deepseek      # deepseek | claude
  model: null             # null = use provider default
  skills:
    critical_reading: false  # 批判性阅读五问法 (good for opinion/discussion articles)
    domain_map: false        # 领域知识地图三问法

obsidian:
  vault: ""               # absolute path to your Obsidian vault root
  folder_picker: false    # show macOS native folder picker dialog on save

platforms:
  xiaohongshu:
    cookies_file: "cookies/xiaohongshu.txt"
    ocr:
      enabled: true
      engine: auto        # auto | easyocr | pytesseract
  twitter:
    cookies_file: "cookies/twitter.txt"
    nitter_instances:
      - "nitter.net"
      - "nitter.privacydev.net"
      - "nitter.poast.org"
      - "nitter.cz"
```

Cookie files use Netscape HTTP format and go in `cookies/` (git-ignored). CLI `--cookies` overrides config.

## Utility Modules (`converter/utils/`)

| Module | Purpose |
| ------ | ------- |
| `http.py` | HTTP fetching with retry/backoff, Chrome UA, optional proxy bypass |
| `cookies.py` | Netscape cookie file → dict |
| `date_parser.py` | Normalizes Chinese dates, Unix timestamps, fuzzy strings → ISO-8601 |
| `slug.py` | Title → safe filename (max 60 chars, preserves CJK) |
| `llm.py` | DeepSeek/Claude API calls, prompt construction, skill analyses (五问法/三问法), reading guide extraction |
| `ocr.py` | Dispatches to easyocr or pytesseract |
| `obsidian.py` | macOS native folder picker via osascript for Obsidian vault selection |
| `tools.py` | CLI tool detection (`is_installed`) and subprocess execution |

## Adding a New Platform

1. Create `converter/platforms/{platform}.py` subclassing `BasePlatform`
2. Implement `extract(url) -> dict` returning the standard schema
3. Add URL regex pattern → class mapping in `converter/dispatcher._ROUTES`
