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

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; LevelRealtyRadar/2.1)"
})

REALTY_WORDS = [
    "недвижим", "девелоп", "застрой", "жилой комплекс", "жк ",
    "новостро", "квартир", "ипотек", "апартамент", "жиль", "дду",
    "бизнес-центр", "офисн", "складск", "коммерческ", "домклик",
    "циан", "первичн", "вторичн", "покупател", "потребител",
    "клиентский опыт", "выбор квартир", "портрет покупателя",
    "жилой проект", "девелоперский проект", "коммерческая недвижимость"
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


def request(url: str, timeout: int = 7) -> requests.Response:
    response = SESSION.get(url, timeout=(4, timeout))
    response.raise_for_status()
    return response


def clean_text(value: str) -> str:
    decoded = html.unescape(value or "")
    soup = BeautifulSoup(decoded, "html.parser")
    text = soup.get_text(" ", strip=True).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def find_competitors(text: str) -> list[str]:
    lowered = text.lower()
    found = []
    for brand, aliases in COMPETITORS.items():
        for alias in aliases:
            alias = alias.lower()
            matched = (
                re.search(rf"(?<![\wа-яё]){re.escape(alias)}(?![\wа-яё])", lowered)
                if len(alias) <= 3 else alias in lowered
            )
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


def analysis_for(topic: str, competitors: list[str], importance: int):
    if competitors:
        signal = "Действие конкурента"
        value = (
            f"Материал показывает активность {', '.join(competitors[:3])}. "
            "Для Level важно сравнить позиционирование, оферы и медиаканалы."
        )
        recs = [
            "Сопоставить коммуникацию конкурента с текущими сообщениями Level.",
            "Проверить поисковый интерес и рекламную активность конкурента.",
            "Оценить применимость механики для релевантных проектов Level."
        ]
    elif topic == "Performance":
        signal = "Практический кейс"
        value = "Материал может помочь улучшить лидогенерацию и качество оценки каналов."
        recs = [
            "Сравнить механику с текущими кампаниями Level.",
            "Смотреть не только CPL, но и дозвон, квалификацию и CRM.",
            "Запустить ограниченный тест с заранее заданным KPI."
        ]
    elif topic == "Digital":
        signal = "Новый инструмент"
        value = "Материал может указывать на новый digital-формат или канал для медиамикса Level."
        recs = [
            "Проверить доступность формата у текущих площадок.",
            "Выделить небольшой тестовый бюджет.",
            "Оценить визиты, брендовый поиск и post-view эффект."
        ]
    elif topic == "Наружная реклама":
        signal = "Медийная возможность"
        value = "Материал полезен для оценки OOH/DOOH не только по охвату, но и по запоминаемости."
        recs = [
            "Проверить простоту сообщения и визуальную иерархию.",
            "Связать OOH-волну с динамикой брендовых запросов.",
            "Использовать brand lift или замер узнавания макета."
        ]
    elif topic == "Исследование":
        signal = "Исследование"
        value = "Данные можно использовать при выборе аудитории, каналов, KPI и рекламного сообщения."
        recs = [
            "Проверить методологию и выборку.",
            "Сопоставить выводы с CRM и внутренними данными Level.",
            "Использовать релевантные цифры при защите стратегии."
        ]
    elif topic == "Бренд и креатив":
        signal = "Креативный сигнал"
        value = "Материал может помочь усилить позиционирование и заметность коммуникации Level."
        recs = [
            "Проверить механику на текущих креативах.",
            "Оставлять один сильный продуктовый аргумент на макет.",
            "Сравнить эмоциональную и рациональную подачу."
        ]
    else:
        signal = "Рыночный сигнал"
        value = "Изменение рынка может повлиять на оферы, сегментацию и распределение бюджета."
        recs = [
            "Актуализировать оферы под текущий спрос.",
            "Проверить различия по классам жилья и локациям.",
            "Скорректировать окна ретаргетинга и приоритеты проектов."
        ]

    priority = "Высокий" if importance >= 80 else "Средний" if importance >= 60 else "Низкий"
    return signal, priority, value, recs


def parse_date(entry) -> datetime:
    for key in ("published", "updated", "created"):
        value = getattr(entry, key, None)
        if value:
            try:
                return parsedate_to_datetime(value).astimezone(MOSCOW)
            except Exception:
                pass
    return datetime.now(MOSCOW)


def discover_feeds(homepage: str) -> list[str]:
    try:
        soup = BeautifulSoup(request(homepage, 6).text, "html.parser")
        found = []
        for node in soup.select('link[rel="alternate"][type*="rss"],link[rel="alternate"][type*="atom"]'):
            href = node.get("href")
            if href:
                found.append(urljoin(homepage, href))
        return list(dict.fromkeys(found))[:3]
    except Exception:
        return []


def get_feed_rows(source: dict):
    candidates = list(dict.fromkeys(source.get("feed_candidates", [])[:2] + discover_feeds(source["homepage"])))
    for feed_url in candidates:
        feed = feedparser.parse(feed_url, request_headers={"User-Agent": SESSION.headers["User-Agent"]})
        if not feed.entries:
            continue

        rows = []
        for entry in feed.entries[:25]:
            link = getattr(entry, "link", "").split("#")[0]
            title = clean_text(getattr(entry, "title", ""))
            summary = clean_text(getattr(entry, "summary", "") or getattr(entry, "description", ""))
            if link and title:
                rows.append({
                    "url": link,
                    "title": title,
                    "summary": summary,
                    "published": parse_date(entry)
                })
        if rows:
            return rows, "rss"
    return [], "rss unavailable"


def get_listing_rows(source: dict):
    rows = []
    for page in source.get("listing_pages", [])[:1]:
        try:
            soup = BeautifulSoup(request(page, 6).text, "html.parser")
            for anchor in soup.select("a[href]"):
                url = urljoin(page, anchor.get("href", "")).split("#")[0]
                if urlparse(url).netloc != urlparse(source["homepage"]).netloc:
                    continue
                if not re.search(source["article_pattern"], url):
                    continue
                title = clean_text(anchor.get_text(" ", strip=True))
                if len(title) >= 24:
                    rows.append({
                        "url": url,
                        "title": title,
                        "summary": "",
                        "published": datetime.now(MOSCOW)
                    })
        except Exception:
            pass
    return list({r["url"]: r for r in rows}.values())[:20], "html fallback"


def make_item(row: dict, source: dict):
    title = clean_text(row.get("title", ""))
    summary = clean_text(row.get("summary", ""))
    combined = f"{title} {summary}"
    lowered = combined.lower()

    realty_hits = sum(1 for word in REALTY_WORDS if word in lowered)
    marketing_hits = sum(1 for word in MARKETING_WORDS if word in lowered)
    competitors = find_competitors(combined)

    strong_marketing_actions = [
        "рекламная кампания", "маркетинговая кампания", "продвижение",
        "лидогенерация", "медиаплан", "медиамикс", "брендинг",
        "ребрендинг", "креатив", "наружная реклама", "digital",
        "диджитал", "performance", "таргетированная реклама",
        "контекстная реклама", "telegram ads", "спецпроект",
        "бренд-платформа", "позиционирование", "рекламный бюджет",
        "маркетинговый бюджет", "cpl", "cpm", "ctr", "охватная кампания",
        "видеореклама", "olv", "dooh", "ooh", "ретаргетинг",
        "классифайд", "авито реклама", "яндекс реклама",
        "медиаизмерение", "brand lift", "сквозная аналитика",
        "коллтрекинг", "атрибуция", "клиентский путь"
    ]
    research_signals = [
        "исследование", "опрос", "аналитика", "портрет покупателя",
        "поведение покупателей", "потребительское поведение",
        "клиентский опыт", "выбор квартиры", "поисковый спрос",
        "медиапотребление", "аудитория", "узнаваемость бренда"
    ]
    market_action_signals = [
        "старт продаж", "вывод проекта", "запуск проекта", "новый проект",
        "изменил позиционирование", "новая концепция", "новый бренд",
        "редизайн", "шоурум", "офис продаж", "презентация проекта"
    ]

    has_strong_marketing_action = any(phrase in lowered for phrase in strong_marketing_actions)
    has_research_signal = any(phrase in lowered for phrase in research_signals)
    has_market_action = any(phrase in lowered for phrase in market_action_signals)

    # Более широкий скоринг вместо бинарного фильтра.
    score = 0
    score += min(realty_hits, 4) * 16
    score += min(marketing_hits, 5) * 11
    score += min(len(competitors), 2) * 18
    score += 20 if has_strong_marketing_action else 0
    score += 13 if has_research_signal else 0
    score += 10 if has_market_action else 0
    score += 7 if source["kind"] == "marketing" and realty_hits >= 1 else 0

    # Минимальные страховочные условия:
    # - нужен хотя бы один сигнал недвижимости;
    # - либо конкретный девелопер + маркетинговая/исследовательская применимость.
    has_realty_context = realty_hits >= 1
    competitor_marketing_context = bool(competitors) and (
        marketing_hits >= 1 or has_strong_marketing_action
        or has_research_signal or has_market_action
    )

    threshold = CONFIG.get("relevance_threshold", 56)
    if not ((has_realty_context or competitor_marketing_context) and score >= threshold):
        return None

    importance = min(100, max(50, score))
    topic = detect_topic(combined)
    signal, priority, value, recs = analysis_for(topic, competitors, importance)

    # Уточняем анализ для широких, но полезных исследований рынка.
    if has_research_signal and marketing_hits < 2 and not competitors:
        signal = "Исследование аудитории"
        value = (
            "Материал не описывает рекламную кампанию напрямую, но помогает "
            "лучше понять спрос, путь покупателя и аргументы для коммуникации Level."
        )
        recs = [
            "Проверить, подтверждаются ли выводы внутренними данными Level.",
            "Использовать инсайт при сегментации аудиторий и разработке оферов.",
            "Оценить влияние на креатив, контент и окна ретаргетинга."
        ]

    return {
        "id": hashlib.sha1(row["url"].encode()).hexdigest()[:16],
        "date": row["published"].date().isoformat(),
        "source": source["name"],
        "title": title,
        "url": row["url"],
        "summary": summary[:500] or title,
        "topic": topic,
        "competitors": competitors,
        "importance": importance,
        "relevance_score": score,
        "signal_type": signal,
        "priority": priority,
        "level_value": value,
        "recommendations": recs,
        "realty_score": realty_hits,
        "marketing_score": marketing_hits,
        "intersection": marketing_hits >= 1 or has_strong_marketing_action,
        "broader_relevance": has_research_signal or has_market_action
    }

def collect_source(source: dict):
    rows, method = get_feed_rows(source)
    if not rows:
        rows, method = get_listing_rows(source)

    items = []
    for row in rows[:20]:
        item = make_item(row, source)
        if item:
            items.append(item)
    return source["name"], items, method


def load_existing():
    try:
        data = json.loads(OUTPUT.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"items": data}
    except Exception:
        return {"items": []}


def main():
    existing = load_existing()
    by_url = {item.get("url"): item for item in existing.get("items", []) if item.get("url")}
    status = {}
    ok = warning = failed = 0

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(collect_source, source) for source in CONFIG["sources"]]
        for future in as_completed(futures):
            try:
                name, items, method = future.result()
                for item in items:
                    by_url[item["url"]] = item
                if items:
                    status[name] = f"ok · {method} · {len(items)}"
                    ok += 1
                else:
                    status[name] = f"warning · {method} · 0"
                    warning += 1
                print(status[name], flush=True)
            except Exception as error:
                failed += 1
                print(f"error · {error}", flush=True)

    cutoff = (datetime.now(MOSCOW) - timedelta(days=CONFIG.get("retention_days", 180))).date().isoformat()
    rows = [
        item for item in by_url.values()
        if item.get("date", "") >= cutoff
        and (
            item.get("relevance_score", 0) >= CONFIG.get("relevance_threshold", 56)
            or item.get("intersection") is True
            or item.get("broader_relevance") is True
        )
    ]

    seen = set()
    dedup = []
    for item in sorted(rows, key=lambda x: (x.get("date", ""), x.get("importance", 0)), reverse=True):
        key = re.sub(r"\W+", "", item.get("title", "").lower())[:150]
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)

    payload = {
        "updated_at": datetime.now(MOSCOW).isoformat(timespec="seconds"),
        "stats": {"sources_ok": ok, "sources_warning": warning, "sources_failed": failed},
        "source_status": status,
        "items": dedup[:CONFIG.get("max_items", 300)]
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved", len(payload["items"]), flush=True)


if __name__ == "__main__":
    main()
