import asyncio
import os
import re
import shutil

from downloader.tracker import tracker, Estado


VIDEO_EXT = re.compile(
    r"\.(mkv|mp4|avi|mov|wmv|m4v|ts|webm)$",
    re.I
)

ANIO_RE = re.compile(r"\((\d{4})\)|\b(19\d{2}|20\d{2})\b")

INVALIDOS_WIN = re.compile(r'[<>:"/\\|?*]')


def limpiar_nombre(nombre):
    if not nombre:
        return ""
    nombre = nombre.strip()
    nombre = re.sub(
        r"[^\w\s\.\-\[\]\(\)]",
        "",
        nombre,
        flags=re.UNICODE
    )
    return nombre


def sanitizar_carpeta(nombre):
    nombre = INVALIDOS_WIN.sub("", nombre or "")
    nombre = nombre.strip(" .")
    return nombre[:200] or "pelicula"


def es_video(nombre):
    return bool(VIDEO_EXT.search(nombre or ""))


def obtener_extension(nombre):
    m = re.search(
        r"\.(mkv|mp4|avi|mov|wmv|m4v|ts|webm)",
        nombre,
        re.I
    )
    if m:
        return "." + m.group(1).lower()
    return ".mp4"


def extraer_anio(nombre):
    m = ANIO_RE.search(nombre or "")
    if m:
        return int(m.group(1) or m.group(2))
    return None


def nombre_pelicula_destino(nombre):
    base = limpiar_nombre(nombre)
    base = re.sub(
        r"\.(mkv|mp4|avi|mov|wmv|m4v|ts|webm)$",
        "",
        base,
        flags=re.I
    )
    return sanitizar_carpeta(base.strip() or "pelicula")


def ruta_part(ruta_base):
    return ruta_base + ".part"


def bytes_parciales(ruta_part):
    if os.path.exists(ruta_part):
        return os.path.getsize(ruta_part)
    return 0


def finalizar_part(ruta_part, ruta_final):
    if not os.path.exists(ruta_part):
        return
    if os.path.exists(ruta_final):
        os.remove(ruta_part)
        return
    os.rename(ruta_part, ruta_final)


async def verificar_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg no está instalado o no está en el PATH"
        )

    proceso = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-version",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proceso.communicate()
    if proceso.returncode != 0:
        raise RuntimeError("ffmpeg no responde correctamente")


def progreso_callback(bot, chat_id, nombre, track_id=None):
    estado = {"valor": 0, "msg_id": None}

    async def actualizar(porcentaje):
        texto = f"📥 {nombre}\n{porcentaje}%"
        try:
            if estado["msg_id"] is None:
                msg = await bot.send_message(chat_id, texto)
                estado["msg_id"] = msg.message_id
            else:
                await bot.edit_message_text(
                    texto,
                    chat_id=chat_id,
                    message_id=estado["msg_id"]
                )
        except Exception:
            pass

    def callback(actual, total):
        if track_id is not None and tracker.esta_cancelado(track_id):
            raise asyncio.CancelledError("cancelado por usuario")
        if not total:
            return
        try:
            porcentaje = int(actual * 100 / total)
            if track_id is not None:
                tracker.set_progreso(track_id, porcentaje)
            if porcentaje >= estado["valor"] + 10:
                estado["valor"] = porcentaje
                asyncio.create_task(actualizar(porcentaje))
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    return callback


async def descargar_reanudable(
    msg,
    ruta_part,
    track_id,
    bot,
    chat_id,
    titulo
):
    if tracker.esta_cancelado(track_id):
        raise asyncio.CancelledError()

    parcial = bytes_parciales(ruta_part)
    if parcial > 0:
        tracker.set_estado(track_id, Estado.DESCARGANDO)
    else:
        tracker.set_estado(track_id, Estado.DESCARGANDO, 0)

    await msg.download_media(
        file=ruta_part,
        progress_callback=progreso_callback(
            bot,
            chat_id,
            titulo,
            track_id
        )
    )


async def convertir_a_mkv(origen, destino, track_id=None):

    if track_id is not None:
        if tracker.esta_cancelado(track_id):
            raise asyncio.CancelledError()

        tracker.set_estado(
            track_id,
            Estado.CONVIRTIENDO
        )

    proceso = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-i",
        origen,

        "-map", "0:v",
        "-map", "0:a?",
        
        "-c:v", "copy",
        "-c:a", "copy",

        destino,
        "-y",

        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    _, error = await proceso.communicate()

    if (
        track_id is not None and
        tracker.esta_cancelado(track_id)
    ):
        raise asyncio.CancelledError()

    if proceso.returncode == 0:

        try:
            os.remove(origen)
        except OSError:
            pass

        return True, ""

    return False, error.decode(
        errors="ignore"
    )