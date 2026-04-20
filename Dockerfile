FROM python:3.12-slim

WORKDIR /app

# Tizim kutubxonalari (ffmpeg TTS uchun kerak)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data papkasi (memory.json uchun)
RUN mkdir -p /app/data

CMD ["python", "bot.py"]
