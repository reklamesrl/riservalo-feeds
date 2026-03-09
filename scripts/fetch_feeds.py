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
        {"url": "https://www.stylosophy.it/feed/",      "label": "Stylosophy",   "cat": "Moda"},
        {"url": "https://www.grazia.it/moda/feed",      "label": "Grazia",       "cat": "Moda"},
        {"url": "https://www.gustoblog.it/feed/",       "label": "Gustoblog",    "cat": "Food"},
        {"url": "https://www.dissapore.com/feed/",      "label": "Dissapore",    "cat": "Food"},
        {"url": "https://www.winemag.it/feed/",         "label": "Wine Mag",     "cat": "Vino"},
        {"url": "https://www.gamberorosso.it/feed/",    "label": "Gambero Rosso","cat": "Food"},
    ],
    "moda": [
        {"url": "https://www.stylosophy.it/feed/",      "label": "Stylosophy",   "cat": "Moda"},
        {"url": "https://www.grazia.it/moda/feed",      "label": "Grazia",       "cat": "Moda"},
    ],
    "lifestyle": [
        {"url": "https://www.gustoblog.it/feed/",       "label": "Gustoblog",    "cat": "Food"},
        {"url": "https://www.dissapore.com/feed/",      "label": "Dissapore",    "cat": "Cucina"},
        {"url": "https://www.winemag.it/feed/",         "label": "Wine Mag",     "cat": "Vino"},
        {"url": "https://www.gamberorosso.it/feed/",    "label": "Gambero Rosso","cat": "Food"},
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
    """Cerca l'immagine in enclosure, media:content, media:thumbnail o <img> nella description."""
    import re

    # Tutti i possibili namespace media
    MEDIA_NS = [
        "media:content", "media:thumbnail",
        "{http://search.yahoo.com/mrss/}content",
        "{http://search.yahoo.com/mrss/}thumbnail",
        "{http://video.search.yahoo.com/mrss/}content",
    ]

    # enclosure
    enc = item_el.find("enclosure")
    if enc is not None:
        url = enc.get("url", "")
        if url and re.search(r"\.(jpe?g|png|webp|gif)", url, re.I):
            return url

    # media:content / media:thumbnail con vari namespace
    for tag in MEDIA_NS:
        for el in item_el.iter(tag.split("}")[-1] if "}" in tag else tag):
            url = el.get("url", "")
            if url:
                return url
        mc = item_el.find(tag)
        if mc is not None:
            url = mc.get("url", "")
            if url:
                return url

    # Cerca qualsiasi tag con attributo url che sia un'immagine
    for child in item_el.iter():
        url = child.get("url", "")
        if url and re.search(r"\.(jpe?g|png|webp|gif)", url, re.I):
            return url

    # prima <img> nella description (anche con entità HTML)
    desc = item_el.findtext("description") or ""
    desc = desc.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc, re.IGNORECASE)
    if m:
        url = m.group(1)
        if not url.startswith("data:"):  # escludi base64
            return url

    # content:encoded (alcuni feed WordPress)
    for tag in ("{http://purl.org/rss/1.0/modules/content/}encoded", "content:encoded"):
        encoded = item_el.findtext(tag) or ""
        if encoded:
            encoded = encoded.replace("&lt;", "<").replace("&gt;", ">")
            m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', encoded, re.IGNORECASE)
            if m:
                url = m.group(1)
                if not url.startswith("data:"):
                    return url

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

        img_count = sum(1 for r in results if r["image"])
        print(f"  ✓ {label}: {len(results)} articoli, {img_count} con immagine")
    return results


def main():
    output = {}
    feed_cache = {}  # cache per URL: evita di scaricare lo stesso feed 2 volte

    for section, feeds in FEEDS.items():
        print(f"\n[{section.upper()}]")
        seen_links = set()  # deduplicazione per sezione
        all_items = []

        for feed in feeds:
            url = feed["url"]
            # Usa cache se il feed e' gia' stato scaricato (magari con label/cat diversi)
            if url in feed_cache:
                raw_items = feed_cache[url]
                print(f"  ↩ {feed['label']} (da cache)")
                # Aggiorna cat/source con quelli di questa sezione
                items = [{**item, "cat": feed["cat"], "source": feed["label"]} for item in raw_items]
            else:
                items = fetch_feed(feed)
                feed_cache[url] = items

            for item in items:
                if item["link"] not in seen_links:
                    seen_links.add(item["link"])
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
