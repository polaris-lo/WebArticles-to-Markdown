from __future__ import annotations
import logging
import time
import httpx

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def get(url: str, cookies: dict | None = None, headers: dict | None = None,
        timeout: int = 20, retries: int = 3, bypass_proxy: bool = False) -> httpx.Response:
    """Fetch a URL with exponential backoff retry."""
    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    last_exc: Exception | None = None

    for attempt in range(retries):
        try:
            client_kwargs: dict = {"follow_redirects": True, "timeout": timeout}
            if bypass_proxy:
                # Override system proxy by mounting direct transports for all schemes
                client_kwargs["mounts"] = {
                    "http://": httpx.HTTPTransport(),
                    "https://": httpx.HTTPTransport(),
                }
            with httpx.Client(**client_kwargs) as client:
                resp = client.get(url, headers=merged_headers, cookies=cookies or {})
                if resp.status_code in (429, 503) and attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning("HTTP %s, retrying in %ds...", resp.status_code, wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exc = exc
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                logger.warning("Network error (%s), retrying in %ds...", exc, wait)
                time.sleep(wait)
            continue
        except httpx.HTTPStatusError:
            raise

    raise last_exc or RuntimeError(f"Failed to fetch {url} after {retries} attempts")
