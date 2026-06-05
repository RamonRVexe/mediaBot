import os

from config import MOVIES_PATH

from downloader.tracker import tracker, Estado
from downloader.utils import (
    convertir_a_mkv,
    nombre_pelicula_destino,
    obtener_extension,
    progreso_callback
)


async def descargar_pelicula(
    telethon_client,
    grupo_id,
    mensaje_id,
    nombre,
    bot,
    chat_id,
    track_id=None
):
    if track_id is None:
        titulo = nombre_pelicula_destino(nombre)
        track_id = tracker.add(titulo, "pelicula")
    else:
        titulo = nombre_pelicula_destino(nombre)

    try:
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

        tracker.set_estado(track_id, Estado.DESCARGANDO, 0)

        await bot.send_message(
            chat_id,
            f"⬇ Descargando\n{titulo}\n\n"
            "Usa /downloads para ver el progreso"
        )

        await msg.download_media(
            file=temp_path,
            progress_callback=progreso_callback(
                bot,
                chat_id,
                titulo,
                track_id
            )
        )

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

    except Exception as e:
        tracker.fallar(track_id, str(e))
        await bot.send_message(
            chat_id,
            f"❌ Error descargando\n{titulo}\n\n{e}"
        )
        return False
