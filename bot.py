import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import os
from dotenv import load_dotenv
import google.generativeai as genai
import validators
import traceback
import logging
import subprocess

try:
    subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
except:
    print("⚠️ Advertencia: FFmpeg no está instalado correctamente")
    
logging.basicConfig(level=logging.WARNING) 
# Configuración inicial
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuración inicial
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
model = genai.GenerativeModel("gemini-2.0-flash")  # Definición global

chat_histories = {}
MAX_HISTORY = 10  

# Configuración de la IA
genai.configure(api_key=GOOGLE_API_KEY)

# Configuración del bot
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='¡', intents=intents)

# --------------------------
# Módulo de Música
# --------------------------

# Opciones para youtube_dl
ydl_opts = {
    'format': 'bestaudio/best',
    'default_search': 'ytsearch',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
    'extract_flat': False,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'opus',
        'preferredquality': '192',
    }],
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'nocheckcertificate': True,
    'source_address': '0.0.0.0'
}

# Variables de estado
queues = {}
current_song = None

async def check_queue(ctx):
    """Versión corregida como corrutina"""
    if queues.get(ctx.guild.id):
        next_song = queues[ctx.guild.id].pop(0)
        
        FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -loglevel warning',
            'options': '-vn -c:a libopus -b:a 128k -ar 48000 -ac 2 -filter:a "volume=0.8"',
            'executable': r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"
        }
        
        try:
            # Crea fuente de audio (await es crucial aquí)
            source = await discord.FFmpegOpusAudio.from_probe(
                next_song['url'],
                method='fallback',
                **FFMPEG_OPTIONS
            )
            
            # Actualizar canción actual
            global current_song
            current_song = next_song
            
            # Reproducir con manejo adecuado del callback
            ctx.voice_client.play(
                source,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    check_queue(ctx), 
                    bot.loop
                ) if not e else print(f'Error: {e}')
            )
            
            # Crear y enviar embed
            embed = discord.Embed(
                title="🎵 Reproduciendo ahora (desde cola)",
                description=f"[{current_song['title']}]({current_song['web_url']})",
                color=discord.Color.blurple()
            )
            
            if current_song['duration'] > 0:
                mins, secs = divmod(current_song['duration'], 60)
                embed.add_field(name="Duración", value=f"{mins}:{secs:02d}")
            
            embed.set_thumbnail(url=current_song['thumbnail'])
            embed.set_footer(text=f"Solicitado por {current_song['requested_by'].display_name}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"Error en check_queue: {e}")
            await ctx.send("⚠️ Error al pasar a la siguiente canción")

        
@bot.command(name='join', help='Hace que el bot se una al canal de voz')
async def join(ctx):
    if ctx.author.voice is None:
        await ctx.send("¡No estás en un canal de voz!")
        return
    
    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()
    else:
        await ctx.voice_client.move_to(channel)

@bot.command(name='play')
async def play(ctx, *, busqueda: str):
    if not ctx.author.voice:
        return await ctx.send("¡No estás en un canal de voz!")
    
    voice_client = ctx.voice_client or await ctx.author.voice.channel.connect()
    
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            # Extraer información del audio
            info = ydl.extract_info(
                busqueda if validators.url(busqueda) else f"ytsearch:{busqueda}",
                download=False
            )
            
            # Si es una búsqueda, tomar el primer resultado
            if 'entries' in info:
                info = info['entries'][0]
            
            # Obtener la URL de audio directamente
            if 'url' in info:
                url2 = info['url']
            else:
                # Buscar el mejor formato de audio
                format = next(
                    (f for f in info['formats'] 
                    if f.get('acodec') != 'none'),
                    info['formats'][0]
                )
                url2 = format['url']
            
            # Configuración de FFmpeg
            FFMPEG_OPTIONS = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -loglevel warning',
                'options': '-vn -c:a libopus -b:a 128k -ar 48000 -ac 2 -filter:a "volume=0.8"',
            }
            
            # Crear objeto canción completo para la cola
            song = {
                'title': info.get('title', busqueda),
                'url': url2,
                'web_url': info.get('webpage_url', busqueda),
                'duration': info.get('duration', 0),
                'requested_by': ctx.author,
                'thumbnail': info.get('thumbnail', '')
            }
            
            # Si ya hay música reproduciéndose, añadir a la cola
            if voice_client.is_playing() or voice_client.is_paused():
                if ctx.guild.id not in queues:
                    queues[ctx.guild.id] = []
                queues[ctx.guild.id].append(song)
                
                embed = discord.Embed(
                    title="🎵 Añadido a la cola",
                    description=f"[{song['title']}]({song['web_url']})",
                    color=discord.Color.green()
                )
                embed.add_field(name="Posición en cola", value=str(len(queues[ctx.guild.id])))
                embed.set_thumbnail(url=song['thumbnail'])
                embed.set_footer(text=f"Solicitado por {ctx.author.display_name}")
                return await ctx.send(embed=embed)
            
            # Si no hay música reproduciéndose, crear fuente y reproducir
            source = await discord.FFmpegOpusAudio.from_probe(
                url2,
                method='fallback',
                **FFMPEG_OPTIONS
            )
            
            # Actualizar estado global
            global current_song
            current_song = song
            
            # Reproducir
            voice_client.play(
                source, 
                after=lambda e: print(f'Error: {e}') if e else check_queue(ctx)
            )
            
            # Mostrar embed
            embed = discord.Embed(
                title="🎵 Reproduciendo ahora",
                description=f"[{current_song['title']}]({current_song['web_url']})",
                color=discord.Color.blurple()
            )
            duration = current_song['duration']
            embed.add_field(name="Duración", value=f"{duration//60}:{duration%60:02d}" if duration else "Desconocida")
            embed.set_thumbnail(url=current_song['thumbnail'])
            embed.set_footer(text=f"Solicitado por {ctx.author.display_name}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            error_msg = f"❌ Error al reproducir: {str(e)}"
            if "formats" in str(e):
                error_msg += "\n⚠️ Problema al obtener formatos de audio. Intenta con otro video."
            await ctx.send(error_msg[:2000])
            import traceback
            traceback.print_exc()
            
@bot.command(name='skip')
async def skip(ctx):
    """Versión corregida del comando skip"""
    voice = ctx.voice_client
    if voice and voice.is_playing():
        voice.stop()
        await ctx.send("⏭️ Canción saltada")
        await check_queue(ctx) # Llama a check_queue para la siguiente canción

    else:
        await ctx.send("⚠️ No hay nada reproduciéndose")
    
@bot.command(name='pause')
async def pause(ctx):
    """Pausar la música"""
    voice = ctx.voice_client
    if voice and voice.is_playing():
        voice.pause()
        await ctx.send("⏸️ Música pausada")
    else:
        await ctx.send("⚠️ No hay música reproduciéndose")

@bot.command(name='resume')
async def resume(ctx):
    """Reanudar la música"""
    voice = ctx.voice_client
    if voice and voice.is_paused():
        voice.resume()
        await ctx.send("▶️ Música reanudada")
    else:
        await ctx.send("⚠️ La música no está pausada")

@bot.command(name='lista')
async def queue(ctx):
    """Mostrar la cola de reproducción"""
    guild_id = ctx.guild.id
    if not queues.get(guild_id) and not current_song:
        await ctx.send("📭 La cola está vacía")
    else:
        embed = discord.Embed(title="🎶 Cola de reproducción", color=discord.Color.purple())
        
        if current_song:
            duration = ""
            if current_song['duration'] > 0:
                mins, secs = divmod(current_song['duration'], 60)
                duration = f" [{mins}:{secs:02d}]"
            
            embed.add_field(
                name="🔊 Reproduciendo ahora",
                value=f"**{current_song['title']}**{duration}\nSolicitado por: {current_song['requested_by'].mention}",
                inline=False
            )
        
        if queues.get(guild_id):
            for i, item in enumerate(queues[guild_id][:10]):
                embed.add_field(name=f"{i+1}.", value=item['title'], inline=False)
            
            if len(queues[guild_id]) > 10:
                embed.set_footer(text=f"Y {len(queues[guild_id])-10} canciones más en la cola...")
        
        await ctx.send(embed=embed)

@bot.command(name='disconnect')
async def disconnect(ctx):
    """Desconecta al bot del canal de voz"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Desconectado del canal de voz")
    else:
        await ctx.send("No estoy conectado a ningún canal de voz")

# --------------------------
# Módulo de IA 
# --------------------------

@bot.command()  
async def charla(ctx, *, mensaje: str):
    """Interactúa con la IA de Google Gemini con memoria contextual mejorada."""
    user_id = str(ctx.author.id)
    
    # Respuestas rápidas
    quick_responses = {
        "¿cómo te llamas?": "🤖 ¡Soy Archeon, tu asistente de Discord! ✨",
        "¿quién eres?": "🤖 ¡Soy Archeon, tu asistente de Discord! ✨",
        "¿cuál es tu nombre?": "🤖 ¡Soy Archeon, tu asistente de Discord! ✨",
        "¿quién soy?": f"🤖 ¡Claro que te conozco, {ctx.author.mention}! Eres {ctx.author.name} 😊",
        "¿cómo me llamo?": f"🤖 ¡Claro que te conozco, {ctx.author.mention}! Eres {ctx.author.name} 😊",
        "¿me conoces?": f"🤖 ¡Claro que te conozco, {ctx.author.mention}! Eres {ctx.author.name} 😊"
    }
    
    lower_msg = mensaje.lower().strip()
    if lower_msg in quick_responses:
        return await ctx.send(quick_responses[lower_msg])

    try:
        # Inicializar historial si es nuevo usuario
        if user_id not in chat_histories:
            chat_histories[user_id] = []
                
        # Construir contexto
        context = {
            "historial": "\n".join(chat_histories[user_id][-MAX_HISTORY:]),
            "nuevo_mensaje": mensaje,
            "usuario": ctx.author.name
        }
        
        prompt = (
            "Eres un asistente de Discord llamado Archeon. "
            "Aquí está el historial de conversación reciente:\n"
            "{historial}\n\n"
            "Nuevo mensaje de {usuario}: {nuevo_mensaje}\n\n"
            "Responde de manera concisa y amigable."
        ).format(**context)
        
        # Generar respuesta
        response = model.generate_content(prompt)
        respuesta = response.text.strip()
        
        # Actualizar historial
        chat_histories[user_id].extend([
            f"{ctx.author.name}: {mensaje}",
            f"Archeon: {respuesta}"
        ])
        chat_histories[user_id] = chat_histories[user_id][-MAX_HISTORY:]
        
        # Enviar respuesta
        await ctx.send(f"{ctx.author.mention} {respuesta}")
        
    except genai.errors.GoogleAPIError as api_error:
        await ctx.send("🔴 Error con la API de Google. Por favor, reporta esto al administrador.")
        logger.error(f"Google API Error: {api_error}")
        
    except asyncio.TimeoutError:
        await ctx.send("⏱️ La IA tardó demasiado en responder. Intenta nuevamente.")
        
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)
        await ctx.send("⚠️ Ocurrió un error inesperado. Por favor, intenta nuevamente más tarde.")
        
        
@bot.command()
async def olvidar(ctx):
    """Reinicia el historial de conversación contigo"""
    user_id = str(ctx.author.id)
    if user_id in chat_histories:
        chat_histories[user_id] = []
    await ctx.send("🔄 ¡He reiniciado nuestra conversación! ¿En qué puedo ayudarte ahora?")
        
# ------------------------------------------
# Módulo de IA para separar por llamadas
# ------------------------------------------

@bot.command(name='separar', aliases=['gamevoice'])
async def separar_jugadores(ctx):
    """Separa a los usuarios en canales de voz según el juego que están jugando"""
    try:
        # Verificar que el comando se ejecuta en un servidor
        if not ctx.guild:
            await ctx.send("❌ Este comando solo funciona en servidores.")
            return

        # Verificar que el usuario está en un canal de voz
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ Debes estar en un canal de voz para usar este comando.")
            return

        voice_channel = ctx.author.voice.channel
        members = voice_channel.members

        # Obtener los juegos activos entre los miembros
        juegos_activos = {}
        for member in members:
            if member.activity and member.activity.type == discord.ActivityType.playing:
                juego = member.activity.name
                if juego not in juegos_activos:
                    juegos_activos[juego] = []
                juegos_activos[juego].append(member)

        # Si no hay suficientes juegos diferentes
        if len(juegos_activos) < 2:
            await ctx.send("🔍 No hay suficientes juegos diferentes para separar (se necesitan al menos 2).")
            return

        # Consultar a la IA para nombres creativos de canales
        prompt = (
            f"Dame nombres creativos para canales de Discord basados en estos juegos: {', '.join(juegos_activos.keys())}. "
            "Los nombres deben ser cortos, relevantes al juego y entre 3-5 palabras. "
            "Formato: Juego: Nombre sugerido (uno por juego)"
        )

        try:
            response = model.generate_content(prompt)
            nombres_canales = {}
            
            # Parsear la respuesta de la IA
            for line in response.text.split('\n'):
                if ':' in line:
                    juego, nombre = line.split(':', 1)
                    juego = juego.strip()
                    nombre = nombre.strip()
                    if juego in juegos_activos:
                        nombres_canales[juego] = nombre
        except Exception as e:
            logging.error(f"Error al generar nombres con IA: {str(e)}")
            # Usar nombres por defecto si falla la IA
            nombres_canales = {juego: f"🎮 {juego}" for juego in juegos_activos}

        # Crear categoría temporal si no existe
        categoria = discord.utils.get(ctx.guild.categories, name="Juegos Temporales")
        if not categoria:
            categoria = await ctx.guild.create_category_channel("Juegos Temporales")

        # Crear canales de voz temporales
        canales_creados = {}
        for juego, nombre in nombres_canales.items():
            try:
                # Limitar longitud del nombre a 100 caracteres (límite de Discord)
                nombre_canal = nombre[:100]
                new_channel = await ctx.guild.create_voice_channel(
                    name=nombre_canal,
                    category=categoria,
                    reason=f"Separación automática por juego: {juego}"
                )
                canales_creados[juego] = new_channel
            except Exception as e:
                logging.error(f"Error al crear canal para {juego}: {str(e)}")
                continue

        # Mover usuarios a los canales correspondientes
        movimientos = {}
        for juego, miembros in juegos_activos.items():
            if juego in canales_creados:
                canal_destino = canales_creados[juego]
                for miembro in miembros:
                    try:
                        await miembro.move_to(canal_destino)
                        if juego not in movimientos:
                            movimientos[juego] = 0
                        movimientos[juego] += 1
                    except Exception as e:
                        logging.error(f"Error al mover {miembro.display_name}: {str(e)}")

        # Enviar resumen
        resumen = "✅ Separación completada:\n"
        for juego, count in movimientos.items():
            resumen += f"- {juego}: {count} jugadores movidos a {canales_creados[juego].mention}\n"

        await ctx.send(resumen)

        # Programar eliminación de canales después de inactividad
        await asyncio.sleep(300)  # Esperar 5 minutos

        # Verificar si los canales están vacíos
        for juego, canal in canales_creados.items():
            if len(canal.members) == 0:
                try:
                    await canal.delete(reason="Canal temporal de juego vacío")
                except Exception as e:
                    logging.error(f"Error al eliminar canal {canal.name}: {str(e)}")

    except Exception as e:
        logging.error(f"Error en comando separar: {str(e)}\n{traceback.format_exc()}")
        await ctx.send("❌ Ocurrió un error al procesar el comando. Por favor intenta nuevamente.")

# --------------------------
# Utilidades
# --------------------------

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

#---------------
# utilidades
# ---------------
@bot.command(name="ayuda")
async def mostrar_ayuda(ctx):
    """Mostrar un menú con los comandos disponibles."""
    prefix = "¡"

    embed = discord.Embed(
        title="📖 Comandos disponibles",
        description="Aquí tienes una lista completa de comandos:",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🎵 Música",
        value=(
            f"`{prefix}play [url/búsqueda]` - Reproduce música\n"
            f"`{prefix}pause` - Pausa la música\n"
            f"`{prefix}resume` - Reanuda\n"
            f"`{prefix}skip` - Salta la canción\n"
            f"`{prefix}lista` - Muestra la cola\n"
            f"`{prefix}disconnect` - Desconecta al bot"
        ),
        inline=False
    )

    embed.add_field(
        name="🧠 IA",
        value=(
            f"`{prefix}charla [mensaje]` - Chatea con la IA\n"
            f"`{prefix}olvidar` - Reinicia la conversación"
        ),
        inline=False
    )

    embed.add_field(
        name="🎮 Juegos",
        value=(
            f"`{prefix}separar` o `{prefix}gamevoice`\n"
            "Separa jugadores por juego"
        ),
        inline=False
    )

    embed.add_field(
        name="📊 Utilidades",
        value=(
            f"`{prefix}votar \"pregunta\" op1 op2`\n"
            "Crea encuestas (usa comillas)"
        ),
        inline=False
    )

    embed.set_footer(text=f"Prefijo: '{prefix}' • Usa comillas para frases largas")
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user.name}')
    await bot.change_presence(activity=discord.Game(name="¡ayuda para comandos"))
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    logger.error(f'Error en comando {ctx.command}: {error}')
    await ctx.send(f'⚠️ Ocurrió un error: {str(error)}')
@bot.event
async def on_ready():
    await bot.tree.sync()  
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import os
from dotenv import load_dotenv
import google.generativeai as genai
import validators
import traceback
import logging
import subprocess

try:
    subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
except:
    print("⚠️ Advertencia: FFmpeg no está instalado correctamente")
    
logging.basicConfig(level=logging.WARNING) 
# Configuración inicial
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuración inicial
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
model = genai.GenerativeModel("gemini-2.0-flash")  # Definición global

chat_histories = {}
MAX_HISTORY = 10  

# Configuración de la IA
genai.configure(api_key=GOOGLE_API_KEY)

# Configuración del bot
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='¡', intents=intents)

# --------------------------
# Módulo de Música
# --------------------------

# Opciones para youtube_dl
ydl_opts = {
    'format': 'bestaudio/best',
    'default_search': 'ytsearch',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
    'extract_flat': False,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'opus',
        'preferredquality': '192',
    }],
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'nocheckcertificate': True,
    'source_address': '0.0.0.0'
}

# Variables de estado
queues = {}
current_song = None

async def check_queue(ctx):
    """Versión corregida como corrutina"""
    if queues.get(ctx.guild.id):
        next_song = queues[ctx.guild.id].pop(0)
        
        FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -loglevel warning',
            'options': '-vn -c:a libopus -b:a 128k -ar 48000 -ac 2 -filter:a "volume=0.8"',
            'executable': r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"
        }
        
        try:
            # Crea fuente de audio (await es crucial aquí)
            source = await discord.FFmpegOpusAudio.from_probe(
                next_song['url'],
                method='fallback',
                **FFMPEG_OPTIONS
            )
            
            # Actualizar canción actual
            global current_song
            current_song = next_song
            
            # Reproducir con manejo adecuado del callback
            ctx.voice_client.play(
                source,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    check_queue(ctx), 
                    bot.loop
                ) if not e else print(f'Error: {e}')
            )
            
            # Crear y enviar embed
            embed = discord.Embed(
                title="🎵 Reproduciendo ahora (desde cola)",
                description=f"[{current_song['title']}]({current_song['web_url']})",
                color=discord.Color.blurple()
            )
            
            if current_song['duration'] > 0:
                mins, secs = divmod(current_song['duration'], 60)
                embed.add_field(name="Duración", value=f"{mins}:{secs:02d}")
            
            embed.set_thumbnail(url=current_song['thumbnail'])
            embed.set_footer(text=f"Solicitado por {current_song['requested_by'].display_name}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"Error en check_queue: {e}")
            await ctx.send("⚠️ Error al pasar a la siguiente canción")

        
@bot.command(name='join', help='Hace que el bot se una al canal de voz')
async def join(ctx):
    if ctx.author.voice is None:
        await ctx.send("¡No estás en un canal de voz!")
        return
    
    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()
    else:
        await ctx.voice_client.move_to(channel)

@bot.command(name='play')
async def play(ctx, *, busqueda: str):
    if not ctx.author.voice:
        return await ctx.send("¡No estás en un canal de voz!")
    
    voice_client = ctx.voice_client or await ctx.author.voice.channel.connect()
    
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            # Extraer información del audio
            info = ydl.extract_info(
                busqueda if validators.url(busqueda) else f"ytsearch:{busqueda}",
                download=False
            )
            
            # Si es una búsqueda, tomar el primer resultado
            if 'entries' in info:
                info = info['entries'][0]
            
            # Obtener la URL de audio directamente
            if 'url' in info:
                url2 = info['url']
            else:
                # Buscar el mejor formato de audio
                format = next(
                    (f for f in info['formats'] 
                    if f.get('acodec') != 'none'),
                    info['formats'][0]
                )
                url2 = format['url']
            
            # Configuración de FFmpeg
            FFMPEG_OPTIONS = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -loglevel warning',
                'options': '-vn -c:a libopus -b:a 128k -ar 48000 -ac 2 -filter:a "volume=0.8"',
            }
            
            # Crear objeto canción completo para la cola
            song = {
                'title': info.get('title', busqueda),
                'url': url2,
                'web_url': info.get('webpage_url', busqueda),
                'duration': info.get('duration', 0),
                'requested_by': ctx.author,
                'thumbnail': info.get('thumbnail', '')
            }
            
            # Si ya hay música reproduciéndose, añadir a la cola
            if voice_client.is_playing() or voice_client.is_paused():
                if ctx.guild.id not in queues:
                    queues[ctx.guild.id] = []
                queues[ctx.guild.id].append(song)
                
                embed = discord.Embed(
                    title="🎵 Añadido a la cola",
                    description=f"[{song['title']}]({song['web_url']})",
                    color=discord.Color.green()
                )
                embed.add_field(name="Posición en cola", value=str(len(queues[ctx.guild.id])))
                embed.set_thumbnail(url=song['thumbnail'])
                embed.set_footer(text=f"Solicitado por {ctx.author.display_name}")
                return await ctx.send(embed=embed)
            
            # Si no hay música reproduciéndose, crear fuente y reproducir
            source = await discord.FFmpegOpusAudio.from_probe(
                url2,
                method='fallback',
                **FFMPEG_OPTIONS
            )
            
            # Actualizar estado global
            global current_song
            current_song = song
            
            # Reproducir
            voice_client.play(
                source, 
                after=lambda e: print(f'Error: {e}') if e else check_queue(ctx)
            )
            
            # Mostrar embed
            embed = discord.Embed(
                title="🎵 Reproduciendo ahora",
                description=f"[{current_song['title']}]({current_song['web_url']})",
                color=discord.Color.blurple()
            )
            duration = current_song['duration']
            embed.add_field(name="Duración", value=f"{duration//60}:{duration%60:02d}" if duration else "Desconocida")
            embed.set_thumbnail(url=current_song['thumbnail'])
            embed.set_footer(text=f"Solicitado por {ctx.author.display_name}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            error_msg = f"❌ Error al reproducir: {str(e)}"
            if "formats" in str(e):
                error_msg += "\n⚠️ Problema al obtener formatos de audio. Intenta con otro video."
            await ctx.send(error_msg[:2000])
            import traceback
            traceback.print_exc()
            
@bot.command(name='skip')
async def skip(ctx):
    """Versión corregida del comando skip"""
    voice = ctx.voice_client
    if voice and voice.is_playing():
        voice.stop()
        await ctx.send("⏭️ Canción saltada")
        await check_queue(ctx) # Llama a check_queue para la siguiente canción

    else:
        await ctx.send("⚠️ No hay nada reproduciéndose")
    
@bot.command(name='pause')
async def pause(ctx):
    """Pausar la música"""
    voice = ctx.voice_client
    if voice and voice.is_playing():
        voice.pause()
        await ctx.send("⏸️ Música pausada")
    else:
        await ctx.send("⚠️ No hay música reproduciéndose")

@bot.command(name='resume')
async def resume(ctx):
    """Reanudar la música"""
    voice = ctx.voice_client
    if voice and voice.is_paused():
        voice.resume()
        await ctx.send("▶️ Música reanudada")
    else:
        await ctx.send("⚠️ La música no está pausada")

@bot.command(name='lista')
async def queue(ctx):
    """Mostrar la cola de reproducción"""
    guild_id = ctx.guild.id
    if not queues.get(guild_id) and not current_song:
        await ctx.send("📭 La cola está vacía")
    else:
        embed = discord.Embed(title="🎶 Cola de reproducción", color=discord.Color.purple())
        
        if current_song:
            duration = ""
            if current_song['duration'] > 0:
                mins, secs = divmod(current_song['duration'], 60)
                duration = f" [{mins}:{secs:02d}]"
            
            embed.add_field(
                name="🔊 Reproduciendo ahora",
                value=f"**{current_song['title']}**{duration}\nSolicitado por: {current_song['requested_by'].mention}",
                inline=False
            )
        
        if queues.get(guild_id):
            for i, item in enumerate(queues[guild_id][:10]):
                embed.add_field(name=f"{i+1}.", value=item['title'], inline=False)
            
            if len(queues[guild_id]) > 10:
                embed.set_footer(text=f"Y {len(queues[guild_id])-10} canciones más en la cola...")
        
        await ctx.send(embed=embed)

@bot.command(name='disconnect')
async def disconnect(ctx):
    """Desconecta al bot del canal de voz"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Desconectado del canal de voz")
    else:
        await ctx.send("No estoy conectado a ningún canal de voz")

