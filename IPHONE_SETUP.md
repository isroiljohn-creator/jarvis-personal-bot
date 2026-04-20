# Jarvis iPhone Command Executor — Apple Shortcuts uchun

## Shortcuts da sozlash qadamlari:

### Qadam 1: Yangi Shortcut yarating
1. iPhone → **Shortcuts** ilovasini oching
2. **+** bosing → **Add Action**

### Qadam 2: HTTP so'rov qo'shing
- **URL** qo'shing: `https://jarvis-personal-bot-production.up.railway.app/commands`
- Method: **GET**
- Response ni o'zgaruvchiga saqlang: `commands`

### Qadam 3: JSON Parse qiling
- **Get Values from Input** → Type: Dictionary
- Key: `commands`

### Qadam 4: Har command uchun IF qo'shing

**Budilnik uchun:**
```
IF command.type == "alarm"
  → Set Alarm (time = command.time, label = command.payload)
```

**Taymer uchun:**
```
IF command.type == "timer"  
  → Start Timer (duration = command.payload minutes)
```

**Musiqa uchun:**
```
IF command.type == "music"
  → Play Music (search = command.payload)
```

**DND uchun:**
```
IF command.type == "dnd"
  → Set Focus (Do Not Disturb = ON/OFF)
```

### Qadam 5: Automation yarating (har minutda)
1. **Automation** tab → **+** → **Time of Day**
2. Repeat: **Every Hour** (yoki har 5 minutda)
3. "Run Immediately" → shortcut ni tanlang

---

## Bot buyruqlari misollari:

```
"Ertaga 7:00 da budilnik qo'y"
"20 minutlik taymer o'rnat"  
"Spotify da lofi music qo'y"
"Do Not Disturb yoq"
"Instagramni och"
"15:00 uchrashuv uchun eslatma qo'y"
```
