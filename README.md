# WebArticles-to-Markdown

中文 | [English](README.en.md)

将微信公众号、小红书、微博、Twitter/X、Reddit 等平台的文章/内容转换为结构化 Markdown 文件，支持 YAML frontmatter，本地运行，适配 Obsidian。

参考 [Agent-Reach](https://github.com/Panniantong/Agent-Reach) 的理念：**每个平台用最匹配的专用工具**。在此基础上扩展了以下能力：

- 📷 **图片 OCR**：自动提取小红书帖子中图片的文字（支持中英文，easyocr 或 pytesseract）
- 🤖 **LLM 后处理**：可选接入 DeepSeek / Claude，自动重排版、去广告、生成中文摘要
- 📱 **快捷指令友好**：工具为纯 CLI，可通过 Apple Shortcuts 的「运行 Shell 脚本」动作一键触发
- 🔄 **多层降级策略**：每个平台均设有备用方案，遇到反爬或登录墙自动切换

## 为什么要转换为结构化 Markdown？

社交媒体和内容平台的文章，散落在各个 App 里——收藏了却再也找不到，想引用却无法复制，喂给 AI 时格式混乱难以识别。

现有的网页抓取工具通常只做「搬运」：原样保存 HTML 或粗暴提取文本，不做任何整理。本工具的不同之处在于，抓取只是第一步，之后会引入 LLM 对内容进行重排版——拆分长段、去除广告和导流文字、补充小标题、生成摘要——输出真正可读、可检索的结构化文档。

将它们转换为带 YAML frontmatter 的 Markdown，能解决几个核心问题：

### 在 Obsidian 中管理知识

- YAML frontmatter 中的 `tags`、`platform`、`author`、`status` 等字段，可直接被 Dataview 插件查询，轻松实现「按平台筛选」「标记已读/未读」「按日期排序」等操作
- 文件名格式 `YYYY-MM-DD-标题.md` 天然可排序，在文件系统层面也保持整洁
- 图片本地化下载，不依赖平台 CDN，不会因链接失效而丢失内容

### 适配 AI 辅助阅读与检索

- 结构化的 frontmatter 让 AI 准确识别文章的来源、作者、时间，而不需要从正文中猜测
- 干净的 Markdown 正文（去除广告、导流文字、无关链接）减少噪音，让 AI 聚焦在实际内容上
- 配合 LLM 后处理生成的摘要字段，可以在不读全文的情况下快速让 AI 理解文章要点

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

小红书帖子中的图片可自动 OCR 提取文字，支持中英文。

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

接入 DeepSeek 或 Claude，自动完成：重排版（分段、去广告、补标题）+ 生成中文摘要 + 阅读辅助分析。

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
  skills:
    critical_reading: true   # 批判性阅读五问法（适合观点类/讨论类文章）
    domain_map: true         # 领域知识地图三问法
```

启用后，每篇文章的输出结构如下：

```text
## 摘要          ← LLM 生成的 3-5 句中文总结
## 导读          ← 从文章核心观点提炼的 ≤5 个问题，帮助带着问题读文章
（正文）
## 批判性阅读（五问法）   ← 可选，分析逻辑边界、隐藏假设、适用范围等
## 领域知识地图（三问法） ← 可选，梳理专家共识与核心分歧
```

## Apple Shortcuts 快捷指令（macOS）

在 Safari / 其他 App 分享 URL 时，一键转换并存入 Obsidian。

### 配置步骤

打开「快捷指令」App，新建快捷指令，依次添加以下动作：

#### 动作 1：从「快速操作」接收输入

- 接收：App 和其他（URL / 文本均可）
- 如果没有输入：继续

#### 动作 2：运行 Shell 脚本

- Shell：`zsh`
- 传入输入内容：给 `stdin`

脚本内容（按安装方式二选一）：

```bash
# ── 方式一：pipx 安装 ──────────────────────────────────────────
URL=$(cat | tr -d '\n\r')
OUTPUT=$(~/.local/bin/webarticles "$URL" 2>&1)
echo "$OUTPUT" | grep "已保存:" | sed 's/.*已保存: //' | xargs basename
```

```bash
# ── 方式二：源码 + venv 安装 ──────────────────────────────────
PROJECT=~/path/to/WebArticles-to-Markdown   # ← 改为你的项目路径
URL=$(cat | tr -d '\n\r')
OUTPUT=$($PROJECT/.venv/bin/python3 $PROJECT/convert.py "$URL" 2>&1)
echo "$OUTPUT" | grep "已保存:" | sed 's/.*已保存: //' | xargs basename
```

> **提示**：快捷指令的 Shell 环境不加载 `.zshrc`，所以 pipx 版需要写全路径 `~/.local/bin/webarticles`，而不能直接写 `webarticles`。

#### 动作 3：显示通知

- 内容：Shell 脚本结果（显示保存的文件名）

#### 动作 4（可选）：打开 Obsidian

### 使用方式

在任意 App 点击分享 → 选择「保存文章为 MD」快捷指令，稍等片刻即可收到通知并自动跳转 Obsidian。

## Obsidian 文件夹选择器（macOS）

保存时弹出原生文件夹选择窗口，动态选择保存到 Obsidian Vault 的哪个子目录，无需每次修改配置。

在 `config.yaml` 中启用：

```yaml
obsidian:
  vault: "/Users/yourname/Documents/My Vault"   # Vault 根目录绝对路径
  folder_picker: true                            # 保存前弹出选择窗口
```

启用后，每次运行时会弹出 macOS 原生文件夹选择对话框，默认定位到 Vault 根目录，选择后文件保存至所选子目录。如取消选择，则回退到 `output_dir` 配置。

## Obsidian Dataview 查询

```dataview
TABLE author, date, platform, summary
FROM "WebArticles-to-Markdown/output"
WHERE status = "unread"
SORT date DESC
```

## 注意事项

- 微信图片 CDN 有时效，建议开启 `images.download: true`
- Jina Reader 为免费在线服务，内容会经过其服务器；介意隐私可加 `--no-jina`
- Reddit 自 2023 年起严格限制 API 访问，无 Cookie 时建议使用 `--force-jina`
- **小红书 + 本地代理（Clash/V2Ray 等）**：若运行时出现 `EOF occurred in violation of protocol` 或 Playwright 报 `NS_ERROR_NET_INTERRUPT`，通常是本地代理拦截了 TLS 握手。解决方法：在代理软件中将 `xiaohongshu.com` 加入直连规则（绕过代理），或临时关闭代理后再运行

