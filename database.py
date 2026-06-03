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

CREATE TABLE IF NOT EXISTS nuvi_users (
    user_id     BIGINT PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nuvi_vacancies (
    id             SERIAL PRIMARY KEY,
    user_id        BIGINT REFERENCES nuvi_users(user_id),
    title          TEXT NOT NULL,
    company        TEXT NOT NULL,
    salary         TEXT NOT NULL,
    location       TEXT NOT NULL,
    working_hours  TEXT,
    requirements   TEXT,
    skills         TEXT,
    benefits       TEXT,
    contact        TEXT NOT NULL,
    formatted_text TEXT,
    status         TEXT DEFAULT 'draft',
    payment_status TEXT DEFAULT 'unpaid',
    payment_method TEXT,
    payment_receipt TEXT,
    rejection_reason TEXT,
    scheduled_for  TIMESTAMPTZ,
    posted_at      TIMESTAMPTZ,
    tariff         TEXT DEFAULT 'pro',
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nuvi_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_vacancies (
    channel_id  BIGINT NOT NULL,
    msg_id      INT NOT NULL,
    sent_at     TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY(channel_id, msg_id)
);

CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_plans_date ON daily_plans(plan_date DESC);
CREATE INDEX IF NOT EXISTS idx_deadlines_date ON deadlines(deadline_date ASC) WHERE completed = FALSE;
CREATE INDEX IF NOT EXISTS idx_nuvi_vacancies_status ON nuvi_vacancies(status);
CREATE INDEX IF NOT EXISTS idx_nuvi_vacancies_scheduled ON nuvi_vacancies(scheduled_for) WHERE status = 'approved';
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
            try:
                await conn.execute("ALTER TABLE nuvi_vacancies ADD COLUMN IF NOT EXISTS tariff TEXT DEFAULT 'pro'")
                await conn.execute("ALTER TABLE nuvi_vacancies ADD COLUMN IF NOT EXISTS skills TEXT")
            except Exception as e:
                logger.error(f"Error altering nuvi_vacancies: {e}")
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
                "SELECT role, content, source, created_at FROM messages WHERE source != 'telegram_group' ORDER BY created_at DESC LIMIT $1",
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
                "SELECT role, content, source, created_at FROM messages WHERE source != 'telegram_group' ORDER BY created_at DESC LIMIT $1",
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

async def db_get_group_messages(limit: int = 50) -> list:
    """Tizimda saqlangan telegram_group xabarlarini qaytaradi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT role, content, created_at FROM messages WHERE source = 'telegram_group' ORDER BY created_at DESC LIMIT $1",
                limit
            )
        return [
            {
                "sender": r["role"],
                "content": r["content"],
                "time": r["created_at"].strftime("%Y-%m-%d %H:%M")
            } for r in reversed(rows)
        ]
    except Exception as e:
        logger.error(f"db_get_group_messages xatosi: {e}")
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
        return {"total": 0, "done": 0, "remaining": 0, "tasks": [], "completion_pct": 0}
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


# ─── VAKANSIYALAR ──────────────────────────────────────────────

async def db_add_processed_vacancy(channel_id: int, msg_id: int) -> bool:
    """Yuborilgan vakansiyani bazaga yozib qo'yadi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO processed_vacancies (channel_id, msg_id)
                VALUES ($1, $2)
                ON CONFLICT (channel_id, msg_id) DO NOTHING
            """, channel_id, msg_id)
        return True
    except Exception as e:
        logger.error(f"db_add_processed_vacancy xatosi: {e}")
        return False


async def db_is_vacancy_processed(channel_id: int, msg_id: int) -> bool:
    """Vakansiya allaqachon yuborilganligini tekshiradi."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("""
                SELECT EXISTS(
                    SELECT 1 FROM processed_vacancies 
                    WHERE channel_id = $1 AND msg_id = $2
                )
            """, channel_id, msg_id)
        return bool(val)
    except Exception as e:
        logger.error(f"db_is_vacancy_processed xatosi: {e}")
        return False


# ─── NUVI JOBS BOT FUNCTIONS ───────────────────────────────────

async def db_upsert_nuvi_user(user_id: int, username: str, first_name: str) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO nuvi_users (user_id, username, first_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO UPDATE 
                SET username = EXCLUDED.username, first_name = EXCLUDED.first_name
            """, user_id, username, first_name)
        return True
    except Exception as e:
        logger.error(f"db_upsert_nuvi_user xatosi: {e}")
        return False

async def db_get_all_nuvi_users() -> list[dict]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM nuvi_users")
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"db_get_all_nuvi_users xatosi: {e}")
        return []

