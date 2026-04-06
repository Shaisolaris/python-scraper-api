# python-scraper-api

![CI](https://github.com/Shaisolaris/python-scraper-api/actions/workflows/ci.yml/badge.svg)

Async web scraper API built with FastAPI, httpx, and BeautifulSoup. Features single-page scraping, batch scraping, website crawling, structured data extraction with custom CSS selector rules, rate limiting with token bucket, concurrent request control, retry with exponential backoff, and async job queue.

## Stack

- **API:** FastAPI + uvicorn
- **HTTP:** httpx (async)
- **Parsing:** BeautifulSoup4
- **Validation:** Pydantic v2

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/scrape` | Scrape a single URL with optional extraction rules |
| POST | `/scrape/batch` | Scrape up to 50 URLs concurrently |
| POST | `/crawl` | Crawl a website (configurable depth and page limit) |
| POST | `/jobs` | Submit async scrape job |
| GET | `/jobs/{id}` | Get job status and result |
| GET | `/stats` | Scraper request/error statistics |
| GET | `/health` | Health check |

## Extraction

Every scraped page returns structured data:

- Title, meta description, H1 headings
- All headings (h1-h6) grouped by level
- Link count, image count, text length, table count
- JSON-LD structured data
- Custom fields via CSS selector rules

### Custom Extraction Rules

```json
POST /scrape
{
  "url": "https://example.com/product",
  "rules": [
    {"name": "price", "selector": ".product-price", "transform": "float"},
    {"name": "reviews", "selector": ".review-text", "multiple": true},
    {"name": "sku", "selector": "[data-sku]", "attribute": "data-sku"}
  ]
}
```

Rule options: `name`, `selector` (CSS), `attribute` (HTML attr or text content), `multiple` (array), `transform` (strip/lower/int/float).

## Architecture

```
python-scraper-api/
├── main.py                    # uvicorn entry point
├── api/
│   └── app.py                 # FastAPI routes, request/response models
├── scraper/
│   ├── client.py              # AsyncClient: rate limiter, retries, concurrency, proxy
│   ├── parser.py              # HTML parsing, structured extraction, custom rules
│   └── engine.py              # ScraperEngine: single, batch, crawl, job queue
├── requirements.txt
└── pyproject.toml
```

## Core Components

### AsyncClient (`scraper/client.py`)
- Token bucket rate limiter (configurable requests/second)
- Semaphore-based concurrency control (configurable max concurrent)
- Exponential backoff retries (configurable max retries, delay, backoff factor)
- 429 rate limit response handling with Retry-After header support
- Proxy support via httpx
- Request/error count statistics

### Parser (`scraper/parser.py`)
- BeautifulSoup HTML parsing
- Auto-extraction: title, meta, headings, links, images, tables, JSON-LD
- Custom CSS selector rules with attribute extraction and type transforms
- Email and phone number extraction from text
- Script/style tag removal for clean text content

### ScraperEngine (`scraper/engine.py`)
- `scrape_url()`: single page with optional rules
- `scrape_urls()`: concurrent multi-page with error handling per URL
- `crawl()`: BFS crawl with depth limit, page limit, domain filtering, URL pattern matching
- `submit_job()` / `get_job()`: async job queue with status tracking
- Configurable exclude patterns (PDFs, images, query strings)

## Setup

```bash
git clone https://github.com/Shaisolaris/python-scraper-api.git
cd python-scraper-api
pip install -r requirements.txt
python main.py
# → http://localhost:8000/docs
```

## Key Design Decisions

**Token bucket rate limiter.** The rate limiter uses a token bucket algorithm with async lock. Tokens refill continuously based on elapsed time, allowing burst requests up to the configured rate while maintaining the average. This is more flexible than fixed-window rate limiting.

**Semaphore for concurrency.** Each request acquires a semaphore slot before the rate limiter. This caps the number of in-flight requests regardless of rate. Combined with the rate limiter, it prevents both overwhelming the target server and exhausting local resources.

**Extraction rules as configuration.** Custom extraction uses CSS selectors with optional attribute access and type transforms. Rules are passed per-request, making the scraper generic without hard-coding site-specific logic. The same engine handles any website structure.

**BFS crawling with domain filter.** The crawler uses breadth-first traversal with configurable depth and page limits. Same-domain filtering is on by default. URL patterns and exclude patterns use regex for flexible link filtering without hard-coding paths.

**Background jobs via FastAPI.** The `/jobs` endpoint uses FastAPI's BackgroundTasks for fire-and-forget scraping. Jobs are stored in-memory with status tracking. In production, replace with Redis/Celery for persistence and horizontal scaling.

## License

MIT