# --------------------------
# Módulo de IA 
# --------------------------

@bot.command()  
async def charla(ctx, *, mensaje: str):
    """Interactúa con la IA de Google Gemini con memoria contextual mejorada."""
    user_id = str(ctx.author.id)
    
    # Respuestas rápidas
    quick_responses = {
        "¿cómo te llamas?": "🤖 ¡Soy Archeon, tu asistente de Discord! ✨",
        "¿quién eres?": "🤖 ¡Soy Archeon, tu asistente de Discord! ✨",
        "¿cuál es tu nombre?": "🤖 ¡Soy Archeon, tu asistente de Discord! ✨",
        "¿quién soy?": f"🤖 ¡Claro que te conozco, {ctx.author.mention}! Eres {ctx.author.name} 😊",
        "¿cómo me llamo?": f"🤖 ¡Claro que te conozco, {ctx.author.mention}! Eres {ctx.author.name} 😊",
        "¿me conoces?": f"🤖 ¡Claro que te conozco, {ctx.author.mention}! Eres {ctx.author.name} 😊"
    }
    
    lower_msg = mensaje.lower().strip()
    if lower_msg in quick_responses:
        return await ctx.send(quick_responses[lower_msg])

    try:
        # Inicializar historial si es nuevo usuario
        if user_id not in chat_histories:
            chat_histories[user_id] = []
                
        # Construir contexto
        context = {
            "historial": "\n".join(chat_histories[user_id][-MAX_HISTORY:]),
            "nuevo_mensaje": mensaje,
            "usuario": ctx.author.name
        }
        
        prompt = (
            "Eres un asistente de Discord llamado Archeon. "
            "Aquí está el historial de conversación reciente:\n"
            "{historial}\n\n"
            "Nuevo mensaje de {usuario}: {nuevo_mensaje}\n\n"
            "Responde de manera concisa y amigable."
        ).format(**context)
        
        # Generar respuesta
        response = model.generate_content(prompt)
        respuesta = response.text.strip()
        
        # Actualizar historial
        chat_histories[user_id].extend([
            f"{ctx.author.name}: {mensaje}",
            f"Archeon: {respuesta}"
        ])
        chat_histories[user_id] = chat_histories[user_id][-MAX_HISTORY:]
        
        # Enviar respuesta
        await ctx.send(f"{ctx.author.mention} {respuesta}")
        
    except genai.errors.GoogleAPIError as api_error:
        await ctx.send("🔴 Error con la API de Google. Por favor, reporta esto al administrador.")
        logger.error(f"Google API Error: {api_error}")
        
    except asyncio.TimeoutError:
        await ctx.send("⏱️ La IA tardó demasiado en responder. Intenta nuevamente.")
        
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)
        await ctx.send("⚠️ Ocurrió un error inesperado. Por favor, intenta nuevamente más tarde.")
        
        
