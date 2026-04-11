# Jarvis Personal Bot — Session String generatsiya qilish

import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(input("API ID: "))
API_HASH = input("API Hash: ")
PHONE = input("Telefon (+998...): ")

async def main():
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        await client.start(phone=PHONE)
        session = client.session.save()
        print("\n✅ SESSION STRING (Railway'ga qo'ying):")
        print("=" * 60)
        print(session)
        print("=" * 60)
        print("\nBu qatorni TG_SESSION_STRING o'zgaruvchisiga qo'ying!")

asyncio.run(main())
