import asyncio
import os

from config import MOVIES_PATH

from downloader.tmdb import resolver_titulo_pelicula
from downloader.tracker import tracker, Estado
from downloader.utils import (
    convertir_a_mkv,
    descargar_reanudable,
    finalizar_part,
    nombre_pelicula_destino,
    obtener_extension,
    ruta_part
)


async def descargar_pelicula(
    telethon_client,
    grupo_id,
    mensaje_id,
    nombre,
    anio,
    bot,
    chat_id,
    track_id=None,
    titulo_personalizado=None
):
    fallback = nombre_pelicula_destino(nombre)

    if titulo_personalizado:
        titulo = titulo_personalizado
        desde_tmdb = titulo != fallback
    else:
        titulo, desde_tmdb = await resolver_titulo_pelicula(
            nombre,
            anio
        )

    if track_id is None:
        track_id = tracker.add(titulo, "pelicula")
    else:
        tracker.set_nombre(track_id, titulo)
        tracker.set_estado(track_id, Estado.COLA)

    tracker.registrar_task(
        track_id,
        asyncio.current_task()
    )

    try:
        if tracker.esta_cancelado(track_id):
            return False

        msg = await telethon_client.get_messages(
            grupo_id,
            ids=mensaje_id
        )

        if not msg or not msg.file:
            tracker.fallar(track_id, "archivo no encontrado")
            await bot.send_message(
                chat_id,
                f"❌ No encontré el archivo:\n{nombre}"
            )
            return False

        carpeta = os.path.join(MOVIES_PATH, titulo)
        os.makedirs(carpeta, exist_ok=True)

        mkv_path = os.path.join(carpeta, titulo + ".mkv")

        if os.path.exists(mkv_path):
            tracker.omitir(track_id)
            await bot.send_message(
                chat_id,
                f"ℹ️ Ya existe:\n{titulo}/{titulo}.mkv"
            )
            return True

        original_ext = obtener_extension(nombre)
        temp_path = os.path.join(
            carpeta,
            titulo + original_ext
        )
        part_path = ruta_part(temp_path)

        inicio = f"⬇ Descargando\n📁 {titulo}"
        if desde_tmdb and titulo != fallback:
            inicio += f"\n📝 Archivo: {fallback}"
        elif not desde_tmdb:
            inicio += "\n⚠️ TMDB no encontró metadatos, usando nombre original"

        await bot.send_message(chat_id, inicio)

        await descargar_reanudable(
            msg,
            part_path,
            track_id,
            bot,
            chat_id,
            titulo
        )

        finalizar_part(part_path, temp_path)

        if original_ext.lower() == ".mkv":
            os.rename(temp_path, mkv_path)
            tracker.completar(track_id)
            await bot.send_message(
                chat_id,
                f"✅ Completado\n{titulo}/{titulo}.mkv"
            )
            return True

        ok, error = await convertir_a_mkv(
            temp_path,
            mkv_path,
            track_id
        )

        if ok:
            tracker.completar(track_id)
            await bot.send_message(
                chat_id,
                f"✅ Completado\n{titulo}/{titulo}.mkv"
            )
            return True

        tracker.fallar(track_id, "error ffmpeg")
        await bot.send_message(
            chat_id,
            f"❌ Error convirtiendo\n{titulo}\n\n{error[:3000]}"
        )
        return False

    except asyncio.CancelledError:
        tracker.marcar_cancelado(track_id)
        return False

    except Exception as e:
        tracker.fallar(track_id, str(e))
        await bot.send_message(
            chat_id,
            f"❌ Error descargando\n{titulo}\n\n{e}"
        )
        return False

    finally:
        tracker.registrar_task(track_id, None)
