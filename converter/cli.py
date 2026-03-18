from __future__ import annotations
import argparse
import logging
import os
import re
import sys

import logging

from ruamel.yaml import YAML

logger = logging.getLogger(__name__)

_yaml = YAML()

# Project root = directory containing this package
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_CONFIG = os.path.join(_PROJECT_ROOT, "config.yaml")


def _load_config(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return _yaml.load(f) or {}
    return {}


def _load_cookies(config: dict, platform_name: str, cli_cookies: str | None) -> dict:
    from converter.utils.cookies import load_cookies_file

    # Priority: CLI flag > config file > default path
    if cli_cookies:
        return load_cookies_file(cli_cookies)

    platforms_cfg = config.get("platforms") or {}
    plat_cfg = platforms_cfg.get(platform_name) or {}
    cfg_path = plat_cfg.get("cookies_file")
    if cfg_path:
        full_path = cfg_path if os.path.isabs(cfg_path) else os.path.join(_PROJECT_ROOT, cfg_path)
        return load_cookies_file(full_path)

    default_path = os.path.join(_PROJECT_ROOT, "cookies", f"{platform_name}.txt")
    return load_cookies_file(default_path)


def main():
    parser = argparse.ArgumentParser(
        description="将网页文章转换为结构化 Markdown 文件",
    )
    parser.add_argument("url", help="要转换的文章 URL")
    parser.add_argument("-o", "--output", metavar="DIR",
                        help="输出目录（默认：config.yaml 中配置，或 ./output）")
    parser.add_argument("--cookies", metavar="FILE",
                        help="Netscape 格式 Cookie 文件路径")
    parser.add_argument("--no-images", action="store_true",
                        help="不下载图片，保留原始 CDN URL")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅打印结果到终端，不写入文件")
    parser.add_argument("--force-jina", action="store_true",
                        help="强制使用 Jina Reader，跳过平台专用解析器")
    parser.add_argument("--no-jina", action="store_true",
                        help="禁用 Jina Reader 兜底")
    parser.add_argument("--comments", action="store_true", default=None,
                        help="包含评论（Reddit 支持，默认：config.yaml 设置）")
    parser.add_argument("--no-comments", action="store_true",
                        help="不包含评论")
    parser.add_argument("--print-frontmatter", action="store_true",
                        help="仅打印 YAML frontmatter 到终端")
    parser.add_argument("--config", metavar="FILE", default=_DEFAULT_CONFIG,
                        help=f"配置文件路径（默认：{_DEFAULT_CONFIG}）")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="显示调试信息")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="静默模式，只显示错误和最终路径")

    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.ERROR
    else:
        level = logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")

    config = _load_config(args.config)

    # Merge comments flag
    if args.no_comments:
        config.setdefault("comments", {})["include"] = False
    elif args.comments:
        config.setdefault("comments", {})["include"] = True

    # Merge images flag
    if args.no_images:
        config.setdefault("images", {})["download"] = False

    # Determine output directory
    output_dir = args.output or config.get("output_dir") or "output"
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(_PROJECT_ROOT, output_dir)

    # Detect platform name early for cookie loading
    from converter.dispatcher import detect_platform
    platform_obj = detect_platform(args.url)
    platform_name = platform_obj.name if platform_obj else "generic"

    cookies = _load_cookies(config, platform_name, args.cookies)

    # Extract content
    try:
        if args.force_jina:
            from converter.fallback.jina_reader import JinaReader
            extracted = JinaReader().extract(args.url, config, cookies)
        else:
            from converter.dispatcher import extract
            use_jina = not args.no_jina and config.get("jina", {}).get("enabled", True)
            extracted = extract(args.url, config, cookies, use_jina=use_jina)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    # Build output
    from converter import frontmatter, markdown_writer
    from markdownify import markdownify as md

    body_html = extracted.pop("body_html", "") or ""
    body_md = extracted.pop("body_md", None)

    if body_md is None:
        body_md = md(body_html, heading_style="ATX", bullets="-") if body_html else ""

    # Optional: LLM restructuring (all platforms)
    llm_cfg = config.get("llm") or {}
    if llm_cfg.get("enabled") and body_md:
        from converter.utils.llm import restructure_with_llm, summarize_with_llm
        llm_kwargs = dict(
            platform=extracted.get("platform", "generic"),
            title=extracted.get("title", ""),
            provider=llm_cfg.get("provider", "deepseek"),
            model=llm_cfg.get("model") or None,
        )
        logger.info("Running LLM restructure (%s)…", llm_kwargs["provider"])
        restructured = restructure_with_llm(body_md, **llm_kwargs)
        if restructured:
            body_md = restructured

        # Always generate a proper Chinese summary via LLM (overrides raw extractor text)
        logger.info("Generating Chinese summary…")
        llm_summary = summarize_with_llm(
            body_md,
            title=extracted.get("title", ""),
            provider=llm_cfg.get("provider", "deepseek"),
            model=llm_cfg.get("model") or None,
        )
        if llm_summary:
            # description = first sentence only (≤100 chars), for frontmatter
            first_sentence = re.split(r"(?<=[。！？.!?])\s*", llm_summary.strip())[0]
            extracted["summary"] = first_sentence[:100]
            # Full summary goes into the body section
            body_md = f"## 摘要\n\n{llm_summary}\n\n---\n\n{body_md}"
        else:
            logger.warning("LLM 摘要生成失败，frontmatter description 将为空")
            extracted["summary"] = ""

    fm_block = frontmatter.build(extracted)

    if args.print_frontmatter:
        print(fm_block)
        return

    full_content = markdown_writer.assemble(fm_block, body_md)

    if args.dry_run:
        print(full_content)
        return

    filepath = markdown_writer.write(full_content, output_dir, extracted)
    if not args.quiet:
        print(f"✅ 已保存: {filepath}")
