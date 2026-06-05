import asyncio
from functools import wraps

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters
)

from telethon import TelegramClient

from config import (
    BOT_TOKEN,
    API_ID,
    API_HASH,
    ADMIN_ID,
    TV_PATH,
    MOVIES_PATH,
    validar_config
)

from downloader.series import (
    descargar_serie,
    obtener_temporadas
)

from downloader.indexer import indexar_peliculas
from downloader.movies import descargar_pelicula
from downloader.utils import verificar_ffmpeg, nombre_pelicula_destino
from downloader.tracker import tracker

from database import (
    search_peliculas,
    list_peliculas,
    count_peliculas,
    init_db
)

LIST_PAGE_SIZE = 30

validar_config()
init_db()

GRUPO, SERIE, TEMP, INDEX = range(4)

telethon_client = TelegramClient(
    "user_session",
    API_ID,
    API_HASH
)


async def iniciar_telethon():
    if not telethon_client.is_connected():
        await telethon_client.start()


def autorizado(user_id):
    return user_id == ADMIN_ID


def solo_admin(handler):
    @wraps(handler)
    async def wrapper(update: Update, context):
        if not autorizado(update.effective_user.id):
            return ConversationHandler.END
        return await handler(update, context)
    return wrapper


async def post_init(application):
    await verificar_ffmpeg()
    print("✅ ffmpeg disponible")


async def start(update: Update, context):
    if not autorizado(update.effective_user.id):
        return

    await update.message.reply_text(
        """
🎬 MediaBot

Series (1 grupo = 1 serie):
/download_series — Descargar episodios

Películas (grupos con muchas pelis):
/index_movies — Indexar grupo de películas
/list — Ver películas indexadas
/list 2 — Página 2 de la lista
/search nombre — Buscar película indexada
/download N — Descargar resultado #N
/downloads — Ver cola y progreso

Utilidades:
/status — Estado del bot
/groups — Listar chats
/paths — Rutas de medios
/cancel — Cancelar operación

Primera vez: ejecuta login.py para la sesión Telethon.
"""
    )


@solo_admin
async def status(update: Update, context):
    await update.message.reply_text("🟢 Activo")


@solo_admin
async def paths(update: Update, context):
    await update.message.reply_text(
        f"""
📁 Rutas

TV:
{TV_PATH}

Movies:
{MOVIES_PATH}
"""
    )


@solo_admin
async def groups(update: Update, context):
    await iniciar_telethon()

    dialogs = await telethon_client.get_dialogs()

    texto = "📺 Grupos\n\n"

    for i, d in enumerate(dialogs):
        texto += f"{i}. {d.name}\n"

    await update.message.reply_text(texto[:4000])


# =====================================
# SERIES
# =====================================

@solo_admin
async def download_series(update: Update, context):
    await iniciar_telethon()

    dialogs = await telethon_client.get_dialogs()

    grupos = []
    texto = "Selecciona el grupo de la serie:\n\n"

    for i, d in enumerate(dialogs):
        texto += f"{i}. {d.name}\n"
        grupos.append(d)

    context.user_data["grupos"] = grupos

    await update.message.reply_text(texto[:4000])
    return GRUPO


@solo_admin
async def set_group(update: Update, context):
    try:
        idx = int(update.message.text)
        grupos = context.user_data.get("grupos", [])

        if idx < 0 or idx >= len(grupos):
            raise ValueError("índice fuera de rango")

        grupo = grupos[idx]
        context.user_data["grupo"] = grupo

        await update.message.reply_text(
            f"Grupo: {grupo.name}\n\n"
            "📝 Escribe el nombre de la carpeta de la serie:"
        )

        return SERIE

    except (ValueError, KeyError):
        await update.message.reply_text("❌ Número inválido")
        return GRUPO


@solo_admin
async def set_serie(update: Update, context):
    nombre = update.message.text.strip()
    grupo = context.user_data["grupo"]

    context.user_data["serie"] = nombre

    await update.message.reply_text("🔍 Buscando temporadas en el grupo...")

    temps = await obtener_temporadas(telethon_client, grupo)

    if not temps:
        await update.message.reply_text(
            "❌ No encontré episodios en ese grupo."
        )
        return ConversationHandler.END

    context.user_data["temps"] = temps

    texto = "📺 Temporadas encontradas\n\n"

    for t in temps:
        texto += f"{t}. Season {t:02d}\n"

    texto += """

A = Todas

E:1,2
Excluir temporadas

1,3
Sólo descargar esas
"""

    await update.message.reply_text(texto)
    return TEMP


