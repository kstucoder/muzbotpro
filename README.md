# 🔐 SecretChat + 🎵 MusicBot

**Professional Telegram boti — ikki rejimda ishlaydi**

---

## 🚀 O'rnatish

### 1. Talablar
- Python 3.11+
- FFmpeg (musiqa uchun)
- Telegram Bot Token ([@BotFather](https://t.me/BotFather))

### 2. FFmpeg o'rnatish
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# https://ffmpeg.org/download.html dan yuklab oling
```

### 3. Botni sozlash
```bash
# Reponi klonlash
git clone <repo>
cd secret_bot

# .env fayli yaratish
cp .env.example .env
nano .env   # BOT_TOKEN va ADMIN_ID ni kiriting
```

### 4. Ishga tushirish
```bash
chmod +x run.sh
./run.sh
```

---

## ⚙️ Admin ID ni topish
[@userinfobot](https://t.me/userinfobot) ga `/start` yozing — ID raqamingizni beradi.

---

## 🔐 Yashirin Chat rejimi

### Qanday ishlaydi:
```
Admin → /addpair <parol>  →  Parolni ikkala kishiga yuboradi
Kishi 1 → parolni kiritadi → Kutish rejimi
Kishi 2 → parolni kiritadi → CHAT BOSHLANADI!
```

### Xususiyatlar:
- ✅ Real-time relay (xabarlar saqlanmaydi)
- 💣 O'qilgandan 1 daqiqada auto-delete
- 📸 Rasm, video, ovoz, stiker qo'llab-quvvatlaydi
- 👁️ Admin kim chatda ekanini ko'ra oladi

---

## 🎵 Musiqa rejimi

### Qanday ishlaydi:
- Parol kiritmagan foydalanuvchi musiqa botiga o'tadi
- Qo'shiq nomini yozadi → MP3 yuklab beriladi

### Qo'llab-quvvatlanadi:
- YouTube Music
- MP3 format, 192kbps
- Maksimal 50MB

---

## 👑 Admin buyruqlari

| Buyruq | Tavsif |
|--------|--------|
| `/admin` | Admin panel |
| `/addpair <parol>` | Yangi juft yaratish |
| `/delpair <parol>` | Juftni o'chirish |
| `/listpairs` | Barcha faol juftlar |
| `/kick <user_id>` | Foydalanuvchini chiqarish |
| `/broadcast <xabar>` | Barcha chatdagilarga xabar |

---

## 📁 Fayl tuzilmasi
```
secret_bot/
├── bot.py          # Asosiy bot kodi
├── requirements.txt
├── .env.example    # Shablon
├── .env            # Sizning sozlamalaringiz (gitga yuklamang!)
└── run.sh          # Ishga tushirish skripti
```

---

## 🔒 Xavfsizlik

- Parollar SHA-256 bilan hash qilinadi
- Xabarlar serverda saqlanmaydi (relay only)
- Auto-delete mexanizmi
- Admin monitoring

---

## 🛠 Muammolar

**Bot javob bermayapti:**
- BOT_TOKEN to'g'riligini tekshiring
- FFmpeg o'rnatilganini tekshiring: `ffmpeg -version`

**Musiqa yuklanmayapti:**
- `yt-dlp --update` bilan yangilang
- VPN kerak bo'lishi mumkin ba'zi qo'shiqlarda


