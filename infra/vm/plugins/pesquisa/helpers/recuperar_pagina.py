"""Recover a blocked page (403/429, Cloudflare "Just a moment...", paywall) from a third-party copy, so the source does
not vanish from the research (14/10: _ler_pagina returned "" on any status >= 400).

Ported from Hermes Agent, skills/web/blocked-page-recovery/scripts/recover_page.py (recover() and its routes), MIT:

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

Changes from the original: Jina Reader runs without a key too (its free tier; JINA_API_KEY is used when present) and can
be turned off; one overall deadline for the whole ladder and a single short wait on 429, only for the Wayback snapshot (the research
reads 14 pages at once);
the Wayback copy is fetched raw (`id_`, without the archive's toolbar) and must be of the page asked for, on
web.archive.org (a snapshot of the page the site redirected to is not a copy); an archive.today copy must stay on
archive.today; the date of an
archive.today copy is read from the page; every result carries the label the source is cited with. Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

ARCHIVE_TODAY_HOSTS = ["archive.ph", "archive.md", "archive.li", "archive.is"]
JINA = True  # Jina Reader without a key (rate-limited); False turns the route off

# Titles that mean "this is not the page you asked for".
INTERSTITIAL_TITLES = (
    "just a moment",
    "redirecting",
    "google search",
    "attention required",
    "access denied",
    "are you a robot",
    "one more step",
    "acesso negado",
)
# Of those, the ones a live 200 answer may carry when it is a bot wall (Cloudflare and friends answer 200 sometimes).
WALL_TITLES = ("just a moment", "attention required", "access denied", "are you a robot", "one more step", "acesso negado")

# Below these floors a body is a stub or an error page, not content.
MIN_BODY_BYTES = {"wayback": 3072, "archive_today": 3072, "jina": 512}

REDIRECT_STUB_RE = re.compile(
    r'http-equiv=["\']?refresh|window\.location|location\.replace', re.IGNORECASE
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
JINA_TITLE_RE = re.compile(r"^Title:\s*(.+)$", re.MULTILINE)
ARCHIVE_DATE_RE = re.compile(r'itemprop=["\']pubdate["\'][^>]*datetime=["\'](\d{4}-\d{2}-\d{2})'
                             r'|datetime=["\'](\d{4}-\d{2}-\d{2})[^"\']*["\'][^>]*itemprop=["\']pubdate', re.IGNORECASE)


def _fetch(url: str, timeout: int, headers: dict | None = None, retries_on_429: int = 0) -> tuple[int, bytes, str]:
    """(status, body, final URL after redirects); status 0 when the request did not go through."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    for attempt in range(retries_on_429 + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read(3_000_000), resp.geturl()
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries_on_429:
                time.sleep(3 * (attempt + 1))
                continue
            try:
                corpo = exc.read() if exc.fp else b""
            except Exception:
                corpo = b""
            return exc.code, corpo, exc.geturl() or url
        except (urllib.error.URLError, OSError, ValueError):
            return 0, b"", url
    return 0, b"", url


def _page_title(body: bytes) -> str:
    texto = body[:65536].decode("utf-8", "replace")
    m = TITLE_RE.search(texto) or JINA_TITLE_RE.search(texto[:2000])
    return re.sub(r"\s+", " ", m.group(1)).strip().lower() if m else ""


def validate(body: bytes, route: str, target_url: str) -> str | None:
    """Return a rejection reason, or None if the body looks like real content."""
    floor = MIN_BODY_BYTES.get(route, 3072)
    if len(body) < floor:
        return f"body_too_small:{len(body)}<{floor}"
    title = _page_title(body)
    for marker in INTERSTITIAL_TITLES:
        if marker in title:
            return f"interstitial_title:{marker!r}"
    # Redirect stub: small-ish page whose only job is bouncing back to the
    # original (blocked) host — the classic AMP-cache failure mode.
    if len(body) < 8192 and REDIRECT_STUB_RE.search(body.decode("utf-8", "replace")):
        target_host = urllib.parse.urlsplit(target_url).hostname or ""
        if target_host and target_host.encode() in body:
            return "redirect_stub_to_origin"
    return None


def bloqueada(status: int, body: bytes) -> bool:
    """The live answer is a wall, not the page: an error status, or a 200 whose title is an interstitial."""
    if status >= 400:
        return True
    title = _page_title(body or b"")
    return any(marker in title for marker in WALL_TITLES)


def _cru(snap_url: str) -> str:
    """The snapshot as archived, without the Wayback toolbar (".../web/<ts>id_/<url>"; "/web/2/" is the newest one)."""
    return re.sub(r"(/web/\d{1,14})(?:[a-z]{2}_)?/", r"\1id_/", snap_url, count=1)


