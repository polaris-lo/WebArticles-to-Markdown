from __future__ import annotations
import json
import logging
import os
import re
import tempfile
import urllib.parse

from bs4 import BeautifulSoup

from converter.platforms.base import BasePlatform, ExtractionError
from converter.utils import http
from converter.utils.date_parser import parse_date
from converter.utils.tools import is_installed, run_tool

logger = logging.getLogger(__name__)

_WECHAT_MD_CMD = "wechat-article-to-markdown"


class WechatPlatform(BasePlatform):
    name = "wechat"

    def extract(self, url: str, config: dict, cookies: dict) -> dict:
        # Tier 1: wechat-article-to-markdown (uses camoufox, most reliable)
        if is_installed(_WECHAT_MD_CMD):
            try:
                return self._extract_via_tool(url, config)
            except Exception as exc:
                logger.warning("wechat-article-to-markdown failed (%s), falling back to HTTP", exc)

        # Tier 2: plain HTTP + BeautifulSoup (works for some articles)
        return self._extract_via_http(url, config)

    def _extract_via_tool(self, url: str, config: dict) -> dict:
        """Use wechat-article-to-markdown CLI to extract article content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_tool([_WECHAT_MD_CMD, url, "--output-dir", tmpdir], timeout=60)

            # Find the generated .md file
            md_files = [f for f in os.listdir(tmpdir) if f.endswith(".md")]
            if not md_files:
                raise ExtractionError("wechat-article-to-markdown produced no output file")

            md_path = os.path.join(tmpdir, md_files[0])
            with open(md_path, encoding="utf-8") as f:
                content = f.read()

        # Parse YAML frontmatter if present
        title, author, date = "", "", ""
        body_md = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm_text, body_md = parts[1], parts[2].strip()
                title = self._fm_field(fm_text, "title")
                author = self._fm_field(fm_text, "author")
                date = parse_date(self._fm_field(fm_text, "date") or None)

        if not title:
            # Fall back to first H1 in body
            m = re.search(r"^#\s+(.+)$", body_md, re.MULTILINE)
            title = m.group(1).strip() if m else ""

        return {
            "title": title,
            "author": author,
            "date": date or parse_date(None),
            "platform": self.name,
            "source_url": url,
            "tags": [],
            "categories": [],
            "summary": body_md[:200].strip(),
            "body_html": "",
            "body_md": body_md,
        }

    def _fm_field(self, fm_text: str, key: str) -> str:
        m = re.search(rf"^{re.escape(key)}:\s*[\"']?(.+?)[\"']?\s*$", fm_text, re.MULTILINE)
        return m.group(1).strip() if m else ""

    def _extract_via_http(self, url: str, config: dict) -> dict:
        """Plain HTTP extraction with BeautifulSoup (fallback)."""
        try:
            resp = http.get(url, timeout=20)
        except Exception as exc:
            raise ExtractionError(f"WeChat HTTP fetch failed: {exc}") from exc

        soup = BeautifulSoup(resp.text, "lxml")

        title = self._get_text(soup, "#activity-name") or self._get_text(soup, "h1")
        author = self._get_text(soup, "#js_author_name") or self._get_text(soup, ".rich_media_meta_nickname")
        date_raw = self._get_text(soup, "#publish_time") or self._get_attr(soup, "#publish_time", "data-dt")
        date = parse_date(date_raw)

        content_tag = soup.select_one("#js_content")
        if not content_tag:
            raise ExtractionError("Could not find WeChat article body (#js_content)")

        # Download images if configured
        download_images = (config.get("images") or {}).get("download", True)
        output_dir = config.get("_output_dir")
        if download_images and output_dir:
            self._download_images(content_tag, url, output_dir, config)

        body_html = str(content_tag)

        # Extract summary from meta description or first paragraph
        summary = ""
        meta_desc = soup.find("meta", {"name": "description"})
        if meta_desc and meta_desc.get("content"):
            summary = meta_desc["content"].strip()
        if not summary:
            first_p = content_tag.find("p")
            if first_p:
                summary = first_p.get_text(strip=True)[:200]

        # Extract account name for categories
        account_name = self._get_text(soup, "#js_name") or ""

        return {
            "title": title,
            "author": author,
            "date": date,
            "platform": self.name,
            "source_url": url,
            "tags": [],
            "categories": [account_name] if account_name else [],
            "summary": summary,
            "body_html": body_html,
        }

    def _get_text(self, soup: BeautifulSoup, selector: str) -> str:
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else ""

    def _get_attr(self, soup: BeautifulSoup, selector: str, attr: str) -> str:
        el = soup.select_one(selector)
        return el.get(attr, "") if el else ""

    def _download_images(self, content_tag, article_url: str, output_dir: str, config: dict):
        """Download WeChat CDN images locally and rewrite src attributes."""
        assets_dir_name = (config.get("images") or {}).get("subdir", "assets")
        # We can't reliably know the final output filename here, so use a shared assets dir
        assets_dir = os.path.join(output_dir, assets_dir_name)
        os.makedirs(assets_dir, exist_ok=True)

        for img in content_tag.find_all("img"):
            src = img.get("data-src") or img.get("src") or ""
            if not src or src.startswith("data:"):
                continue
            if not src.startswith("http"):
                src = urllib.parse.urljoin(article_url, src)

            filename = self._url_to_filename(src)
            local_path = os.path.join(assets_dir, filename)

            if not os.path.exists(local_path):
                try:
                    img_resp = http.get(src, timeout=15)
                    with open(local_path, "wb") as f:
                        f.write(img_resp.content)
                    logger.debug("Downloaded image: %s", filename)
                except Exception as exc:
                    logger.warning("Image download failed (%s): %s", src[:60], exc)
                    continue

            # Rewrite to relative path
            img["src"] = f"{assets_dir_name}/{filename}"
            if "data-src" in img.attrs:
                del img["data-src"]

    def _url_to_filename(self, url: str) -> str:
        """Derive a safe local filename from an image URL."""
        path = urllib.parse.urlparse(url).path
        name = os.path.basename(path) or "image"
        # Strip query params that might have crept in
        name = name.split("?")[0]
        # Ensure there's an extension
        if "." not in name:
            name += ".jpg"
        # Sanitize
        name = re.sub(r"[^\w.\-]", "_", name)
        return name[:100]
