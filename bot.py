import asyncio
import logging
from functools import wraps

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update
)
from telegram.ext import (
    ApplicationBuilder,
    ApplicationHandlerStop,
    CallbackQueryHandler,
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
    MAX_DOWNLOAD_QUEUE,
    tmdb_configurado,
    validar_config
)

from downloader.series import (
    descargar_serie,
    obtener_temporadas
)

from downloader.indexer import indexar_peliculas
from downloader.queue import movie_queue, TrabajoPelicula
from downloader.utils import (
    verificar_ffmpeg,
    nombre_pelicula_destino,
    sanitizar_carpeta
)
from downloader.tmdb import (
    resolver_titulo_serie,
    resolver_titulo_pelicula
)
from downloader.tracker import tracker

from database import (
    search_peliculas,
    list_peliculas,
    count_peliculas,
    get_pelicula,
    init_db
)

LIST_PAGE_SIZE = 30

validar_config()
init_db()

GRUPO, SERIE, CONFIRM_SERIE, TEMP, INDEX = range(5)

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
        user = update.effective_user
        if not user or not autorizado(user.id):
            return ConversationHandler.END
        return await handler(update, context)
    return wrapper


async def post_init(application):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    await verificar_ffmpeg()
    movie_queue.iniciar()
    print("✅ ffmpeg disponible")
    if tmdb_configurado():
        print("✅ TMDB configurado")
    else:
        print("⚠️ TMDB no configurado (TMDB_API_KEY o TMDB_READ_TOKEN)")


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

    mensaje += "Pulsa ⬇ en un botón para descargar."

    return mensaje


def teclado_peliculas(resultados, pagina=None, total=None):
    botones = []
    fila = []

    for r in resultados:
        pid, nombre, _, anio, _, _ = r
        etiqueta = nombre[:28]
        if anio:
            etiqueta = f"{etiqueta[:22]} ({anio})"
        fila.append(InlineKeyboardButton(
            f"⬇ {etiqueta}",
            callback_data=f"dl:{pid}"
        ))
        if len(fila) == 2:
            botones.append(fila)
            fila = []

    if fila:
        botones.append(fila)

    nav = []
    if pagina and pagina > 1:
        nav.append(InlineKeyboardButton(
            "◀️ Anterior",
            callback_data=f"list:{pagina - 1}"
        ))
    if pagina and total:
        paginas = max(1, (total + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE)
        if pagina < paginas:
            nav.append(InlineKeyboardButton(
                "Siguiente ▶️",
                callback_data=f"list:{pagina + 1}"
            ))
    if nav:
        botones.append(nav)

    return InlineKeyboardMarkup(botones)


def teclado_descargas(hay_activas):
    if not hay_activas:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🚫 Cancelar todas",
            callback_data="cancel_dl"
        )
    ]])


async def encolar_pelicula(
    pelicula_id,
    bot,
    chat_id,
    titulo_personalizado=None
):
    pelicula = get_pelicula(pelicula_id)

    if not pelicula:
        return False, "❌ Película no encontrada en el índice"

    _, nombre, _, anio, grupo_id, mensaje_id = pelicula

    if titulo_personalizado:
        titulo = titulo_personalizado
    else:
        titulo = nombre_pelicula_destino(nombre)

    track_id = tracker.add(titulo, "pelicula")

    await iniciar_telethon()

    trabajo = TrabajoPelicula(
        telethon_client=telethon_client,
        grupo_id=grupo_id,
        mensaje_id=mensaje_id,
        nombre=nombre,
        anio=anio,
        bot=bot,
        chat_id=chat_id,
        track_id=track_id,
        titulo_personalizado=titulo_personalizado
    )

    return await movie_queue.encolar(trabajo)


async def iniciar_descarga_pelicula(
    pelicula_id,
    bot,
    chat_id,
    context
):
    pelicula = get_pelicula(pelicula_id)

    if not pelicula:
        return False, "❌ Película no encontrada en el índice"

    _, nombre, _, anio, _, _ = pelicula

    if tmdb_configurado():
        titulo, desde_tmdb = await resolver_titulo_pelicula(
            nombre,
            anio
        )

        if not desde_tmdb:
            context.user_data["pendiente_pelicula"] = {
                "pelicula_id": pelicula_id,
                "sugerido": titulo,
            }
            return False, (
                "⚠️ TMDB no encontró metadatos.\n\n"
                f"Sugerido: {titulo}\n\n"
                "Escribe el nombre de la carpeta:\n"
                "`ok` = usar el sugerido"
            )

        return await encolar_pelicula(
            pelicula_id,
            bot,
            chat_id,
            titulo_personalizado=titulo
        )

    return await encolar_pelicula(pelicula_id, bot, chat_id)