def _mesma_pagina(pedida: str, arquivada: str) -> bool:
    """The archived address is the page asked for (host without www, path without the trailing slash): a snapshot of
    the home page or of a login page that the site redirected to is not a copy of the article."""
    def chave(u: str) -> tuple:
        p = urllib.parse.urlsplit(u)
        return (p.hostname or "").lower().removeprefix("www."), p.path.rstrip("/") or "/"
    return chave(pedida) == chave(arquivada)


def try_wayback(url: str, timeout: int) -> dict | None:
    snap_url = None
    snap_ts = None
    discovery = "https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="")
    status, raw, _ = _fetch(discovery, timeout)
    if status == 200:
        try:
            closest = json.loads(raw).get("archived_snapshots", {}).get("closest", {})
        except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
            closest = {}
        if closest.get("available") and closest.get("url"):
            snap_url = closest["url"].replace(
                "http://web.archive.org", "https://web.archive.org"
            )
            snap_ts = closest.get("timestamp")
    if snap_url is None:
        # Discovery API is rate-limited far more aggressively than snapshot
        # serving. Fall back to the redirect form: /web/2/<url> bounces to
        # the newest snapshot if one exists (404 page otherwise).
        snap_url = "https://web.archive.org/web/2/" + url
    status, body, final_url = _fetch(_cru(snap_url), timeout, retries_on_429=1)  # snapshots: 429 often clears in seconds
    if status != 200 or validate(body, "wayback", url):
        return None
    m = re.match(r"https://web\.archive\.org/web/\d+(?:[a-z]{2}_)?/(.+)$", final_url)
    if not m or not _mesma_pagina(url, m.group(1)):
        return None  # bounced off the archive, or the snapshot is of another page (a redirect): not a copy
    m = re.search(r"/web/(\d{14})", final_url)
    snap_ts = (m.group(1) if m else None) or snap_ts
    return {
        "route": "wayback",
        "provenance": "snapshot",
        "snapshot_timestamp": snap_ts,
        "source_url": final_url,
        "body": body,
    }


def try_archive_today(url: str, timeout: int) -> dict | None:
    for host in ARCHIVE_TODAY_HOSTS:
        fetch_url = f"https://{host}/newest/{url}"
        status, body, final_url = _fetch(fetch_url, timeout)
        if status != 200:
            continue
        if validate(body, "archive_today", url):
            continue  # 429 bodies and interstitials land here
        if (urllib.parse.urlsplit(final_url).hostname or "") not in ARCHIVE_TODAY_HOSTS:
            continue  # sent somewhere else: not a copy
        m = ARCHIVE_DATE_RE.search(body[:200000].decode("utf-8", "replace"))
        data = (m.group(1) or m.group(2)) if m else None
        return {
            "route": f"archive_today:{host}",
            "provenance": "snapshot",
            "snapshot_timestamp": data.replace("-", "") + "000000" if data else None,
            "source_url": final_url,
            "body": body,
        }
    return None


def try_jina(url: str, timeout: int) -> dict | None:
    if not JINA:
        return None
    key = os.environ.get("JINA_API_KEY")
    status, body, _ = _fetch("https://r.jina.ai/" + url, timeout,
                             headers={"Authorization": f"Bearer {key}"} if key else None)
    if status != 200 or validate(body, "jina", url):
        return None
    return {
        "route": "jina_reader",
        "provenance": "live",
        "snapshot_timestamp": time.strftime("%Y%m%d%H%M%S", time.gmtime()),
        "source_url": "https://r.jina.ai/" + url,
        "body": body,
    }


ROUTES = (try_wayback, try_archive_today, try_jina)


def recover(url: str, timeout: int = 12, prazo: float = 45) -> dict | None:
    """First genuine copy along the ladder, or None. `prazo`: seconds for the whole ladder (a route already started
    finishes; no new one starts after it)."""
    if not str(url or "").startswith(("http://", "https://")):
        return None
    fim = time.monotonic() + prazo
    for route_fn in ROUTES:
        if time.monotonic() >= fim:
            break
        try:
            result = route_fn(url, timeout)
        except Exception:  # one broken route never stops the others
            result = None
        if result:
            result["label"] = rotulo(result)
            return result
    return None


def rotulo(result: dict) -> str:
    """How the source is cited: an archived copy carries its date (it may be old; never the live page)."""
    ts = str(result.get("snapshot_timestamp") or "")
    data = f"{ts[6:8]}/{ts[4:6]}/{ts[:4]}" if re.fullmatch(r"\d{8,14}", ts) else ""
    if result.get("provenance") == "live":
        return f"cópia lida pelo Jina Reader em {data}" if data else "cópia lida pelo Jina Reader"
    return f"cópia arquivada de {data}" if data else "cópia arquivada (data não informada)"
