import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
import yt_dlp as youtube_dl
import validators
import asyncio
import os
from dotenv import load_dotenv
import google.generativeai as genai
from keep_alive import keep_alive
import aiohttp

# Configuración inicial
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Configurar Google AI
genai.configure(api_key=GOOGLE_API_KEY)

# Configuración de intents
intents = discord.Intents.default()
intents.message_content = True

class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='¡',
            intents=intents,
            help_command=None
        )
    
    async def setup_hook(self):
        await self.add_cog(Music(self))
        await self.add_cog(UtilityCommands(self))
        print("✅ Extensiones cargadas")

bot = MusicBot()

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.is_playing = False
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'geo_bypass': True,
            'noplaylist': True,
            'extract_flat': True,
            'socket_timeout': 10,
            'default_search': 'auto',
            'source_address': '0.0.0.0',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        }

    async def reproducir(self, ctx):
        if not self.queue:
            await ctx.send("📭 No hay canciones en la cola")
            self.is_playing = False
            return

        url = self.queue.pop(0)
        
        try:
            with youtube_dl.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                
                url2 = info.get('url')
                if not url2:
                    raise Exception("No se pudo obtener la URL de audio")
                
                title = info.get('title', url)
                duration = info.get('duration', 0)

            voice = ctx.voice_client
            if not voice:
                await ctx.send("⚠️ No estoy conectado a un canal de voz")
                return

            self.is_playing = True
            
            ffmpeg_options = {
                'options': '-vn -loglevel quiet',
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
            }
            
            voice.play(FFmpegPCMAudio(url2, **ffmpeg_options),
                      after=lambda e: self.bot.loop.create_task(self.siguiente(ctx)))

            embed = discord.Embed(title="🎵 Reproduciendo", color=discord.Color.blue())
            embed.add_field(name="Título", value=title, inline=False)
            if duration > 0:
                minutes, seconds = divmod(duration, 60)
                embed.add_field(name="Duración", value=f"{minutes}:{seconds:02d}", inline=True)
            embed.add_field(name="URL", value=f"[Link]({url})", inline=False)
            
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ Error al reproducir: {str(e)}")
            await self.siguiente(ctx)

    async def siguiente(self, ctx):
        if self.queue:
            await self.reproducir(ctx)
        else:
            await ctx.send("📭 La cola está vacía")
            self.is_playing = False

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
                
                if 'entries' in info:
                    entries = info['entries']
                    if not entries:
                        return await ctx.send("❌ No se encontraron resultados")
                        
                    if query.startswith('ytsearch:'):
                        entry = entries[0]
                        self.queue.append(entry['url'])
                        await ctx.send(f"🎵 Añadido a la cola: {entry.get('title', entry['url'])}")
                    else:
                        for entry in entries:
                            if entry:
                                self.queue.append(entry['url'])
                        await ctx.send(f"🎵 Añadidas {len(entries)} canciones a la cola")
                else:
                    self.queue.append(info['url'])
                    await ctx.send(f"🎵 Añadido a la cola: {info.get('title', info['url'])}")
                
            if not ctx.voice_client:
                await ctx.author.voice.channel.connect()
                
            if not self.is_playing:
                await self.reproducir(ctx)
                
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")

    @commands.command()
    async def skip(self, ctx):
        """Saltar la canción actual"""
        voice = ctx.voice_client
        if voice and voice.is_playing():
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

    @commands.command()
    async def continuar(self, ctx):
        """Reanudar la música"""
        voice = ctx.voice_client
        if voice and voice.is_paused():
            voice.resume()
            await ctx.send("▶️ Música reanudada")

    @commands.command()
    async def cola(self, ctx):
        """Mostrar la cola de reproducción"""
        if not self.queue:
            await ctx.send("📭 La cola está vacía")
        else:
            embed = discord.Embed(title="🎶 Cola de reproducción", color=discord.Color.purple())
            for i, url in enumerate(self.queue):
                embed.add_field(name=f"{i+1}.", value=url, inline=False)
            await ctx.send(embed=embed)
            
    @commands.command()
    async def remover(self, ctx, posicion: int):
        """Remover una canción de la cola"""
        if 0 < posicion <= len(self.queue):
            removido = self.queue.pop(posicion - 1)
            await ctx.send(f"🗑️ Eliminado: {removido}")
        else:
            await ctx.send("❌ Posición inválida")

class UtilityCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    @commands.command()
    async def charla(self, ctx, *, mensaje):
        """Habla con la IA Gemini"""
        user_name = ctx.author.name
        
        try:
            if mensaje.lower() in ["¿cómo te llamas?", "¿quién eres?", "¿cuál es tu nombre?"]:
                return await ctx.send("¡Soy Archeon, el asistente del servidor! 😊")
                
            if mensaje.lower() in ["¿quién soy?", "¿cómo me llamo?", "¿me conoces?"]:
                return await ctx.send(f"¡Eres {user_name}! Claro que te conozco 😃")
                
            prompt = f"{user_name} ha dicho: {mensaje}. Responde de manera amigable y personalizada."
            respuesta = self.model.generate_content(prompt)
            await ctx.send(f'🤖 {respuesta.text}')
            
        except Exception as e:
            await ctx.send(f'❌ Error: {str(e)}')

    @commands.command()
    async def votar(self, ctx, pregunta: str, *opciones):
        """Crear una encuesta"""
        emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣']
        
        if len(opciones) < 2:
            return await ctx.send("❌ Necesitas al menos 2 opciones")
        if len(opciones) > 6:
            return await ctx.send("⚠️ Máximo 6 opciones")

        descripcion = "\n".join(f"{emojis[i]} {opcion}" for i, opcion in enumerate(opciones))
        
        embed = discord.Embed(
            title=f"📊 {pregunta}",
            description=descripcion,
            color=discord.Color.gold()
        )
        embed.set_footer(text="Vota reaccionando con los emojis")
        
        msg = await ctx.send(embed=embed)
        for i in range(len(opciones)):
            await msg.add_reaction(emojis[i])

    @commands.command()
    async def letra(self, ctx, *, cancion):
        """Obtener letra de canción"""
        try:
            artista, titulo = map(str.strip, cancion.split('-', 1))
        except ValueError:
            return await ctx.send("❌ Formato: artista - título")

        letra = await self.obtener_letra(artista, titulo)
        
        if not letra or "no encontrada" in letra.lower():
            return await ctx.send("😢 Letra no encontrada")

        for parte in [letra[i:i+1900] for i in range(0, len(letra), 1900)]:
            await ctx.send(f"🎤 {parte}")
            await asyncio.sleep(1)

    async def obtener_letra(self, artista, titulo):
        url = f"https://api.lyrics.ovh/v1/{artista}/{titulo}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as res:
                    if res.status == 200:
                        data = await res.json()
                        return data.get('lyrics', 'Letra no encontrada').strip()
                    return "Letra no encontrada"
        except Exception as e:
            return f"Error: {str(e)}"

    @commands.command(name="ayuda")
    async def ayuda(self, ctx):
        """Mostrar ayuda"""
        embed = discord.Embed(
            title="📖 Comandos disponibles",
            color=discord.Color.blurple()
        )
        
        embed.add_field(name="🎵 Música", value="""
`¡play [url/búsqueda]` - Reproduce música
`¡pause` - Pausa la música
`¡continuar` - Reanuda la música
`¡skip` - Salta la canción
`¡cola` - Muestra la cola
`¡remover [pos]` - Elimina una canción
""", inline=False)

        embed.add_field(name="🧠 Utilidades", value="""
`¡charla [mensaje]` - Habla con la IA
`¡votar [pregunta] [opciones]` - Crea encuesta
`¡letra artista - título` - Busca letra
""", inline=False)

        await ctx.send(embed=embed)

# Iniciar el bot
keep_alive()
bot.run(TOKEN)