@solo_admin
async def set_temp(update: Update, context):
    try:
        valor = update.message.text.upper().strip()
        disponibles = context.user_data["temps"]

        if valor == "A":
            seleccion = disponibles

        elif valor.startswith("E:"):
            excluir = [
                int(x.strip())
                for x in valor[2:].split(",")
                if x.strip()
            ]
            seleccion = [
                x for x in disponibles
                if x not in excluir
            ]

        else:
            seleccion = [
                int(x.strip())
                for x in valor.split(",")
                if x.strip()
            ]

        if not seleccion:
            await update.message.reply_text(
                "❌ No quedaron temporadas seleccionadas."
            )
            return TEMP

        await update.message.reply_text(
            "🚀 Iniciando descarga...\n\n"
            "Usa /downloads para ver el progreso"
        )

        asyncio.create_task(
            descargar_serie(
                telethon_client,
                context.user_data["grupo"],
                context.user_data["serie"],
                seleccion,
                context.bot,
                update.effective_chat.id
            )
        )

        return ConversationHandler.END

    except Exception as e:
        await update.message.reply_text(
            f"❌ Formato inválido\n\n{e}"
        )
        return TEMP


# =====================================
# PELÍCULAS
# =====================================

@solo_admin
async def index_movies(update: Update, context):
    await iniciar_telethon()

    dialogs = await telethon_client.get_dialogs()

    grupos = []
    texto = "Selecciona grupo de películas para indexar:\n\n"

    for i, d in enumerate(dialogs):
        texto += f"{i}. {d.name}\n"
        grupos.append(d)

    context.user_data["index_grupos"] = grupos

    await update.message.reply_text(texto[:4000])
    return INDEX


@solo_admin
async def set_index_group(update: Update, context):
    try:
        idx = int(update.message.text)
        grupos = context.user_data.get("index_grupos", [])

        if idx < 0 or idx >= len(grupos):
            raise ValueError("índice fuera de rango")

        grupo = grupos[idx]

        await update.message.reply_text(
            f"🔎 Indexando películas en:\n{grupo.name}"
        )

        nuevos, total = await indexar_peliculas(
            telethon_client,
            grupo
        )

        await update.message.reply_text(
            f"✅ {nuevos} películas nuevas indexadas "
            f"({total} archivos revisados)\n\n"
            "Usa /list o /search nombre para explorar."
        )

        return ConversationHandler.END

    except (ValueError, KeyError) as e:
        await update.message.reply_text(
            f"❌ Número inválido\n{e}"
        )
        return INDEX