async def continuar_temporadas(update, context):
    grupo = context.user_data["grupo"]
    titulo = context.user_data["serie"]

    temps = await obtener_temporadas(telethon_client, grupo)

    if not temps:
        await update.message.reply_text(
            "❌ No encontré episodios en ese grupo."
        )
        return ConversationHandler.END

    context.user_data["temps"] = temps

    texto = (
        f"📺 Serie: {titulo}\n\n"
        "Temporadas encontradas\n\n"
    )

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
/list — Ver películas indexadas (con botones)
/search nombre — Buscar película indexada
/download N — Descargar por número (alternativo)

Descargas:
/downloads — Ver cola y progreso
/cancel_download — Cancelar descargas activas
/cancel_download ID — Cancelar una descarga
/cancel_download serie Nombre — Cancelar serie

Utilidades:
/status — Estado del bot
/groups — Listar chats
/paths — Rutas de medios
/cancel — Cancelar conversación

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

Cola máxima: {MAX_DOWNLOAD_QUEUE} películas
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
            "📝 Escribe el nombre de la serie.\n"
            "TMDB renombrará la carpeta si está configurado."
        )

        return SERIE

    except (ValueError, KeyError):
        await update.message.reply_text("❌ Número inválido")
        return GRUPO


@solo_admin
async def set_serie(update: Update, context):
    nombre_escrito = update.message.text.strip()
    grupo = context.user_data["grupo"]

    context.user_data["nombre_escrito"] = nombre_escrito

    if not tmdb_configurado():
        context.user_data["serie"] = sanitizar_carpeta(nombre_escrito)
        await update.message.reply_text(
            f"📺 Carpeta: {context.user_data['serie']}\n\n"
            "🔍 Buscando temporadas..."
        )
        return await continuar_temporadas(update, context)

    titulo, desde_tmdb = await resolver_titulo_serie(
        nombre_escrito,
        alternativo=grupo.name
    )
    context.user_data["serie_sugerida"] = titulo

    if desde_tmdb:
        aviso = (
            f"📺 TMDB sugiere:\n{titulo}\n\n"
            "Escribe otro nombre para cambiarlo,\n"
            "o envía `ok` para usar este."
        )
    else:
        aviso = (
            "⚠️ TMDB no encontró metadatos.\n\n"
            "Escribe el nombre de la carpeta:\n"
            f"`ok` = usar sugerido ({titulo})"
        )

    await update.message.reply_text(aviso)
    return CONFIRM_SERIE


