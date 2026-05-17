from __future__ import annotations
import json
import logging
import re

from bs4 import BeautifulSoup

from converter.platforms.base import BasePlatform, ExtractionError
from converter.utils import http
from converter.utils.date_parser import parse_date

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

        post_data = self._extract_render_data(resp.text)
        if post_data:
            return self._parse_from_json(post_data, url)

        return self._parse_from_html(resp.text, url)

    def _to_mobile_url(self, url: str) -> str:
        """Convert desktop Weibo URL to mobile version."""
        if "m.weibo.cn" in url:
            return url

        m = re.search(r"weibo\.com/\w+/(\w+)", url)
        if m:
            return f"https://m.weibo.cn/detail/{m.group(1)}"

        m = re.search(r"weibo\.com/status/(\w+)", url)
        if m:
            return f"https://m.weibo.cn/detail/{m.group(1)}"

        return url.replace("www.weibo.com", "m.weibo.cn").replace("weibo.com", "m.weibo.cn")

    def _extract_render_data(self, html: str) -> dict | None:
        """Extract $render_data JSON embedded in page script."""
        idx = html.find("$render_data = [")
        if idx == -1:
            return None
        try:
            start = html.index("[", idx)
            data, _ = json.JSONDecoder().raw_decode(html, start)
            if isinstance(data, list) and data:
                return data[0].get("status") or data[0]
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        return None

    def _parse_from_json(self, post: dict, url: str) -> dict:
        """Parse weibo post from the $render_data JSON blob."""
        text_html = post.get("text", "")
        user = post.get("user") or {}
        author = user.get("screen_name", "")
        date = parse_date(post.get("created_at", ""))

        tags = re.findall(r"#([^#]+)#", text_html)

        extra = {}
        retweeted = post.get("retweeted_status")
        if retweeted:
            rt_user = (retweeted.get("user") or {}).get("screen_name", "")
            extra["retweeted_from"] = f"@{rt_user}"
            rt_text = retweeted.get("text", "")
            text_html += f'<hr/><blockquote><p><strong>转自 @{rt_user}：</strong></p>{rt_text}</blockquote>'

        # Append post images so the image downloader picks them up
        for pic in post.get("pics") or []:
            large = pic.get("large") or {}
            img_url = large.get("url") or pic.get("url", "")
            if img_url:
                text_html += f'<img src="{img_url}"/>'

        soup = BeautifulSoup(text_html, "lxml")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        plain_text = soup.get_text(separator="\n", strip=True)

        extra.update({
            "reposts_count": post.get("reposts_count"),
            "comments_count": post.get("comments_count"),
            "attitudes_count": post.get("attitudes_count"),
        })

        return {
            "title": plain_text[:50] + ("..." if len(plain_text) > 50 else ""),
            "author": author,
            "date": date,
            "platform": self.name,
            "source_url": url,
            "tags": tags,
            "categories": [f"@{author}"] if author else [],
            "summary": plain_text[:200],
            "extra": {k: v for k, v in extra.items() if v is not None},
            "body_html": text_html,
        }

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
