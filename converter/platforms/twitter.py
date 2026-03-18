from __future__ import annotations
import json
import logging
import re

from converter.platforms.base import BasePlatform, ExtractionError
from converter.utils import http
from converter.utils.date_parser import parse_date
from converter.utils.tools import is_installed, run_tool

logger = logging.getLogger(__name__)

_NITTER_INSTANCES = [
    "nitter.net",
    "nitter.privacydev.net",
    "nitter.poast.org",
    "nitter.cz",
]

_XREACH_CMD = "xreach"


class TwitterPlatform(BasePlatform):
    name = "twitter"

    def extract(self, url: str, config: dict, cookies: dict) -> dict:
        # Normalize URL
        url = self._normalize_url(url)

        # Tier 1: xreach CLI (Agent-Reach recommended tool, cookie-based)
        if is_installed(_XREACH_CMD):
            try:
                result = self._extract_via_xreach(url, config)
                if result.get("title") or result.get("body_md"):
                    return result
            except Exception as exc:
                logger.debug("xreach failed (%s), trying Jina Reader", exc)

        # Tier 2: Jina Reader (no auth needed)
        try:
            from converter.fallback.jina_reader import JinaReader
            result = JinaReader().extract(url, config, cookies)
            if result.get("title") and result.get("body_md"):
                result["platform"] = self.name
                # Clean up Twitter page title format: 'Author on X: "Article Title" / X'
                raw_title = result.get("title", "")
                m = re.search(r'on X:\s+"([^"]+)"', raw_title)
                if m:
                    result["title"] = m.group(1).strip()
                return result
        except ExtractionError:
            logger.debug("Jina Reader failed for Twitter, trying Nitter")

        # Tier 3: Nitter mirror
        nitter_instances = (
            (config.get("platforms") or {})
            .get("twitter", {})
            .get("nitter_instances", _NITTER_INSTANCES)
        )
        for instance in nitter_instances:
            try:
                result = self._fetch_nitter(url, instance)
                if result:
                    return result
            except Exception as exc:
                logger.debug("Nitter %s failed: %s", instance, exc)
                continue

        # Tier 4: Cookie-based direct fetch
        if cookies:
            try:
                return self._fetch_direct(url, cookies)
            except ExtractionError:
                logger.debug("Direct Twitter fetch failed")

        # Tier 5: Graceful failure — save metadata only
        username, tweet_id = self._parse_url(url)
        return {
            "title": f"Tweet by @{username}" if username else "Tweet",
            "author": username,
            "date": parse_date(None),
            "platform": self.name,
            "source_url": url,
            "tags": [],
            "categories": [f"@{username}"] if username else [],
            "summary": "",
            "body_html": "",
            "body_md": (
                f"> ⚠️ 内容无法自动抓取（Twitter 需要登录）\n>\n"
                f"> 原始链接：{url}\n"
            ),
            "extra": {"tweet_id": tweet_id},
        }

    def _extract_via_xreach(self, url: str, config: dict) -> dict:
        """Use xreach CLI to fetch tweet content."""
        output = run_tool([_XREACH_CMD, "tweet", url, "--json"], timeout=30)
        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"xreach returned invalid JSON: {exc}") from exc

        username, tweet_id = self._parse_url(url)
        text = data.get("text") or data.get("full_text") or data.get("content") or ""
        author = data.get("user", {}).get("screen_name") or username
        date = parse_date(data.get("created_at") or data.get("date"))
        tags = re.findall(r"#(\w+)", text)

        return {
            "title": text[:60] + ("..." if len(text) > 60 else ""),
            "author": author,
            "date": date,
            "platform": self.name,
            "source_url": url,
            "tags": tags,
            "categories": [f"@{author}"] if author else [],
            "summary": text[:200],
            "body_html": "",
            "body_md": text,
            "extra": {
                "tweet_id": tweet_id,
                "likes": data.get("favorite_count"),
                "retweets": data.get("retweet_count"),
            },
        }

    def _normalize_url(self, url: str) -> str:
        """Resolve t.co short URLs and normalize to x.com."""
        if "t.co" in url:
            try:
                resp = http.get(url, timeout=10)
                url = str(resp.url)
            except Exception:
                pass
        return url

    def _parse_url(self, url: str) -> tuple:
        m = re.search(r"(?:twitter\.com|x\.com)/([^/]+)/status/(\d+)", url)
        if m:
            return m.group(1), m.group(2)
        return "", ""

    def _fetch_nitter(self, url: str, instance: str) -> dict | None:
        from bs4 import BeautifulSoup

        username, tweet_id = self._parse_url(url)
        if not username or not tweet_id:
            return None

        nitter_url = f"https://{instance}/{username}/status/{tweet_id}"
        try:
            resp = http.get(nitter_url, timeout=15)
        except Exception as exc:
            raise ExtractionError(f"Nitter fetch failed: {exc}") from exc

        soup = BeautifulSoup(resp.text, "lxml")
        tweet_div = soup.select_one(".tweet-content") or soup.select_one(".main-tweet .tweet-body")
        if not tweet_div:
            return None

        text = tweet_div.get_text(separator="\n", strip=True)
        if not text:
            return None

        # Date
        date_el = soup.select_one(".tweet-date a") or soup.select_one("time")
        date_raw = date_el.get("title") or date_el.get("datetime", "") if date_el else ""
        date = parse_date(date_raw) if date_raw else parse_date(None)

        # Stats
        extra = {}
        for stat in soup.select(".tweet-stat"):
            label = stat.get_text(strip=True)
            if "Retweet" in label:
                extra["retweets"] = re.search(r"\d+", label)
            elif "Like" in label:
                extra["likes"] = re.search(r"\d+", label)

        return {
            "title": text[:60] + ("..." if len(text) > 60 else ""),
            "author": username,
            "date": date,
            "platform": self.name,
            "source_url": url,
            "tags": re.findall(r"#(\w+)", text),
            "categories": [f"@{username}"],
            "summary": text[:200],
            "body_html": str(tweet_div),
            "extra": {"tweet_id": tweet_id, **{k: v.group() if v else None for k, v in extra.items()}},
        }

    def _fetch_direct(self, url: str, cookies: dict) -> dict:
        """Attempt direct fetch with cookies (Twitter HTML is JS-rendered, may fail)."""
        try:
            resp = http.get(url, cookies=cookies, timeout=20)
        except Exception as exc:
            raise ExtractionError(f"Direct Twitter fetch failed: {exc}") from exc

        # Twitter's HTML without JS execution is mostly empty
        if "login" in resp.url.lower() or len(resp.text) < 500:
            raise ExtractionError("Twitter redirected to login page or returned empty content")

        raise ExtractionError("Twitter direct HTML parsing not supported (JS-rendered)")
