from __future__ import annotations
import logging
import re

from converter.platforms.base import BasePlatform, ExtractionError
from converter.utils import http
from converter.utils.date_parser import parse_date

logger = logging.getLogger(__name__)

_REDDIT_UA = "web-to-markdown/1.0 (personal note archiving tool)"


class RedditPlatform(BasePlatform):
    name = "reddit"

    def extract(self, url: str, config: dict, cookies: dict) -> dict:
        # Reddit 2023+ requires authentication for API access.
        # Strategy: try JSON API with cookies if available, else raise to trigger Jina fallback.
        if not cookies:
            raise ExtractionError(
                "Reddit JSON API requires login cookies since 2023.\n"
                "保存 cookies 到 cookies/reddit.txt，或使用 --force-jina 参数（Jina 对公开帖支持较好）"
            )

        json_url = self._to_json_url(url)
        logger.debug("Reddit JSON URL: %s", json_url)

        try:
            resp = http.get(
                json_url,
                cookies=cookies,
                headers={"User-Agent": _REDDIT_UA},
                timeout=20,
            )
        except Exception as exc:
            raise ExtractionError(f"Reddit fetch failed: {exc}") from exc

        try:
            data = resp.json()
        except Exception as exc:
            raise ExtractionError(f"Reddit JSON parse failed: {exc}") from exc

        post = self._get_post(data)
        if not post:
            raise ExtractionError("Could not locate post data in Reddit JSON")

        title = post.get("title", "")
        author = post.get("author", "")
        subreddit = post.get("subreddit_name_prefixed") or f"r/{post.get('subreddit', '')}"
        date = parse_date(post.get("created_utc"))
        flair = post.get("link_flair_text") or ""
        selftext = post.get("selftext", "")  # already Markdown
        post_url = f"https://www.reddit.com{post.get('permalink', '')}"
        link_url = post.get("url", "")

        tags = [subreddit]
        if flair:
            tags.append(flair)

        # Build body
        lines = []
        if selftext:
            lines.append(selftext)
        elif link_url and link_url != post_url:
            lines.append(f"**链接**: {link_url}")

        # Include top comments if configured
        include_comments = (config.get("comments") or {}).get("include", True)
        max_comments = (config.get("comments") or {}).get("max_top_level", 3)
        if include_comments and len(data) > 1:
            comments = self._get_top_comments(data[1], max_comments)
            if comments:
                lines.append("\n---\n\n## 评论\n")
                for c in comments:
                    lines.append(f"**{c['author']}**\n\n{c['body']}\n")

        body_md = "\n\n".join(lines)

        return {
            "title": title,
            "author": author,
            "date": date,
            "platform": self.name,
            "source_url": url,
            "tags": tags,
            "categories": [subreddit],
            "summary": selftext[:200] if selftext else "",
            "body_html": "",
            "body_md": body_md,
            "extra": {
                "score": post.get("score"),
                "num_comments": post.get("num_comments"),
                "subreddit": subreddit,
            },
        }

    def _to_json_url(self, url: str) -> str:
        # Resolve redd.it short links by making a HEAD request
        if "redd.it" in url:
            try:
                import httpx
                with httpx.Client(follow_redirects=True, timeout=10) as client:
                    resp = client.head(url)
                    url = str(resp.url)
            except Exception:
                pass

        # Use old.reddit.com — less aggressive anti-bot than www
        url = re.sub(r"https?://(www\.)?reddit\.com", "https://old.reddit.com", url)
        url = re.sub(r"https?://redd\.it", "https://old.reddit.com", url)

        # Strip trailing slash, then add .json before any query string
        if "?" in url:
            base, query = url.split("?", 1)
            base = base.rstrip("/")
            if base.endswith(".json"):
                return base + "?" + query
            return base + ".json?" + query
        url = url.rstrip("/")
        if url.endswith(".json"):
            return url
        return url + ".json"

    def _get_post(self, data) -> dict | None:
        try:
            return data[0]["data"]["children"][0]["data"]
        except (IndexError, KeyError, TypeError):
            return None

    def _get_top_comments(self, comments_data, max_count: int) -> list:
        results = []
        try:
            children = comments_data["data"]["children"]
        except (KeyError, TypeError):
            return results

        for child in children[:max_count]:
            try:
                d = child["data"]
                if d.get("body") and d.get("author"):
                    results.append({"author": d["author"], "body": d["body"]})
            except (KeyError, TypeError):
                continue
        return results
