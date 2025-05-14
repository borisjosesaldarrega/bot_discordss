import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
import yt_dlp as youtube_dl
import validators
import asyncio
import os
from dotenv import load_dotenv
import google.generativeai as genai
import aiohttp
from flask import Flask
from threading import Thread


# Configuración inicial
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Configurar Google AI
genai.configure(api_key=GOOGLE_API_KEY)

# Configuración de intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="¡", intents=intents)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.is_playing = False
        self.current_song = None
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'geo_bypass': True,
            'noplaylist': True,
            'extract_flat': True,
            'socket_timeout': 30,
            'retries': 10,
            'sleep_interval': 5,
            'default_search': 'auto',
            'source_address': '0.0.0.0',
            'cookiefile': 'cookies.txt',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.5'
            }
        }

    async def reproducir(self, ctx):
        if not self.queue:
            await ctx.send("📭 No hay canciones en la cola")
            self.is_playing = False
            self.current_song = None
            return

        url = self.queue.pop(0)
        
        try:
            with youtube_dl.YoutubeDL(self.ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        raise Exception("No se pudo obtener información del video")
                    
                    if 'entries' in info:
                        info = info['entries'][0]
                    
                    url2 = info.get('url')
                    if not url2:
                        # Intenta con un método alternativo
                        search_query = info.get('title', url)
                        info = ydl.extract_info(f"ytsearch:{search_query}", download=False)
                        if 'entries' in info:
                            info = info['entries'][0]
                        url2 = info.get('url')
                        if not url2:
                            raise Exception("No se pudo obtener la URL de audio")
                    
                    title = info.get('title', url)
                    duration = info.get('duration', 0)
                    self.current_song = {
                        'title': title,
                        'url': url,
                        'duration': duration,
                        'requested_by': ctx.author
                    }

                    voice = ctx.voice_client
                    if not voice:
                        await ctx.send("⚠️ No estoy conectado a un canal de voz")
                        return

                    self.is_playing = True
                    
                    ffmpeg_options = {
                        'options': '-vn -loglevel quiet',
                        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
                    }
                    
                    def after_playing(error):
                        if error:
                            print(f"Error en after_playing: {error}")
                        asyncio.run_coroutine_threadsafe(self.siguiente(ctx), self.bot.loop)
                    
                    voice.play(FFmpegPCMAudio(url2, **ffmpeg_options), after=after_playing)

                    embed = discord.Embed(title="🎵 Reproduciendo", color=discord.Color.blue())
                    embed.add_field(name="Título", value=title, inline=False)
                    if duration > 0:
                        minutes, seconds = divmod(duration, 60)
                        embed.add_field(name="Duración", value=f"{minutes}:{seconds:02d}", inline=True)
                    embed.add_field(name="Solicitado por", value=ctx.author.mention, inline=True)
                    embed.add_field(name="URL", value=f"[Link]({url})", inline=False)
                    
                    await ctx.send(embed=embed)

                except youtube_dl.utils.DownloadError as e:
                    if "Too Many Requests" in str(e):
                        await ctx.send("⚠️ YouTube ha bloqueado temporalmente nuestras solicitudes. Por favor, espera unos minutos.")
                    else:
                        await ctx.send(f"❌ Error al procesar el video: {str(e)}")
                    await self.siguiente(ctx)
                    
                except Exception as e:
                    await ctx.send(f"❌ Error al reproducir: {str(e)}. Reintentando con la siguiente canción...")
                    await self.siguiente(ctx)
                    
        except Exception as e:
            await ctx.send(f"❌ Error grave al procesar la canción: {str(e)}")
            await self.siguiente(ctx)

    async def siguiente(self, ctx):
        if self.queue:
            await self.reproducir(ctx)
        else:
            await ctx.send("📭 La cola está vacía")
            self.is_playing = False
            self.current_song = None

    @commands.command(aliases=['p'])
    async def play(self, ctx, *, query):
        """Reproduce música desde YouTube"""
        if not ctx.author.voice:
            return await ctx.send("🚨 Debes estar en un canal de voz")
            
        if not validators.url(query) and not query.startswith(('http://', 'https://')):
            query = f"ytsearch:{query}"
        
        try:
            with youtube_dl.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                
                if not info:
                    return await ctx.send("❌ No se pudo obtener información del video")
                
                if 'entries' in info:
                    entries = info['entries']
                    if not entries:
                        return await ctx.send("❌ No se encontraron resultados")
                        
                    if query.startswith('ytsearch:'):
                        entry = entries[0]
                        if not entry:
                            return await ctx.send("❌ No se encontró el video")
                            
                        self.queue.append(entry['url'])
                        await ctx.send(f"🎵 Añadido a la cola: {entry.get('title', entry['url'])}")
                    else:
                        added = 0
                        for entry in entries:
                            if entry:
                                self.queue.append(entry['url'])
                                added += 1
                        await ctx.send(f"🎵 Añadidas {added} canciones a la cola")
                else:
                    self.queue.append(info['url'])
                    await ctx.send(f"🎵 Añadido a la cola: {info.get('title', info['url'])}")
                
            if not ctx.voice_client:
                await ctx.author.voice.channel.connect()
                
            if not self.is_playing:
                await self.reproducir(ctx)
                
        except youtube_dl.utils.DownloadError as e:
            if "Too Many Requests" in str(e):
                await ctx.send("⚠️ YouTube ha bloqueado temporalmente nuestras solicitudes. Por favor, espera unos minutos.")
            else:
                await ctx.send(f"❌ Error de YouTube: {str(e)}")
        except Exception as e:
            await ctx.send(f"❌ Error inesperado: {str(e)}")

    @commands.command()
    async def skip(self, ctx):
        """Saltar la canción actual"""
        voice = ctx.voice_client
        if voice and (voice.is_playing() or voice.is_paused()):
            voice.stop()
            await ctx.send("⏭️ Canción saltada")
            await self.siguiente(ctx)
        else:
            await ctx.send("⚠️ No hay nada reproduciéndose")

    @commands.command()
    async def pause(self, ctx):
        """Pausar la música"""
        voice = ctx.voice_client
        if voice and voice.is_playing():
            voice.pause()
            await ctx.send("⏸️ Música pausada")
        else:
            await ctx.send("⚠️ No hay música reproduciéndose")

    @commands.command()
    async def continuar(self, ctx):
        """Reanudar la música"""
        voice = ctx.voice_client
        if voice and voice.is_paused():
            voice.resume()
            await ctx.send("▶️ Música reanudada")
        else:
            await ctx.send("⚠️ La música no está pausada")

    @commands.command()
    async def cola(self, ctx):
        """Mostrar la cola de reproducción"""
        if not self.queue and not self.current_song:
            await ctx.send("📭 La cola está vacía")
        else:
            embed = discord.Embed(title="🎶 Cola de reproducción", color=discord.Color.purple())
            
            if self.current_song:
                duration = ""
                if self.current_song['duration'] > 0:
                    mins, secs = divmod(self.current_song['duration'], 60)
                    duration = f" [{mins}:{secs:02d}]"
                
                embed.add_field(
                    name="🔊 Reproduciendo ahora",
                    value=f"**{self.current_song['title']}**{duration}\nSolicitado por: {self.current_song['requested_by'].mention}",
                    inline=False
                )
            
            if self.queue:
                for i, url in enumerate(self.queue[:10]):  # Mostrar solo las primeras 10
                    embed.add_field(name=f"{i+1}.", value=url, inline=False)
                
                if len(self.queue) > 10:
                    embed.set_footer(text=f"Y {len(self.queue)-10} canciones más en la cola...")
            
            await ctx.send(embed=embed)
            
    @commands.command()
    async def remover(self, ctx, posicion: int):
        """Remover una canción de la cola"""
        if 0 < posicion <= len(self.queue):
            removido = self.queue.pop(posicion - 1)
            await ctx.send(f"🗑️ Eliminado: {removido}")
        else:
            await ctx.send("❌ Posición inválida")

    @commands.command()
    async def ahora(self, ctx):
        """Muestra la canción que se está reproduciendo actualmente"""
        if self.current_song:
            duration = ""
            if self.current_song['duration'] > 0:
                mins, secs = divmod(self.current_song['duration'], 60)
                duration = f" [{mins}:{secs:02d}]"
            
            embed = discord.Embed(title="🎵 Reproduciendo ahora", color=discord.Color.green())
            embed.add_field(name="Título", value=self.current_song['title'], inline=False)
            embed.add_field(name="Duración", value=duration if duration else "Desconocida", inline=True)
            embed.add_field(name="Solicitado por", value=self.current_song['requested_by'].mention, inline=True)
            embed.add_field(name="URL", value=f"[Link]({self.current_song['url']})", inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send("⚠️ No hay ninguna canción reproduciéndose")
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
