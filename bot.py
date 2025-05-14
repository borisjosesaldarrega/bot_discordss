import discord
from discord.ext import commands
import yt_dlp
import os
import requests
import asyncio
from dotenv import load_dotenv
import google.generativeai as genai
import validators
import aiohttp
from discord import FFmpegPCMAudio  # ✅ Importación correcta para reproducir audio

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

class MyBot(commands.Bot):
    async def setup_hook(self):
        await self.load_extension("cogs.music")

bot = MyBot(command_prefix="¡", intents=intents)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.is_playing = False  # Para evitar bloqueos en la reproducción

    async def reproducir(self, ctx, region='MX'):
        if not self.queue:
            await ctx.send("📭 No hay canciones en la cola.")
            self.is_playing = False
            return

        url = self.queue.pop(0)
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'geo_bypass': True,  # Evita restricciones geográficas
            'geo': region,  # Establece la región
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
                       after=lambda e: self.bot.loop.create_task(self.siguiente(ctx)) if ctx else None)
            await ctx.send(f"🎵 Reproduciendo: {url}")

        except yt_dlp.utils.ExtractorError as e:
            await ctx.send(f"❌ Error al reproducir la canción: {str(e)}. El video puede no estar disponible.")
            self.is_playing = False
        except Exception as e:
            await ctx.send(f"❌ Error inesperado: {str(e)}")
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
    async def play(self, ctx, url: str, region: str = 'MX'):
        """Añadir una canción a la cola y reproducirla."""
        if not validators.url(url) or not ("youtube.com" in url or "youtu.be" in url):
            await ctx.send("❌ La URL proporcionada no es válida o no es de YouTube.")
            return

        self.queue.append(url)
        await ctx.send(f"🎵 Añadido a la cola: {url}")

        if not ctx.voice_client:
            await self.entrar(ctx)

        if not self.is_playing:
            await self.reproducir(ctx, region)

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
            await ctx.send("📭 La cola está vacía")
        else:
            embed = discord.Embed(title="🎶 Cola de reproducción", color=discord.Color.purple())
            for i, url in enumerate(self.queue):
                embed.add_field(name=f"{i+1}.", value=url, inline=False)
            await ctx.send(embed=embed)
            
    @commands.command()
    async def remover(self, ctx, posicion: int):
        if 0 < posicion <= len(self.queue):
            removido = self.queue.pop(posicion - 1)
            await ctx.send(f"🗑️ Eliminado de la cola: {removido}")
        else:
            await ctx.send("❌ Posición inválida.")

@bot.command()  
async def charla(ctx, *, mensaje):
    """Interactuar con la IA de Google Gemini."""
    user_name = ctx.author.name  # ✅ Obtiene el nombre del usuario
    respuesta = responder_ia(mensaje, user_name)
    await ctx.send(f'🤖 {respuesta}')

def responder_ia(mensaje, user_name):
    """Obtener respuesta de la IA de Google Gemini."""
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")  

        # ✅ Si el usuario pregunta por el nombre del bot, responde con su nombre
        if mensaje.lower() in ["¿cómo te llamas?", "¿quién eres?", "¿cuál es tu nombre?"]:
            return "¡Soy Archeon, el asitente del servidor! 😊"

        # ✅ Si el usuario pregunta "¿Quién soy?", responde con su nombre
        if mensaje.lower() in ["¿quién soy?", "¿cómo me llamo?", "¿me conoces?"]:
            return f"Tú eres {user_name}, ¡claro que te conozco! 😃"

        # ✅ Genera una respuesta personalizada con el nombre del usuario
        prompt = f"{user_name} ha dicho: {mensaje}. Responde de manera amigable y personalizada."
        respuesta = model.generate_content(prompt)
        return respuesta.text
    except Exception as e:
        return f"❌ Error al obtener respuesta de IA: {str(e)}"

