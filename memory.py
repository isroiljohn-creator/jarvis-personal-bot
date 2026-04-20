"""Jarvis xotira tizimi — JSON-based uzoq muddatli xotira."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("jarvis.memory")

MEMORY_FILE = Path(os.environ.get("MEMORY_PATH", "data/memory.json"))


def load_memory() -> dict:
    """Xotirani yuklash."""
    if not MEMORY_FILE.exists():
        return {}
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def update_memory(category: str, key: str, value: str) -> str:
    """Xotiraga ma'lumot qo'shish/yangilash."""
    memory = load_memory()
    if category not in memory:
        memory[category] = {}
    memory[category][key] = {
        "value": value,
        "updated": datetime.now().isoformat(),
    }
    _save(memory)
    logger.info(f"💾 Xotira: {category}/{key} = {value}")
    return f"Saqlandi: {key} = {value}"


def format_memory_for_prompt() -> str:
    """Xotirani AI prompt uchun formatlash."""
    memory = load_memory()
    if not memory:
        return ""
    lines = ["[FOYDALANUVCHI HAQIDA ESLAB QOLGANLARIM]"]
    for category, items in memory.items():
        lines.append(f"\n{category.upper()}:")
        for key, data in items.items():
            val = data.get("value", data) if isinstance(data, dict) else data
            lines.append(f"  - {key}: {val}")
    return "\n".join(lines)


def _save(data: dict) -> None:
    """JSON faylga saqlash."""
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
