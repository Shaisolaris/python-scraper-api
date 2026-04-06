"""
Demo: Scrape and extract data from public websites.
Run: python examples/demo.py
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scraper.client import AsyncClient, ClientConfig
from scraper.parser import extract_page
from scraper.engine import ScraperEngine

async def main():
    print("🕷️ Scraper Demo")
    print("=" * 50)

    engine = ScraperEngine(ClientConfig(max_concurrent=3, requests_per_second=2))

    # Scrape a public page
    print("\n📄 Scraping https://example.com ...")
    page = await engine.scrape_url("https://example.com")
    print(f"   Title: {page.title}")
    print(f"   Links: {len(page.links)}")
    print(f"   Text length: {len(page.text_content)} chars")

    # Scrape multiple pages
    urls = [
        "https://httpbin.org/html",
        "https://httpbin.org/json",
    ]
    print(f"\n📄 Batch scraping {len(urls)} URLs...")
    results = await engine.scrape_urls(urls)
    for r in results:
        if hasattr(r, 'title'):
            print(f"   ✅ {r.url}: {r.title}")
        else:
            print(f"   ❌ {r}")

    print(f"\n📊 Stats: {engine.stats}")
    await engine.close()

if __name__ == "__main__":
    asyncio.run(main())