@solo_admin
async def confirm_serie(update: Update, context):
    texto = update.message.text.strip()
    sugerida = context.user_data.get("serie_sugerida", "")

    if texto.lower() in ("ok", "si", "sí", "yes"):
        titulo = sugerida
    else:
        titulo = sanitizar_carpeta(texto)

    if not titulo:
        await update.message.reply_text(
            "❌ Nombre inválido. Escribe otro o `ok`."
        )
        return CONFIRM_SERIE

    context.user_data["serie"] = titulo

    await update.message.reply_text(
        f"📺 Carpeta: {titulo}\n\n🔍 Buscando temporadas..."
    )

    return await continuar_temporadas(update, context)


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

        nombre_serie = context.user_data["serie"]

        await update.message.reply_text(
            "🚀 Iniciando descarga...\n\n"
            "Usa /downloads para ver el progreso\n"
            f"/cancel_download serie {nombre_serie} — cancelar"
        )

        asyncio.create_task(
            descargar_serie(
                telethon_client,
                context.user_data["grupo"],
                nombre_serie,
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


async def mostrar_lista(
    bot,
    chat_id,
    pagina,
    editar=None
):
    total = count_peliculas()
    paginas = max(1, (total + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE)

    if pagina < 1 or pagina > paginas:
        return False, f"❌ Página inválida (1-{paginas})"

    resultados = list_peliculas(pagina, LIST_PAGE_SIZE)

    mensaje = formatear_peliculas(
        resultados,
        "📋 Películas indexadas",
        pagina=pagina,
        total=total
    )
    teclado = teclado_peliculas(
        resultados,
        pagina=pagina,
        total=total
    )

    if editar:
        await editar.edit_text(
            mensaje[:4000],
            reply_markup=teclado
        )
    else:
        await bot.send_message(
            chat_id,
            mensaje[:4000],
            reply_markup=teclado
        )

    return True, None


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

    total = count_peliculas()

    if total == 0:
        await update.message.reply_text(
            "📭 No hay películas indexadas.\n\n"
            "Usa /index_movies primero."
        )
        return

    ok, error = await mostrar_lista(
        context.bot,
        update.effective_chat.id,
        pagina
    )

    if not ok:
        await update.message.reply_text(error)


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
    teclado = teclado_peliculas(resultados)

    await update.message.reply_text(
        mensaje[:4000],
        reply_markup=teclado
    )


@solo_admin
async def downloads(update: Update, context):
    texto, hay_activas = tracker.formatear()
    teclado = teclado_descargas(hay_activas)
    await update.message.reply_text(
        texto,
        reply_markup=teclado
    )


@solo_admin
async def cancel_download(update: Update, context):
    args = context.args

    if not args:
        n = tracker.cancelar_activas()
        await update.message.reply_text(
            f"🚫 {n} descarga(s) cancelada(s)"
        )
        return

    if args[0].lower() == "serie":
        lote = " ".join(args[1:]).strip()
        if not lote:
            await update.message.reply_text(
                "Uso:\n/cancel_download serie Nombre Serie"
            )
            return
        n = tracker.cancelar_lote(lote)
        await update.message.reply_text(
            f"🚫 Serie cancelada: {lote}\n"
            f"{n} elemento(s) en cola"
        )
        return

    try:
        track_id = int(args[0])
    except ValueError:
        await update.message.reply_text(
            "Uso:\n/cancel_download\n"
            "/cancel_download ID\n"
            "/cancel_download serie Nombre"
        )
        return

    if tracker.cancelar(track_id):
        await update.message.reply_text(
            f"🚫 Descarga #{track_id} cancelada"
        )
    else:
        await update.message.reply_text(
            f"❌ No se pudo cancelar #{track_id}"
        )


@solo_admin
async def download(update: Update, context):
    if not context.args:
        await update.message.reply_text(
            "Uso:\n/download N\n\n"
            "O usa los botones en /list y /search"
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
    pelicula_id = pelicula[0]

    ok, msg = await iniciar_descarga_pelicula(
        pelicula_id,
        context.bot,
        update.effective_chat.id,
        context
    )

    await update.message.reply_text(msg)


async def callback_query(update: Update, context):
    query = update.callback_query

    if not query.from_user or not autorizado(query.from_user.id):
        await query.answer("No autorizado", show_alert=True)
        return

    data = query.data

    if data.startswith("dl:"):
        pelicula_id = int(data[3:])
        ok, msg = await iniciar_descarga_pelicula(
            pelicula_id,
            context.bot,
            query.message.chat_id,
            context
        )
        await query.answer("Encolada" if ok else "Nombre requerido")
        await query.message.reply_text(msg)
        return

    if data.startswith("list:"):
        pagina = int(data[5:])
        await query.answer()
        ok, error = await mostrar_lista(
            context.bot,
            query.message.chat_id,
            pagina,
            editar=query.message
        )
        if not ok:
            await query.message.reply_text(error)
        return

    if data == "cancel_dl":
        n = tracker.cancelar_activas()
        await query.answer("Canceladas")
        await query.message.reply_text(
            f"🚫 {n} descarga(s) cancelada(s)"
        )
        return

    await query.answer()


async def recibir_nombre_pelicula(update: Update, context):
    if not update.effective_user or not autorizado(update.effective_user.id):
        return

    pendiente = context.user_data.get("pendiente_pelicula")
    if not pendiente:
        return

    texto = update.message.text.strip()
    sugerido = pendiente.get("sugerido", "")

    if texto.lower() in ("ok", "si", "sí", "yes"):
        titulo = sugerido
    else:
        titulo = sanitizar_carpeta(texto)

    if not titulo:
        await update.message.reply_text(
            "❌ Nombre inválido. Escribe otro o `ok`."
        )
        raise ApplicationHandlerStop

    context.user_data.pop("pendiente_pelicula", None)

    ok, msg = await encolar_pelicula(
        pendiente["pelicula_id"],
        context.bot,
        update.effective_chat.id,
        titulo_personalizado=titulo
    )

    await update.message.reply_text(msg)
    raise ApplicationHandlerStop


@solo_admin
async def cancel(update: Update, context):
    context.user_data.pop("pendiente_pelicula", None)
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
app.add_handler(CommandHandler("cancel_download", cancel_download))
app.add_handler(CallbackQueryHandler(callback_query))
app.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    recibir_nombre_pelicula
))

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
        CONFIRM_SERIE: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                confirm_serie
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
