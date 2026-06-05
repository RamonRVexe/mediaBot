from database import insert_peliculas_batch

from downloader.series import parse_episode
from downloader.utils import (
    limpiar_nombre,
    es_video,
    extraer_anio
)

BATCH_SIZE = 100


async def indexar_peliculas(telethon_client, grupo):
    total = 0
    nuevos = 0
    buffer = []
    grupo_nombre = grupo.name or str(grupo.id)

    async for msg in telethon_client.iter_messages(grupo):
        if not msg.file:
            continue

        nombre = limpiar_nombre(msg.file.name or "")

        if not nombre or not es_video(nombre):
            continue

        if parse_episode(nombre):
            continue

        buffer.append((
            grupo.id,
            grupo_nombre,
            msg.id,
            nombre,
            extraer_anio(nombre)
        ))

        total += 1

        if len(buffer) >= BATCH_SIZE:
            nuevos += insert_peliculas_batch(buffer)
            buffer.clear()

    if buffer:
        nuevos += insert_peliculas_batch(buffer)

    return nuevos, total