@bot.command()
async def olvidar(ctx):
    """Reinicia el historial de conversación contigo"""
    user_id = str(ctx.author.id)
    if user_id in chat_histories:
        chat_histories[user_id] = []
    await ctx.send("🔄 ¡He reiniciado nuestra conversación! ¿En qué puedo ayudarte ahora?")
        
# ------------------------------------------
# Módulo de IA para separar por llamadas
# ------------------------------------------

@bot.command(name='separar', aliases=['gamevoice'])
async def separar_jugadores(ctx):
    """Separa a los usuarios en canales de voz según el juego que están jugando"""
    try:
        # Verificar que el comando se ejecuta en un servidor
        if not ctx.guild:
            await ctx.send("❌ Este comando solo funciona en servidores.")
            return

        # Verificar que el usuario está en un canal de voz
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ Debes estar en un canal de voz para usar este comando.")
            return

        voice_channel = ctx.author.voice.channel
        members = voice_channel.members

        # Obtener los juegos activos entre los miembros
        juegos_activos = {}
        for member in members:
            if member.activity and member.activity.type == discord.ActivityType.playing:
                juego = member.activity.name
                if juego not in juegos_activos:
                    juegos_activos[juego] = []
                juegos_activos[juego].append(member)

        # Si no hay suficientes juegos diferentes
        if len(juegos_activos) < 2:
            await ctx.send("🔍 No hay suficientes juegos diferentes para separar (se necesitan al menos 2).")
            return

        # Consultar a la IA para nombres creativos de canales
        prompt = (
            f"Dame nombres creativos para canales de Discord basados en estos juegos: {', '.join(juegos_activos.keys())}. "
            "Los nombres deben ser cortos, relevantes al juego y entre 3-5 palabras. "
            "Formato: Juego: Nombre sugerido (uno por juego)"
        )

        try:
            response = model.generate_content(prompt)
            nombres_canales = {}
            
            # Parsear la respuesta de la IA
            for line in response.text.split('\n'):
                if ':' in line:
                    juego, nombre = line.split(':', 1)
                    juego = juego.strip()
                    nombre = nombre.strip()
                    if juego in juegos_activos:
                        nombres_canales[juego] = nombre
        except Exception as e:
            logging.error(f"Error al generar nombres con IA: {str(e)}")
            # Usar nombres por defecto si falla la IA
            nombres_canales = {juego: f"🎮 {juego}" for juego in juegos_activos}

        # Crear categoría temporal si no existe
        categoria = discord.utils.get(ctx.guild.categories, name="Juegos Temporales")
        if not categoria:
            categoria = await ctx.guild.create_category_channel("Juegos Temporales")

        # Crear canales de voz temporales
        canales_creados = {}
        for juego, nombre in nombres_canales.items():
            try:
                # Limitar longitud del nombre a 100 caracteres (límite de Discord)
                nombre_canal = nombre[:100]
                new_channel = await ctx.guild.create_voice_channel(
                    name=nombre_canal,
                    category=categoria,
                    reason=f"Separación automática por juego: {juego}"
                )
                canales_creados[juego] = new_channel
            except Exception as e:
                logging.error(f"Error al crear canal para {juego}: {str(e)}")
                continue

        # Mover usuarios a los canales correspondientes
        movimientos = {}
        for juego, miembros in juegos_activos.items():
            if juego in canales_creados:
                canal_destino = canales_creados[juego]
                for miembro in miembros:
                    try:
                        await miembro.move_to(canal_destino)
                        if juego not in movimientos:
                            movimientos[juego] = 0
                        movimientos[juego] += 1
                    except Exception as e:
                        logging.error(f"Error al mover {miembro.display_name}: {str(e)}")

        # Enviar resumen
        resumen = "✅ Separación completada:\n"
        for juego, count in movimientos.items():
            resumen += f"- {juego}: {count} jugadores movidos a {canales_creados[juego].mention}\n"

        await ctx.send(resumen)

        # Programar eliminación de canales después de inactividad
        await asyncio.sleep(300)  # Esperar 5 minutos

        # Verificar si los canales están vacíos
        for juego, canal in canales_creados.items():
            if len(canal.members) == 0:
                try:
                    await canal.delete(reason="Canal temporal de juego vacío")
                except Exception as e:
                    logging.error(f"Error al eliminar canal {canal.name}: {str(e)}")

    except Exception as e:
        logging.error(f"Error en comando separar: {str(e)}\n{traceback.format_exc()}")
        await ctx.send("❌ Ocurrió un error al procesar el comando. Por favor intenta nuevamente.")