@bot.command()
async def votar(ctx, pregunta: str, *opciones):
    """Crear una encuesta con hasta 6 opciones."""
    emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣']

    if len(opciones) < 2:
        await ctx.send("❌ Debes proporcionar al menos dos opciones para la encuesta.")
        return
    if len(opciones) > len(emojis):
        await ctx.send("⚠️ Máximo 6 opciones permitidas.")
        return

    # Construir la descripción de la encuesta
    descripcion = "\n".join([f"{emojis[i]} **{opcion.strip()}**" for i, opcion in enumerate(opciones)])

    embed = discord.Embed(
        title=f"📊 Encuesta: {pregunta}",
        description=descripcion,
        color=discord.Color.gold()
    )
    embed.set_footer(text="¡Vota reaccionando a los emojis!")

    try:
        mensaje = await ctx.send(embed=embed)
        for i in range(len(opciones)):
            await mensaje.add_reaction(emojis[i])
    except Exception as e:
        await ctx.send(f"❌ Ocurrió un error al crear la encuesta: {str(e)}")

@bot.command()
async def letra(ctx, *, cancion):
    """Obtener la letra de una canción en formato karaoke."""
    try:
        artista, titulo = map(str.strip, cancion.split('-', 1))
    except ValueError:
        await ctx.send("❌ Usa el formato correcto: `artista - título`")
        return

    letra = await obtener_letra(artista, titulo)
    
    if not letra or "no encontrada" in letra.lower():
        await ctx.send("😢 No pude encontrar la letra. Asegúrate de escribir bien el artista y título.")
        return

    partes = [letra[i:i+1900] for i in range(0, len(letra), 1900)]
    for parte in partes:
        await ctx.send(f"🎤 {parte}")
        await asyncio.sleep(1)

async def obtener_letra(artista, titulo):
    """Obtener la letra de una canción desde la API lyrics.ovh."""
    url = f"https://api.lyrics.ovh/v1/{artista}/{titulo}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as res:
                if res.status == 200:
                    data = await res.json()
                    letra = data.get('lyrics', '').strip()
                    return letra if letra else "Letra no encontrada"
                else:
                    return "Letra no encontrada"
    except asyncio.TimeoutError:
        return "⏱️ La API tardó demasiado en responder."
    except Exception as e:
        return f"❌ Error al obtener la letra: {str(e)}"

@bot.command(name="ayuda")
async def mostrar_ayuda(ctx):
    """Mostrar un menú con los comandos disponibles."""
    prefix = "¡"  # Si usas otro prefijo dinámico, reemplázalo aquí

    embed = discord.Embed(
        title="📖 Comandos disponibles",
        description="Aquí tienes una lista de comandos que puedes usar:",
        color=discord.Color.blurple()
    )

    # 🎵 Comandos de música
    embed.add_field(name="🎵 Música",
        value=(
            f"`{prefix}play [url]` - Reproduce música en el canal de voz\n"
            f"`{prefix}pause` - Pausa la canción actual\n"
            f"`{prefix}continuar` - Reanuda la música pausada\n"
            f"`{prefix}skip` - Salta la canción actual\n"
            f"`{prefix}remover [posición]` - Elimina una canción de la cola"
        ),
        inline=False
    )

    # 💬 Otros comandos
    embed.add_field(name="🧠 Chat IA", value=f"`{prefix}charla [mensaje]` - Habla con la IA de OpenAI", inline=False)
    embed.add_field(name="📊 Encuestas", value=f"`{prefix}votar [pregunta] [opciones...]` - Crea una encuesta rápida", inline=False)
    embed.add_field(name="🎤 Karaoke", value=f"`{prefix}letra artista - título` - Muestra la letra de una canción", inline=False)

    # Pie de página
    embed.set_footer(text="Usa el prefijo '!' antes de cada comando | Bot de música e IA")
    embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else discord.Embed.Empty)

    await ctx.send(embed=embed)


# Añadir el módulo de música al bot
async def setup_hook():
    await bot.add_cog(Music(bot))

bot.setup_hook = setup_hook
# Ejecutar el bot

bot.run(TOKEN)
