"""Scraper engine — single page, multi-page, and crawl operations."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

from scraper.client import AsyncClient, ClientConfig
from scraper.parser import ExtractedPage, ExtractionRule, extract_page

logger = logging.getLogger(__name__)


@dataclass
class ScrapeJob:
    """Scraping job definition."""

    id: str
    url: str
    status: str = "pending"  # pending, running, completed, failed
    rules: list[ExtractionRule] = field(default_factory=list)
    result: Optional[ExtractedPage] = None
    error: Optional[str] = None


@dataclass
class CrawlConfig:
    """Configuration for web crawling."""

    max_pages: int = 50
    max_depth: int = 3
    same_domain_only: bool = True
    url_patterns: list[str] = field(default_factory=list)  # regex patterns to include
    exclude_patterns: list[str] = field(default_factory=lambda: [r"\.pdf$", r"\.jpg$", r"\.png$", r"\?"])


class ScraperEngine:
    """Core scraping engine with single and multi-page support."""

    def __init__(self, client_config: ClientConfig | None = None):
        self._client = AsyncClient(client_config or ClientConfig())
        self._jobs: dict[str, ScrapeJob] = {}

    async def scrape_url(self, url: str, rules: list[ExtractionRule] | None = None) -> ExtractedPage:
        """Scrape a single URL."""
        response = await self._client.fetch(url)
        return extract_page(response.text, url=url, rules=rules)

    async def scrape_urls(self, urls: list[str], rules: list[ExtractionRule] | None = None) -> list[ExtractedPage | dict]:
        """Scrape multiple URLs concurrently."""
        results: list[ExtractedPage | dict] = []
        responses = await self._client.fetch_many(urls)

        for url, resp in zip(urls, responses):
            if isinstance(resp, Exception):
                results.append({"url": url, "error": str(resp)})
            else:
                results.append(extract_page(resp.text, url=url, rules=rules))

        return results

    async def crawl(self, start_url: str, config: CrawlConfig | None = None) -> list[ExtractedPage]:
        """Crawl a website starting from a URL."""
        config = config or CrawlConfig()
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(start_url, 0)]
        results: list[ExtractedPage] = []
        domain = urlparse(start_url).netloc

        while queue and len(results) < config.max_pages:
            url, depth = queue.pop(0)

            if url in visited or depth > config.max_depth:
                continue

            visited.add(url)

            try:
                page = await self.scrape_url(url)
                results.append(page)
                logger.info(f"Crawled [{len(results)}/{config.max_pages}] depth={depth}: {url}")

                if depth < config.max_depth:
                    for link in page.links:
                        href = link.get("href", "")
                        absolute_url = urljoin(url, href)
                        parsed = urlparse(absolute_url)

                        if absolute_url in visited:
                            continue
                        if config.same_domain_only and parsed.netloc != domain:
                            continue
                        if not parsed.scheme.startswith("http"):
                            continue

                        import re
                        if config.exclude_patterns and any(re.search(p, absolute_url) for p in config.exclude_patterns):
                            continue
                        if config.url_patterns and not any(re.search(p, absolute_url) for p in config.url_patterns):
                            continue

                        queue.append((absolute_url, depth + 1))

            except Exception as e:
                logger.error(f"Failed to crawl {url}: {e}")

        logger.info(f"Crawl complete: {len(results)} pages from {start_url}")
        return results

    async def submit_job(self, job: ScrapeJob) -> ScrapeJob:
        """Submit a scraping job for async processing."""
        self._jobs[job.id] = job
        job.status = "running"

        try:
            job.result = await self.scrape_url(job.url, rules=job.rules)
            job.status = "completed"
        except Exception as e:
            job.status = "failed"
            job.error = str(e)

        return job

    def get_job(self, job_id: str) -> ScrapeJob | None:
        return self._jobs.get(job_id)

    @property
    def stats(self) -> dict:
        return {**self._client.stats, "jobs_total": len(self._jobs), "jobs_completed": sum(1 for j in self._jobs.values() if j.status == "completed")}

    async def close(self) -> None:
        await self._client.close()
