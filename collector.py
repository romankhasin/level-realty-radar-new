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


ADTECH_WORDS = [
    "новый формат", "новый инструмент", "таргетинг", "рекламный кабинет",
    "programmatic", "retail media", "ctv", "dooh", "telegram ads",
    "vk реклама", "яндекс реклама", "маркетплейс реклама",
    "медиаизмерение", "brand lift", "look-alike", "динамический креатив"
]

CASE_WORDS = [
    "кейс", "спецпроект", "кампания", "активация", "бренд-платформа",
    "ребрендинг", "партнерство", "интеграция", "инфлюенсер",
    "контентный проект", "омниканальный", "промо", "лендинг",
    "механика", "розыгрыш", "геймификация", "нативная реклама",
    "брендированный контент", "коллаборация", "партнёрский проект"
]

RESEARCH_WORDS = [
    "исследование", "опрос", "аналитика", "портрет покупателя",
    "поведение покупателей", "потребительское поведение",
    "клиентский путь", "поисковый спрос", "медиапотребление",
    "узнаваемость бренда", "сегментация", "персонализация",
    "лояльность", "удержание", "воронка", "crm", "first-party data",
    "данные аудитории", "поведение аудитории", "мобильная аудитория"
]


LUXURY_WORDS = [
    "luxury", "premium", "премиум", "премиальный", "люкс", "роскошь",
    "высокий доход", "состоятельная аудитория", "wealth", "wealthy",
    "high-net-worth", "hnwi", "ultra-high-net-worth", "uhnwi",
    "private banking", "private bank", "vip", "vip-клиент",
    "эксклюзивный", "эксклюзив", "закрытый клуб", "клиентский клуб",
    "персональный сервис", "консьерж", "concierge", "boutique",
    "бутик", "limited edition", "лимитированная серия", "bespoke",
    "индивидуальный заказ", "персонализация", "персонализированный",
    "элитный", "элитная недвижимость", "de luxe", "ultra luxury"
]

LUXURY_BRANDS = [
    "louis vuitton", "hermes", "hermès", "chanel", "dior", "cartier",
    "rolex", "patek philippe", "richard mille", "bentley", "rolls-royce",
    "ferrari", "lamborghini", "aston martin", "maybach", "porsche",
    "aman", "four seasons", "mandarin oriental", "rosewood",
    "six senses", "one&only", "tsum", "цум", "bosco", "mercury",
    "сбер первый", "alfa only", "альфа only", "т-банк private",
    "втб private", "газпромбанк private", "julius baer", "ubs",
    "emaar", "damac", "omniyat", "sobha"
]

LUXURY_MARKETING_PHRASES = [
    "закрытое мероприятие", "vip-мероприятие", "клиентское мероприятие",
    "private event", "эксклюзивная презентация", "персональное предложение",
    "индивидуальное предложение", "программа лояльности", "клиентский опыт",
    "премиальный сервис", "персональный менеджер", "concierge service",
    "бренд-амбассадор", "fashion campaign", "luxury campaign",
    "private sale", "предварительный доступ", "ранний доступ",
    "коллаборация с художником", "арт-проект", "бренд-пространство"
]

NOISE_WORDS = [
    "ставка по ипотеке", "выдача ипотеки", "ввод жилья",
    "разрешение на строительство", "сдан дом", "стройготовность",
    "эскроу", "земельный участок", "реновация", "градостроительный"
]

TEAM_MAP = {
    "Performance": ["Performance", "CRM", "Аналитика"],
    "Digital": ["Медиапланирование", "Programmatic", "Performance"],
    "Наружная реклама": ["Медиапланирование", "Бренд"],
    "Бренд и креатив": ["Бренд", "Креатив", "PR"],
    "Медиарынок": ["Медиапланирование", "Стратегия"],
    "Исследование": ["Стратегия", "Аналитика", "Бренд"],
    "Рынок недвижимости": ["Стратегия", "CRM", "Продукт"],
    "AdTech": ["Programmatic", "Медиапланирование", "Аналитика"]
}

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
        for entry in feed.entries[:CONFIG.get("items_per_feed", 45)]:
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
    for page in source.get("listing_pages", [])[:CONFIG.get("listing_pages_per_source", 2)]:
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
    return list({r["url"]: r for r in rows}.values())[:CONFIG.get("items_per_listing", 45)], "html fallback"


