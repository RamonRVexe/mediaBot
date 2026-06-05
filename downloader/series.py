import asyncio
import os
import re

from config import TV_PATH

from downloader.tracker import tracker, Estado
from downloader.utils import (
    convertir_a_mkv,
    limpiar_nombre,
    obtener_extension,
    progreso_callback
)

PATTERNS = {
    "S_EP": re.compile(
        r"S(\d{1,2})[.\-_ ]?EP(\d{1,3})",
        re.I
    ),
    "S01E01": re.compile(
        r"S(\d{1,2})E(\d{1,3})",
        re.I
    ),
    "SxE": re.compile(
        r"S\s*(\d{1,2})\s*E\s*(\d{1,3})",
        re.I
    ),
    "T01E01": re.compile(
        r"T(\d{1,2})[:\-]?E(\d{1,3})",
        re.I
    ),
    "TxE": re.compile(
        r"T\s*(\d{1,2})\s*[:\-]?\s*E\s*(\d{1,3})",
        re.I
    ),
    "1x01": re.compile(
        r"(\d{1,2})\s*[xX×]\s*(\d{1,3})",
        re.I
    ),
    "TempCap": re.compile(
        r"Temp(?:orada)?\s*(\d+).*?Cap(?:itulo)?\s*(\d+)",
        re.I
    ),
    "Temporada": re.compile(
        r"Temporada\s*(\d+).*?Episodio\s*(\d+)",
        re.I
    ),
    "EP_T": re.compile(
        r"EP\s*(\d+).*?T\s*(\d+)",
        re.I
    )
}


def parse_episode(texto):
    if not texto:
        return None

    texto = limpiar_nombre(texto)

    for patron, regex in PATTERNS.items():
        m = regex.search(texto)

        if not m:
            continue

        season = int(m.group(1))
        episode = int(m.group(2))

        if patron == "EP_T":
            season, episode = episode, season

        return season, episode, patron

    return None


async def obtener_temporadas(telethon_client, grupo):
    temporadas = set()

    async for msg in telethon_client.iter_messages(grupo):
        if not msg.file:
            continue

        nombre = limpiar_nombre(msg.file.name or "")
        parsed = parse_episode(nombre)

        if parsed:
            season, _, _ = parsed
            temporadas.add(season)

    return sorted(temporadas)


async def descargar_serie(
    telethon_client,
    grupo,
    nombre_serie,
    temporadas,
    bot,
    chat_id
):
    patrones_encontrados = set()
    cola = []

    await bot.send_message(
        chat_id,
        "🔎 Escaneando episodios pendientes..."
    )

    async for msg in telethon_client.iter_messages(grupo, reverse=True):
        if not msg.file:
            continue

        original = limpiar_nombre(msg.file.name or "")
        parsed = parse_episode(original)

        if not parsed:
            continue

        season, episode, patron = parsed
        patrones_encontrados.add(patron)

        if season not in temporadas:
            continue

        folder = os.path.join(
            TV_PATH,
            nombre_serie,
            f"Season {season:02d}"
        )

        filename = (
            f"{nombre_serie} - "
            f"S{season:02d}E{episode:02d}"
        )

        mkv_path = os.path.join(folder, filename + ".mkv")

        if os.path.exists(mkv_path):
            continue

        cola.append({
            "msg": msg,
            "filename": filename,
            "folder": folder,
            "original": original,
            "original_ext": obtener_extension(original),
        })

    if not cola:
        await bot.send_message(
            chat_id,
            f"ℹ️ No hay episodios nuevos para descargar.\n"
            f"Serie: {nombre_serie}"
        )
        return

    track_ids = []
    for item in cola:
        tid = tracker.add(
            item["filename"],
            "serie",
            lote=nombre_serie
        )
        track_ids.append(tid)

    await bot.send_message(
        chat_id,
        f"🚀 {len(cola)} episodios en cola\n"
        f"Serie: {nombre_serie}\n\n"
        "Usa /downloads para ver el progreso"
    )

    descargados = 0

    for item, track_id in zip(cola, track_ids):
        msg = item["msg"]
        filename = item["filename"]
        folder = item["folder"]
        original_ext = item["original_ext"]

        os.makedirs(folder, exist_ok=True)

        mkv_path = os.path.join(folder, filename + ".mkv")
        temp_path = os.path.join(
            folder,
            filename + original_ext
        )

        tracker.set_estado(track_id, Estado.DESCARGANDO, 0)

        await msg.download_media(
            file=temp_path,
            progress_callback=progreso_callback(
                bot,
                chat_id,
                filename,
                track_id
            )
        )

        if original_ext.lower() == ".mkv":
            os.rename(temp_path, mkv_path)
            tracker.completar(track_id)
            descargados += 1
            await asyncio.sleep(0.2)
            continue

        ok, error = await convertir_a_mkv(
            temp_path,
            mkv_path,
            track_id
        )

        if ok:
            tracker.completar(track_id)
            descargados += 1
        else:
            tracker.fallar(track_id, "error ffmpeg")
            await bot.send_message(
                chat_id,
                f"❌ Error convirtiendo\n{filename}\n\n{error[:500]}"
            )

        await asyncio.sleep(0.2)

    await bot.send_message(
        chat_id,
        f"""
✅ Descarga terminada

Serie:
{nombre_serie}

Temporadas:
{', '.join(map(str, temporadas))}

Patrones encontrados:
{', '.join(sorted(patrones_encontrados))}

Episodios descargados:
{descargados} de {len(cola)}
"""
    )
