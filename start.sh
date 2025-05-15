#!/bin/bash
# Verifica FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ Error: FFmpeg no está instalado. Usa Docker o contacta a Render.";
    exit 1;
fi
# Inicia el bot
python bot.py
