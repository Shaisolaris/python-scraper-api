"""HTML parsing and structured data extraction."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


@dataclass
class ExtractedPage:
    """Structured data extracted from a web page."""

    url: str
    title: str | None = None
    meta_description: str | None = None
    h1: list[str] = field(default_factory=list)
    headings: dict[str, list[str]] = field(default_factory=dict)
    links: list[dict[str, str]] = field(default_factory=list)
    images: list[dict[str, str]] = field(default_factory=list)
    text_content: str = ""
    tables: list[list[list[str]]] = field(default_factory=list)
    structured_data: list[dict[str, Any]] = field(default_factory=list)
    custom_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionRule:
    """Rule for extracting custom fields from HTML."""

    name: str
    selector: str
    attribute: str | None = None  # None means text content
    multiple: bool = False
    transform: str | None = None  # strip, lower, int, float


def parse_html(html: str, url: str = "") -> BeautifulSoup:
    """Parse HTML string into BeautifulSoup tree."""
    return BeautifulSoup(html, "html.parser")


def extract_page(html: str, url: str = "", rules: list[ExtractionRule] | None = None) -> ExtractedPage:
    """Extract structured data from an HTML page."""
    soup = parse_html(html, url)
    page = ExtractedPage(url=url)

    # Title
    title_tag = soup.find("title")
    page.title = title_tag.get_text(strip=True) if title_tag else None

    # Meta description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and isinstance(meta, Tag):
        page.meta_description = meta.get("content", "")

    # Headings
    for level in range(1, 7):
        tag = f"h{level}"
        headings = [h.get_text(strip=True) for h in soup.find_all(tag)]
        if headings:
            page.headings[tag] = headings
            if level == 1:
                page.h1 = headings

    # Links
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if href and not href.startswith(("#", "javascript:")):
            page.links.append({"href": href, "text": text})

    # Images
    for img in soup.find_all("img"):
        src = img.get("src", "")
        alt = img.get("alt", "")
        if src:
            page.images.append({"src": src, "alt": alt})

    # Text content (stripped)
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    page.text_content = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))

    # Tables
    for table in soup.find_all("table"):
        rows: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if rows:
            page.tables.append(rows)

    # JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string or "")
            page.structured_data.append(data)
        except (json.JSONDecodeError, TypeError):
            pass

    # Custom extraction rules
    if rules:
        for rule in rules:
            page.custom_fields[rule.name] = _apply_rule(soup, rule)

    logger.debug(f"Extracted: {page.title}, {len(page.links)} links, {len(page.images)} images")
    return page


def _apply_rule(soup: BeautifulSoup, rule: ExtractionRule) -> Any:
    """Apply an extraction rule to the soup."""
    elements = soup.select(rule.selector)

    if not elements:
        return [] if rule.multiple else None

    def get_value(el: Tag) -> str | None:
        if rule.attribute:
            val = el.get(rule.attribute)
            return str(val) if val else None
        return el.get_text(strip=True)

    def transform(val: str | None) -> Any:
        if val is None:
            return None
        match rule.transform:
            case "strip": return val.strip()
            case "lower": return val.lower()
            case "int":
                try: return int(re.sub(r"[^\d-]", "", val))
                except ValueError: return None
            case "float":
                try: return float(re.sub(r"[^\d.-]", "", val))
                except ValueError: return None
            case _: return val

    if rule.multiple:
        return [transform(get_value(el)) for el in elements]
    return transform(get_value(elements[0]))


def extract_emails(text: str) -> list[str]:
    """Extract email addresses from text."""
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    return list(set(re.findall(pattern, text)))


def extract_phones(text: str) -> list[str]:
    """Extract phone numbers from text."""
    pattern = r"[\+]?[(]?[0-9]{1,4}[)]?[-\s\./0-9]{7,15}"
    return list(set(re.findall(pattern, text)))
