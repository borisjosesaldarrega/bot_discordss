# Usamos una imagen de Python con Slim para reducir tamaño
FROM python:3.10-slim

# 1. Instala dependencias del sistema (FFmpeg + librerías de audio)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libffi-dev \
    libnacl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*  # Limpia caché

# 2. Configura el entorno
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 3. Instala dependencias de Python
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install --upgrade PyNaCl google-generativeai

# 4. Copia el código del bot
COPY . .

# 5. Inicia el bot (ajusta el nombre de tu archivo)
CMD ["python", "bot.py"]  # Cambia "tu_bot.py" al nombre de tu archivo principal