"""FastAPI scraper API — scrape, crawl, and extract endpoints."""

from __future__ import annotations

import uuid
import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, HttpUrl

from scraper.engine import ScraperEngine, ScrapeJob, CrawlConfig
from scraper.parser import ExtractionRule, ExtractedPage
from scraper.client import ClientConfig

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Scraper API",
    description="Async web scraping API with rate limiting, structured extraction, and crawling",
    version="1.0.0",
)

_engine: ScraperEngine | None = None


def get_engine() -> ScraperEngine:
    global _engine
    if _engine is None:
        _engine = ScraperEngine(ClientConfig(
            max_concurrent=10,
            requests_per_second=5.0,
            timeout=30.0,
            max_retries=3,
        ))
    return _engine


# ─── Request/Response Models ─────────────────────────────

class ScrapeRequest(BaseModel):
    url: str = Field(..., description="URL to scrape")
    rules: list[dict[str, Any]] = Field(default=[], description="Custom extraction rules")
    wait_for: Optional[str] = Field(default=None, description="CSS selector to wait for (placeholder for JS rendering)")


class ScrapeResponse(BaseModel):
    url: str
    title: str | None = None
    meta_description: str | None = None
    h1: list[str] = []
    headings: dict[str, list[str]] = {}
    links_count: int = 0
    images_count: int = 0
    text_length: int = 0
    tables_count: int = 0
    custom_fields: dict[str, Any] = {}
    structured_data: list[dict[str, Any]] = []


class BatchScrapeRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=50, description="URLs to scrape (max 50)")
    rules: list[dict[str, Any]] = Field(default=[])


class CrawlRequest(BaseModel):
    url: str = Field(..., description="Starting URL")
    max_pages: int = Field(default=20, ge=1, le=100)
    max_depth: int = Field(default=2, ge=1, le=5)
    same_domain_only: bool = True


class CrawlResponse(BaseModel):
    start_url: str
    pages_crawled: int
    pages: list[ScrapeResponse]


class JobResponse(BaseModel):
    job_id: str
    status: str
    url: str
    result: ScrapeResponse | None = None
    error: str | None = None


class StatsResponse(BaseModel):
    requests: int
    errors: int
    jobs_total: int
    jobs_completed: int


# ─── Helpers ─────────────────────────────────────────────

def _parse_rules(raw_rules: list[dict[str, Any]]) -> list[ExtractionRule]:
    rules = []
    for r in raw_rules:
        rules.append(ExtractionRule(
            name=r.get("name", "field"),
            selector=r.get("selector", ""),
            attribute=r.get("attribute"),
            multiple=r.get("multiple", False),
            transform=r.get("transform"),
        ))
    return rules


def _page_to_response(page: ExtractedPage) -> ScrapeResponse:
    return ScrapeResponse(
        url=page.url,
        title=page.title,
        meta_description=page.meta_description,
        h1=page.h1,
        headings=page.headings,
        links_count=len(page.links),
        images_count=len(page.images),
        text_length=len(page.text_content),
        tables_count=len(page.tables),
        custom_fields=page.custom_fields,
        structured_data=page.structured_data,
    )


# ─── Endpoints ───────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "healthy", "engine": _engine is not None}


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape(request: ScrapeRequest) -> ScrapeResponse:
    """Scrape a single URL and return extracted data."""
    engine = get_engine()
    rules = _parse_rules(request.rules)

    try:
        page = await engine.scrape_url(request.url, rules=rules)
        return _page_to_response(page)
    except Exception as e:
        logger.error(f"Scrape failed: {e}")
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/scrape/batch")
async def scrape_batch(request: BatchScrapeRequest) -> list[ScrapeResponse | dict]:
    """Scrape multiple URLs concurrently."""
    engine = get_engine()
    rules = _parse_rules(request.rules)

    results = await engine.scrape_urls(request.urls, rules=rules)
    responses: list[ScrapeResponse | dict] = []
    for r in results:
        if isinstance(r, ExtractedPage):
            responses.append(_page_to_response(r))
        else:
            responses.append(r)  # error dict
    return responses


@app.post("/crawl", response_model=CrawlResponse)
async def crawl(request: CrawlRequest) -> CrawlResponse:
    """Crawl a website starting from a URL."""
    engine = get_engine()
    config = CrawlConfig(
        max_pages=request.max_pages,
        max_depth=request.max_depth,
        same_domain_only=request.same_domain_only,
    )

    try:
        pages = await engine.crawl(request.url, config=config)
        return CrawlResponse(
            start_url=request.url,
            pages_crawled=len(pages),
            pages=[_page_to_response(p) for p in pages],
        )
    except Exception as e:
        logger.error(f"Crawl failed: {e}")
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/jobs", response_model=JobResponse)
async def create_job(request: ScrapeRequest, background_tasks: BackgroundTasks) -> JobResponse:
    """Submit an async scrape job."""
    engine = get_engine()
    job_id = str(uuid.uuid4())[:8]
    rules = _parse_rules(request.rules)
    job = ScrapeJob(id=job_id, url=request.url, rules=rules)

    async def run_job():
        await engine.submit_job(job)

    background_tasks.add_task(run_job)
    return JobResponse(job_id=job_id, status="pending", url=request.url)


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    """Get job status and result."""
    engine = get_engine()
    job = engine.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse(
        job_id=job.id,
        status=job.status,
        url=job.url,
        result=_page_to_response(job.result) if job.result else None,
        error=job.error,
    )


@app.get("/stats", response_model=StatsResponse)
def stats() -> StatsResponse:
    """Get scraper statistics."""
    engine = get_engine()
    return StatsResponse(**engine.stats)


@app.on_event("shutdown")
async def shutdown() -> None:
    if _engine:
        await _engine.close()
