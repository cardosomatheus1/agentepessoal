"""Read RSS / Atom / JSON Feed sources and discover the feed behind a page.

Ported from Hermes Agent, optional-skills/research/rss-feeds/scripts/feed.py, MIT:

    MIT License

    Copyright (c) 2025 Nous Research

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

Changes from the original: no command line; the fetch is passed in (tests use a fake one) and returns the final URL
too; `read` raises LookupError instead of exiting; `discover` can skip the well-known paths. Stdlib only.
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "media": "http://search.yahoo.com/mrss/",
}
FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/feed+json", "application/json")
COMMON_FEED_PATHS = ("/feed", "/feed.xml", "/rss", "/rss.xml", "/atom.xml", "/index.xml", "/feed.json", "/blog/feed", "/blog/rss.xml")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", text))).strip()


def parse_date(value: str | None) -> str | None:
    """Normalise RFC 822 (RSS) and ISO 8601 (Atom/JSON Feed) dates to UTC ISO."""
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _text(el, *paths) -> str | None:
    for p in paths:
        found = el.find(p, NS)
        if found is not None and (found.text or "").strip():
            return found.text
    return None


def _atom_link(entry) -> str | None:
    alternate = None
    for link in entry.findall("atom:link", NS) + entry.findall("link"):
        href = link.get("href")
        if not href:
            continue
        rel = link.get("rel", "alternate")
        if rel == "alternate":
            return href
        alternate = alternate or href
    return alternate


def parse_xml(data: bytes) -> dict:
    root = ET.fromstring(data)
    tag = root.tag.rsplit("}", 1)[-1].lower()
    if tag == "feed":  # Atom
        title = strip_html(_text(root, "atom:title"))
        entries = []
        for e in root.findall("atom:entry", NS):
            entries.append({
                "title": strip_html(_text(e, "atom:title")),
                "link": _atom_link(e),
                "published": parse_date(_text(e, "atom:published", "atom:updated")),
                "author": strip_html(_text(e, "atom:author/atom:name", "dc:creator")),
                "summary": strip_html(_text(e, "atom:summary", "atom:content"))[:2000],
            })
        return {"format": "atom", "title": title, "entries": entries}
    channel = root.find("channel") if tag == "rss" else root  # RSS 2.0 vs RDF/RSS 1.0
    if channel is None:
        raise ValueError(f"unrecognised XML root <{tag}>")
    entries = []
    for item in channel.iter("item") if tag == "rss" else root.iter("{http://purl.org/rss/1.0/}item"):
        entries.append({
            "title": strip_html(_text(item, "title", "{http://purl.org/rss/1.0/}title")),
            "link": (_text(item, "link", "{http://purl.org/rss/1.0/}link") or "").strip() or None,
            "published": parse_date(_text(item, "pubDate", "dc:date")),
            "author": strip_html(_text(item, "dc:creator", "author")),
            "summary": strip_html(_text(item, "content:encoded", "description", "{http://purl.org/rss/1.0/}description"))[:2000],
        })
    return {"format": "rss", "title": strip_html(_text(channel, "title", "{http://purl.org/rss/1.0/}title")), "entries": entries}


def parse_json_feed(data: bytes) -> dict:
    doc = json.loads(data)
    entries = []
    for item in doc.get("items", []):
        authors = item.get("authors") or ([item["author"]] if item.get("author") else [])
        entries.append({
            "title": strip_html(item.get("title")),
            "link": item.get("url") or item.get("external_url"),
            "published": parse_date(item.get("date_published") or item.get("date_modified")),
            "author": ", ".join(a.get("name", "") for a in authors if isinstance(a, dict)) or None,
            "summary": strip_html(item.get("summary") or item.get("content_text") or item.get("content_html"))[:2000],
        })
    return {"format": "jsonfeed", "title": strip_html(doc.get("title")), "entries": entries}


def parse_feed(data: bytes, content_type: str = "") -> dict:
    head = data.lstrip()[:1]
    if head == b"{" or "json" in content_type:
        return parse_json_feed(data)
    return parse_xml(data)


def discover(page_url: str, page_html: bytes, common_paths: bool = True) -> list[str]:
    """Return candidate feed URLs for a page: <link rel=alternate> first, then well-known paths."""
    text = page_html.decode("utf-8", "replace")
    found: list[str] = []
    for m in re.finditer(r"<link\b[^>]*>", text, re.IGNORECASE):
        tag = m.group(0)
        type_m = re.search(r"""type\s*=\s*["']([^"']+)""", tag, re.IGNORECASE)
        href_m = re.search(r"""href\s*=\s*["']([^"']+)""", tag, re.IGNORECASE)
        rel_m = re.search(r"""rel\s*=\s*["']([^"']+)""", tag, re.IGNORECASE)
        if not href_m or not type_m or type_m.group(1).lower() not in FEED_TYPES:
            continue
        if rel_m and "alternate" not in rel_m.group(1).lower():
            continue
        url = urllib.parse.urljoin(page_url, html.unescape(href_m.group(1)))
        if url not in found:
            found.append(url)
    if found or not common_paths:
        return found
    parsed = urllib.parse.urlsplit(page_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return [base + p for p in COMMON_FEED_PATHS]


def looks_like_feed(data: bytes, content_type: str) -> bool:
    head = data.lstrip()[:300].lower()
    return head.startswith(b"{") and b"items" in data[:2000] or b"<rss" in head or b"<feed" in head or b"<rdf" in head


def read(url: str, fetch, common_paths: bool = True) -> dict:
    """The feed at `url`, or the one the page advertises. `fetch(url) -> (status, body, content_type)`; raises
    LookupError when there is none, OSError/ValueError when the page itself could not be read."""
    status, data, ctype = fetch(url)
    if status != 200:
        raise OSError(f"HTTP {status}" if status else "sem resposta")
    if looks_like_feed(data, ctype):
        feed = parse_feed(data, ctype)
        feed["url"] = url
        return feed
    candidates = discover(url, data, common_paths)
    for cand in candidates:
        try:
            cstatus, cdata, cctype = fetch(cand)
        except OSError:
            continue
        if cstatus == 200 and looks_like_feed(cdata, cctype):
            feed = parse_feed(cdata, cctype)
            feed["url"] = cand
            feed["discovered_from"] = url
            return feed
    raise LookupError(f"nenhum feed em {url} ({len(candidates)} endereços tentados)")
