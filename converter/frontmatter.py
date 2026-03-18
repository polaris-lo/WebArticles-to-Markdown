from __future__ import annotations
import re
from datetime import datetime
from io import StringIO

from ruamel.yaml import YAML

_yaml = YAML()
_yaml.default_flow_style = False
_yaml.allow_unicode = True
_yaml.width = 4096  # prevent line-wrapping in long strings


def _detect_language(text: str) -> str:
    if not text:
        return "zh"
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return "zh" if cjk / max(len(text), 1) > 0.15 else "en"


def build(extracted: dict) -> str:
    """Build a YAML frontmatter block from an extraction result dict."""
    title = extracted.get("title") or "Untitled"
    description_raw = extracted.get("summary") or ""

    data = {
        "title": title,
        "source": extracted.get("source_url", ""),
        "platform": extracted.get("platform", "unknown"),
        "author": extracted.get("author") or "",
        "published": extracted.get("date", datetime.now().strftime("%Y-%m-%d")),
        "created": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "tags": extracted.get("tags") or [],
        "categories": extracted.get("categories") or [],
        "description": _truncate(description_raw, 100),
        "language": _detect_language(title + description_raw),
        "status": "unread",
    }

    extra = extracted.get("extra")
    if extra:
        data["extra"] = extra

    buf = StringIO()
    _yaml.dump(data, buf)
    yaml_str = buf.getvalue().rstrip()
    return f"---\n{yaml_str}\n---\n"


def _truncate(text: str, length: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "..."