# --------------------------
# Utilidades
# --------------------------

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

#---------------
# utilidades
# ---------------
@bot.command(name="ayuda")
async def mostrar_ayuda(ctx):
    """Mostrar un menú con los comandos disponibles."""
    prefix = "¡"

    embed = discord.Embed(
        title="📖 Comandos disponibles",
        description="Aquí tienes una lista completa de comandos:",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🎵 Música",
        value=(
            f"`{prefix}play [url/búsqueda]` - Reproduce música\n"
            f"`{prefix}pause` - Pausa la música\n"
            f"`{prefix}resume` - Reanuda\n"
            f"`{prefix}skip` - Salta la canción\n"
            f"`{prefix}lista` - Muestra la cola\n"
            f"`{prefix}disconnect` - Desconecta al bot"
        ),
        inline=False
    )

    embed.add_field(
        name="🧠 IA",
        value=(
            f"`{prefix}charla [mensaje]` - Chatea con la IA\n"
            f"`{prefix}olvidar` - Reinicia la conversación"
        ),
        inline=False
    )

    embed.add_field(
        name="🎮 Juegos",
        value=(
            f"`{prefix}separar` o `{prefix}gamevoice`\n"
            "Separa jugadores por juego"
        ),
        inline=False
    )

    embed.add_field(
        name="📊 Utilidades",
        value=(
            f"`{prefix}votar \"pregunta\" op1 op2`\n"
            "Crea encuestas (usa comillas)"
        ),
        inline=False
    )

    embed.set_footer(text=f"Prefijo: '{prefix}' • Usa comillas para frases largas")
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user.name}')
    await bot.change_presence(activity=discord.Game(name="¡ayuda para comandos"))
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    logger.error(f'Error en comando {ctx.command}: {error}')
    await ctx.send(f'⚠️ Ocurrió un error: {str(error)}')
@bot.event
async def on_ready():
    await bot.tree.sync()  
    bot.run(TOKEN)
