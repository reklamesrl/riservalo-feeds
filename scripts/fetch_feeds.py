#!/usr/bin/env python3
"""
fetch_feeds.py — scarica i feed RSS e genera public/feeds.json
Gira su GitHub Actions: nessun blocco CORS, nessun proxy necessario.
"""

import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

# ── FEED DA SCARICARE ──────────────────────────────────────────────────────────
FEEDS = {
    "offerte": [
        {"url": "https://www.ilsalvagente.it/feed/",  "label": "Il Salvagente", "cat": "Risparmio"},
        {"url": "https://www.dissapore.com/feed/",     "label": "Dissapore",     "cat": "Food & Vita"},
        {"url": "https://www.stylosophy.it/feed/",     "label": "Stylosophy",    "cat": "Moda"},
    ],
    "moda": [
        {"url": "https://www.stylosophy.it/feed/",     "label": "Stylosophy",    "cat": "Moda"},
        {"url": "https://www.ilsalvagente.it/feed/",   "label": "Il Salvagente", "cat": "Acquisti"},
    ],
    "lifestyle": [
        {"url": "https://www.gustoblog.it/feed/",      "label": "Gustoblog",     "cat": "Food"},
        {"url": "https://www.dissapore.com/feed/",     "label": "Dissapore",     "cat": "Food & Life"},
        {"url": "https://www.ilsalvagente.it/feed/",   "label": "Il Salvagente", "cat": "Risparmio"},
    ],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RSSBot/1.0; +https://riservalo.it)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

MAX_ITEMS = 10
TIMEOUT   = 15


def parse_date(date_str: str) -> str:
    """Normalizza la data RSS in ISO 8601."""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def extract_image(item_el: ET.Element, ns: dict) -> str:
    """Cerca l'immagine in enclosure, media:content o prima <img> della description."""
    # enclosure
    enc = item_el.find("enclosure")
    if enc is not None:
        url = enc.get("url", "")
        if url and any(url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
            return url

    # media:content (namespace)
    for tag in ("media:content", "{http://search.yahoo.com/mrss/}content"):
        mc = item_el.find(tag)
        if mc is not None:
            url = mc.get("url", "")
            if url:
                return url

    # prima <img> nella description
    desc = item_el.findtext("description") or ""
    import re
    m = re.search(r'<img[^>]+src=["\']([^"\']+\.(jpe?g|png|webp|gif))["\']', desc, re.IGNORECASE)
    if m:
        return m.group(1)

    return ""


def fetch_feed(feed: dict) -> list:
    """Scarica e parsa un feed RSS, restituisce lista di item."""
    url   = feed["url"]
    label = feed["label"]
    cat   = feed["cat"]

    try:
        req  = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except Exception as e:
        print(f"  ✗ {label}: {e}")
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"  ✗ {label} (XML parse error): {e}")
        return []

    # Supporta sia RSS <channel><item> che Atom
    items_el = root.findall(".//item")
    if not items_el:
        items_el = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    results = []
    for item in items_el[:MAX_ITEMS]:
        title = (item.findtext("title") or "").strip()
        if len(title) < 4:
            continue

        link = (
            item.findtext("link")
            or item.findtext("{http://www.w3.org/2005/Atom}link")
            or item.findtext("guid")
            or ""
        ).strip()

        desc_raw = item.findtext("description") or item.findtext("{http://www.w3.org/2005/Atom}summary") or ""
        import re
        desc = re.sub(r"<[^>]+>", "", desc_raw)
        desc = re.sub(r"&[a-z]+;", " ", desc).strip()[:160] + "…"

        pub = parse_date(item.findtext("pubDate") or item.findtext("{http://www.w3.org/2005/Atom}updated") or "")
        image = extract_image(item, {})

        results.append({
            "title":       title,
            "description": desc,
            "link":        link,
            "pubDate":     pub,
            "image":       image,
            "cat":         cat,
            "source":      label,
        })

    print(f"  ✓ {label}: {len(results)} articoli")
    return results


def main():
    output = {}
    seen_urls = set()  # deduplicazione globale

    for section, feeds in FEEDS.items():
        print(f"\n[{section.upper()}]")
        all_items = []

        for feed in feeds:
            items = fetch_feed(feed)
            for item in items:
                if item["link"] not in seen_urls:
                    seen_urls.add(item["link"])
                    all_items.append(item)

        # Ordina per data decrescente
        all_items.sort(key=lambda x: x["pubDate"] or "", reverse=True)
        output[section] = all_items[:20]  # max 20 per sezione

    # Scrivi il JSON
    out_path = Path(__file__).parent.parent / "public" / "feeds.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(),
        "feeds": output,
    }, ensure_ascii=False, indent=2))

    print(f"\n✅ Scritto: {out_path}")
    for section, items in output.items():
        print(f"   {section}: {len(items)} articoli")


if __name__ == "__main__":
    main()
