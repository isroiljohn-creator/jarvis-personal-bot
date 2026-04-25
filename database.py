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
    payment_method TEXT DEFAULT 'naqd',
    currency    TEXT DEFAULT 'UZS',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_plans (
    id          SERIAL PRIMARY KEY,
    plan_date   DATE NOT NULL UNIQUE,   -- Reja qaysi kun uchun
    tasks       JSONB NOT NULL,         -- [{text, done, priority}]
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deadlines (
    id           SERIAL PRIMARY KEY,
    title        TEXT NOT NULL,
    project      TEXT DEFAULT '',
    deadline_date DATE NOT NULL,
    priority     TEXT DEFAULT 'normal', -- 'critical', 'high', 'normal', 'low'
    completed    BOOLEAN DEFAULT FALSE,
    notes        TEXT DEFAULT '',
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_plans_date ON daily_plans(plan_date DESC);
CREATE INDEX IF NOT EXISTS idx_deadlines_date ON deadlines(deadline_date ASC) WHERE completed = FALSE;
"""

async def init_db():
    """Serverda bir marta chaqiriladi — jadvallarni yaratadi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(INIT_SQL)
            # Try to alter existing table just in case
            try:
                await conn.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_method TEXT DEFAULT 'naqd'")
                await conn.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'UZS'")
            except Exception:
                pass
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

async def db_log_transaction(type: str, amount: float, category: str, description: str = "", payment_method: str = "naqd", currency: str = "UZS") -> str:
    """Yangi daromad yoki xarajatni qayd etadi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO transactions (type, amount, category, description, payment_method, currency) VALUES ($1, $2, $3, $4, $5, $6)",
                type, amount, category, description, payment_method, currency
            )
        return f"✅ Moliyaviy yozuv muvaffaqiyatli saqlandi! ({category} guruhiga, to'lov: {payment_method}, {currency})"
    except Exception as e:
        logger.error(f"db_log_transaction xatosi: {e}")
        return f"❌ Moliya yozishda xatolik: {e}"

async def db_get_transactions_raw() -> list:
    """Barcha tranzaksiyalarni array sifatida qaytaradi, to'liq AI Finansist aggregatsiyasi uchun."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, type, amount, category, description, payment_method, currency, created_at FROM transactions ORDER BY created_at ASC")
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"db_get_transactions_raw xatosi: {e}")
        return []

async def db_get_finance_data() -> dict:
    """Barcha tranzaksiyalar va summarini chartlar uchun yig'ib beradi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT type, amount, category, description, payment_method, currency, created_at FROM transactions ORDER BY created_at DESC")
            
        transactions = []
        # UZS Stats
        total_income_uzs = 0; total_expense_uzs = 0
        categories_expense_uzs = {}
        # USD Stats
        total_income_usd = 0; total_expense_usd = 0
        categories_expense_usd = {}
        # Payment breakdown
        payment_methods = {"naqd": 0, "karta": 0}
        
        for r in rows:
            amount = float(r["amount"])
            t_type = r["type"]
            cat = r["category"]
            pm = r.get("payment_method", "naqd") or "naqd"
            curr = r.get("currency", "UZS") or "UZS"
            curr = curr.upper()
            pm = pm.lower()
            
            transactions.append({
                "type": t_type, "amount": amount, "category": cat,
                "description": r["description"], "payment_method": pm, "currency": curr,
                "date": r["created_at"].strftime("%Y-%m-%d %H:%M")
            })
            
            if curr == "UZS":
                if t_type == "income": total_income_uzs += amount
                elif t_type == "expense": 
                    total_expense_uzs += amount
                    categories_expense_uzs[cat] = categories_expense_uzs.get(cat, 0) + amount
                    if pm in payment_methods: payment_methods[pm] += amount
            elif curr == "USD":
                if t_type == "income": total_income_usd += amount
                elif t_type == "expense": 
                    total_expense_usd += amount
                    categories_expense_usd[cat] = categories_expense_usd.get(cat, 0) + amount
                
        return {
            "uzs": {
                "income": total_income_uzs,
                "expense": total_expense_uzs,
                "balance": total_income_uzs - total_expense_uzs,
                "expense_by_category": categories_expense_uzs
            },
            "usd": {
                "income": total_income_usd,
                "expense": total_expense_usd,
                "balance": total_income_usd - total_expense_usd,
                "expense_by_category": categories_expense_usd
            },
            "payment_methods": payment_methods,
            "transactions": transactions[:100]
        }
    except Exception as e:
        logger.error(f"db_get_finance_data xatosi: {e}")
        return {"uzs": {"income": 0, "expense": 0, "balance": 0, "expense_by_category": {}}, "usd": {}, "transactions": []}


# ─── KUNLIK REJA (Daily Plans) ────────────────────────────────

async def db_save_plan(plan_date: str, tasks: list) -> bool:
    """
    Kunlik rejani saqlaydi yoki yangilaydi.
    tasks = [{"text": "...", "done": False, "priority": "high"}, ...]
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO daily_plans (plan_date, tasks, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (plan_date)
                DO UPDATE SET tasks = $2, updated_at = NOW()
            """, plan_date, json.dumps(tasks, ensure_ascii=False))
        logger.info(f"✅ Reja saqlandi: {plan_date} ({len(tasks)} ta vazifa)")
        return True
    except Exception as e:
        logger.error(f"db_save_plan xatosi: {e}")
        return False


async def db_get_plan(plan_date: str) -> list:
    """Berilgan sana uchun rejani qaytaradi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT tasks FROM daily_plans WHERE plan_date = $1", plan_date
            )
        if row:
            return json.loads(row["tasks"])
        return []
    except Exception as e:
        logger.error(f"db_get_plan xatosi: {e}")
        return []


async def db_update_task_status(plan_date: str, task_index: int, done: bool) -> bool:
    """Rejadagi bitta vazifani bajarildi/bajarilmadi deb belgilaydi."""
    try:
        tasks = await db_get_plan(plan_date)
        if 0 <= task_index < len(tasks):
            tasks[task_index]["done"] = done
            return await db_save_plan(plan_date, tasks)
        return False
    except Exception as e:
        logger.error(f"db_update_task_status xatosi: {e}")
        return False


async def db_get_plan_summary(plan_date: str) -> dict:
    """Reja holati: nechta bajarildi, nechta qoldi."""
    tasks = await db_get_plan(plan_date)
    if not tasks:
        return {"total": 0, "done": 0, "remaining": 0, "tasks": []}
    done  = sum(1 for t in tasks if t.get("done"))
    return {
        "total": len(tasks),
        "done": done,
        "remaining": len(tasks) - done,
        "tasks": tasks,
        "completion_pct": round(done / len(tasks) * 100) if tasks else 0,
    }


# ─── DEADLINELAR ──────────────────────────────────────────────

async def db_add_deadline(title: str, deadline_date: str, project: str = "",
                           priority: str = "normal", notes: str = "") -> int:
    """Yangi deadline qo'shadi. ID qaytaradi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO deadlines (title, project, deadline_date, priority, notes)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """, title, project, deadline_date, priority, notes)
        logger.info(f"✅ Deadline qo'shildi: {title} ({deadline_date})")
        return row["id"]
    except Exception as e:
        logger.error(f"db_add_deadline xatosi: {e}")
        return -1


