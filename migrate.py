import asyncio
from database import get_pool
import logging

logging.basicConfig(level=logging.INFO)

async def run_migration():
    pool = await get_pool()
    async with pool.acquire() as conn:
        print("Migratsiya boshlandi...")
        await conn.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_method TEXT DEFAULT 'karta'")
        await conn.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'UZS'")
        print("Migratsiya tugallandi: currency va payment_method ustunlari mavjud.")

if __name__ == "__main__":
    asyncio.run(run_migration())
