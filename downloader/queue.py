import asyncio
from dataclasses import dataclass
from typing import Optional

from config import MAX_CONCURRENT_DOWNLOADS, MAX_DOWNLOAD_QUEUE

from downloader.tracker import tracker


@dataclass
class TrabajoPelicula:
    telethon_client: object
    grupo_id: int
    mensaje_id: int
    nombre: str
    anio: Optional[int]
    bot: object
    chat_id: int
    track_id: int
    titulo_personalizado: Optional[str] = None


class MovieDownloadQueue:
    def __init__(self):
        self._cola: asyncio.Queue = asyncio.Queue(
            maxsize=MAX_DOWNLOAD_QUEUE
        )
        self._iniciado = False

    def iniciar(self):
        if self._iniciado:
            return
        self._iniciado = True
        for _ in range(MAX_CONCURRENT_DOWNLOADS):
            asyncio.create_task(self._worker())

    @property
    def tamano(self):
        return self._cola.qsize()

    @property
    def llena(self):
        return self._cola.full()

    async def encolar(self, trabajo: TrabajoPelicula):
        if self._cola.full():
            tracker.fallar(
                trabajo.track_id,
                "cola llena"
            )
            return False, (
                f"❌ Cola llena (máx. {MAX_DOWNLOAD_QUEUE}).\n"
                "Espera o usa /cancel_download"
            )

        await self._cola.put(trabajo)
        posicion = self._cola.qsize()
        return True, (
            f"📥 En cola (#{trabajo.track_id}): "
            f"{trabajo.nombre}\n"
            f"Posición: ~{posicion}\n\n"
            "Usa /downloads para ver el progreso"
        )

    async def _worker(self):
        from downloader.movies import descargar_pelicula

        while True:
            trabajo = await self._cola.get()
            try:
                if tracker.esta_cancelado(trabajo.track_id):
                    continue

                await descargar_pelicula(
                    trabajo.telethon_client,
                    trabajo.grupo_id,
                    trabajo.mensaje_id,
                    trabajo.nombre,
                    trabajo.anio,
                    trabajo.bot,
                    trabajo.chat_id,
                    track_id=trabajo.track_id,
                    titulo_personalizado=trabajo.titulo_personalizado
                )
            except asyncio.CancelledError:
                tracker.cancelar(trabajo.track_id)
            except Exception as e:
                tracker.fallar(trabajo.track_id, str(e))
            finally:
                self._cola.task_done()


movie_queue = MovieDownloadQueue()
