from __future__ import annotations
import logging
import re

from converter.platforms.base import BasePlatform, ExtractionError
from converter.utils import http
from converter.utils.date_parser import parse_date

logger = logging.getLogger(__name__)

_JINA_BASE = "https://r.jina.ai/"


class JinaReader(BasePlatform):
    name = "generic"

    def extract(self, url: str, config: dict, cookies: dict) -> dict:
        jina_url = _JINA_BASE + url
        timeout = (config.get("jina") or {}).get("timeout", 30)

        try:
            resp = http.get(
                jina_url,
                headers={"Accept": "text/markdown", "X-Return-Format": "markdown"},
                timeout=timeout,
            )
        except Exception as exc:
            raise ExtractionError(f"Jina Reader failed: {exc}") from exc

        text = resp.text.strip()
        if not text:
            raise ExtractionError("Jina Reader returned empty content")

        # Parse the Jina response: first line is usually "Title: ..."
        title = self._parse_header(text, "Title") or self._first_heading(text) or "Untitled"
        date_str = self._parse_header(text, "Published Time") or ""
        date = parse_date(date_str) if date_str else parse_date(None)

        # Strip Jina metadata headers from body
        body_md = self._strip_jina_headers(text)

        # Detect platform from URL for better tagging
        platform = self._detect_platform_name(url)

        # For Twitter/X, strip the login-wall block Jina captures at the top
        if platform == "twitter":
            body_md = self._strip_twitter_login_wall(body_md)

        return {
            "title": title,
            "author": self._parse_header(text, "Author") or "",
            "date": date,
            "platform": platform,
            "source_url": url,
            "tags": [],
            "categories": [],
            "summary": "",
            "body_html": "",
            "body_md": body_md,
        }

    def _parse_header(self, text: str, key: str) -> str:
        m = re.search(rf"^{re.escape(key)}:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
        return m.group(1).strip() if m else ""

    def _first_heading(self, text: str) -> str:
        lines = text.split("\n")
        for i, line in enumerate(lines):
            # ATX headings: # / ## / ###
            m = re.match(r"^#{1,3}\s+(.+)$", line)
            if m:
                return m.group(1).strip()
            # Setext headings: line followed by === or ---
            if (line.strip() and i + 1 < len(lines)
                    and re.match(r"^[=\-]{2,}\s*$", lines[i + 1])):
                return line.strip()
        return ""

    def _strip_jina_headers(self, text: str) -> str:
        """Remove Jina's metadata header lines at the top of the response."""
        lines = text.split("\n")
        body_start = 0
        for i, line in enumerate(lines):
            if re.match(r"^(Title|URL|Published Time|Author|Description|Keywords):", line, re.IGNORECASE):
                body_start = i + 1
            elif line.strip() == "" and body_start == i:
                body_start = i + 1
            else:
                if i > body_start:
                    break
        return "\n".join(lines[body_start:]).strip()

    def _strip_twitter_login_wall(self, body_md: str) -> str:
        """Remove the Twitter/X login-wall block that Jina captures before real content."""
        # Markers that indicate the login wall section
        login_wall_markers = [
            r"Don't miss what's happening",
            r"People on X are the first to know",
            r"\[Log in\]\(https://x\.com/login\)",
            r"\[Sign up\]\(https://x\.com",
        ]
        lines = body_md.split("\n")
        # Find the last line that belongs to the login wall block
        wall_end = 0
        for i, line in enumerate(lines):
            if any(re.search(pat, line, re.IGNORECASE) for pat in login_wall_markers):
                wall_end = i + 1
        if wall_end:
            # Skip blank lines after the wall
            while wall_end < len(lines) and not lines[wall_end].strip():
                wall_end += 1
            body_md = "\n".join(lines[wall_end:]).strip()
        return body_md

    def _detect_platform_name(self, url: str) -> str:
        patterns = {
            "wechat": r"mp\.weixin\.qq\.com",
            "xiaohongshu": r"(xiaohongshu\.com|xhslink\.com)",
            "weibo": r"(weibo\.com|m\.weibo\.cn)",
            "reddit": r"(reddit\.com|redd\.it)",
            "twitter": r"(twitter\.com|(?<![a-z])x\.com|//t\.co/)",
        }
        for name, pattern in patterns.items():
            if re.search(pattern, url):
                return name
        return "generic"
