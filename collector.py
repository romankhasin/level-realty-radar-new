from __future__ import annotations

import hashlib
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
COMPETITORS = json.loads((ROOT / "competitors.json").read_text(encoding="utf-8"))
OUTPUT = ROOT / "news.json"
MOSCOW = timezone(timedelta(hours=3))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; LevelRealtyRadar/2.0; "
        "+https://github.com/romankhasin)"
    )
}

REALTY_WORDS = [
    "недвижим", "девелоп", "застрой", "жилой комплекс", "жк ",
    "новостро", "квартир", "ипотек", "апартамент", "жиль", "дду",
    "бизнес-центр", "офисн", "складск", "коммерческ", "домклик",
    "циан", "первичн", "вторичн"
]

MARKETING_WORDS = [
    "реклам", "маркетинг", "digital", "диджитал", "медиа", "бюджет",
    "бренд", "креатив", "лид", "cpl", "cpm", "ctr", "performance",
    "наружн", "ooh", "dooh", "продвиж", "кампан", "таргет", "ретарг",
    "классифайд", "авито", "циан", "яндекс", "telegram", "olv", "ctv",
    "аудитори", "охват", "конверси", "контент", "позиционирован"
]

TOPICS = {
    "Performance": ["лид", "cpl", "performance", "конверси", "заявк", "продаж"],
    "Digital": ["digital", "диджитал", "programmatic", "olv", "ctv", "telegram", "яндекс", "авито", "циан"],
    "Наружная реклама": ["наружн", "ooh", "dooh", "билборд"],
    "Бренд и креатив": ["бренд", "репутац", "позиционирован", "креатив", "контент", "ролик"],
    "Медиарынок": ["бюджет", "рынок рекламы", "медиаинвестици", "расход на реклам", "cpm"],
    "Исследование": ["исследован", "аналитик", "опрос", "данные", "рейтинг", "измерен"],
    "Рынок недвижимости": ["спрос", "продаж", "дду", "ипотек", "цены", "новостро", "сделк"],
    "Коммерческая недвижимость": ["бизнес-центр", "офисн", "складск", "коммерческ"]
}


def request(url: str, timeout: int = 12) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response


def clean_text(value: str) -> str:
    decoded = html.unescape(value or "")
    soup = BeautifulSoup(decoded, "html.parser")
    text = soup.get_text(" ", strip=True)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(url: str) -> str:
    return url.split("#")[0].strip()


