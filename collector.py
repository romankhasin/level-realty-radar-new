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
CONFIG = json.loads((ROOT / "queries.json").read_text(encoding="utf-8"))
COMPETITORS = json.loads((ROOT / "competitors.json").read_text(encoding="utf-8"))
OUTPUT = ROOT / "news.json"
MOSCOW = timezone(timedelta(hours=3))

REALTY_WORDS = [
    "недвижим", "девелоп", "застрой", "жилой комплекс", "жк ",
    "новостро", "квартир", "ипотек", "апартамент", "жиль", "дду",
    "бизнес-центр", "офисн", "складск", "коммерческ"
]

MARKETING_WORDS = [
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
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", without_tags).strip()


def find_competitors(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []

    for brand, aliases in COMPETITORS.items():
        for alias in aliases:
            alias = alias.lower()

            if len(alias) <= 3:
                pattern = rf"(?<![\wа-яё]){re.escape(alias)}(?![\wа-яё])"
                if re.search(pattern, lowered):
                    found.append(brand)
                    break
            elif alias in lowered:
                found.append(brand)
                break

    return found


def detect_topic(text: str) -> str:
    lowered = text.lower()
    scores = {
        topic: sum(1 for keyword in keywords if keyword in lowered)
        for topic, keywords in TOPICS.items()
    }

    if not scores or max(scores.values()) == 0:
        return "Новости"

    return max(scores, key=scores.get)


def get_source_name(entry) -> str:
    if getattr(entry, "source", None) and getattr(entry.source, "title", None):
        return entry.source.title

    title = getattr(entry, "title", "")
    match = re.search(r" - ([^-]{2,60})$", title)
    return match.group(1).strip() if match else "Google Новости"


def remove_source_suffix(title: str, source: str) -> str:
    suffix = " - " + source
    return title[:-len(suffix)].strip() if title.endswith(suffix) else title.strip()


def parse_date(entry) -> datetime:
    for key in ("published", "updated"):
        value = getattr(entry, key, None)
        if value:
            try:
                return parsedate_to_datetime(value).astimezone(MOSCOW)
            except Exception:
                continue

    return datetime.now(MOSCOW)


def load_existing() -> dict:
    try:
        data = json.loads(OUTPUT.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"items": data}
    except Exception:
        return {"items": []}


def collect_query(label: str, query: str) -> list[dict]:
    feed_url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=ru&gl=RU&ceid=RU:ru"
    )

    feed = feedparser.parse(feed_url)

    if getattr(feed, "bozo", False) and not feed.entries:
        raise RuntimeError(str(getattr(feed, "bozo_exception", "RSS error")))

    items: list[dict] = []

    for entry in feed.entries[:50]:
        source = get_source_name(entry)
        title = remove_source_suffix(getattr(entry, "title", ""), source)
        summary = clean_html(getattr(entry, "summary", ""))
        combined = (title + " " + summary).lower()

        realty_hits = sum(1 for word in REALTY_WORDS if word in combined)
        marketing_hits = sum(1 for word in MARKETING_WORDS if word in combined)

        if realty_hits < 1:
            continue

        competitors = find_competitors(title + " " + summary)
        importance = min(
            100,
            45 + realty_hits * 8 + marketing_hits * 4 + len(competitors) * 10
        )
        published = parse_date(entry)
        link = getattr(entry, "link", "")

        items.append({
            "id": hashlib.sha1(link.encode()).hexdigest()[:16],
            "date": published.date().isoformat(),
            "source": source,
            "title": title,
            "url": link,
            "summary": summary[:420],
            "topic": detect_topic(combined),
            "competitors": competitors,
            "importance": importance,
            "query": label
        })

    return items


def main() -> None:
    existing = load_existing()
    by_url = {
        item.get("url"): item
        for item in existing.get("items", [])
        if item.get("url")
    }

    successful = 0
    failed = 0

    for item in CONFIG["queries"] + CONFIG["source_queries"]:
        try:
            rows = collect_query(item["name"], item["query"])
            for row in rows:
                by_url[row["url"]] = row

            successful += 1
            print(f"{item['name']}: {len(rows)}")
        except Exception as error:
            failed += 1
            print(f"{item['name']}: ERROR {error}")

    cutoff = (
        datetime.now(MOSCOW)
        - timedelta(days=CONFIG.get("retention_days", 180))
    ).date().isoformat()

    rows = [
        item for item in by_url.values()
        if item.get("date", "") >= cutoff
    ]

    seen_titles: set[str] = set()
    deduplicated: list[dict] = []

    for item in sorted(
        rows,
        key=lambda value: (
            value.get("date", ""),
            value.get("importance", 0)
        ),
        reverse=True
    ):
        title_key = re.sub(r"\W+", "", item.get("title", "").lower())[:140]

        if title_key in seen_titles:
            continue

        seen_titles.add(title_key)
        deduplicated.append(item)

    payload = {
        "updated_at": datetime.now(MOSCOW).isoformat(timespec="seconds"),
        "items": deduplicated[:CONFIG.get("max_items", 500)],
        "stats": {
            "queries_ok": successful,
            "queries_failed": failed
        }
    }

    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("Saved", len(payload["items"]))


if __name__ == "__main__":
    main()
