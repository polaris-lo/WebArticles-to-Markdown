"""LLM utilities — OCR cleanup and general content restructuring.

Supported providers: ``deepseek`` (default, OpenAI-compatible), ``claude``.

API key resolution order (DeepSeek):
  1. ``api_key`` argument
  2. ``DEEPSEEK_API_KEY`` environment variable
  3. Key file at ``~/.config/webarticles/deepseek_api_key``

API key resolution (Claude):
  1. ``api_key`` argument
  2. ``ANTHROPIC_API_KEY`` environment variable
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_PROVIDER_DEFAULTS = {
    "deepseek": ("deepseek-chat", "https://api.deepseek.com"),
    "claude":   ("claude-haiku-4-5-20251001", None),
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def cleanup_ocr_with_llm(
    raw_ocr: str,
    desc: str = "",
    *,
    source_description: str = "从小红书帖子的图片中",
    provider: str = "deepseek",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str | None:
    """Clean up raw OCR text from image extraction.

    Returns cleaned Markdown, or ``None`` if the call is skipped / fails.
    """
    context_block = (
        f"\n【原帖说明文字（仅供参考）】\n{desc.strip()}" if desc.strip() else ""
    )
    prompt = (
        f"以下是{source_description}通过 OCR 批量提取的原始文字。"
        "由于是多张图片拼接，可能含有乱码、重复内容、识别错误或格式混乱。"
        f"{context_block}\n\n"
        "【OCR 原始文字】\n"
        f"{raw_ocr}\n\n"
        "请帮我整理，规则如下：\n"
        "- 去除乱码、无意义符号和明显的 OCR 识别错误\n"
        "- 基于语义尽量多地分段，段落宜短，便于 ADHD 友好阅读\n"
        "- 段落内若有编号（1. 2. 3.）或字母（a. b. c.）标记的并列论点，一律另起一行格式化为列表\n"
        "- 保留原有结构（如标题、步骤、列表、代码块等）\n"
        "- 直接输出整理后的 Markdown，不要添加任何说明或前言"
    )
    return _call(prompt, provider=provider, model=model, api_key=api_key, base_url=base_url)


def restructure_with_llm(
    body_md: str,
    *,
    platform: str = "generic",
    title: str = "",
    provider: str = "deepseek",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str | None:
    """Restructure an already-converted Markdown body for readability.

    Used as a general post-processing step for all platforms (WeChat, Reddit, etc.).
    Returns restructured Markdown, or ``None`` if the call is skipped / fails.
    """
    platform_hints = {
        "wechat":      "这是一篇微信公众号文章，可能含有广告推荐语、二维码描述文字或无关的推送引导语，请一并去除。",
        "reddit":      (
            "这是一条 Reddit 帖子（含楼主正文和若干评论），保留英文原文，不需要翻译。"
            "请按以下结构整理：\n"
            "1. **OP**：保留楼主原帖内容，适当精简\n"
            "2. **Key Points**：综合评论区主要观点，整理成要点列表；每个要点引用最能代表该观点的原声英文短句（blockquote 格式）\n"
            "3. **Notable Details**（可选）：特别有价值的具体建议、数据或案例，保留原文引用\n"
            "删除重复、无实质内容的评论（如 '+1'、表情包描述等）。"
        ),
        "weibo":       (
            "这是一条微博内容，可能包含正文文字和话题标签。\n"
            "请执行以下处理：\n"
            "- 将大段连续文字基于语义拆分为短段落，尽量多地分段，便于 ADHD 友好阅读\n"
            "- 段落内若有编号（1. 2. 3.）或字母（a. b. c.）标记的论点，一律将每个论点另起一行，格式化为列表\n"
            "- 保留话题标签（#话题#）"
        ),
        "twitter":     (
            "这是一条推文或推文串。"
            "正文开头可能含有 Twitter/X 的登录提示（如 'Don't miss what's happening'、'Log in'、'Sign up' 等），"
            "请将这些内容全部删除，只保留推文实质内容和所分享的文章正文。"
            "保持原文语言，不做翻译。"
        ),
        "xiaohongshu": "这是一篇小红书图文笔记，请整理格式。",
    }
    hint = platform_hints.get(platform, "")
    title_line = f"文章标题：{title}\n\n" if title else ""

    # Detect content language to prevent the LLM from translating
    cjk_count = sum(1 for c in body_md if "\u4e00" <= c <= "\u9fff")
    is_chinese = cjk_count / max(len(body_md), 1) > 0.15
    lang_instruction = (
        "**语言**：原文为中文，保持中文输出，不要翻译。\n"
        if is_chinese else
        "**语言**：原文为英文（或其他非中文语言），必须保持原文语言输出，严禁将任何内容翻译成中文。\n"
    )

    prompt = (
        f"{title_line}"
        f"以下是从网页文章转换而来的 Markdown 原文。{hint}\n\n"
        "【原始 Markdown】\n"
        f"{body_md}\n\n"
        "请帮我整理排版，规则如下：\n\n"
        f"{lang_instruction}\n"
        "**内容清理**\n"
        "- 去除无关内容（广告、推荐阅读、二维码描述、无意义的元数据等）\n"
        "- 保留原文所有实质性内容，不要删减或改写正文文字\n\n"
        "**段落处理（ADHD 友好）**\n"
        "- 如果原文存在大段连续文字，请基于语义将其拆分为更多短段落，尽量多分段\n"
        "- 段落内若有用编号（1. 2. 3.）或字母（a. b. c.）标记的并列论点，无论是否在同一行，一律将每个论点另起一行，格式化为有序或无序列表\n"
        "- 如果原文段落已经较短、结构已经清晰，保持原样即可\n\n"
        "**标题层级**\n"
        "- 如果全文只有一级标题（或完全没有标题）且正文较长，请根据语义为各部分补充二级、三级标题\n"
        "- 如果原文已有丰富的多级标题结构，保持原样，不要修改标题\n\n"
        "直接输出整理后的 Markdown，不要添加任何说明或前言"
    )
    return _call(prompt, provider=provider, model=model, api_key=api_key, base_url=base_url)


def summarize_with_llm(
    body_md: str,
    *,
    title: str = "",
    provider: str = "deepseek",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str | None:
    """Generate a concise Chinese summary for non-Chinese content.

    Returns a 3–5 sentence Chinese summary, or ``None`` if the call fails.
    """
    title_line = f"文章标题：{title}\n\n" if title else ""
    prompt = (
        f"{title_line}"
        "以下是一篇文章或讨论的 Markdown 正文。请用中文写 3–5 句话的摘要，"
        "概括核心议题、主要观点和结论，便于读者快速了解全文内容。"
        "直接输出摘要文字，不要加标题、前言或任何额外说明。\n\n"
        f"{body_md[:3000]}"  # cap to avoid huge prompts
    )
    return _call(prompt, provider=provider, model=model, api_key=api_key, base_url=base_url)


def analyze_critical_reading_with_llm(
    body_md: str,
    *,
    title: str = "",
    provider: str = "deepseek",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str | None:
    """Run a batch critical-reading analysis (五问法) on the article body.

    Adapts the interactive thinking-skills framework into a single non-interactive
    LLM pass. Returns structured Markdown with Q1–Q5 sections, or ``None`` on failure.
    """
    title_line = f"【文章标题】{title}\n\n" if title else ""
    prompt = (
        "你是一位批判性思维分析师。请用中文对以下文章进行批判性阅读分析，依次回答五个问题。\n\n"
        "写作要求：\n"
        "- 表达简明易懂，避免学术腔；每条尽量一句话说清楚\n"
        "- 宁缺毋滥：只写真正有力的论点，牵强或有抬杠嫌疑的直接跳过\n"
        "- 每条观点尽量引用文章中的具体论点或例子作为依据，避免空泛断言\n\n"
        "### Q1 逻辑边界\n"
        "分两部分回答：\n"
        "- **能推出的结论**：文章最有力地论证了什么？一两句话概括即可。\n"
        "- **不能推出的结论**：先在脑中列举多个文章无法证明的方向，只写其中最有力的一个。"
        "详细说明原因，可以从多个角度解释（例如：作者跨越了证据边界、把个案当普遍规律、"
        "把相关性说成因果、前提条件不成立等），引用文章中的具体论断来佐证。\n\n"
        "### Q2 隐藏假设\n"
        "分三部分回答：\n"
        "- **预设前提**：作者的逻辑暗中依赖哪些未经论证的前提？\n"
        "- **忽略的关键变量**：有哪些重要因素被忽略了？\n"
        "- **对结论的影响**：如果把这些变量纳入考虑，核心结论会如何改变？\n\n"
        "### Q3 适用范围\n"
        "分两部分回答：\n"
        "- **失效情境**：在哪些具体场景下，文章的结论会不适用或效果打折？\n"
        "- **边界条件**：这个方法/结论更适合哪类读者、项目或情境？\n\n"
        "### Q4 论辩定位\n"
        "只在文章涉及实质性争论时才写；如果文章是纯教程或操作指南，整个Q4可以省略。\n"
        "分两部分回答：\n"
        "- **回应的争论**：文章在反驳什么观点或现象？\n"
        "- **对立观点的最有力反驳**：站在反对者角度，最有说服力的一个论点是什么？"
        "然后说明作者的回应是否足够有力。\n\n"
        "### Q5 缺失声音\n"
        "只在缺失的视角会实质性影响结论时才写；如果影响不大，整个Q5可以省略。\n"
        "分两部分回答：\n"
        "- **缺失的视角**：哪个重要的相关方或角度完全没有出现？\n"
        "- **对结论的影响**：这个视角的缺席如何让结论变得片面或不完整？\n\n"
        "直接输出分析内容，保留以上标题格式，不要添加前言或总结。\n\n"
        f"{title_line}"
        "【文章正文】\n"
        f"{body_md[:4000]}"
    )
    return _call(prompt, provider=provider, model=model, api_key=api_key, base_url=base_url)


def analyze_domain_map_with_llm(
    body_md: str,
    *,
    title: str = "",
    provider: str = "deepseek",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str | None:
    """Run a batch domain-knowledge mapping analysis (三问法 Q1+Q2) on the article body.

    Adapts the interactive thinking-skills framework into a single non-interactive
    LLM pass. Returns structured Markdown with Q1–Q2 sections, or ``None`` on failure.
    """
    title_line = f"【文章标题】{title}\n\n" if title else ""
    prompt = (
        "你是一位领域知识分析师。请用中文梳理以下文章涉及的领域知识，"
        "依次回答两个问题。\n\n"
        "写作要求：\n"
        "- 表达简明易懂，用普通读者能理解的说法，避免堆砌术语\n"
        "- 每个要点尽量一句话说清楚核心意思，说不清楚的宁可不写\n"
        "- 宁缺毋滥：不必强行凑足条数，只写真正能说清楚的要点\n\n"
        "### Q1 专家共识\n"
        "该领域所有专家共享的5个核心心智模型是什么？\n\n"
        "### Q2 核心分歧\n"
        "专家之间存在根本分歧的3个领域是什么？各方最有力的论点是什么？\n\n"
        "直接输出分析内容，保留以上标题格式，不要添加前言或总结。\n\n"
        f"{title_line}"
        "【文章正文】\n"
        f"{body_md[:4000]}"
    )
    return _call(prompt, provider=provider, model=model, api_key=api_key, base_url=base_url)


def extract_reading_questions_with_llm(
    body_md: str,
    *,
    title: str = "",
    provider: str = "deepseek",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str | None:
    """Generate a reading guide based on the article's own core ideas.

    Identifies the key concepts and knowledge points the author actually answers,
    then turns them into questions for the reader to seek out while reading.
    Returns a Markdown bullet list, or ``None`` on failure.
    """
    title_line = f"【文章标题】{title}\n\n" if title else ""
    prompt = (
        "请根据以下文章，提炼出作者在文中实际给出了答案的核心知识点或核心观点，"
        "然后把它们变成问题，帮助读者带着问题去读文章、在文中找答案。\n\n"
        "要求：\n"
        "- 最多5个问题，只选最核心的，宁少勿多\n"
        "- 每个问题控制在20字以内，简洁直接\n"
        "- 问题必须是文章里有明确答案的，不要出开放性或文章没有回答的问题\n"
        "- 直接输出问题列表（Markdown 无序列表格式），不要加标题、前言或说明\n\n"
        f"{title_line}"
        "【文章正文】\n"
        f"{body_md[:3000]}"
    )
    return _call(prompt, provider=provider, model=model, api_key=api_key, base_url=base_url)


# ---------------------------------------------------------------------------
# Internal dispatch
# ---------------------------------------------------------------------------

def _call(
    prompt: str,
    *,
    provider: str,
    model: str | None,
    api_key: str | None,
    base_url: str | None,
) -> str | None:
    provider = provider.lower()
    default_model, default_base = _PROVIDER_DEFAULTS.get(provider, _PROVIDER_DEFAULTS["deepseek"])

    if provider == "claude":
        return _call_claude(prompt, model or default_model, api_key)
    return _call_openai_compat(
        prompt,
        model or default_model,
        api_key or _resolve_deepseek_key(),
        base_url or default_base,
    )


def _resolve_deepseek_key() -> str | None:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    key_file = os.path.expanduser("~/.config/webarticles/deepseek_api_key")
    if os.path.isfile(key_file):
        with open(key_file) as f:
            key = f.read().strip()
        if key:
            logger.debug("DeepSeek API key loaded from %s", key_file)
            return key
    return None


def _call_openai_compat(prompt: str, model: str, api_key: str | None, base_url: str) -> str | None:
    if not api_key:
        logger.warning("DeepSeek API key 未设置，跳过 LLM。设置 DEEPSEEK_API_KEY 环境变量或写入 ~/.config/webarticles/deepseek_api_key")
        return None
    try:
        from openai import OpenAI
    except ImportError:
        logger.debug("openai 未安装，跳过 LLM（pip install openai）")
        return None
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("LLM 调用失败 (%s): %s", model, exc)
        return None


def _call_claude(prompt: str, model: str, api_key: str | None) -> str | None:
    resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not resolved_key:
        logger.debug("ANTHROPIC_API_KEY 未设置，跳过 LLM")
        return None
    try:
        import anthropic
    except ImportError:
        logger.debug("anthropic 未安装，跳过 LLM（pip install anthropic）")
        return None
    try:
        client = anthropic.Anthropic(api_key=resolved_key)
        message = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as exc:
        logger.warning("LLM 调用失败 (%s): %s", model, exc)
        return None