async def db_get_deadlines(days_ahead: int = 30, include_overdue: bool = True) -> list:
    """Yaqinlashayotgan va kechikkan deadlinelarni qaytaradi."""
    try:
        from datetime import date, timedelta
        today = date.today()
        end_date = today + timedelta(days=days_ahead)
        pool = await get_pool()
        async with pool.acquire() as conn:
            if include_overdue:
                rows = await conn.fetch("""
                    SELECT id, title, project, deadline_date, priority, notes, completed,
                           (deadline_date - CURRENT_DATE) AS days_left
                    FROM deadlines
                    WHERE completed = FALSE AND deadline_date <= $1
                    ORDER BY deadline_date ASC
                """, end_date)
            else:
                rows = await conn.fetch("""
                    SELECT id, title, project, deadline_date, priority, notes, completed,
                           (deadline_date - CURRENT_DATE) AS days_left
                    FROM deadlines
                    WHERE completed = FALSE AND deadline_date BETWEEN $1 AND $2
                    ORDER BY deadline_date ASC
                """, today, end_date)
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"db_get_deadlines xatosi: {e}")
        return []


async def db_complete_deadline(deadline_id: int) -> bool:
    """Deadlineni bajarildi deb belgilaydi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE deadlines SET completed = TRUE WHERE id = $1", deadline_id
            )
        return True
    except Exception as e:
        logger.error(f"db_complete_deadline xatosi: {e}")
        return False


async def db_get_deadline_summary() -> str:
    """Deadlinelarni qisqa matn ko'rinishida chiqaradi — AI prompt uchun."""
    deadlines = await db_get_deadlines(days_ahead=14)
    if not deadlines:
        return "Yaqin 2 hafta ichida deadline yo'q"

    pri_emoji = {"critical": "🔴", "high": "🟠", "normal": "🟡", "low": "🟢"}
    lines = []
    for d in deadlines:
        days = d["days_left"]
        if days < 0:
            when = f"⚠️ {abs(days)} kun kechikdi!"
        elif days == 0:
            when = "🚨 BUGUN!"
        elif days == 1:
            when = "⏰ ERTAGA!"
        else:
            when = f"{days} kun qoldi"
        pri = pri_emoji.get(d["priority"], "⚪")
        proj = f" [{d['project']}]" if d["project"] else ""
        lines.append(f"{pri} {d['title']}{proj} — {when}")
    return "\n".join(lines)