def make_item(row: dict, source: dict):
    title = clean_text(row.get("title", ""))
    summary = clean_text(row.get("summary", ""))
    combined = f"{title} {summary}"
    lowered = combined.lower()

    realty = sum(1 for word in REALTY_WORDS if word in lowered)
    marketing = sum(1 for word in MARKETING_WORDS if word in lowered)
    adtech = sum(1 for word in ADTECH_WORDS if word in lowered)
    cases = sum(1 for word in CASE_WORDS if word in lowered)
    research = sum(1 for word in RESEARCH_WORDS if word in lowered)
    luxury = sum(1 for word in LUXURY_WORDS if word in lowered)
    luxury_brands = [brand for brand in LUXURY_BRANDS if brand in lowered]
    luxury_marketing = sum(1 for phrase in LUXURY_MARKETING_PHRASES if phrase in lowered)
    noise = sum(1 for word in NOISE_WORDS if word in lowered)
    competitors = find_competitors(combined)

    source_kind = source.get("kind", "realty")

    # Strong signals that justify broader inclusion.
    direct_action_phrases = [
        "рекламная кампания", "маркетинговая кампания", "запустил кампанию",
        "запустила кампанию", "новый формат", "новый инструмент",
        "спецпроект", "ребрендинг", "позиционирование", "креативная концепция",
        "лидогенерация", "сквозная аналитика", "brand lift", "таргетинг",
        "рекламный кабинет", "продвижение проекта", "медиамикс",
        "медиаплан", "охватная кампания", "ретаргетинг", "персонализация"
    ]
    market_context_phrases = [
        "старт продаж", "вывод проекта", "новый жилой комплекс",
        "офис продаж", "шоурум", "покупатели жилья", "портрет покупателя",
        "выбор квартиры", "спрос на новостройки", "аудитория недвижимости"
    ]

    direct_action = any(p in lowered for p in direct_action_phrases)
    market_context = any(p in lowered for p in market_context_phrases)

    score = (
        min(realty, 5) * 13
        + min(marketing, 7) * 10
        + min(adtech, 4) * 14
        + min(cases, 4) * 9
        + min(research, 4) * 8
        + min(luxury, 5) * 11
        + min(luxury_marketing, 4) * 15
        + min(len(luxury_brands), 2) * 20
        + min(len(competitors), 2) * 18
        + (14 if direct_action else 0)
        + (8 if market_context else 0)
    )

    # Noise is punished only when there is no real marketing value.
    if noise and not (direct_action or adtech >= 1 or cases >= 1 or research >= 1 or competitors):
        score -= noise * 32
    elif noise:
        score -= noise * 12

    # Stream classification.
    luxury_signal = (
        (luxury >= 1 and (marketing >= 1 or direct_action or cases >= 1 or research >= 1))
        or luxury_marketing >= 1
        or (len(luxury_brands) >= 1 and (marketing >= 1 or direct_action or cases >= 1))
    )

    if luxury_signal:
        stream = "Luxury Marketing"
    elif competitors and (marketing >= 1 or direct_action or cases >= 1):
        stream = "Действия конкурентов"
    elif source_kind == "adtech" and (adtech >= 1 or direct_action):
        stream = "Рекламные технологии"
    elif realty >= 1 and (marketing >= 1 or direct_action):
        stream = "Недвижимость × маркетинг"
    elif realty >= 1 and research >= 1:
        stream = "Рынок и аудитория"
    elif source_kind in {"marketing", "cases"} and adtech >= 1:
        stream = "Рекламные технологии"
    elif source_kind in {"marketing", "cases"} and cases >= 1 and marketing >= 1:
        stream = "Идеи из других отраслей"
    elif source_kind == "marketing" and research >= 1 and marketing >= 1:
        stream = "Маркетинговая практика"
    elif source_kind == "marketing" and marketing >= 2 and (direct_action or cases >= 1):
        stream = "Маркетинговая практика"
    else:
        return None

    thresholds = {
        "Действия конкурентов": 44,
        "Рекламные технологии": 36,
        "Недвижимость × маркетинг": 42,
        "Рынок и аудитория": 44,
        "Идеи из других отраслей": 40,
        "Маркетинговая практика": 38,
        "Luxury Marketing": 40
    }

    if score < thresholds[stream]:
        return None

    # Hard exclusions for pure mortgage/construction/regulation news.
    pure_market_noise = noise >= 1 and marketing == 0 and adtech == 0 and cases == 0 and research == 0 and not competitors
    if pure_market_noise:
        return None

    topic = detect_topic(combined)
    importance = max(45, min(100, score))
    team = TEAM_MAP.get(topic, ["Стратегия", "Медиапланирование"])

    if stream == "Luxury Marketing":
        urgency = "Высокая" if luxury_marketing >= 1 or luxury_brands else "Средняя"
        value = (
            "Материал показывает, как премиальные бренды работают с состоятельной "
            "аудиторией через сервис, персонализацию, эксклюзивность и клиентский опыт. "
            "Подход можно адаптировать для премиальных проектов Level."
        )
        recs = [
            "Выделить механику работы с премиальной аудиторией: сервис, доступ, клубность или персонализация.",
            "Проверить применимость к премиальным ЖК и клиентским коммуникациям Level.",
            "Сформировать тест для CRM, спецпроекта, мероприятия или персонального предложения."
        ]
    elif competitors:
        urgency = "Высокая"
        value = (
            f"Упоминается {', '.join(competitors[:3])}. Материал помогает сравнить "
            "позиционирование, каналы, креатив или офер конкурента с активностями Level."
        )
        recs = [
            "Сопоставить сообщение и визуальный подход с текущими креативами Level.",
            "Проверить медиаприсутствие, поисковый интерес и посадочные страницы конкурента.",
            "Оценить, можно ли адаптировать механику для релевантного ЖК."
        ]
    elif stream == "Рекламные технологии":
        urgency = "Высокая"
        value = (
            "Материал описывает рекламный формат, данные или инструмент, который "
            "может расширить медиамикс и улучшить работу с аудиторией Level."
        )
        recs = [
            "Проверить доступность инструмента у текущих площадок и партнёров.",
            "Оценить тестовый бюджет, инвентарь и метод измерения.",
            "Сформировать пилот с контрольной группой и понятным KPI."
        ]
    elif stream == "Идеи из других отраслей":
        urgency = "Средняя"
        value = (
            "Кейс относится к другой категории, но его механика, креатив или "
            "способ вовлечения аудитории можно адаптировать для Level."
        )
        recs = [
            "Выделить механику кейса без отраслевой оболочки.",
            "Определить подходящий ЖК, аудиторию и этап воронки.",
            "Собрать быстрый прототип или креативный тест."
        ]
    elif stream == "Маркетинговая практика":
        urgency = "Средняя"
        value = (
            "Практический маркетинговый материал может улучшить аналитику, CRM, "
            "контент, персонализацию или оценку эффективности кампаний Level."
        )
        recs = [
            "Сопоставить подход с текущими процессами команды.",
            "Выбрать один применимый элемент для небольшого теста.",
            "Заранее определить метрику успеха и период оценки."
        ]
    elif stream == "Рынок и аудитория":
        urgency = "Средняя"
        value = (
            "Материал помогает понимать аудиторию, спрос и путь покупателя, "
            "что может повлиять на сегментацию, офер и рекламное сообщение Level."
        )
        recs = [
            "Сверить выводы с CRM, Метрикой и внутренними исследованиями.",
            "Использовать инсайт при сегментации и разработке оферов.",
            "Оценить влияние на контент и окна ретаргетинга."
        ]
    else:
        urgency = "Высокая" if topic in {"Performance", "Digital"} else "Средняя"
        value = (
            "Материал находится на стыке недвижимости и маркетинга и может "
            "дать практический ориентир для кампаний Level."
        )
        recs = [
            "Сопоставить механику с текущими кампаниями.",
            "Проверить применимость к конкретному проекту Level.",
            "Запустить ограниченный тест с заранее заданным KPI."
        ]

    return {
        "id": hashlib.sha1(row["url"].encode()).hexdigest()[:16],
        "date": row["published"].date().isoformat(),
        "source": source["name"],
        "title": title,
        "url": row["url"],
        "summary": summary[:650] or title,
        "topic": topic,
        "stream": stream,
        "competitors": competitors,
        "luxury": stream == "Luxury Marketing",
        "luxury_score": luxury * 11 + luxury_marketing * 15 + len(luxury_brands) * 20,
        "luxury_brands": luxury_brands,
        "importance": importance,
        "relevance_score": score,
        "urgency": urgency,
        "team": team,
        "level_value": value,
        "recommendations": recs
    }

def collect_source(source: dict):
    rows, method = get_feed_rows(source)
    if not rows:
        rows, method = get_listing_rows(source)

    items = []
    for row in rows[:CONFIG.get("items_per_listing", 45)]:
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

    with ThreadPoolExecutor(max_workers=8) as executor:
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
        and item.get("stream")
        and item.get("relevance_score", 0) >= 36
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
