"""Tiny stdlib HTTP client with retries and an on-disk JSON cache."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

USER_AGENT = "incentive-analyzer/0.1"
DEFAULT_CACHE_DIR = Path(os.environ.get("INCENTIVES_CACHE_DIR", Path.home() / ".cache" / "incentive-analyzer"))


class HttpError(RuntimeError):
    pass


class HttpClient:
    def __init__(
        self,
        cache_dir: Path | None = DEFAULT_CACHE_DIR,
        cache_ttl: int = 600,
        timeout: float = 30.0,
        retries: int = 3,
        backoff: float = 1.5,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir or self.cache_ttl <= 0:
            return None
        digest = hashlib.sha256(url.encode()).hexdigest()[:32]
        return self.cache_dir / f"{digest}.json"

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
            url = f"{url}{'&' if '?' in url else '?'}{query}"

        cache_path = self._cache_path(url)
        if cache_path and cache_path.exists() and time.time() - cache_path.stat().st_mtime < self.cache_ttl:
            try:
                return json.loads(cache_path.read_text())
            except (OSError, json.JSONDecodeError):
                pass

        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                last_exc = exc
                # 4xx other than rate limiting will not get better on retry.
                if 400 <= exc.code < 500 and exc.code != 429:
                    raise HttpError(f"GET {url} -> HTTP {exc.code}") from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError) as exc:
                last_exc = exc
            if attempt < self.retries:
                delay = self.backoff ** attempt
                log.debug("retrying %s in %.1fs (%s)", url, delay, last_exc)
                time.sleep(delay)
        else:
            raise HttpError(f"GET {url} failed after {self.retries} attempts: {last_exc}") from last_exc

        if cache_path:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(data))
            except OSError as exc:  # cache is best effort
                log.debug("cache write failed: %s", exc)
        return data
