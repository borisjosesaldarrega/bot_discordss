import discord
from discord.ext import commands
import yt_dlp
import os
import requests
import asyncio
from dotenv import load_dotenv
import google.generativeai as genai
import validators

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # Eliminé la segunda llamada a load_dotenv()

# Configurar Google AI
genai.configure(api_key=GOOGLE_API_KEY)

# Configuración de intents
intents = discord.Intents.default()
intents.message_content = True

# Inicialización del bot
bot = commands.Bot(command_prefix='¡', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    
class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.is_playing = False  # Para evitar bloqueos en la reproducción

    async def reproducir(self, ctx):
        if not self.queue:
            await ctx.send("📭 No hay canciones en la cola.")
            self.is_playing = False
            return

        url = self.queue.pop(0)
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'geo_bypass': True,  # Evita restricciones geográficas
            'outtmpl': 'song.%(ext)s',
            }

        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                url2 = info.get('url')

            if not url2:
                await ctx.send("⚠️ No se pudo obtener la URL del audio.")
                self.is_playing = False
                return

            voice = ctx.voice_client

            if not voice:
                await ctx.send("⚠️ No estoy conectado a un canal de voz.")
                self.is_playing = False
                return

            self.is_playing = True
            voice.play(discord.FFmpegPCMAudio(url2), 
                       after=lambda e: self.bot.loop.create_task(self.siguiente(ctx)))
            await ctx.send(f"🎵 Reproduciendo: {url}")

        except Exception as e:
            await ctx.send(f"❌ Error al reproducir la canción: {str(e)}")
            self.is_playing = False

    async def siguiente(self, ctx):
        if self.queue:
            await self.reproducir(ctx)
        else:
            await ctx.send("📭 La cola está vacía.")
            self.is_playing = False

    @commands.command()
    async def entrar(self, ctx):
        """Conectar al canal de voz."""
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
            await ctx.send("🎧 Conectado al canal de voz.")
        else:
            await ctx.send("🚨 Debes estar en un canal de voz.")

    @commands.command()
    async def salir(self, ctx):
        """Desconectar del canal de voz y limpiar la cola."""
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            self.queue.clear()
            self.is_playing = False
            await ctx.send("👋 Desconectado y cola borrada.")
        else:
            await ctx.send("⚠️ No estoy conectado a ningún canal de voz.")

    @commands.command()
    async def play(self, ctx, url: str):
        """Añadir una canción a la cola y reproducirla."""
        if not validators.url(url):
            await ctx.send("❌ La URL proporcionada no es válida.")
            return

        self.queue.append(url)
        await ctx.send(f"🎵 Añadido a la cola: {url}")

        if not ctx.voice_client:
            await self.entrar(ctx)

        if not self.is_playing:
            await self.reproducir(ctx)

    @commands.command()
    async def skip(self, ctx):
        """Saltar la canción actual."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ Canción saltada.")
            await self.siguiente(ctx)

    @commands.command()
    async def pause(self, ctx):
        """Pausar la música actual."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ Música pausada.")

    @commands.command()
    async def continuar(self, ctx):
        """Reanudar la música pausada."""
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ Música reanudada.")

    @commands.command()
    async def cola(self, ctx):
        """Mostrar la cola de reproducción."""
        if not self.queue:
            await ctx.send("📭 La cola está vacía.")
        else:
            embed = discord.Embed(title="🎶 Cola de reproducción", color=discord.Color.purple())
            for i, url in enumerate(self.queue):
                embed.add_field(name=f"{i+1}.", value=url, inline=False)
            await ctx.send(embed=embed)

# Comando: con IA
@bot.command()  # ✅ Corrección: Eliminé el doble "@"
async def charla(ctx, *, mensaje):
    """Interactuar con la IA de Google Gemini."""
    respuesta = responder_ia(mensaje)
    await ctx.send(f'🤖 {respuesta}')

def responder_ia(mensaje):
    """Obtener respuesta de la IA de Google Gemini."""
    try:
        model = genai.GenerativeModel("gemini-pro")  # Usa "gemini-pro" para respuestas avanzadas
        respuesta = model.generate_content(mensaje)
        return respuesta.text
    except Exception as e:
        return f"❌ Error al obtener respuesta de IA: {str(e)}"
        
# Comando: Encuesta
@bot.command()
async def votar(ctx, pregunta, *opciones):
    """Crear una encuesta con opciones."""
    if len(opciones) < 2:
        await ctx.send("Debes proporcionar al menos dos opciones.")
    else:
        await crear_encuesta(ctx, pregunta, opciones)

async def crear_encuesta(ctx, pregunta, opciones):
    """Enviar una encuesta al canal."""
    emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣']
    if len(opciones) > len(emojis):
        await ctx.send("Máximo 6 opciones.")
        return

    descripcion = ""
    for i, opcion in enumerate(opciones):
        descripcion += f"{emojis[i]} {opcion}\n"

    embed = discord.Embed(title=f"📊 {pregunta}", description=descripcion, color=discord.Color.blue())
    mensaje = await ctx.send(embed=embed)

    for i in range(len(opciones)):
        await mensaje.add_reaction(emojis[i])

# Comando: Karaoke
@bot.command()
async def letra(ctx, *, cancion):
    """Obtener la letra de una canción."""
    letra = obtener_letra(cancion)
    partes = [letra[i:i+1900] for i in range(0, len(letra), 1900)]
    for parte in partes:
        await ctx.send(f"🎤 {parte}")
        await asyncio.sleep(1)

def obtener_letra(cancion):
    """Obtener la letra de la canción desde una API."""
    try:
        artista, titulo = cancion.split('-', 1)
    except ValueError:
        return "Usa el formato: artista - título"

    url = f"https://api.lyrics.ovh/v1/{artista.strip()}/{titulo.strip()}"
    res = requests.get(url)
    if res.status_code == 200:
        return res.json()['lyrics']
    else:
        return "Letra no encontrada 😢"

@bot.command()
async def ayuda(ctx):
    """Mostrar un menú con los comandos disponibles."""
    embed = discord.Embed(title="📖 Comandos del bot", color=discord.Color.blue())
    embed.add_field(name="🎵 ¡play [url]", value="Reproducir música en el canal de voz.", inline=False)
    embed.add_field(name="⏸️ ¡pause", value="Pausar la canción en curso.", inline=False)
    embed.add_field(name="▶️ ¡continuar", value="Reanudar la música pausada.", inline=False)
    embed.add_field(name="⏭️ ¡skip", value="Saltar la canción actual.", inline=False)
    embed.add_field(name="🗑️ ¡remover [posición]", value="Eliminar una canción específica de la cola.", inline=False)
    embed.add_field(name="💬 ¡charla [mensaje]", value="Hablar con la IA de OpenAI.", inline=False)
    embed.add_field(name="📊 ¡votar [pregunta] [opción1] [opción2]", value="Crear una encuesta.", inline=False)
    await ctx.send(embed=embed)


# Añadir el módulo de música al bot
async def setup_hook():
    await bot.add_cog(Music(bot))

bot.setup_hook = setup_hook
# Ejecutar el bot

bot.run(TOKEN)
