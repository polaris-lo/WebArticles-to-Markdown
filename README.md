# WebArticles-to-Markdown

将微信公众号、小红书、微博、Twitter/X、Reddit 等平台的文章/内容转换为结构化 Markdown 文件，支持 YAML frontmatter，本地运行，适配 Obsidian。

参考 [Agent-Reach](https://github.com/Panniantong/Agent-Reach) 的理念：**每个平台用最匹配的专用工具**。在此基础上扩展了以下能力：

- 📷 **图片 OCR**：自动提取小红书/微博帖子中图片的文字（支持中英文，easyocr 或 pytesseract）
- 🤖 **LLM 后处理**：可选接入 DeepSeek / Claude，自动重排版、去广告、生成中文摘要
- 📱 **快捷指令友好**：工具为纯 CLI，可通过 Apple Shortcuts 的「运行 Shell 脚本」动作一键触发
- 🔄 **多层降级策略**：每个平台均设有备用方案，遇到反爬或登录墙自动切换

## 安装

### 方式一：pipx 安装（推荐，全局可用）

```bash
pipx install git+https://github.com/polaris-lo/WebArticles-to-Markdown
```

安装后直接运行：

```bash
webarticles https://mp.weixin.qq.com/s/xxx
webarticles --help
```

可选功能按需安装：

```bash
pipx inject webarticles-to-markdown wechat-article-to-markdown  # 微信公众号
pipx inject webarticles-to-markdown xreach                      # Twitter/X
pipx inject webarticles-to-markdown easyocr                     # 图片 OCR（中英文）
pipx inject webarticles-to-markdown openai anthropic            # LLM 后处理
```

小红书需要额外安装浏览器：

```bash
pipx inject webarticles-to-markdown playwright
pipx runpip webarticles-to-markdown install playwright
python -m playwright install firefox
```

### 方式二：源码安装（开发 / 调试用）

```bash
git clone https://github.com/polaris-lo/WebArticles-to-Markdown
cd WebArticles-to-Markdown
pip3 install -e .                   # 安装核心依赖
cp config.example.yaml config.yaml  # 按需修改配置
webarticles <URL>                   # 或 python3 convert.py <URL>
```

可选功能：

```bash
pip3 install wechat-article-to-markdown   # 微信
pip3 install xreach                        # Twitter/X
pip3 install playwright && playwright install firefox  # 小红书
pip3 install easyocr                       # OCR（首次运行下载约 1GB 模型）
```

## 快速开始

```bash
# 微信公众号
webarticles https://mp.weixin.qq.com/s/YOUR_ARTICLE_ID

# Reddit（需要 Cookie，或使用 --force-jina 兜底）
webarticles https://www.reddit.com/r/Python/comments/xyz/ --force-jina

# 微博（无需登录）
webarticles https://weibo.com/status/POST_ID

# 预览内容（不写入文件）
webarticles https://mp.weixin.qq.com/s/xxx --dry-run

# 指定输出目录
webarticles https://mp.weixin.qq.com/s/xxx -o ~/notes/clippings
```

## 平台支持详情

| 平台 | 主要方案 | 降级方案 | 是否需要 Cookie |
| --- | --- | --- | --- |
| 微信公众号 | `wechat-article-to-markdown`（camoufox） | HTTP + BeautifulSoup | 否 |
| 微博 | HTTP + `$render_data` JSON | Jina Reader | 否（公开帖） |
| Reddit | JSON API + Cookie | Jina Reader | 需要（2023年后） |
| 小红书 | Playwright headless | `__NEXT_DATA__` HTTP | 需要 |
| Twitter/X | `xreach` CLI | Jina → Nitter → 占位符 | 需要（xreach） |

## Cookie 配置

### 小红书

1. 在 Chrome 中登录 [小红书网页版](https://www.xiaohongshu.com)
2. 安装 [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) 扩展
3. 在小红书页面点击扩展图标 → **导出 Netscape HTTP Cookie 文件（cookies.txt 格式）**
4. 保存为 `cookies/xiaohongshu.txt`
5. 使用时有两种方式传入 Cookie：

   **方式一：每次命令指定（临时）**

   ```bash
   webarticles https://www.xiaohongshu.com/explore/abc --cookies cookies/xiaohongshu.txt
   ```

   **方式二：写入 `config.yaml`（永久，推荐）**

   ```yaml
   platforms:
     xiaohongshu:
       cookies_file: "cookies/xiaohongshu.txt"
   ```

   配置后直接运行即可，无需每次加 `--cookies` 参数：

   ```bash
   webarticles https://www.xiaohongshu.com/explore/abc
   ```

### Reddit

1. 在 Chrome 中登录 [Reddit](https://www.reddit.com)
2. 同上方法（Get cookies.txt LOCALLY 扩展）导出，保存为 `cookies/reddit.txt`

### Twitter/X（使用 xreach）

```bash
# 安装后配置 Cookie（在 Chrome 中导出 Twitter cookies）
pip3 install xreach
# 按 xreach 文档配置认证
```

### 指定 Cookie 文件

```bash
webarticles https://www.xiaohongshu.com/explore/abc --cookies cookies/xiaohongshu.txt
```

## 完整参数

```text
webarticles <URL> [选项]

选项:
  -o, --output DIR       输出目录（默认：./output 或 config.yaml 中设置）
  --cookies FILE         Netscape Cookie 文件路径
  --no-images            不下载图片，保留原始 CDN URL
  --dry-run              仅打印到终端，不写入文件
  --force-jina           强制使用 Jina Reader（适合 Reddit 等需要认证的平台）
  --no-jina              禁用 Jina Reader 兜底
  --comments             包含评论（Reddit 支持）
  --no-comments          不包含评论
  --print-frontmatter    仅打印 YAML frontmatter
  --config FILE          指定配置文件（默认：./config.yaml）
  -v, --verbose          显示调试信息
  -q, --quiet            静默模式
```

## 输出格式

每篇文章生成 `YYYY-MM-DD-标题slug.md`，包含 YAML frontmatter：

```yaml
---
title: 文章标题
source_url: https://...
platform: wechat
author: 作者名
date: 2026-03-17
saved_at: 2026-03-17T14:23:00
tags:
  - 科技
  - AI
categories:
  - 公众号名称
summary: 文章摘要前200字...
language: zh
status: unread
---

# 正文内容...
```

## OCR 图片文字提取

小红书和微博帖子中的图片可自动 OCR 提取文字，支持中英文。

```bash
# 推荐（纯 Python，支持中文，首次运行会下载约 1GB 模型）
pip3 install easyocr

# 轻量替代（需要系统安装 Tesseract + chi_sim 语言包）
pip3 install pytesseract pillow
```

在 `config.yaml` 中启用：

```yaml
platforms:
  xiaohongshu:
    ocr:
      enabled: true
      engine: auto    # auto | easyocr | pytesseract
```

## LLM 后处理（可选）

接入 DeepSeek 或 Claude，自动完成：重排版（分段、去广告、补标题）+ 生成中文摘要。

```bash
# 设置 API Key（二选一）
export DEEPSEEK_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

在 `config.yaml` 中启用：

```yaml
llm:
  enabled: true
  provider: deepseek    # deepseek | claude
```

## Obsidian Dataview 查询

```dataview
TABLE author, date, platform, summary
FROM "WebArticles-to-Markdown/output"
WHERE status = "unread"
SORT date DESC
```

## 注意事项

- `cookies/` 目录已加入 `.gitignore`，Cookie 文件不会被提交
- 微信图片 CDN 有时效，建议开启 `images.download: true`
- Jina Reader 为免费在线服务，内容会经过其服务器；介意隐私可加 `--no-jina`
- Reddit 自 2023 年起严格限制 API 访问，无 Cookie 时建议使用 `--force-jina`
- **小红书 + 本地代理（Clash/V2Ray 等）**：若运行时出现 `EOF occurred in violation of protocol` 或 Playwright 报 `NS_ERROR_NET_INTERRUPT`，通常是本地代理拦截了 TLS 握手。解决方法：在代理软件中将 `xiaohongshu.com` 加入直连规则（绕过代理），或临时关闭代理后再运行
