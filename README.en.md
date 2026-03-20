# WebArticles-to-Markdown

[中文](README.md) | English

Convert articles from WeChat, Weibo, Xiaohongshu (Little Red Book), Twitter/X, and Reddit into structured Markdown files with YAML frontmatter — optimized for [Obsidian](https://obsidian.md).

Inspired by [Agent-Reach](https://github.com/Panniantong/Agent-Reach)'s philosophy of **using the best dedicated tool for each platform**. Extended with:

- **Image OCR** — automatically extracts text from images in Xiaohongshu posts (Chinese + English, via easyocr or pytesseract)
- **LLM post-processing** — optional DeepSeek / Claude integration for reformatting, ad removal, and Chinese summary generation
- **Apple Shortcuts friendly** — pure CLI, triggerable via the "Run Shell Script" action in Apple Shortcuts
- **Multi-tier fallback** — each platform has backup strategies that kick in when scrapers hit paywalls or login walls

## Why convert to structured Markdown?

Articles on social media are scattered across apps — saved but never found again, impossible to quote, and messy when fed to AI.

Most web clippers just "move" content: raw HTML or blunt text extraction with no cleanup. This tool goes further: after fetching, it uses an LLM to reformat the content — splitting long paragraphs, removing ads and promotional text, adding section headers, and generating summaries — producing genuinely readable, searchable documents.

Converting to Markdown with YAML frontmatter solves several core problems:

### Knowledge management in Obsidian

- Fields like `tags`, `platform`, `author`, and `status` in YAML frontmatter are directly queryable by the Dataview plugin — filter by platform, mark read/unread, sort by date
- Filenames in `YYYY-MM-DD-title.md` format are naturally sortable at the filesystem level
- Images are downloaded locally — no dependency on platform CDNs, no broken links

### AI-assisted reading and retrieval

- Structured frontmatter lets AI accurately identify source, author, and date without guessing from the body
- Clean Markdown body (ads and irrelevant links removed) reduces noise so AI can focus on actual content
- LLM-generated summaries let AI understand the article's key points without reading the full text

## Installation

### Option 1: pipx (recommended, globally available)

```bash
pipx install git+https://github.com/polaris-lo/WebArticles-to-Markdown
```

Then run directly:

```bash
webarticles https://mp.weixin.qq.com/s/xxx
webarticles --help
```

Install optional features as needed:

```bash
pipx inject webarticles-to-markdown wechat-article-to-markdown  # WeChat
pipx inject webarticles-to-markdown xreach                      # Twitter/X
pipx inject webarticles-to-markdown easyocr                     # Image OCR (Chinese + English)
pipx inject webarticles-to-markdown openai anthropic            # LLM post-processing
```

Xiaohongshu requires an additional browser install:

```bash
pipx inject webarticles-to-markdown playwright
pipx runpip webarticles-to-markdown install playwright
python -m playwright install firefox
```

### Option 2: Source install (development / debugging)

```bash
git clone https://github.com/polaris-lo/WebArticles-to-Markdown
cd WebArticles-to-Markdown
pip3 install -e .                   # Install core dependencies
cp config.example.yaml config.yaml  # Edit as needed
webarticles <URL>                   # or: python3 convert.py <URL>
```

Optional features:

```bash
pip3 install wechat-article-to-markdown   # WeChat
pip3 install xreach                        # Twitter/X
pip3 install playwright && playwright install firefox  # Xiaohongshu
pip3 install easyocr                       # OCR (downloads ~1GB model on first run)
```

## Quick Start

```bash
# WeChat
webarticles https://mp.weixin.qq.com/s/YOUR_ARTICLE_ID

# Reddit (use --force-jina if no cookie)
webarticles https://www.reddit.com/r/Python/comments/xyz/ --force-jina

# Weibo (no login required)
webarticles https://weibo.com/status/POST_ID

# Preview without saving
webarticles https://mp.weixin.qq.com/s/xxx --dry-run

# Specify output directory
webarticles https://mp.weixin.qq.com/s/xxx -o ~/notes/clippings
```

## Platform Support

| Platform | Primary | Fallback | Cookie required |
|---|---|---|---|
| WeChat | `wechat-article-to-markdown` (camoufox) | HTTP + BeautifulSoup | No |
| Weibo | HTTP + `$render_data` JSON | Jina Reader | No (public posts) |
| Reddit | JSON API + Cookie | Jina Reader | Yes (post-2023) |
| Xiaohongshu | Playwright headless | `__NEXT_DATA__` HTTP | Yes |
| Twitter/X | `xreach` CLI | Jina → Nitter → placeholder | Yes (xreach) |

## Cookie Setup

### Xiaohongshu

1. Log in to [Xiaohongshu web](https://www.xiaohongshu.com) in Chrome
2. Install [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
3. Click the extension on a Xiaohongshu page → export as Netscape HTTP Cookie format
4. Save as `cookies/xiaohongshu.txt`
5. Pass the cookie file in one of two ways:

   **Option A: per-command (temporary)**
   ```bash
   webarticles https://www.xiaohongshu.com/explore/abc --cookies cookies/xiaohongshu.txt
   ```

   **Option B: in `config.yaml` (permanent, recommended)**
   ```yaml
   platforms:
     xiaohongshu:
       cookies_file: "cookies/xiaohongshu.txt"
   ```

### Reddit

1. Log in to [Reddit](https://www.reddit.com) in Chrome
2. Export cookies using the same extension, save as `cookies/reddit.txt`

### Twitter/X (via xreach)

```bash
pip3 install xreach
# Configure authentication per xreach docs
```

## CLI Options

```text
webarticles <URL> [options]

Options:
  -o, --output DIR       Output directory (default: ./output or config.yaml value)
  --cookies FILE         Netscape cookie file path
  --no-images            Skip image download, keep original CDN URLs
  --dry-run              Print to terminal only, do not write file
  --force-jina           Force Jina Reader (useful for Reddit and paywalled sites)
  --no-jina              Disable Jina Reader fallback
  --comments             Include comments (Reddit)
  --no-comments          Exclude comments
  --print-frontmatter    Print only YAML frontmatter
  --config FILE          Config file path (default: ./config.yaml)
  -v, --verbose          Debug logging
  -q, --quiet            Suppress output
```

## Output Format

Each article is saved as `YYYY-MM-DD-title-slug.md` with YAML frontmatter:

```yaml
---
title: Article Title
source_url: https://...
platform: wechat
author: Author Name
date: 2026-03-17
saved_at: 2026-03-17T14:23:00
tags:
  - tech
  - AI
categories:
  - Account Name
summary: First 200 chars of summary...
language: zh
status: unread
---

# Article body...
```

## OCR Image Text Extraction

Images in Xiaohongshu posts can be automatically OCR-scanned for text (Chinese + English).

```bash
# Recommended (pure Python, Chinese support, downloads ~1GB model on first run)
pip3 install easyocr

# Lightweight alternative (requires system Tesseract + chi_sim language pack)
pip3 install pytesseract pillow
```

Enable in `config.yaml`:

```yaml
platforms:
  xiaohongshu:
    ocr:
      enabled: true
      engine: auto    # auto | easyocr | pytesseract
```

## LLM Post-Processing (Optional)

Connect DeepSeek or Claude to automatically reformat content, remove ads, generate summaries, and run reading analyses.

```bash
# Set API key (one of)
export DEEPSEEK_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

Enable in `config.yaml`:

```yaml
llm:
  enabled: true
  provider: deepseek    # deepseek | claude
  skills:
    critical_reading: true   # Critical reading analysis — best for opinion/discussion articles
    domain_map: true         # Domain knowledge map
```

When enabled, each article's output is structured as:

```text
## 摘要 (Summary)       ← LLM-generated 3–5 sentence Chinese summary
## 导读 (Reading Guide) ← Up to 5 questions based on the article's core ideas
(Article body)
## 批判性阅读（五问法）  ← Optional: logical boundaries, hidden assumptions, applicability, etc.
## 领域知识地图（三问法）← Optional: expert consensus and core disagreements in the domain
```

### Critical Reading Analysis (五问法)

Analyzes the article across five dimensions:

- **Q1 Logical boundaries** — what the article can and cannot conclude; where the author oversteps the evidence
- **Q2 Hidden assumptions** — unstated premises, ignored variables, and their impact on the conclusion
- **Q3 Applicability** — scenarios where the argument breaks down, and what conditions it actually requires
- **Q4 Debate positioning** — what position the article takes, and the strongest counterargument
- **Q5 Missing voices** — perspectives absent from the article and how their absence affects the conclusion

Q4 and Q5 are omitted when not substantive (e.g., pure tutorials).

### Domain Knowledge Map (三问法)

- **Q1 Expert consensus** — 5 core mental models shared across the field
- **Q2 Core disagreements** — 3 areas of genuine debate among experts, with the strongest arguments on each side

## Apple Shortcuts (macOS)

Share a URL from Safari or any app, and save it to Obsidian with one tap.

### Setup

Open the Shortcuts app and create a new shortcut with these actions:

#### Action 1: Receive input from Quick Actions

- Receive: Apps and others (URL or text)
- If no input: continue

#### Action 2: Run Shell Script

- Shell: `zsh`
- Pass input as: stdin

Script (choose based on installation method):

```bash
# ── Option A: pipx install ──────────────────────────────────────
URL=$(cat | tr -d '\n\r')
OUTPUT=$(~/.local/bin/webarticles "$URL" 2>&1)
echo "$OUTPUT" | grep "已保存:" | sed 's/.*已保存: //' | xargs basename
```

```bash
# ── Option B: source + venv install ────────────────────────────
PROJECT=~/path/to/WebArticles-to-Markdown   # ← change to your project path
URL=$(cat | tr -d '\n\r')
OUTPUT=$($PROJECT/.venv/bin/python3 $PROJECT/convert.py "$URL" 2>&1)
echo "$OUTPUT" | grep "已保存:" | sed 's/.*已保存: //' | xargs basename
```

> **Note**: The Shortcuts shell environment does not load `.zshrc`. When using the pipx install, write the full path `~/.local/bin/webarticles` rather than just `webarticles`.

#### Action 3: Show notification

- Content: Shell Script Result (displays the saved filename)

#### Action 4 (optional): Open Obsidian

### Usage

In any app, tap Share → select "Save Article as MD". A notification will appear when the file is saved.

## Obsidian Folder Picker (macOS)

When saving, show a native macOS folder picker to dynamically choose which subfolder in your Obsidian vault to save to — no need to edit config every time.

Enable in `config.yaml`:

```yaml
obsidian:
  vault: "/Users/yourname/Documents/My Vault"   # Absolute path to vault root
  folder_picker: true                            # Show picker dialog on save
```

When enabled, a native macOS folder dialog appears pre-navigated to your vault root. If you cancel, the file falls back to `output_dir`.

## Obsidian Dataview Query

```dataview
TABLE author, date, platform, summary
FROM "WebArticles-to-Markdown/output"
WHERE status = "unread"
SORT date DESC
```

## Notes

- WeChat image CDN links expire over time — enable `images.download: true` to save locally
- Jina Reader is a free online service; content passes through their servers. Use `--no-jina` if privacy is a concern
- Reddit has enforced strict API limits since 2023 — use `--force-jina` when running without cookies
- **Xiaohongshu + local proxy (Clash/V2Ray etc.)**: If you see `EOF occurred in violation of protocol` or Playwright reports `NS_ERROR_NET_INTERRUPT`, your proxy is likely intercepting TLS. Fix: add `xiaohongshu.com` to your proxy's direct-connection rules, or temporarily disable the proxy

---

## About

**WebArticles-to-Markdown** is a CLI tool that converts articles from Chinese social media and content platforms — WeChat, Weibo, Xiaohongshu (Little Red Book), Twitter/X, and Reddit — into structured Markdown files with YAML frontmatter, optimized for use with [Obsidian](https://obsidian.md).

Beyond simple web clipping, it optionally uses an LLM (DeepSeek or Claude) to reformat content, generate Chinese summaries, extract reading-guide questions, and run structured analyses (critical reading and domain knowledge mapping) — turning raw captures into readable, searchable notes.

Runs entirely locally. Designed for macOS, with Apple Shortcuts integration for one-tap saving from any app.
