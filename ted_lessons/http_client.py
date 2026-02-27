"""Shared HTTP client with exponential backoff, per-host rate limiting, and caching."""

from __future__ import annotations

import time
import random
import logging
from functools import lru_cache

import requests

log = logging.getLogger(__name__)

# Per-host minimum delay (seconds) between requests
HOST_DELAYS = {
    "ed.ted.com": 1.0,
    "www.youtube.com": 2.0,
    "youtube.com": 2.0,
}

# Backoff settings
MAX_RETRIES = 3
BACKOFF_BASE = 1.0
BACKOFF_MAX = 8.0
RETRYABLE_CODES = {429, 500, 502, 503, 504}


class HttpClient:
    """Requests session with backoff, rate limiting, and per-run response caching."""

    def __init__(self, delay_multiplier: float = 1.0):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.delay_multiplier = delay_multiplier
        self._last_request_time: dict[str, float] = {}
        self._cache: dict[str, requests.Response] = {}

    def get(self, url: str, use_cache: bool = True, **kwargs) -> requests.Response:
        """GET with rate limiting, caching, and retry."""
        if use_cache and url in self._cache:
            log.debug("Cache hit: %s", url)
            return self._cache[url]

        self._rate_limit(url)
        response = self._request_with_retry("GET", url, **kwargs)

        if use_cache and response.status_code == 200:
            self._cache[url] = response
        return response

    def post(self, url: str, **kwargs) -> requests.Response:
        """POST with rate limiting and retry (no caching)."""
        self._rate_limit(url)
        return self._request_with_retry("POST", url, **kwargs)

    def get_text(self, url: str, **kwargs) -> str | None:
        """GET and return UTF-8 text, or None on failure."""
        try:
            resp = self.get(url, **kwargs)
            if resp.status_code != 200:
                log.warning("HTTP %d for %s", resp.status_code, url)
                return None
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException as e:
            log.warning("Request failed for %s: %s", url, e)
            return None

    def _rate_limit(self, url: str):
        """Enforce per-host delay between requests."""
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        delay = HOST_DELAYS.get(host, 0.5) * self.delay_multiplier

        last = self._last_request_time.get(host, 0)
        elapsed = time.time() - last
        if elapsed < delay:
            wait = delay - elapsed
            log.debug("Rate limiting %s: waiting %.1fs", host, wait)
            time.sleep(wait)

        self._last_request_time[host] = time.time()

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """Execute request with exponential backoff on retryable errors."""
        kwargs.setdefault("timeout", 20)

        last_exc = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self.session.request(method, url, **kwargs)
                if response.status_code not in RETRYABLE_CODES or attempt == MAX_RETRIES:
                    return response
                log.warning(
                    "HTTP %d for %s (attempt %d/%d)",
                    response.status_code, url, attempt + 1, MAX_RETRIES + 1,
                )
            except requests.RequestException as e:
                last_exc = e
                if attempt == MAX_RETRIES:
                    raise
                log.warning("Request error for %s: %s (attempt %d/%d)",
                            url, e, attempt + 1, MAX_RETRIES + 1)

            # Exponential backoff with jitter
            backoff = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_MAX)
            jitter = random.uniform(0, backoff * 0.5)
            time.sleep(backoff + jitter)

        raise last_exc  # should not reach here