def formatear_peliculas(resultados, titulo, pagina=None, total=None):
    mensaje = titulo + "\n\n"

    for i, r in enumerate(resultados):
        _, nombre, grupo, anio, _, _ = r
        anio_txt = f" ({anio})" if anio else ""
        mensaje += (
            f"{i}. 🎬 {nombre}{anio_txt}\n"
            f"   📂 {grupo}\n\n"
        )

    if total is not None and pagina is not None:
        paginas = max(1, (total + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE)
        mensaje += (
            f"Mostrando {len(resultados)} de {total} "
            f"(pág. {pagina}/{paginas})\n\n"
        )
    else:
        mensaje += f"Total: {len(resultados)}\n\n"

    mensaje += "Descarga con:\n/download N"

    if pagina and pagina > 1:
        mensaje += f"\n\nPágina anterior:\n/list {pagina - 1}"

    if total and pagina:
        paginas = max(1, (total + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE)
        if pagina < paginas:
            mensaje += f"\nSiguiente página:\n/list {pagina + 1}"

    return mensaje


@solo_admin
async def list_movies(update: Update, context):
    pagina = 1

    if context.args:
        try:
            pagina = int(context.args[0])
        except ValueError:
            await update.message.reply_text(
                "Uso:\n/list\n/list 2"
            )
            return

        if pagina < 1:
            await update.message.reply_text("❌ La página debe ser ≥ 1")
            return

    total = count_peliculas()

    if total == 0:
        await update.message.reply_text(
            "📭 No hay películas indexadas.\n\n"
            "Usa /index_movies primero."
        )
        return

    paginas = max(1, (total + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE)

    if pagina > paginas:
        await update.message.reply_text(
            f"❌ Solo hay {paginas} página(s).\n"
            f"Usa /list {paginas}"
        )
        return

    resultados = list_peliculas(pagina, LIST_PAGE_SIZE)
    context.user_data["busqueda"] = resultados

    mensaje = formatear_peliculas(
        resultados,
        "📋 Películas indexadas",
        pagina=pagina,
        total=total
    )

    await update.message.reply_text(mensaje[:4000])


@solo_admin
async def search(update: Update, context):
    texto = " ".join(context.args).strip()

    if not texto:
        await update.message.reply_text(
            "Uso:\n/search nombre pelicula\n\n"
            "Ejemplo:\n/search inception 2010"
        )
        return

    resultados = search_peliculas(texto)

    if not resultados:
        await update.message.reply_text(
            "❌ Sin resultados.\n\n"
            "Indexa primero con /index_movies"
        )
        return

    context.user_data["busqueda"] = resultados

    mensaje = formatear_peliculas(
        resultados,
        f"🔍 Películas: {texto}"
    )

    await update.message.reply_text(mensaje[:4000])


@solo_admin
async def downloads(update: Update, context):
    await update.message.reply_text(tracker.formatear())


@solo_admin
async def download(update: Update, context):
    if not context.args:
        await update.message.reply_text(
            "Uso:\n/download N\n\n"
            "Primero usa /list o /search"
        )
        return

    try:
        idx = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Número inválido")
        return

    resultados = context.user_data.get("busqueda")

    if not resultados:
        await update.message.reply_text(
            "❌ No hay lista activa.\n"
            "Usa /list o /search primero."
        )
        return

    if idx < 0 or idx >= len(resultados):
        await update.message.reply_text(
            f"❌ Elige un número entre 0 y "
            f"{len(resultados) - 1}"
        )
        return

    pelicula = resultados[idx]
    _, nombre, _, _, grupo_id, mensaje_id = pelicula

    titulo = nombre_pelicula_destino(nombre)
    track_id = tracker.add(titulo, "pelicula")

    await iniciar_telethon()

    asyncio.create_task(
        descargar_pelicula(
            telethon_client,
            grupo_id,
            mensaje_id,
            nombre,
            context.bot,
            update.effective_chat.id,
            track_id=track_id
        )
    )

    await update.message.reply_text(
        f"📥 En cola: {titulo}\n\n"
        "Usa /downloads para ver el progreso"
    )


@solo_admin
async def cancel(update: Update, context):
    await update.message.reply_text("❌ Cancelado")
    return ConversationHandler.END


# =====================================
# APP
# =====================================

app = (
    ApplicationBuilder()
    .token(BOT_TOKEN)
    .post_init(post_init)
    .build()
)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("groups", groups))
app.add_handler(CommandHandler("paths", paths))
app.add_handler(CommandHandler("list", list_movies))
app.add_handler(CommandHandler("search", search))
app.add_handler(CommandHandler("download", download))
app.add_handler(CommandHandler("downloads", downloads))

series_conv = ConversationHandler(
    entry_points=[
        CommandHandler("download_series", download_series)
    ],
    states={
        GRUPO: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                set_group
            )
        ],
        SERIE: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                set_serie
            )
        ],
        TEMP: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                set_temp
            )
        ]
    },
    fallbacks=[
        CommandHandler("cancel", cancel)
    ]
)

movies_conv = ConversationHandler(
    entry_points=[
        CommandHandler("index_movies", index_movies)
    ],
    states={
        INDEX: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                set_index_group
            )
        ]
    },
    fallbacks=[
        CommandHandler("cancel", cancel)
    ]
)

app.add_handler(series_conv)
app.add_handler(movies_conv)

print("🤖 Bot iniciado...")
app.run_polling()