async def db_create_nuvi_vacancy(
    user_id: int, title: str, company: str, salary: str, location: str, 
    working_hours: str, requirements: str, skills: str, benefits: str, contact: str, 
    formatted_text: str = None, tariff: str = 'pro'
) -> Optional[int]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO nuvi_vacancies (
                    user_id, title, company, salary, location, 
                    working_hours, requirements, skills, benefits, contact, formatted_text, tariff
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING id
            """, user_id, title, company, salary, location, working_hours, requirements, skills, benefits, contact, formatted_text, tariff)
            if row:
                return row["id"]
        return None
    except Exception as e:
        logger.error(f"db_create_nuvi_vacancy xatosi: {e}")
        return None

async def db_get_nuvi_vacancy(vacancy_id: int) -> Optional[dict]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM nuvi_vacancies WHERE id = $1", vacancy_id)
            if row:
                return dict(row)
        return None
    except Exception as e:
        logger.error(f"db_get_nuvi_vacancy xatosi: {e}")
        return None

async def db_get_nuvi_vacancies_by_user(user_id: int) -> list[dict]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM nuvi_vacancies WHERE user_id = $1 ORDER BY id DESC", user_id)
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"db_get_nuvi_vacancies_by_user xatosi: {e}")
        return []

async def db_update_nuvi_vacancy(vacancy_id: int, **kwargs) -> bool:
    if not kwargs:
        return False
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            set_clauses = []
            values = []
            for i, (key, value) in enumerate(kwargs.items(), start=2):
                set_clauses.append(f"{key} = ${i}")
                values.append(value)
            query = f"UPDATE nuvi_vacancies SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = $1"
            await conn.execute(query, vacancy_id, *values)
        return True
    except Exception as e:
        logger.error(f"db_update_nuvi_vacancy xatosi: {e}")
        return False

async def db_get_pending_approval_vacancies() -> list[dict]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM nuvi_vacancies 
                WHERE status = 'pending_approval' 
                ORDER BY id ASC
            """)
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"db_get_pending_approval_vacancies xatosi: {e}")
        return []