def find_competitors(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []

    for brand, aliases in COMPETITORS.items():
        for alias in aliases:
            alias = alias.lower()

            if len(alias) <= 3:
                pattern = rf"(?<![\wа-яё]){re.escape(alias)}(?![\wа-яё])"
                matched = re.search(pattern, lowered)
            else:
                matched = alias in lowered

            if matched:
                found.append(brand)
                break

    return found


def detect_topic(text: str) -> str:
    lowered = text.lower()
    scores = {
        topic: sum(1 for keyword in keywords if keyword in lowered)
        for topic, keywords in TOPICS.items()
    }
    return max(scores, key=scores.get) if scores and max(scores.values()) else "Новости"


def generate_analysis(
    text: str,
    topic: str,
    competitors: list[str],
    importance: int
) -> tuple[str, str, str, list[str]]:
    lowered = text.lower()

    if competitors:
        signal_type = "Действие конкурента"
        value = (
            f"Материал показывает активность {', '.join(competitors[:3])}. "
            "Для Level это повод проверить их позиционирование, каналы, оферы "
            "и возможное влияние на долю рекламного присутствия."
        )
        recommendations = [
            "Сравнить коммуникацию конкурента с текущими сообщениями Level.",
            "Проверить изменение поискового интереса и рекламной активности конкурента.",
            "Оценить, применима ли механика к релевантным проектам Level."
        ]
    elif topic == "Performance":
        signal_type = "Практический кейс"
        value = (
            "Материал может помочь улучшить лидогенерацию и оценку каналов. "
            "Особенно важно смотреть не только на CPL, но и на качество обращения."
        )
        recommendations = [
            "Сопоставить механику с текущими кампаниями Level.",
            "Оценивать дозвон, квалификацию лида и движение по CRM.",
            "Провести ограниченный тест с заранее определённым KPI."
        ]
    elif topic == "Digital":
        signal_type = "Новый инструмент"
        value = (
            "Материал может указывать на новый digital-канал, формат или способ "
            "работы с аудиторией, который стоит проверить в медиамиксе Level."
        )
        recommendations = [
            "Проверить доступность формата у текущих площадок и DSP.",
            "Сформировать небольшой тестовый бюджет и контрольную группу.",
            "Оценить вклад в визиты, брендовый поиск и post-view конверсии."
        ]
    elif topic == "Наружная реклама":
        signal_type = "Медийная возможность"
        value = (
            "Для Level материал полезен при планировании OOH/DOOH и оценке "
            "запоминаемости коммуникации, а не только количества контактов."
        )
        recommendations = [
            "Проверить простоту ключевого сообщения и визуальную иерархию.",
            "Связать OOH-волну с динамикой брендовых запросов.",
            "Использовать измерение brand lift или узнавания макета."
        ]
    elif topic == "Исследование":
        signal_type = "Исследование"
        value = (
            "Данные могут использоваться как аргумент при выборе аудитории, "
            "каналов, KPI или рекламного сообщения для проектов Level."
        )
        recommendations = [
            "Проверить методологию и размер выборки.",
            "Сопоставить выводы с внутренними данными Level и CRM.",
            "Использовать релевантные цифры при защите медиастратегии."
        ]
    elif topic == "Бренд и креатив":
        signal_type = "Креативный сигнал"
        value = (
            "Материал может помочь усилить позиционирование проектов Level, "
            "визуальную заметность и понятность рекламного сообщения."
        )
        recommendations = [
            "Проверить механику на текущих креативах Level.",
            "Тестировать один сильный продуктовый аргумент на макет.",
            "Сравнить эмоциональный и рациональный варианты сообщения."
        ]
    elif topic in {"Рынок недвижимости", "Коммерческая недвижимость"}:
        signal_type = "Рыночный сигнал"
        value = (
            "Изменение спроса, цен или условий покупки может повлиять на оферы, "
            "сегментацию и распределение рекламного бюджета Level."
        )
        recommendations = [
            "Актуализировать оферы и сообщения под текущий спрос.",
            "Проверить различия по классам жилья и локациям.",
            "Скорректировать окна ретаргетинга и приоритеты проектов."
        ]
    else:
        signal_type = "Информационный сигнал"
        value = (
            "Материал стоит использовать как дополнительный контекст для "
            "медиапланирования и коммуникации Level."
        )
        recommendations = [
            "Проверить релевантность для текущих проектов.",
            "Сопоставить с внутренними данными и планами кампаний.",
            "Добавить в обсуждение команды при наличии прямой применимости."
        ]

    priority = "Высокий" if importance >= 80 else "Средний" if importance >= 60 else "Низкий"
    return signal_type, priority, value, recommendations


def parse_date(entry) -> datetime:
    for key in ("published", "updated", "created"):
        value = getattr(entry, key, None)
        if value:
            try:
                return parsedate_to_datetime(value).astimezone(MOSCOW)
            except Exception:
                continue
    return datetime.now(MOSCOW)


def discover_feeds(homepage: str) -> list[str]:
    try:
        soup = BeautifulSoup(request(homepage).text, "html.parser")
        discovered = []

        for link in soup.select(
            'link[rel="alternate"][type*="rss"], '
            'link[rel="alternate"][type*="atom"], '
            'a[href*="rss"], a[href*="feed"]'
        ):
            href = link.get("href")
            if href:
                discovered.append(urljoin(homepage, href))

        return list(dict.fromkeys(discovered))[:8]
    except Exception:
        return []


def feed_items(source: dict) -> tuple[list[dict], str]:
    candidates = list(source.get("feed_candidates", []))
    candidates.extend(discover_feeds(source["homepage"]))
    candidates = list(dict.fromkeys(candidates))

    for feed_url in candidates:
        feed = feedparser.parse(feed_url)

        if not feed.entries:
            continue

        rows = []
        for entry in feed.entries[:60]:
            link = normalize_url(getattr(entry, "link", ""))
            title = clean_text(getattr(entry, "title", ""))
            summary = clean_text(
                getattr(entry, "summary", "")
                or getattr(entry, "description", "")
            )
            if link and title:
                rows.append({
                    "url": link,
                    "title": title,
                    "summary": summary,
                    "published": parse_date(entry)
                })

        if rows:
            return rows, f"rss · {feed_url}"

    return [], "rss unavailable"


def html_listing_items(source: dict) -> tuple[list[dict], str]:
    rows = []
    pattern = source["article_pattern"]

    for page in source.get("listing_pages", []):
        try:
            soup = BeautifulSoup(request(page).text, "html.parser")

            for anchor in soup.select("a[href]"):
                url = normalize_url(urljoin(page, anchor.get("href", "")))
                if source["homepage"] and urlparse(url).netloc != urlparse(source["homepage"]).netloc:
                    continue
                if not re.search(pattern, url):
                    continue

                title = clean_text(anchor.get_text(" ", strip=True))
                if len(title) < 20:
                    continue

                rows.append({
                    "url": url,
                    "title": title,
                    "summary": "",
                    "published": datetime.now(MOSCOW)
                })
        except Exception:
            continue

    unique = {row["url"]: row for row in rows}
    return list(unique.values())[:60], "html fallback"


def enrich_article(row: dict, source: dict) -> dict | None:
    title = clean_text(row.get("title", ""))
    summary = clean_text(row.get("summary", ""))
    body = ""

    try:
        soup = BeautifulSoup(request(row["url"], timeout=10).text, "html.parser")
        meta = (
            soup.find("meta", attrs={"name": "description"})
            or soup.find("meta", property="og:description")
        )
        if meta and not summary:
            summary = clean_text(meta.get("content", ""))

        paragraphs = soup.select(
            "article p, main p, .article p, .content p, .news-detail p"
        )
        body = clean_text(" ".join(
            paragraph.get_text(" ", strip=True)
            for paragraph in paragraphs[:24]
        ))
    except Exception:
        pass

    combined = clean_text(" ".join([title, summary, body[:5000]]))
    lowered = combined.lower()

    realty_hits = sum(1 for word in REALTY_WORDS if word in lowered)
    marketing_hits = sum(1 for word in MARKETING_WORDS if word in lowered)
    competitors = find_competitors(combined)

    if source["kind"] == "marketing":
        if realty_hits < 1:
            return None
    else:
        if realty_hits < 1 and not competitors:
            return None

    importance = min(
        100,
        42
        + realty_hits * 8
        + marketing_hits * 4
        + len(competitors) * 12
        + (8 if source["kind"] == "marketing" and marketing_hits >= 2 else 0)
    )

    topic = detect_topic(combined)
    signal_type, priority, level_value, recommendations = generate_analysis(
        combined, topic, competitors, importance
    )

    return {
        "id": hashlib.sha1(row["url"].encode()).hexdigest()[:16],
        "date": row["published"].date().isoformat(),
        "source": source["name"],
        "title": title,
        "url": row["url"],
        "summary": (summary or body[:420] or title)[:500],
        "topic": topic,
        "competitors": competitors,
        "importance": importance,
        "signal_type": signal_type,
        "priority": priority,
        "level_value": level_value,
        "recommendations": recommendations
    }


def load_existing() -> dict:
    try:
        data = json.loads(OUTPUT.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"items": data}
    except Exception:
        return {"items": []}


def collect_source(source: dict) -> tuple[list[dict], str]:
    rows, method = feed_items(source)

    if not rows:
        rows, method = html_listing_items(source)

    articles = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(enrich_article, row, source)
            for row in rows[:50]
        ]

        for future in as_completed(futures):
            item = future.result()
            if item:
                articles.append(item)

    return articles, method


