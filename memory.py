"""Jarvis xotira tizimi — PostgreSQL RAG xotira (JSON dan migratsiya)."""

from __future__ import annotations
import json, logging, os, asyncio
from datetime import datetime
import numpy as np
import google.generativeai as genai

logger = logging.getLogger("jarvis.memory")

# ─── Embedding ────────────────────────────────────────────────
def get_embedding(text: str) -> list[float]:
    """Gemini orqali matnning Embedding vektorini olish."""
    try:
        response = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="retrieval_document"
        )
        return response.get('embedding', [])
    except Exception as e:
        logger.error(f"Embedding xatosi: {e}")
        return []

# ─── Sync wrappers (bot.py sync context uchun) ────────────────
def load_memory() -> dict:
    """PostgreSQL dan barcha xotirani dict formatida qaytaradi."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Async kontekstda — future sifatida
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(_run_async, _load_from_db())
                return future.result(timeout=10)
        else:
            return loop.run_until_complete(_load_from_db())
    except Exception as e:
        logger.error(f"load_memory xatosi: {e}")
        return {}

def update_memory(category: str, key: str, value: str) -> str:
    """RAG Xotiraga PostgreSQL ga vektor bilan saqlaydi."""
    try:
        text_content = f"{category} - {key}: {value}"
        emb = get_embedding(text_content)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_save_to_db(category, key, value, emb))
            return f"✅ Xotiraga saqlandi: [{category}] {key}"
        else:
            return loop.run_until_complete(_save_to_db(category, key, value, emb))
    except Exception as e:
        logger.error(f"update_memory xatosi: {e}")
        return f"❌ Xatolik: {e}"

def search_memory(query: str, top_k: int = 5) -> list:
    """Matnni vektori bo'yicha xotiradan qidiradi."""
    try:
        q_emb = get_embedding(query)
        if not q_emb:
            return []
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(_run_async, _search_db(q_emb, top_k))
                return future.result(timeout=10)
        else:
            return loop.run_until_complete(_search_db(q_emb, top_k))
    except Exception as e:
        logger.error(f"search_memory xatosi: {e}")
        return []

def format_memory_for_prompt(memories: dict) -> str:
    """Xotirani system prompt uchun tekst formatiga o'tkazadi."""
    if not memories:
        return ""
    lines = ["[JARVIS UZOQ MUDDATLI XOTIRA]:"]
    for cat, items in memories.items():
        lines.append(f"\n📂 {cat.upper()}:")
        if isinstance(items, dict):
            for k, v in items.items():
                lines.append(f"  • {k}: {v}")
        else:
            lines.append(f"  • {items}")
    return "\n".join(lines)

# ─── Async DB funksiyalar ─────────────────────────────────────
async def _load_from_db() -> dict:
    from database import db_load_all_memories
    return await db_load_all_memories()

async def _save_to_db(category: str, key: str, value: str, embedding: list) -> str:
    from database import db_save_memory
    return await db_save_memory(category, key, value, embedding)

async def _search_db(q_emb: list, top_k: int) -> list:
    from database import db_search_memory
    return await db_search_memory(q_emb, top_k)

def _run_async(coro):
    """Yangi event loop da coroutine ishlatadi."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
