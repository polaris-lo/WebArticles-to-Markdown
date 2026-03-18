from __future__ import annotations
import http.cookiejar
import logging
import os

logger = logging.getLogger(__name__)


def load_cookies_file(path: str) -> dict:
    """Load a Netscape-format cookie file and return a dict suitable for httpx."""
    if not os.path.exists(path):
        logger.debug("Cookie file not found: %s", path)
        return {}

    jar = http.cookiejar.MozillaCookieJar(path)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as exc:
        logger.warning("Failed to load cookie file %s: %s", path, exc)
        return {}

    return {cookie.name: cookie.value for cookie in jar}
