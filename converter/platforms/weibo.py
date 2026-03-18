from __future__ import annotations
import json
import logging
import re

from bs4 import BeautifulSoup

from converter.platforms.base import BasePlatform, ExtractionError
from converter.utils import http
from converter.utils.date_parser import parse_date
from converter.utils.ocr import ocr_available, ocr_image

logger = logging.getLogger(__name__)


class WeiboPlatform(BasePlatform):
    name = "weibo"

    def extract(self, url: str, config: dict, cookies: dict) -> dict:
        mobile_url = self._to_mobile_url(url)
        logger.debug("Weibo mobile URL: %s", mobile_url)

        try:
            resp = http.get(mobile_url, cookies=cookies, timeout=20, bypass_proxy=True)
            # Follow JavaScript location.replace() redirects (Weibo login-gate pattern)
            js_redirect = re.search(r'location\.replace\(["\']([^"\']+)["\']\)', resp.text)
            if js_redirect:
                redirect_url = js_redirect.group(1)
                logger.debug("Weibo JS redirect → %s", redirect_url)
                resp = http.get(redirect_url, cookies=cookies, timeout=20, bypass_proxy=True)
        except Exception as exc:
            raise ExtractionError(f"Weibo fetch failed: {exc}") from exc

        # Try $render_data JSON extraction first
        post_data = self._extract_render_data(resp.text)

        if post_data:
            return self._parse_from_json(post_data, url, config)

        # Fallback: parse HTML directly (less reliable)
        return self._parse_from_html(resp.text, url)

    def _to_mobile_url(self, url: str) -> str:
        """Convert desktop Weibo URL to mobile version."""
        # Handle m.weibo.cn already
        if "m.weibo.cn" in url:
            return url

        # weibo.com/USER/POST_ID → m.weibo.cn/detail/POST_ID
        m = re.search(r"weibo\.com/\w+/(\w+)", url)
        if m:
            return f"https://m.weibo.cn/detail/{m.group(1)}"

        # weibo.com/status/POST_ID
        m = re.search(r"weibo\.com/status/(\w+)", url)
        if m:
            return f"https://m.weibo.cn/detail/{m.group(1)}"

        # Already numeric ID format
        return url.replace("www.weibo.com", "m.weibo.cn").replace("weibo.com", "m.weibo.cn")

    def _extract_render_data(self, html: str) -> dict | None:
        """Extract $render_data JSON embedded in page script."""
        idx = html.find("$render_data = [")
        if idx == -1:
            return None
        try:
            start = html.index("[", idx)
            data, _ = json.JSONDecoder().raw_decode(html, start)
            # Structure: [{status: {...}}, ...]
            if isinstance(data, list) and data:
                return data[0].get("status") or data[0]
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        return None

    def _parse_from_json(self, post: dict, url: str, config: dict | None = None) -> dict:
        """Parse weibo post from the $render_data JSON blob."""
        text_html = post.get("text", "")
        user = post.get("user") or {}
        author = user.get("screen_name", "")
        date_raw = post.get("created_at", "")
        date = parse_date(date_raw)

        # Extract hashtags from text
        tags = re.findall(r"#([^#]+)#", text_html)

        # Retweeted post info
        extra = {}
        retweeted = post.get("retweeted_status")
        if retweeted:
            rt_user = (retweeted.get("user") or {}).get("screen_name", "")
            extra["retweeted_from"] = f"@{rt_user}"
            rt_text = retweeted.get("text", "")
            text_html += f'<hr/><blockquote><p><strong>转自 @{rt_user}：</strong></p>{rt_text}</blockquote>'

        # Clean up Weibo-specific HTML tags like <a href="/n/...">@user</a>
        soup = BeautifulSoup(text_html, "lxml")
        # Replace <br> with newlines
        for br in soup.find_all("br"):
            br.replace_with("\n")

        plain_text = soup.get_text(separator="\n", strip=True)
        summary = plain_text[:200]

        extra.update({
            "reposts_count": post.get("reposts_count"),
            "comments_count": post.get("comments_count"),
            "attitudes_count": post.get("attitudes_count"),
        })

        base = {
            "title": plain_text[:50] + ("..." if len(plain_text) > 50 else ""),
            "author": author,
            "date": date,
            "platform": self.name,
            "source_url": url,
            "tags": tags,
            "categories": [f"@{author}"] if author else [],
            "summary": summary,
            "extra": {k: v for k, v in extra.items() if v is not None},
        }

        # Image OCR: extract article images and OCR them
        image_urls = self._extract_image_urls(post)
        ocr_cfg = (config or {}).get("platforms", {}).get("weibo", {}).get("ocr", {})
        do_ocr = ocr_cfg.get("enabled", True) and image_urls and ocr_available(
            ocr_cfg.get("engine", "auto")
        )

        if do_ocr:
            llm_cfg = (config or {}).get("llm") or {}
            body_md = self._build_body_with_ocr(
                plain_text, image_urls, ocr_cfg.get("engine", "auto"), llm_cfg
            )
            base["body_md"] = body_md
        else:
            base["body_html"] = text_html

        return base

    def _extract_image_urls(self, post: dict) -> list[str]:
        """Extract image URLs from Weibo post JSON (pics array)."""
        urls = []
        for pic in post.get("pics") or []:
            large = pic.get("large") or {}
            url = large.get("url") or pic.get("url", "")
            if url:
                urls.append(url)
        return urls

    def _build_body_with_ocr(
        self, caption: str, image_urls: list[str], engine: str, llm_cfg: dict | None = None
    ) -> str:
        """Combine Chinese caption with OCR'd image text (typically English article)."""
        from converter.utils.llm import cleanup_ocr_with_llm

        lines: list[str] = []

        if caption.strip():
            lines.append("## 博主译文\n")
            lines.append(caption.strip())
            lines.append("")

        ocr_sections: list[str] = []
        for idx, img_url in enumerate(image_urls, start=1):
            try:
                resp = http.get(img_url, timeout=20, bypass_proxy=True)
                ocr_text = ocr_image(resp.content, engine=engine)
            except Exception as exc:
                logger.debug("图片 %d OCR 失败: %s", idx, exc)
                ocr_text = None
            if ocr_text and ocr_text.strip():
                ocr_sections.append(ocr_text.strip())

        if not ocr_sections:
            return "\n".join(lines)

        raw_ocr = "\n\n".join(ocr_sections)

        cfg = llm_cfg or {}
        if cfg.get("enabled", True):
            cleaned = cleanup_ocr_with_llm(
                raw_ocr,
                desc=caption,
                source_description="从微博帖子的图片中",
                provider=cfg.get("provider", "deepseek"),
                model=cfg.get("model") or None,
            )
            if cleaned:
                raw_ocr = cleaned

        lines.append("## 原文\n")
        lines.append(raw_ocr)
        lines.append("")

        return "\n".join(lines)

    def _parse_from_html(self, html: str, url: str) -> dict:
        """Fallback: parse Weibo HTML directly."""
        soup = BeautifulSoup(html, "lxml")

        content = soup.select_one(".weibo-text") or soup.select_one(".WB_text")
        if not content:
            raise ExtractionError("Could not find Weibo post content in HTML")

        text = content.get_text(strip=True)
        tags = re.findall(r"#([^#]+)#", text)

        return {
            "title": text[:50] + "...",
            "author": "",
            "date": parse_date(None),
            "platform": self.name,
            "source_url": url,
            "tags": tags,
            "categories": [],
            "summary": text[:200],
            "body_html": str(content),
        }
