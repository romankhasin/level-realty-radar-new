from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

import feedparser

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "queries.json").read_text(encoding="utf-8"))
COMPETITORS = json.loads((ROOT / "competitors.json").read_text(encoding="utf-8"))
OUT = ROOT / "news.json"
MSK = timezone(timedelta(hours=3))

REALTY = [
    "недвижим", "девелоп", "застрой", "жилой комплекс", "жк ",
    "новостро", "квартир", "ипотек", "апартамент", "жиль", "дду",
    "бизнес-центр", "офисн", "складск", "коммерческ"
]
MARKETING = [
    "реклам", "маркетинг", "digital", "диджитал", "медиа", "бюджет",
    "бренд", "креатив", "лид", "cpl", "performance", "наружн", "ooh",
    "продвиж", "кампан", "таргет", "ретарг", "классифайд", "авито",
    "циан", "яндекс", "telegram"
]
TOPICS = {
    "Performance": ["лид", "cpl", "performance", "конверси", "заявк"],
    "Digital": ["digital", "диджитал", "programmatic", "olv", "ctv", "telegram", "яндекс", "авито", "циан"],
    "Наружная реклама": ["наружн", "ooh", "dooh", "билборд"],
    "Бренд": ["бренд", "репутац", "позиционирован", "креатив", "контент"],
    "Медиарынок": ["бюджет", "рынок рекламы", "медиаинвестици", "расход на реклам"],
    "Исследование": ["исследован", "аналитик", "опрос", "данные", "рейтинг"],
    "Рынок недвижимости": ["спрос", "продаж", "дду", "ипотек", "цены", "новостро"],
    "Коммерческая недвижимость": ["бизнес-центр", "офисн", "складск", "коммерческ"]
}

def clean_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()

def find_competitors(text: str) -> list[str]:
    lowered = text.lower()
    found = []
    for brand, aliases in COMPETITORS.items():
        for alias in aliases:
            alias = alias.lower()
            if len(alias) <= 3:
                if re.search(rf"(?<![\wа-яё]){re.escape(alias)}(?![\wа-яё])", lowered):
                    found.append(brand)
                    break
            elif alias in lowered:
                found.append(brand)
                break
    return found

def detect_topic(text: str) -> str:
    lowered = text.lower()
    scores = {name: sum(1 for keyword in keywords if keyword in lowered) for name, keywords in TOPICS.items()}
    return max(scores, key=scores.get) if scores and max(scores.values()) else "Новости"

def source_name(entry) -> str:
    if getattr(entry, "source", None) and getattr(entry.source, "title", None):
        return entry.source.title
    title = getattr(entry, "title", "")
    match = re.search(r" - ([^-]{2,60})$", title)
    return match.group(1).strip() if match else "Google Новости"

def original_title(title: str, source: str) -> str:
    suffix = " - " + source
    return title[:-len(suffix)].strip() if title.endswith(suffix) else title.strip()

def parse_date(entry) -> datetime:
    for key in ("published", "updated"):
        value = getattr(entry, key, None)
        if value:
            try:
                return parsedate_to_datetime(value).astimezone(MSK)
            except Exception:
                pass
    return datetime.now(MSK)

def load_existing() -> dict:
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"items": data}
    except Exception:
        return {"items": []}

def fetch_query(label: str, query: str) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=ru&gl=RU&ceid=RU:ru"
    )
    feed = feedparser.parse(url)
    if getattr(feed, "bozo", False) and not feed.entries:
        raise RuntimeError(str(getattr(feed, "bozo_exception", "RSS error")))

    result = []
    for entry in feed.entries[:50]:
        source = source_name(entry)
        title = original_title(getattr(entry, "title", ""), source)
        summary = clean_html(getattr(entry, "summary", ""))
        text = (title + " " + summary).lower()

        realty_hits = sum(1 for keyword in REALTY if keyword in text)
        marketing_hits = sum(1 for keyword in MARKETING if keyword in text)
        if realty_hits < 1:
            continue

        competitors = find_competitors(title + " " + summary)
        importance = min(100, 45 + realty_hits * 8 + marketing_hits * 4 + len(competitors) * 10)
        date = parse_date(entry)
        link = getattr(entry, "link", "")

        result.append({
            "id": hashlib.sha1(link.encode()).hexdigest()[:16],
            "date": date.date().isoformat(),
            "source": source,
            "title": title,
            "url": link,
            "summary": summary[:420],
            "topic": detect_topic(text),
            "competitors": competitors,
            "importance": importance,
            "query": label
        })
    return result

def main() -> None:
    existing = load_existing()
    by_url = {item.get("url"): item for item in existing.get("items", []) if item.get("url")}
    successful = 0
    failed = 0

    for item in CFG["queries"] + CFG["source_queries"]:
        try:
            rows = fetch_query(item["name"], item["query"])
            for row in rows:
                by_url[row["url"]] = row
            successful += 1
            print(f"{item['name']}: {len(rows)}")
        except Exception as error:
            failed += 1
            print(f"{item['name']}: ERROR {error}")

    cutoff = (datetime.now(MSK) - timedelta(days=CFG.get("retention_days", 180))).date().isoformat()
    rows = [item for item in by_url.values() if item.get("date", "") >= cutoff]

    seen_titles = set()
    deduplicated = []
    for item in sorted(rows, key=lambda value: (value.get("date", ""), value.get("importance", 0)), reverse=True):
        title_key = re.sub(r"\W+", "", item.get("title", "").lower())[:140]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        deduplicated.append(item)

    payload = {
        "updated_at": datetime.now(MSK).isoformat(timespec="seconds"),
        "items": deduplicated[:CFG.get("max_items", 500)],
        "stats": {"queries_ok": successful, "queries_failed": failed}
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved", len(payload["items"]))

if __name__ == "__main__":
    main()
