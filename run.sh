#!/bin/bash
# run.sh — Botni ishga tushirish skripti

echo "🔐 SecretChat + 🎵 MusicBot ishga tushmoqda..."

# .env faylidan o'zgaruvchilarni yuklash
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ .env fayli yuklandi"
else
    echo "❌ .env fayli topilmadi! .env.example dan nusxa oling:"
    echo "   cp .env.example .env"
    echo "   nano .env"
    exit 1
fi

# FFmpeg tekshirish (musiqa uchun kerak)
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  FFmpeg topilmadi. O'rnatilmoqda..."
    sudo apt-get install -y ffmpeg 2>/dev/null || brew install ffmpeg 2>/dev/null
fi

# Virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Virtual environment yaratilmoqda..."
    python3 -m venv venv
fi

source venv/bin/activate

# Dependencies
echo "📥 Kutubxonalar o'rnatilmoqda..."
pip install -q -r requirements.txt

# Run
echo "🚀 Bot ishga tushdi!"
python bot.py
