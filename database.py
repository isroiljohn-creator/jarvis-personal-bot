"""
Jarvis — Markaziy PostgreSQL baza moduli.
Barcha xotira, suhbat tarixi shu yerda saqlanadi.
"""
import os, json, asyncio, logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("jarvis.db")

# ─── Ulanish ─────────────────────────────────────────────────
_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        import asyncpg
        url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
        if not url:
            raise RuntimeError("DATABASE_URL env o'zgaruvchisi topilmadi!")
        _pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
        logger.info("✅ PostgreSQL ulanish pool yaratildi")
    return _pool

# ─── Jadvallarni yaratish ─────────────────────────────────────
INIT_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id          SERIAL PRIMARY KEY,
    category    TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    embedding   JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(category, key)
);

CREATE TABLE IF NOT EXISTS messages (
    id          SERIAL PRIMARY KEY,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    source      TEXT DEFAULT 'telegram',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    id          SERIAL PRIMARY KEY,
    type        TEXT NOT NULL, -- 'income' or 'expense'
    amount      NUMERIC NOT NULL,
    category    TEXT NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at DESC);
"""

async def init_db():
    """Serverda bir marta chaqiriladi — jadvallarni yaratadi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(INIT_SQL)
        logger.info("✅ DB jadvallar tayyor")
    except Exception as e:
        logger.error(f"❌ DB init xatosi: {e}")
        raise

# ─── XOTIRA (RAG long-term) ────────────────────────────────────

async def db_save_memory(category: str, key: str, value: str, embedding: list = None):
    """Xotiraga yozadi yoki yangilaydi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO memories (category, key, value, embedding, updated_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (category, key) 
                DO UPDATE SET value=$3, embedding=$4, updated_at=NOW()
            """, category, key, value, json.dumps(embedding) if embedding else None)
        return f"✅ Xotiraga saqlandi: [{category}] {key}"
    except Exception as e:
        logger.error(f"db_save_memory xatosi: {e}")
        return f"❌ Saqlashda xatolik: {e}"

async def db_load_all_memories() -> dict:
    """Barcha xotirani dict ko'rinishida qaytaradi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT category, key, value FROM memories ORDER BY updated_at DESC")
        result = {}
        for row in rows:
            cat = row["category"]
            if cat not in result:
                result[cat] = {}
            result[cat][row["key"]] = row["value"]
        return result
    except Exception as e:
        logger.error(f"db_load_memories xatosi: {e}")
        return {}

async def db_search_memory(query_embedding: list, limit: int = 5) -> list:
    """Vektor o'xshashligiga qarab xotiradan qidiradi."""
    import numpy as np
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT category, key, value, embedding FROM memories WHERE embedding IS NOT NULL"
            )
        if not rows or not query_embedding:
            return []

        q_vec = np.array(query_embedding)
        scored = []
        for row in rows:
            emb = json.loads(row["embedding"])
            m_vec = np.array(emb)
            # Cosine similarity
            sim = float(np.dot(q_vec, m_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(m_vec) + 1e-9))
            scored.append((sim, row["category"], row["key"], row["value"]))

        scored.sort(reverse=True)
        return [(cat, key, val) for _, cat, key, val in scored[:limit]]
    except Exception as e:
        logger.error(f"db_search xatosi: {e}")
        return []

# ─── SUHBAT TARIXI (Session) ───────────────────────────────────

async def db_add_message(role: str, content: str, source: str = "telegram"):
    """Suhbat tarixiga xabar qo'shadi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO messages (role, content, source) VALUES ($1, $2, $3)",
                role, content, source
            )
    except Exception as e:
        logger.error(f"db_add_message xatosi: {e}")

async def db_get_history(limit: int = 30) -> list:
    """So'nggi N ta xabarni Gemini formatida qaytaradi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT role, content, source, created_at FROM messages ORDER BY created_at DESC LIMIT $1",
                limit
            )
        return [{"role": r["role"], "parts": [r["content"]], "source": r["source"]} for r in reversed(rows)]
    except Exception as e:
        logger.error(f"db_get_history xatosi: {e}")
        return []

async def db_get_history_display(limit: int = 50) -> list:
    """UI uchun tarix."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT role, content, source, created_at FROM messages ORDER BY created_at DESC LIMIT $1",
                limit
            )
        return [
            {
                "role": r["role"],
                "parts": [r["content"]],
                "source": r["source"],
                "time": r["created_at"].strftime("%H:%M")
            } for r in reversed(rows)
        ]
    except Exception as e:
        logger.error(f"db_get_history_display xatosi: {e}")
        return []

async def db_clear_history():
    """Barcha suhbat tarixini o'chiradi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM messages")
    except Exception as e:
        logger.error(f"db_clear_history xatosi: {e}")

# ─── MOLIYA (MOLIYAVIY HISOB-KITOB) ────────────────────────────

async def db_log_transaction(type: str, amount: float, category: str, description: str = "") -> str:
    """Yangi daromad yoki xarajatni qayd etadi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO transactions (type, amount, category, description) VALUES ($1, $2, $3, $4)",
                type, amount, category, description
            )
        return "✅ Moliyaviy yozuv muvaffaqiyatli saqlandi!"
    except Exception as e:
        logger.error(f"db_log_transaction xatosi: {e}")
        return f"❌ Moliya yozishda xatolik: {e}"

async def db_get_finance_data() -> dict:
    """Barcha tranzaksiyalar va summarini chartlar uchun yig'ib beradi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT type, amount, category, description, created_at FROM transactions ORDER BY created_at DESC")
            
        transactions = []
        total_income = 0
        total_expense = 0
        categories_expense = {}
        
        for r in rows:
            amount = float(r["amount"])
            t_type = r["type"]
            cat = r["category"]
            
            transactions.append({
                "type": t_type, "amount": amount, "category": cat,
                "description": r["description"], "date": r["created_at"].strftime("%Y-%m-%d %H:%M")
            })
            
            if t_type == "income":
                total_income += amount
            elif t_type == "expense":
                total_expense += amount
                categories_expense[cat] = categories_expense.get(cat, 0) + amount
                
        return {
            "total_income": total_income,
            "total_expense": total_expense,
            "balance": total_income - total_expense,
            "expense_by_category": categories_expense,
            "transactions": transactions[:50] # So'nggi 50 tasi history ga
        }
    except Exception as e:
        logger.error(f"db_get_finance_data xatosi: {e}")
        return {"total_income": 0, "total_expense": 0, "balance": 0, "expense_by_category": {}, "transactions": []}

