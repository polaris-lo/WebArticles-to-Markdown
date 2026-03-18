from __future__ import annotations
import re
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Chinese date patterns
_CN_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def parse_date(raw: str | int | float | None) -> str:
    """Normalise a date string or Unix timestamp to YYYY-MM-DD (ISO-8601 date)."""
    if raw is None:
        return datetime.now().strftime("%Y-%m-%d")

    # Unix timestamp (int or float)
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=timezone.utc).strftime("%Y-%m-%d")

    raw = str(raw).strip()

    # Chinese date: 2024年3月17日
    m = _CN_DATE_RE.search(raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # Try dateutil for everything else
    try:
        from dateutil import parser as du_parser
        dt = du_parser.parse(raw, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    logger.debug("Could not parse date: %r, using today", raw)
    return datetime.now().strftime("%Y-%m-%d")