async def db_get_next_scheduled_vacancy() -> Optional[dict]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM nuvi_vacancies 
                WHERE status = 'approved' AND posted_at IS NULL AND scheduled_for <= NOW()
                ORDER BY scheduled_for ASC, id ASC
                LIMIT 1
            """)
            if row:
                return dict(row)
        return None
    except Exception as e:
        logger.error(f"db_get_next_scheduled_vacancy xatosi: {e}")
        return None

async def db_get_nuvi_setting(key: str, default: str = None) -> Optional[str]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT value FROM nuvi_settings WHERE key = $1", key)
            if val is not None:
                return val
        return default
    except Exception as e:
        logger.error(f"db_get_nuvi_setting xatosi: {e}")
        return default

async def db_set_nuvi_setting(key: str, value: str) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO nuvi_settings (key, value)
                VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, key, str(value))
        return True
    except Exception as e:
        logger.error(f"db_set_nuvi_setting xatosi: {e}")
        return False

async def db_get_nuvi_stats() -> dict:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            total_users = await conn.fetchval("SELECT COUNT(*) FROM nuvi_users")
            total_vacancies = await conn.fetchval("SELECT COUNT(*) FROM nuvi_vacancies")
            total_posted = await conn.fetchval("SELECT COUNT(*) FROM nuvi_vacancies WHERE status = 'posted'")
            total_pending = await conn.fetchval("SELECT COUNT(*) FROM nuvi_vacancies WHERE status = 'pending_approval'")
            total_scheduled = await conn.fetchval("SELECT COUNT(*) FROM nuvi_vacancies WHERE status = 'approved' AND posted_at IS NULL")
        return {
            "total_users": total_users or 0,
            "total_vacancies": total_vacancies or 0,
            "total_posted": total_posted or 0,
            "total_pending": total_pending or 0,
            "total_scheduled": total_scheduled or 0,
        }
    except Exception as e:
        logger.error(f"db_get_nuvi_stats xatosi: {e}")
        return {}


async def db_get_nuvi_detailed_stats() -> dict:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # 1. Total counts
            total_users = await conn.fetchval("SELECT COUNT(*) FROM nuvi_users")
            total_vacancies = await conn.fetchval("SELECT COUNT(*) FROM nuvi_vacancies")
            total_posted = await conn.fetchval("SELECT COUNT(*) FROM nuvi_vacancies WHERE status = 'posted'")
            total_pending = await conn.fetchval("SELECT COUNT(*) FROM nuvi_vacancies WHERE status = 'pending_approval'")
            
            # 2. Tariff prices (from settings or fallback)
            pro_price = 20000
            prem_price = 35000
            vip_price = 50000
            
            p_pro = await conn.fetchval("SELECT value FROM nuvi_settings WHERE key = 'tariff_pro_price'")
            if p_pro: pro_price = int(p_pro)
            p_prem = await conn.fetchval("SELECT value FROM nuvi_settings WHERE key = 'tariff_premium_price'")
            if p_prem: prem_price = int(p_prem)
            p_vip = await conn.fetchval("SELECT value FROM nuvi_settings WHERE key = 'tariff_vip_price'")
            if p_vip: vip_price = int(p_vip)
            
            # 3. Calculate turnover based on paid vacancies
            paid_pro = await conn.fetchval("SELECT COUNT(*) FROM nuvi_vacancies WHERE payment_status = 'paid' AND tariff = 'pro'") or 0
            paid_premium = await conn.fetchval("SELECT COUNT(*) FROM nuvi_vacancies WHERE payment_status = 'paid' AND tariff = 'premium'") or 0
            paid_vip = await conn.fetchval("SELECT COUNT(*) FROM nuvi_vacancies WHERE payment_status = 'paid' AND tariff = 'vip'") or 0
            
            total_turnover = (paid_pro * pro_price) + (paid_premium * prem_price) + (paid_vip * vip_price)
            
            # 4. Status breakdown
            status_rows = await conn.fetch("SELECT status, COUNT(*) as cnt FROM nuvi_vacancies GROUP BY status")
            status_breakdown = {r['status']: r['cnt'] for r in status_rows}
            
            # 5. Tariff breakdown
            tariff_rows = await conn.fetch("SELECT tariff, COUNT(*) as cnt FROM nuvi_vacancies GROUP BY tariff")
            tariff_breakdown = {r['tariff']: r['cnt'] for r in tariff_rows}
            
            # 6. Recent 10 vacancies
            recent_rows = await conn.fetch(
                """
                SELECT v.id, v.title, v.company, v.salary, v.status, v.payment_status, v.tariff, v.created_at, u.first_name as user_name
                FROM nuvi_vacancies v
                LEFT JOIN nuvi_users u ON v.user_id = u.user_id
                ORDER BY v.id DESC LIMIT 10
                """
            )
            recent_vacancies = []
            for r in recent_rows:
                recent_vacancies.append({
                    "id": r['id'],
                    "title": r['title'],
                    "company": r['company'],
                    "salary": r['salary'],
                    "status": r['status'],
                    "payment_status": r['payment_status'],
                    "tariff": r['tariff'],
                    "user_name": r['user_name'] or "Moma'lum",
                    "created_at": r['created_at'].strftime("%Y-%m-%d %H:%M")
                })
                
            # 7. Monthly turnover dynamics (last 6 months)
            monthly_data = await conn.fetch(
                "SELECT tariff, created_at FROM nuvi_vacancies WHERE payment_status = 'paid'"
            )
            monthly_turnover = {}
            for m in monthly_data:
                m_str = m['created_at'].strftime("%Y-%m")
                tariff = m['tariff']
                price = pro_price if tariff == 'pro' else (prem_price if tariff == 'premium' else vip_price)
                monthly_turnover[m_str] = monthly_turnover.get(m_str, 0) + price
                
            monthly_turnover_sorted = [{"month": k, "amount": v} for k, v in sorted(monthly_turnover.items())]
            
            return {
                "total_users": total_users or 0,
                "total_vacancies": total_vacancies or 0,
                "total_posted": total_posted or 0,
                "total_pending": total_pending or 0,
                "total_turnover": total_turnover,
                "prices": {
                    "pro": pro_price,
                    "premium": prem_price,
                    "vip": vip_price
                },
                "tariffs": {
                    "pro": {"paid": paid_pro, "total": tariff_breakdown.get("pro", 0)},
                    "premium": {"paid": paid_premium, "total": tariff_breakdown.get("premium", 0)},
                    "vip": {"paid": paid_vip, "total": tariff_breakdown.get("vip", 0)}
                },
                "status_breakdown": status_breakdown,
                "recent_vacancies": recent_vacancies,
                "monthly_dynamics": monthly_turnover_sorted
            }
    except Exception as e:
        logger.error(f"db_get_nuvi_detailed_stats xatosi: {e}")
        return {}

async def db_align_vacancy_queue() -> bool:
    try:
        import pytz
        import datetime
        
        tz = pytz.timezone("Asia/Tashkent")
        now_tz = datetime.datetime.now(tz)
        
        # Align now_tz to the next 30-minute boundary
        minutes = now_tz.minute
        if minutes == 0 and now_tz.second == 0:
            next_slot = now_tz
        elif minutes <= 30:
            next_slot = now_tz.replace(minute=30, second=0, microsecond=0)
        else:
            next_slot = (now_tz + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            
        # Ensure within active hours (09:00 - 21:30)
        if next_slot.hour < 9:
            next_slot = next_slot.replace(hour=9, minute=0, second=0, microsecond=0)
        elif next_slot.hour >= 22 or (next_slot.hour == 21 and next_slot.minute > 30):
            next_slot = (next_slot + datetime.timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, tariff, created_at, scheduled_for 
                FROM nuvi_vacancies 
                WHERE status = 'approved' AND posted_at IS NULL
                ORDER BY 
                  CASE tariff 
                    WHEN 'vip' THEN 0 
                    WHEN 'premium' THEN 1 
                    WHEN 'pro' THEN 2 
                    ELSE 3 
                  END ASC, 
                  created_at ASC
            """)
            
            if not rows:
                return True
                
            current_slot = next_slot
            async with conn.transaction():
                for r in rows:
                    await conn.execute(
                        "UPDATE nuvi_vacancies SET scheduled_for = $1, updated_at = NOW() WHERE id = $2",
                        current_slot, r["id"]
                    )
                    
                    # Advance to next slot
                    current_slot += datetime.timedelta(minutes=30)
                    if current_slot.hour < 9:
                        current_slot = current_slot.replace(hour=9, minute=0, second=0, microsecond=0)
                    elif current_slot.hour >= 22 or (current_slot.hour == 21 and current_slot.minute > 30):
                        current_slot = (current_slot + datetime.timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
                        
            logger.info(f"✅ Vacancy queue aligned successfully for {len(rows)} vacancies.")
            return True
    except Exception as e:
        logger.error(f"db_align_vacancy_queue xatosi: {e}")
        return False

async def db_get_nuvi_queue() -> list[dict]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT v.id, v.title, v.company, v.salary, v.status, v.payment_status, v.tariff, v.scheduled_for, u.first_name as user_name
                FROM nuvi_vacancies v
                LEFT JOIN nuvi_users u ON v.user_id = u.user_id
                WHERE v.status = 'approved' AND v.posted_at IS NULL
                ORDER BY v.scheduled_for ASC
            """)
            queue = []
            for r in rows:
                s_time = r['scheduled_for']
                s_time_str = s_time.strftime("%Y-%m-%d %H:%M") if s_time else "Kutilmoqda"
                queue.append({
                    "id": r['id'],
                    "title": r['title'],
                    "company": r['company'],
                    "salary": r['salary'],
                    "status": r['status'],
                    "payment_status": r['payment_status'],
                    "tariff": r['tariff'],
                    "user_name": r['user_name'] or "Moma'lum",
                    "scheduled_for": s_time_str
                })
            return queue
    except Exception as e:
        logger.error(f"db_get_nuvi_queue xatosi: {e}")
        return []






