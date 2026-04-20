# Kunlik Telegram Tahlili (Daily Digest) Loyihasi

Sizning so'rov bo'yicha botingiz har kuni 20:00 da guruhlaringiz va shaxsiy yozishmalaringizni o'qib, ularni ahamiyatiga ko'ra tahlil qilib (Digest) beradigan funksiya bilan boyitiladi.

## User Review Required

> [!IMPORTANT]  
> Barcha o'qilmagan xabarlarni bitta to'plamga yig'ib Gemini AI'ga beramiz. Ushbu amal har kuni 20:00 da fonga rejalashtiriladi (Avtomat ishlaydi).
> Ammo e'tibor bering: Telegramda minglab xabarlar keluvchi "Yangiliklar Kanallari" (Channels) ni bu tahlilga kiritmaslikni maslahat beraman, aks holda tahlil faqat kanallardagi yangiliklarga to'lib qolib do'stlaringiz va ishchi guruhlardagi muhim matnlar ko'rinmay qolishi mumkin. Faqat **Shaxsiy Chatlar** va **Guruhlar** o'qilsinmi? (Tasdiqlasangiz shunday qilaman).

## Proposed Changes

### 1-qadam: Kutubxonalar (Dependencies)

- `python-telegram-bot` ning JobQueue (Vazifalar navbati) modulini ishlatish uchun zarur kutubxonalar (`apscheduler`, `pytz`) `requirements.txt` ga yuklanadi.

#### [MODIFY] requirements.txt
- `python-telegram-bot[job-queue]==21.5` hamda `pytz` qatorlari qo'shiladi.

---

### 2-qadam: UserBot Orqali Xabarlarni Yig'ish

`userbot.py` faylida yangi funksiya (masalan, `get_daily_digest_messages`) yozamiz. Bunga asosan:
- O'tgan 24 soat (yoki bugungi kun) ichida yozishilgan eng aktiv 30-40 ta chat yig'iladi.
- Har bir guruh va shaxsiy chatdan oxirgi/o'qilmagan xabarlar (limit asosida, masalan har biridan 20 tadan) to'planadi.
- Bu ma'lumotlar bitta yirik matn ko'rinishiga keladi.

#### [MODIFY] userbot.py

---

### 3-qadam: Autoreport (Avtohisobot) Jadvallashtirish

`bot.py` asosiy fayliga `apscheduler` ulanadi hamda `run_daily` vazifasi TShT (Toshkent vaqti) bilan soat `20:00:00` ga o'rnatiladi.
- Soat 20:00 bo'lganda bot UserBot'dan barcha matnlarni so'raydi.
- Olingan matnlarni Gemini-pro-latest modeliga: *"Bular foydalanuvchining bugungi barcha muhim chatlari va guruhlaridan xabarlar. Bularni o'qib eng muhim, ahamiyatli qismlarini asosiy planga chiqarib foydalanuvchiga 20:00-Tahlil ro'yxati qilib tushuntirib ber"* degan so'rov jo'natiladi.
- Qaytib kelgan natijani shaxsan o'zingizga (Egasi – Owner'ga) Telegramdan chiroyli formatda jo'natadi.

#### [MODIFY] bot.py

## Open Questions

> [!WARNING]  
> Hozir biz avtomatik Telegramingiz (Userbot) ga kirdik, lekin bot natijani siz bilan muloqot qilayotgan bot oynasiga (Control Botga) yuborishi kerakmi yoki o'zingizning "Saqlangan xabarlaringizga - Saved Messages" tashlashini xohlaysizmi? Odatda Control Bot orqali kelgani qulay, chunki ovozli xabar va qulayliklar o'sha yerda. Bu borada maxsus g'oyangiz yo'q bo'lsa Control Bot'da qoldiraman.

## Verification Plan

### Automated/Manual Tests
- Dastlab `20:00` o'rniga hozirgi vaqtdan +2 daqiqa o'tib ishlaydigan qilib kichik Test o'tkazaman (Vaqtni aldab ko'ramiz).
- O'sha vaqt o'tganda bot menga Chatlar yig'indisini mukammal tahlil qilib bersa, asl kodni 20:00 ga tiklab Serverga qo'yaman.
