from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "status.json"
TZ = timezone(timedelta(hours=3))


def read_json(name: str) -> dict:
    try:
        data = json.loads((ROOT / name).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"items": data}
    except Exception:
        return {"items": [], "stats": {}}


def count_sources(data: dict) -> int:
    items = data.get("items", [])
    return len({item.get("source") for item in items if item.get("source")})


def main() -> None:
    russian = read_json("news.json")
    global_data = read_json("global_news.json")

    russian_stats = russian.get("stats") or {}
    global_stats = global_data.get("stats") or {}

    event = os.getenv("GITHUB_EVENT_NAME", "local")
    trigger_label = {
        "schedule": "Автоматически по расписанию",
        "workflow_dispatch": "Запущено вручную",
        "local": "Локальный запуск",
    }.get(event, event)

    russian_items = len(russian.get("items", []))
    global_items = len(global_data.get("items", []))
    errors = int(russian_stats.get("sources_failed", 0) or 0) + int(global_stats.get("sources_failed", 0) or 0)
    warnings = int(russian_stats.get("sources_warning", 0) or 0) + int(global_stats.get("sources_warning", 0) or 0)

    now = datetime.now(TZ)
    payload = {
        "last_update": now.isoformat(timespec="seconds"),
        "timezone": "Europe/Moscow",
        "trigger": event,
        "trigger_label": trigger_label,
        "run_number": os.getenv("GITHUB_RUN_NUMBER", ""),
        "run_id": os.getenv("GITHUB_RUN_ID", ""),
        "branch": os.getenv("GITHUB_REF_NAME", "main"),
        "health": "warning" if errors or warnings else "ok",
        "russian": {
            "items": russian_items,
            "sources": count_sources(russian),
            "sources_ok": int(russian_stats.get("sources_ok", 0) or 0),
            "sources_warning": int(russian_stats.get("sources_warning", 0) or 0),
            "sources_failed": int(russian_stats.get("sources_failed", 0) or 0),
        },
        "global": {
            "items": global_items,
            "sources": count_sources(global_data),
            "sources_ok": int(global_stats.get("sources_ok", 0) or 0),
            "sources_warning": int(global_stats.get("sources_warning", 0) or 0),
            "sources_failed": int(global_stats.get("sources_failed", 0) or 0),
        },
        "totals": {
            "items": russian_items + global_items,
            "sources": count_sources(russian) + count_sources(global_data),
            "warnings": warnings,
            "errors": errors,
        },
        "schedule": {
            "cron": "30 5 * * *",
            "display": "Ежедневно около 08:30 по Москве",
        },
    }

    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Status saved: {payload['totals']['items']} materials, "
        f"{payload['totals']['errors']} errors, trigger={event}",
        flush=True,
    )


if __name__ == "__main__":
    main()
