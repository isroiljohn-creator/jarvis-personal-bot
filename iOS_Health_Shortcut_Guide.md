# iOS Health → Jasmina Bot (Qo'llanma)

## Qanday ishlaydi?

```
iPhone Health App → iOS Shortcuts → Jasminaning serveri → Telegram
```

Har kuni ertalab avtomatik ravishda iPhone sog'liq ma'lumotlaringiz Jasminaga yuboriladi va u tahlil qilib Telegramga yozadi.

---

## Server URL

```
https://jarvis-personal-bot.up.railway.app/ios-health
```

---

## Qo'llab-quvvatlanadigan ma'lumotlar

| Ma'lumot | Kalit |
|---|---|
| Qadam soni | `steps` |
| Masofa (km) | `distance_km` |
| Aktiv kaloriya | `calories_active` |
| Yurak urishi (o'rt) | `heart_rate_avg` |
| Yurak urishi (min/max) | `heart_rate_min`, `heart_rate_max` |
| HRV | `hrv` |
| Uyqu (soat) | `sleep_hours` |
| Chuqur uyqu | `sleep_deep_hours` |
| REM uyqu | `sleep_rem_hours` |
| Turgan soatlar | `stand_hours` |
| Mashq daqiqalari | `exercise_minutes` |
| Qon kislorodi | `blood_oxygen` |
| Nafas tezligi | `respiratory_rate` |
| Vazn | `weight_kg` |
| Shovqin | `noise_avg_db` |
| Meditatsiya | `mindful_minutes` |
| Suv (ml) | `water_ml` |

---

## iOS Shortcuts O'rnatish

### Qadam 1: Shortcuts ilovasini oching

iPhone da **Shortcuts (Qisqartirishlar)** ilovasini oching.

### Qadam 2: Yangi Shortcut yarating

**"+"** tugmasini bosing → **"Add Action"** → **"Scripting"** → **"Get Contents of URL"**

### Qadam 3: URL va JSON sozlash

**URL:** `https://jarvis-personal-bot.up.railway.app/ios-health`

**Method:** POST

**Headers:**
```
Content-Type: application/json
```

**Body (JSON):** — Har bir "Get Health Sample" qo'shamiz

---

## Shortcut Qadamlari (to'liq)

Shortcut ichida ketma-ket bu amallarni bajaring:

```
1. "Health" → "Get Health Sample" → Steps → Today
   → Variable ga saqlang: "steps_val"

2. "Health" → "Get Health Sample" → Active Energy Burned → Today  
   → Variable: "calories_val"

3. "Health" → "Get Health Sample" → Heart Rate → Average → Today
   → Variable: "hr_val"

4. "Health" → "Get Health Sample" → Sleep Analysis → Last Night
   → Variable: "sleep_val"

5. "Health" → "Get Health Sample" → HRV → Latest
   → Variable: "hrv_val"

6. "Health" → "Get Health Sample" → Blood Oxygen Saturation → Latest
   → Variable: "spo2_val"

7. "Scripting" → "Text" → JSON yozing:
   {
     "steps": [steps_val],
     "calories_active": [calories_val],
     "heart_rate_avg": [hr_val],
     "sleep_hours": [sleep_val],
     "hrv": [hrv_val],
     "blood_oxygen": [spo2_val],
     "date": "[Current Date - YYYY-MM-DD format]"
   }

8. "Web" → "Get Contents of URL":
   URL: https://jarvis-personal-bot.up.railway.app/ios-health
   Method: POST
   Headers: Content-Type = application/json
   Body: [Text from step 7]
```

---

## Avtomatik ishga tushirish (Automation)

Shortcuts → **Automation** tab → **"+"** → **Personal Automation**:
- **Trigger:** Time of Day → 9:30 AM
- **Action:** yuqoridagi Shortcut
- **"Ask Before Running":** O'chirib qo'ying ✅

---

## Test qilish (Curl bilan)

```bash
curl -X POST https://jarvis-personal-bot.up.railway.app/ios-health \
  -H "Content-Type: application/json" \
  -d '{
    "steps": 8500,
    "calories_active": 420,
    "heart_rate_avg": 72,
    "heart_rate_min": 58,
    "heart_rate_max": 145,
    "hrv": 45,
    "sleep_hours": 7.5,
    "sleep_deep_hours": 1.8,
    "sleep_rem_hours": 1.5,
    "blood_oxygen": 98,
    "exercise_minutes": 45,
    "stand_hours": 10,
    "date": "2026-04-26"
  }'
```

---

## Jasmina qaytaradigan xabar namunasi

```
🏥 iOS Sog'liq Hisoboti — 2026-04-26

👣 Qadam: 8500
❤️ Yurak urishi (o'rt): 72 bpm  
😴 Uyqu: 7.5 soat
🔥 Aktiv kaloriya: 420 kkal

---
🤖 Jasmina Tahlili:
Xo'jayin, bugungi ko'rsatkichlaringiz umuman yaxshi! 🌟
Uyqu sifati zo'r — 7.5 soat etarli va chuqur uyqu ham normal.
Lekin qadam soni maqsaddan 1500 ta kam, bugun kechqurun
10 daqiqa yurish tavsiya etiladi. Yurak urishi normal zonada ✅
```
