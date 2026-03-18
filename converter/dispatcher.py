from __future__ import annotations
import logging
import re

from converter.platforms.base import ExtractionError

logger = logging.getLogger(__name__)

# (regex pattern, platform_module_path, platform_class_name)
_ROUTES = [
    (r"mp\.weixin\.qq\.com", "converter.platforms.wechat", "WechatPlatform"),
    (r"(xiaohongshu\.com|xhslink\.com)", "converter.platforms.xiaohongshu", "XiaohongshuPlatform"),
    (r"(weibo\.com|m\.weibo\.cn)", "converter.platforms.weibo", "WeiboPlatform"),
    (r"(twitter\.com|(?<![a-z])x\.com|//t\.co/)", "converter.platforms.twitter", "TwitterPlatform"),
    (r"(reddit\.com|old\.reddit\.com|redd\.it)", "converter.platforms.reddit", "RedditPlatform"),
]


def _load_platform(module_path: str, class_name: str):
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)()


def detect_platform(url: str):
    """Return an instantiated platform extractor for the URL, or None."""
    for pattern, module_path, class_name in _ROUTES:
        if re.search(pattern, url):
            try:
                return _load_platform(module_path, class_name)
            except Exception as exc:
                logger.warning("Could not load platform %s: %s", class_name, exc)
    return None


def extract(url: str, config: dict, cookies: dict, use_jina: bool = True) -> dict:
    """Route the URL to the correct extractor, falling back to Jina Reader."""
    platform = detect_platform(url)

    if platform is not None:
        try:
            result = platform.extract(url, config, cookies)
            if result.get("title") or result.get("body_html"):
                return result
            logger.warning("Platform extractor returned empty result, falling back.")
        except ExtractionError as exc:
            logger.warning("Platform extractor failed (%s), falling back. Reason: %s",
                           type(platform).__name__, exc)

    if use_jina:
        from converter.fallback.jina_reader import JinaReader
        logger.info("Using Jina Reader fallback for: %s", url)
        return JinaReader().extract(url, config, cookies)

    raise ExtractionError(f"Could not extract content from: {url}")
