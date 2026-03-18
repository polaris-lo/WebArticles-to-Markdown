from __future__ import annotations
import json
import logging
import re

from bs4 import BeautifulSoup

from converter.platforms.base import BasePlatform, ExtractionError
from converter.utils import http
from converter.utils.date_parser import parse_date
from converter.utils.llm import cleanup_ocr_with_llm
from converter.utils.ocr import ocr_available, ocr_image

logger = logging.getLogger(__name__)


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


class XiaohongshuPlatform(BasePlatform):
    name = "xiaohongshu"

    def extract(self, url: str, config: dict, cookies: dict) -> dict:
        # Resolve short links
        url = self._resolve_short_url(url)

        # Tier 1: Playwright (most reliable — handles JS rendering + cookie injection)
        if _playwright_available() and cookies:
            try:
                return self._extract_via_playwright(url, cookies, config)
            except Exception as exc:
                logger.debug("Playwright extraction failed (%s), falling back to HTTP", exc)

        if not cookies:
            logger.warning(
                "小红书需要登录 Cookie。请将 cookies 保存到 cookies/xiaohongshu.txt\n"
                "获取方式：在 Chrome 中登录小红书后，使用 EditThisCookie 插件导出 Netscape 格式\n"
                "可选：pip install playwright && playwright install firefox"
            )

        # Tier 2: HTTP + __NEXT_DATA__ JSON parsing
        try:
            resp = http.get(url, cookies=cookies, timeout=20, bypass_proxy=True)
        except Exception as exc:
            raise ExtractionError(f"小红书 fetch failed: {exc}") from exc

        # Try __NEXT_DATA__ JSON extraction (most reliable)
        note = self._extract_next_data(resp.text)
        if note:
            return self._parse_from_json(note, url, config)

        # Fallback: parse HTML
        return self._parse_from_html(resp.text, url, config)

    def _extract_via_playwright(self, url: str, cookies: dict, config: dict | None = None) -> dict:
        """Use Playwright headless Firefox to extract XHS note content."""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.firefox.launch(
                headless=True,
                firefox_user_prefs={"network.proxy.type": 0},  # 0 = direct, no proxy
            )
            context = browser.new_context()

            # Inject cookies
            pw_cookies = [
                {"name": k, "value": v, "domain": ".xiaohongshu.com", "path": "/"}
                for k, v in cookies.items()
            ]
            context.add_cookies(pw_cookies)

            page = context.new_page()
            page.goto(url, timeout=30000, wait_until="networkidle")

            # Wait for __NEXT_DATA__ to be populated
            html = page.content()
            browser.close()

        note = self._extract_next_data(html)
        if note:
            return self._parse_from_json(note, url, config)

        # Try plain HTML parsing on the rendered page
        return self._parse_from_html(html, url, config)

    def _resolve_short_url(self, url: str) -> str:
        if "xhslink.com" not in url:
            return url
        try:
            resp = http.get(url, timeout=10, bypass_proxy=True)
            return str(resp.url)
        except Exception:
            return url

    def _extract_next_data(self, html: str) -> dict | None:
        """Extract note data from __NEXT_DATA__ script tag."""
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', html, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(1))
            # Navigate to note data - path varies by XHS version
            note = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("initialState", {})
                    .get("note", {})
                    .get("noteDetailMap", {})
            )
            if note:
                # Get first (and usually only) note
                first_key = next(iter(note))
                return note[first_key].get("note", {})
        except (json.JSONDecodeError, StopIteration, AttributeError):
            pass
        return None

    def _parse_from_json(self, note: dict, url: str, config: dict | None = None) -> dict:
        title = note.get("title") or note.get("desc", "")[:50]
        desc = note.get("desc", "")
        author_info = note.get("user") or {}
        author = author_info.get("nickname") or author_info.get("user_id", "")
        date_raw = note.get("time") or note.get("createTime")
        date = parse_date(date_raw)

        # Tags: both topic tags and hashtags from desc
        tag_list = [t.get("name", "") for t in (note.get("tagList") or []) if t.get("name")]
        hashtags = re.findall(r"#([^\s#]+)", desc)
        tags = list(dict.fromkeys(tag_list + hashtags))  # deduplicate preserving order

        # Images + optional OCR
        img_list = note.get("imageList") or []
        ocr_cfg = (config or {}).get("platforms", {}).get("xiaohongshu", {}).get("ocr", {})
        do_ocr = ocr_cfg.get("enabled", True) and img_list and ocr_available(
            ocr_cfg.get("engine", "auto")
        )

        if do_ocr:
            llm_cfg = (config or {}).get("llm") or {}
            body_md = self._build_body_with_ocr(desc, img_list, ocr_cfg.get("engine", "auto"), llm_cfg)
        else:
            # Plain layout: desc paragraph + image tags
            img_html = ""
            for img in img_list:
                src = img.get("urlDefault") or img.get("url", "")
                if src:
                    img_html += f'<img src="{src}" alt=""/>\n'
            body_html = f"<p>{desc}</p>\n{img_html}"
            return {
                "title": title or desc[:50],
                "author": author,
                "date": date,
                "platform": self.name,
                "source_url": url,
                "tags": tags,
                "categories": [f"@{author}"] if author else [],
                "summary": desc[:200],
                "body_html": body_html,
                "extra": {
                    "likes": note.get("likedCount"),
                    "collects": note.get("collectedCount"),
                    "comments": note.get("commentCount"),
                },
            }

        return {
            "title": title or desc[:50],
            "author": author,
            "date": date,
            "platform": self.name,
            "source_url": url,
            "tags": tags,
            "categories": [f"@{author}"] if author else [],
            "summary": desc[:200],
            "body_md": body_md,
            "extra": {
                "likes": note.get("likedCount"),
                "collects": note.get("collectedCount"),
                "comments": note.get("commentCount"),
            },
        }

    def _build_body_with_ocr(self, desc: str, img_list: list, engine: str, llm_cfg: dict | None = None) -> str:
        """Download each image, run OCR, optionally clean up with LLM, and assemble Markdown.

        Structure:
            ## 导览
            <original desc text>

            ## 图文内容
            <LLM-cleaned OCR text, or raw OCR if LLM unavailable>
        """
        lines: list[str] = []

        # --- Overview / summary section (original post text) ---
        if desc.strip():
            lines.append("## 导览\n")
            lines.append(desc.strip())
            lines.append("")

        # --- OCR text from all images ---
        ocr_sections: list[str] = []
        for idx, img in enumerate(img_list, start=1):
            src = img.get("urlDefault") or img.get("url", "")
            if not src:
                continue
            try:
                resp = http.get(src, timeout=20, bypass_proxy=True)
                ocr_text = ocr_image(resp.content, engine=engine)
            except Exception as exc:
                logger.debug("图片 %d OCR 失败: %s", idx, exc)
                ocr_text = None

            if ocr_text and ocr_text.strip():
                ocr_sections.append(ocr_text.strip())

        if not ocr_sections:
            return "\n".join(lines)

        raw_ocr = "\n\n".join(ocr_sections)

        # --- LLM cleanup ---
        cfg = llm_cfg or {}
        if cfg.get("enabled", True):
            cleaned = cleanup_ocr_with_llm(
                raw_ocr,
                desc=desc,
                provider=cfg.get("provider", "deepseek"),
                model=cfg.get("model") or None,
            )
            if cleaned:
                logger.debug("OCR LLM 清理完成")
                raw_ocr = cleaned

        lines.append("## 图文内容\n")
        lines.append(raw_ocr)
        lines.append("")

        return "\n".join(lines)

    def _parse_from_html(self, html: str, url: str, config: dict | None = None) -> dict:
        """Fallback HTML parsing for XHS."""
        soup = BeautifulSoup(html, "lxml")

        title = ""
        title_el = soup.select_one("h1") or soup.select_one(".note-title")
        if title_el:
            title = title_el.get_text(strip=True)

        desc_el = soup.select_one(".note-content") or soup.select_one("#detail-desc")
        body_html = str(desc_el) if desc_el else ""
        desc_text = desc_el.get_text(strip=True) if desc_el else ""

        if not title and not body_html:
            raise ExtractionError(
                "小红书内容提取失败。可能原因：\n"
                "1. 需要登录 Cookie（请参考 README 配置）\n"
                "2. 帖子已删除或私密\n"
                "建议使用 --force-jina 参数重试"
            )

        tags = re.findall(r"#([^\s#]+)", desc_text)

        # Extract image URLs (XHS content images only, skip avatars/icons)
        img_list = []
        seen = set()
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if not src or not src.startswith("http"):
                continue
            if "sns-avatar" in src or "avatar" in src:
                continue
            if any(cdn in src for cdn in ("sns-webpic", "xiaohongshu.com/image", "ci.xiaohongshu.com")):
                if src not in seen:
                    seen.add(src)
                    img_list.append({"urlDefault": src})

        ocr_cfg = (config or {}).get("platforms", {}).get("xiaohongshu", {}).get("ocr", {})
        do_ocr = ocr_cfg.get("enabled", True) and img_list and ocr_available(
            ocr_cfg.get("engine", "auto")
        )

        if do_ocr:
            llm_cfg = (config or {}).get("llm") or {}
            body_md = self._build_body_with_ocr(desc_text, img_list, ocr_cfg.get("engine", "auto"), llm_cfg)
            return {
                "title": title or desc_text[:50],
                "author": "",
                "date": parse_date(None),
                "platform": self.name,
                "source_url": url,
                "tags": tags,
                "categories": [],
                "summary": desc_text[:200],
                "body_md": body_md,
            }

        return {
            "title": title or desc_text[:50],
            "author": "",
            "date": parse_date(None),
            "platform": self.name,
            "source_url": url,
            "tags": tags,
            "categories": [],
            "summary": desc_text[:200],
            "body_html": body_html,
        }
