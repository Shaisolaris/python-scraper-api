"""Async HTTP client with rate limiting, retries, and proxy support."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ClientConfig:
    """HTTP client configuration."""

    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0
    max_concurrent: int = 5
    requests_per_second: float = 2.0
    user_agent: str = "ScraperAPI/1.0"
    proxy: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)


class RateLimiter:
    """Token bucket rate limiter for async requests."""

    def __init__(self, rate: float):
        self._rate = rate
        self._tokens = rate
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens < 1:
                wait = (1 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0
            else:
                self._tokens -= 1


class AsyncClient:
    """Managed async HTTP client with rate limiting and retries."""

    def __init__(self, config: ClientConfig | None = None):
        self.config = config or ClientConfig()
        self._limiter = RateLimiter(self.config.requests_per_second)
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        self._client: httpx.AsyncClient | None = None
        self._request_count = 0
        self._error_count = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.config.timeout,
                headers={"User-Agent": self.config.user_agent, **self.config.headers},
                follow_redirects=True,
                proxy=self.config.proxy,
            )
        return self._client

    async def fetch(self, url: str, method: str = "GET", **kwargs) -> httpx.Response:
        """Fetch a URL with rate limiting, concurrency control, and retries."""
        async with self._semaphore:
            await self._limiter.acquire()

            client = await self._get_client()
            delay = self.config.retry_delay

            for attempt in range(1, self.config.max_retries + 1):
                try:
                    self._request_count += 1
                    response = await client.request(method, url, **kwargs)
                    response.raise_for_status()
                    logger.debug(f"[{response.status_code}] {url}")
                    return response
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        retry_after = float(e.response.headers.get("Retry-After", delay))
                        logger.warning(f"Rate limited on {url}, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                    elif e.response.status_code >= 500 and attempt < self.config.max_retries:
                        logger.warning(f"Server error {e.response.status_code} on {url}, retry {attempt}/{self.config.max_retries}")
                        await asyncio.sleep(delay)
                        delay *= self.config.retry_backoff
                    else:
                        self._error_count += 1
                        raise
                except (httpx.ConnectError, httpx.ReadTimeout) as e:
                    if attempt < self.config.max_retries:
                        logger.warning(f"Connection error on {url}: {e}, retry {attempt}/{self.config.max_retries}")
                        await asyncio.sleep(delay)
                        delay *= self.config.retry_backoff
                    else:
                        self._error_count += 1
                        raise

            raise RuntimeError(f"All {self.config.max_retries} retries exhausted for {url}")

    async def fetch_many(self, urls: list[str]) -> list[httpx.Response | Exception]:
        """Fetch multiple URLs concurrently."""
        tasks = [self._safe_fetch(url) for url in urls]
        return await asyncio.gather(*tasks)

    async def _safe_fetch(self, url: str) -> httpx.Response | Exception:
        try:
            return await self.fetch(url)
        except Exception as e:
            return e

    @property
    def stats(self) -> dict[str, int]:
        return {"requests": self._request_count, "errors": self._error_count}

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