def main() -> None:
    existing = load_existing()
    by_url = {
        item.get("url"): item
        for item in existing.get("items", [])
        if item.get("url")
    }

    source_status = {}
    ok = warning = failed = 0

    for source in CONFIG["sources"]:
        try:
            items, method = collect_source(source)
            for item in items:
                by_url[item["url"]] = item

            if items:
                source_status[source["name"]] = f"ok · {method} · {len(items)}"
                ok += 1
            else:
                source_status[source["name"]] = f"warning · {method} · 0"
                warning += 1
        except Exception as error:
            source_status[source["name"]] = f"error · {error}"
            failed += 1

    cutoff = (
        datetime.now(MOSCOW)
        - timedelta(days=CONFIG.get("retention_days", 180))
    ).date().isoformat()

    rows = [
        item for item in by_url.values()
        if item.get("date", "") >= cutoff
    ]

    seen_titles = set()
    deduplicated = []

    for item in sorted(
        rows,
        key=lambda value: (
            value.get("date", ""),
            value.get("importance", 0)
        ),
        reverse=True
    ):
        key = re.sub(r"\W+", "", item.get("title", "").lower())[:150]
        if key in seen_titles:
            continue
        seen_titles.add(key)
        deduplicated.append(item)

    payload = {
        "updated_at": datetime.now(MOSCOW).isoformat(timespec="seconds"),
        "stats": {
            "sources_ok": ok,
            "sources_warning": warning,
            "sources_failed": failed
        },
        "source_status": source_status,
        "items": deduplicated[:CONFIG.get("max_items", 500)]
    }

    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("Saved", len(payload["items"]))


if __name__ == "__main__":
    main()
