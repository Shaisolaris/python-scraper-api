"""
Scraper Demo: Demonstrates the scraping pipeline without external dependencies.
Run: python examples/demo.py
"""
import json, time, hashlib, urllib.request, html.parser

class SimpleHTMLParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.links = []
        self.text = []
        self._in_title = False
    
    def handle_starttag(self, tag, attrs):
        if tag == "title": self._in_title = True
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v: self.links.append(v)
    
    def handle_endtag(self, tag):
        if tag == "title": self._in_title = False
    
    def handle_data(self, data):
        if self._in_title: self.title += data
        self.text.append(data.strip())

def scrape_url(url: str) -> dict:
    """Scrape a URL using only stdlib."""
    start = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SolarisScraper/1.0)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            parser = SimpleHTMLParser()
            parser.feed(content)
            return {
                "url": url,
                "status": resp.status,
                "title": parser.title.strip(),
                "links": len(parser.links),
                "text_length": len(" ".join(parser.text)),
                "time_ms": round((time.time() - start) * 1000),
            }
    except Exception as e:
        return {"url": url, "status": "error", "error": str(e), "time_ms": round((time.time() - start) * 1000)}

def main():
    print("🕷️ Web Scraper Demo (stdlib only, no pip dependencies)")
    print("=" * 55)
    
    urls = [
        "https://example.com",
        "https://httpbin.org/html",
        "https://httpbin.org/status/200",
    ]
    
    results = []
    for url in urls:
        print(f"\n📄 Scraping {url}...")
        result = scrape_url(url)
        results.append(result)
        if result.get("status") == "error":
            print(f"   ❌ {result['error']} ({result['time_ms']}ms)")
        else:
            print(f"   ✅ Status: {result['status']}")
            print(f"   Title: {result.get('title', 'N/A')}")
            print(f"   Links found: {result['links']}")
            print(f"   Text length: {result['text_length']} chars")
            print(f"   Time: {result['time_ms']}ms")
    
    print(f"\n📊 Summary:")
    print(f"   URLs scraped: {len(results)}")
    print(f"   Successful: {sum(1 for r in results if r.get('status') != 'error')}")
    print(f"   Total time: {sum(r['time_ms'] for r in results)}ms")

if __name__ == "__main__":
    main()
