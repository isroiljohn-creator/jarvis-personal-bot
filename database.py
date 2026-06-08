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
    referred_by BIGINT,
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
    telegram_message_id INT,
    pinned         BOOLEAN DEFAULT FALSE,
    pin_expires_at TIMESTAMPTZ,
    promocode      TEXT,
    discounted_price INT,
    archive_prompted BOOLEAN DEFAULT FALSE,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nuvi_promocodes (
    code           TEXT PRIMARY KEY,
    discount_pct   INT DEFAULT 0,
    discount_flat  INT DEFAULT 0,
    max_uses       INT DEFAULT 100,
    uses_count     INT DEFAULT 0,
    active         BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
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

CREATE TABLE IF NOT EXISTS nuvi_cvs (
    user_id        BIGINT PRIMARY KEY REFERENCES nuvi_users(user_id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    contact        TEXT NOT NULL,
    specialty      TEXT NOT NULL,
    skills         TEXT NOT NULL,
    experience     TEXT NOT NULL,
    education      TEXT NOT NULL,
    about          TEXT,
    pdf_file_id    TEXT,
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nuvi_applications (
    id             SERIAL PRIMARY KEY,
    vacancy_id     INT REFERENCES nuvi_vacancies(id) ON DELETE CASCADE,
    candidate_id   BIGINT REFERENCES nuvi_users(user_id) ON DELETE CASCADE,
    cover_letter   TEXT,
    resume_file_id TEXT,
    status         TEXT DEFAULT 'pending', -- pending / accepted / rejected
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nuvi_preferences (
    user_id        BIGINT PRIMARY KEY REFERENCES nuvi_users(user_id) ON DELETE CASCADE,
    keywords       TEXT NOT NULL,
    location       TEXT,
    is_active      BOOLEAN DEFAULT TRUE,
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nuvi_reviews (
    id             SERIAL PRIMARY KEY,
    employer_id    BIGINT REFERENCES nuvi_users(user_id) ON DELETE CASCADE,
    reviewer_id    BIGINT REFERENCES nuvi_users(user_id) ON DELETE CASCADE,
    rating         INT CHECK (rating >= 1 AND rating <= 5),
    comment        TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(employer_id, reviewer_id)
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
                await conn.execute("ALTER TABLE nuvi_users ADD COLUMN IF NOT EXISTS referred_by BIGINT")
                await conn.execute("ALTER TABLE nuvi_users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE")
            except Exception as e:
                logger.error(f"Error altering nuvi_users: {e}")
            try:
                await conn.execute("ALTER TABLE nuvi_vacancies ADD COLUMN IF NOT EXISTS tariff TEXT DEFAULT 'pro'")
                await conn.execute("ALTER TABLE nuvi_vacancies ADD COLUMN IF NOT EXISTS skills TEXT")
                await conn.execute("ALTER TABLE nuvi_vacancies ADD COLUMN IF NOT EXISTS telegram_message_id INT")
                await conn.execute("ALTER TABLE nuvi_vacancies ADD COLUMN IF NOT EXISTS pinned BOOLEAN DEFAULT FALSE")
                await conn.execute("ALTER TABLE nuvi_vacancies ADD COLUMN IF NOT EXISTS pin_expires_at TIMESTAMPTZ")
                await conn.execute("ALTER TABLE nuvi_vacancies ADD COLUMN IF NOT EXISTS promocode TEXT")
                await conn.execute("ALTER TABLE nuvi_vacancies ADD COLUMN IF NOT EXISTS discounted_price INT")
                await conn.execute("ALTER TABLE nuvi_vacancies ADD COLUMN IF NOT EXISTS archive_prompted BOOLEAN DEFAULT FALSE")
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
    if isinstance(plan_date, str):
        from datetime import datetime
        try:
            plan_date = datetime.strptime(plan_date, "%Y-%m-%d").date()
        except ValueError:
            pass
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
    if isinstance(plan_date, str):
        from datetime import datetime
        try:
            plan_date = datetime.strptime(plan_date, "%Y-%m-%d").date()
        except ValueError:
            pass
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

async def db_upsert_nuvi_user(user_id: int, username: str, first_name: str, referred_by: int = None) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if referred_by:
                # Check if user already exists
                exists = await conn.fetchval("SELECT 1 FROM nuvi_users WHERE user_id = $1", user_id)
                if not exists:
                    # Check if referrer exists in nuvi_users
                    ref_exists = await conn.fetchval("SELECT 1 FROM nuvi_users WHERE user_id = $1", referred_by)
                    if ref_exists:
                        await conn.execute("""
                            INSERT INTO nuvi_users (user_id, username, first_name, referred_by)
                            VALUES ($1, $2, $3, $4)
                            ON CONFLICT (user_id) DO UPDATE 
                            SET username = EXCLUDED.username, first_name = EXCLUDED.first_name
                        """, user_id, username, first_name, referred_by)
                        return True
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
            
            monthly_turnover_sorted = dict(sorted(monthly_turnover.items()))
                
            # 8. Referral & Promo Stats
            referral_signups = await conn.fetchval("SELECT COUNT(*) FROM nuvi_users WHERE referred_by IS NOT NULL") or 0
            promocodes_used = await conn.fetchval("SELECT SUM(uses_count) FROM nuvi_promocodes") or 0
            
            return {
                "total_users": total_users or 0,
                "total_vacancies": total_vacancies or 0,
                "total_posted": total_posted or 0,
                "total_pending": total_pending or 0,
                "total_turnover": total_turnover,
                "referral_signups": referral_signups,
                "promocodes_used": promocodes_used,
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

async def db_align_vacancy_queue() -> tuple[bool, list]:
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
                SELECT id, tariff, created_at, scheduled_for, user_id, title 
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
                return True, []
                
            current_slot = next_slot
            shifted_vacancies = []
            async with conn.transaction():
                for r in rows:
                    old_time = r["scheduled_for"]
                    await conn.execute(
                        "UPDATE nuvi_vacancies SET scheduled_for = $1, updated_at = NOW() WHERE id = $2",
                        current_slot, r["id"]
                    )
                    
                    # If it was shifted to a LATER time, and it is a PAID vacancy (pro, premium, vip)
                    # and old_time was not None
                    if old_time and current_slot > old_time and r["tariff"] in ('pro', 'premium', 'vip'):
                        shifted_vacancies.append({
                            "id": r["id"],
                            "user_id": r["user_id"],
                            "title": r["title"],
                            "tariff": r["tariff"],
                            "old_time": old_time,
                            "new_time": current_slot
                        })
                    
                    # Advance to next slot
                    current_slot += datetime.timedelta(minutes=30)
                    if current_slot.hour < 9:
                        current_slot = current_slot.replace(hour=9, minute=0, second=0, microsecond=0)
                    elif current_slot.hour >= 22 or (current_slot.hour == 21 and current_slot.minute > 30):
                        current_slot = (current_slot + datetime.timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
                        
            logger.info(f"✅ Vacancy queue aligned successfully for {len(rows)} vacancies. Shifted: {len(shifted_vacancies)}")
            return True, shifted_vacancies
    except Exception as e:
        logger.error(f"db_align_vacancy_queue xatosi: {e}")
        return False, []

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

async def db_get_pinned_nuvi_vacancies_to_unpin() -> list[dict]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, telegram_message_id 
                FROM nuvi_vacancies 
                WHERE pinned = TRUE AND telegram_message_id IS NOT NULL AND pin_expires_at <= NOW()
            """)
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"db_get_pinned_nuvi_vacancies_to_unpin xatosi: {e}")
        return []

async def db_validate_promocode(code: str) -> Optional[dict]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM nuvi_promocodes 
                WHERE code = $1 AND active = TRUE AND uses_count < max_uses
            """, code.strip().upper())
            if row:
                return dict(row)
        return None
    except Exception as e:
        logger.error(f"db_validate_promocode xatosi: {e}")
        return None

async def db_use_promocode(code: str) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE nuvi_promocodes 
                SET uses_count = uses_count + 1 
                WHERE code = $1
            """, code.strip().upper())
        return True
    except Exception as e:
        logger.error(f"db_use_promocode xatosi: {e}")
        return False

async def db_create_promocode(code: str, discount_pct: int = 0, discount_flat: int = 0, max_uses: int = 100) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO nuvi_promocodes (code, discount_pct, discount_flat, max_uses, active)
                VALUES ($1, $2, $3, $4, TRUE)
                ON CONFLICT (code) DO UPDATE 
                SET discount_pct = $2, discount_flat = $3, max_uses = $4, active = TRUE
            """, code.strip().upper(), discount_pct, discount_flat, max_uses)
        return True
    except Exception as e:
        logger.error(f"db_create_promocode xatosi: {e}")
        return False

async def db_get_user_referrer(user_id: int) -> Optional[int]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT referred_by FROM nuvi_users WHERE user_id = $1", user_id)
            return val
        return None
    except Exception as e:
        logger.error(f"db_get_user_referrer xatosi: {e}")
        return None

async def db_get_user_paid_vacancies_count(user_id: int) -> int:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("""
                SELECT COUNT(*) FROM nuvi_vacancies 
                WHERE user_id = $1 AND payment_status = 'paid'
            """, user_id)
            return val or 0
    except Exception as e:
        logger.error(f"db_get_user_paid_vacancies_count xatosi: {e}")
        return 0

async def db_get_nuvi_vacancies_to_archive() -> list[dict]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM nuvi_vacancies 
                WHERE status = 'posted' 
                  AND posted_at <= NOW() - INTERVAL '14 days' 
                  AND archive_prompted = FALSE
            """)
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"db_get_nuvi_vacancies_to_archive xatosi: {e}")
        return []

async def db_mark_nuvi_vacancy_archive_prompted(vac_id: int) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE nuvi_vacancies SET archive_prompted = TRUE WHERE id = $1", vac_id)
        return True
    except Exception as e:
        logger.error(f"db_mark_nuvi_vacancy_archive_prompted xatosi: {e}")
        return False

async def db_get_posted_vacancies_count() -> int:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT COUNT(*) FROM nuvi_vacancies WHERE status = 'posted'")
            return val or 0
    except Exception as e:
        logger.error(f"db_get_posted_vacancies_count xatosi: {e}")
        return 0

# ─── CVlar Tizimi (Resume Builder) ───
async def db_save_cv(user_id: int, name: str, contact: str, specialty: str, skills: str, experience: str, education: str, about: str = None, pdf_file_id: str = None) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO nuvi_cvs (user_id, name, contact, specialty, skills, experience, education, about, pdf_file_id, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                ON CONFLICT (user_id) DO UPDATE 
                SET name = $2, contact = $3, specialty = $4, skills = $5, experience = $6, education = $7, about = $8, pdf_file_id = $9, updated_at = NOW()
            """, user_id, name, contact, specialty, skills, experience, education, about, pdf_file_id)
        return True
    except Exception as e:
        logger.error(f"db_save_cv xatosi: {e}")
        return False

async def db_get_cv(user_id: int) -> Optional[dict]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM nuvi_cvs WHERE user_id = $1", user_id)
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"db_get_cv xatosi: {e}")
        return None

# ─── Nomzodlarni Boshqarish (ATS) ───
async def db_create_application(vacancy_id: int, candidate_id: int, cover_letter: str, resume_file_id: str = None) -> Optional[int]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("""
                INSERT INTO nuvi_applications (vacancy_id, candidate_id, cover_letter, resume_file_id, status, created_at)
                VALUES ($1, $2, $3, $4, 'pending', NOW())
                RETURNING id
            """, vacancy_id, candidate_id, cover_letter, resume_file_id)
            return val
    except Exception as e:
        logger.error(f"db_create_application xatosi: {e}")
        return None

async def db_get_application(app_id: int) -> Optional[dict]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT a.*, v.title as vacancy_title, v.company as vacancy_company, v.user_id as employer_id, u.first_name as candidate_name, u.username as candidate_username
                FROM nuvi_applications a
                JOIN nuvi_vacancies v ON a.vacancy_id = v.id
                JOIN nuvi_users u ON a.candidate_id = u.user_id
                WHERE a.id = $1
            """, app_id)
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"db_get_application xatosi: {e}")
        return None

async def db_update_application_status(app_id: int, status: str) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE nuvi_applications SET status = $1 WHERE id = $2", status, app_id)
        return True
    except Exception as e:
        logger.error(f"db_update_application_status xatosi: {e}")
        return False

# ─── Mos Vakansiyalar Obunasi (Job Alerts) ───
async def db_save_preferences(user_id: int, keywords: str, location: str = None, is_active: bool = True) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO nuvi_preferences (user_id, keywords, location, is_active, updated_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (user_id) DO UPDATE 
                SET keywords = $2, location = $3, is_active = $4, updated_at = NOW()
            """, user_id, keywords.lower(), location.lower() if location else None, is_active)
        return True
    except Exception as e:
        logger.error(f"db_save_preferences xatosi: {e}")
        return False

async def db_get_preferences(user_id: int) -> Optional[dict]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM nuvi_preferences WHERE user_id = $1", user_id)
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"db_get_preferences xatosi: {e}")
        return None

async def db_get_matching_candidates(vac_title: str, vac_desc: str, vac_skills: str, vac_loc: str) -> list[int]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT user_id, keywords, location FROM nuvi_preferences WHERE is_active = TRUE")
            matched = []
            
            vac_title_safe = vac_title or ""
            vac_desc_safe = vac_desc or ""
            vac_text = f"{vac_title_safe} {vac_desc_safe} {vac_skills or ''}".lower()
            vac_loc_lower = vac_loc.lower() if vac_loc else ""
            
            for r in rows:
                user_id = r["user_id"]
                loc = r["location"]
                
                if loc:
                    if loc == "masofaviy" or loc == "remote":
                        if "masofaviy" not in vac_loc_lower and "remote" not in vac_loc_lower:
                            continue
                    else:
                        if loc not in vac_loc_lower:
                            continue
                        
                kws = [k.strip() for k in r["keywords"].split(",") if k.strip()]
                if not kws:
                    continue
                    
                if any(kw in vac_text for kw in kws):
                    matched.append(user_id)
            return matched
    except Exception as e:
        logger.error(f"db_get_matching_candidates xatosi: {e}")
        return []

# ─── Reyting va Baholash (Trust Badge) ───
async def db_save_review(employer_id: int, reviewer_id: int, rating: int, comment: str = None) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO nuvi_reviews (employer_id, reviewer_id, rating, comment, created_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (employer_id, reviewer_id) DO UPDATE 
                SET rating = $3, comment = $4, created_at = NOW()
            """, employer_id, reviewer_id, rating, comment)
        return True
    except Exception as e:
        logger.error(f"db_save_review xatosi: {e}")
        return False

async def db_get_employer_rating(employer_id: int) -> dict:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT AVG(rating) as avg_rating, COUNT(*) as reviews_count 
                FROM nuvi_reviews 
                WHERE employer_id = $1
            """, employer_id)
            
            avg_val = row["avg_rating"] if row and row["avg_rating"] is not None else 0.0
            cnt_val = row["reviews_count"] if row else 0
            
            return {"avg_rating": float(avg_val), "reviews_count": cnt_val}
    except Exception as e:
        logger.error(f"db_get_employer_rating xatosi: {e}")
        return {"avg_rating": 0.0, "reviews_count": 0}

async def db_is_employer_verified(employer_id: int) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            verified_flag = await conn.fetchval("SELECT is_verified FROM nuvi_users WHERE user_id = $1", employer_id)
            if verified_flag:
                return True
                
            row = await conn.fetchrow("""
                SELECT AVG(rating) as avg_rating, COUNT(*) as reviews_count 
                FROM nuvi_reviews 
                WHERE employer_id = $1
            """, employer_id)
            
            if row and row["avg_rating"] is not None:
                if float(row["avg_rating"]) >= 4.5 and row["reviews_count"] >= 3:
                    return True
            return False
    except Exception as e:
        logger.error(f"db_is_employer_verified xatosi: {e}")
        return False

async def db_get_candidate_applications(candidate_id: int) -> list[dict]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT a.*, v.title as vacancy_title, v.company as vacancy_company, v.user_id as employer_id
                FROM nuvi_applications a
                JOIN nuvi_vacancies v ON a.vacancy_id = v.id
                WHERE a.candidate_id = $1
                ORDER BY a.id DESC
            """, candidate_id)
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"db_get_candidate_applications xatosi: {e}")
        return []








