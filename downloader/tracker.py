import asyncio
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Set


class Estado(str, Enum):
    COLA = "en cola"
    DESCARGANDO = "descargando"
    CONVIRTIENDO = "convirtiendo"
    COMPLETADO = "completado"
    ERROR = "error"
    OMITIDO = "omitido"
    CANCELADO = "cancelado"


@dataclass
class Descarga:
    id: int
    nombre: str
    tipo: str
    estado: Estado
    progreso: int = 0
    lote: Optional[str] = None
    error: Optional[str] = None
    inicio: float = field(default_factory=time.time)
    cancelado: bool = False
    task: Optional[asyncio.Task] = field(
        default=None,
        repr=False,
        compare=False
    )


class DownloadTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._items: dict[int, Descarga] = {}
        self._lotes_cancelados: Set[str] = set()
        self._series_tasks: dict = {}
        self._next_id = 1
        self._max_items = 80

    def registrar_serie_task(self, lote, task):
        with self._lock:
            if task is None:
                self._series_tasks.pop(lote, None)
            else:
                self._series_tasks[lote] = task

    def add(self, nombre, tipo, lote=None):
        with self._lock:
            item_id = self._next_id
            self._next_id += 1
            self._items[item_id] = Descarga(
                id=item_id,
                nombre=nombre,
                tipo=tipo,
                estado=Estado.COLA,
                lote=lote
            )
            self._recortar()
            return item_id

    def registrar_task(self, item_id, task):
        with self._lock:
            item = self._items.get(item_id)
            if item:
                item.task = task

    def set_estado(self, item_id, estado, progreso=None):
        with self._lock:
            item = self._items.get(item_id)
            if not item or item.cancelado:
                return
            item.estado = estado
            if progreso is not None:
                item.progreso = progreso

    def set_progreso(self, item_id, progreso):
        with self._lock:
            item = self._items.get(item_id)
            if not item or item.cancelado:
                return
            item.progreso = max(0, min(100, progreso))

    def set_nombre(self, item_id, nombre):
        with self._lock:
            item = self._items.get(item_id)
            if item:
                item.nombre = nombre

    def completar(self, item_id):
        with self._lock:
            item = self._items.get(item_id)
            if not item:
                return
            item.estado = Estado.COMPLETADO
            item.progreso = 100

    def omitir(self, item_id):
        with self._lock:
            item = self._items.get(item_id)
            if not item:
                return
            item.estado = Estado.OMITIDO
            item.progreso = 100

    def fallar(self, item_id, error=""):
        with self._lock:
            item = self._items.get(item_id)
            if not item:
                return
            item.estado = Estado.ERROR
            item.error = (error or "error")[:200]

    def _marcar_cancelado(self, item):
        item.cancelado = True
        item.estado = Estado.CANCELADO
        if item.task and not item.task.done():
            item.task.cancel()

    def marcar_cancelado(self, item_id):
        with self._lock:
            item = self._items.get(item_id)
            if not item:
                return
            item.cancelado = True
            item.estado = Estado.CANCELADO

    def cancelar(self, item_id):
        with self._lock:
            item = self._items.get(item_id)
            if not item:
                return False
            if item.estado in (
                Estado.COMPLETADO,
                Estado.ERROR,
                Estado.OMITIDO,
                Estado.CANCELADO
            ):
                return False
            self._marcar_cancelado(item)
            return True

    def cancelar_activas(self):
        with self._lock:
            count = 0
            for item in self._items.values():
                if item.estado in (
                    Estado.COLA,
                    Estado.DESCARGANDO,
                    Estado.CONVIRTIENDO
                ):
                    self._marcar_cancelado(item)
                    count += 1
            return count

    def cancelar_lote(self, lote):
        with self._lock:
            self._lotes_cancelados.add(lote)
            count = 0
            for item in self._items.values():
                if item.lote == lote and item.estado in (
                    Estado.COLA,
                    Estado.DESCARGANDO,
                    Estado.CONVIRTIENDO
                ):
                    self._marcar_cancelado(item)
                    count += 1
            task = self._series_tasks.get(lote)
            if task and not task.done():
                task.cancel()
            return count

    def lote_cancelado(self, lote):
        with self._lock:
            return lote in self._lotes_cancelados

    def esta_cancelado(self, item_id):
        with self._lock:
            item = self._items.get(item_id)
            if not item:
                return True
            return item.cancelado or item.estado == Estado.CANCELADO

    def _recortar(self):
        if len(self._items) <= self._max_items:
            return
        finalizados = [
            i for i in self._items.values()
            if i.estado in (
                Estado.COMPLETADO,
                Estado.ERROR,
                Estado.OMITIDO,
                Estado.CANCELADO
            )
        ]
        finalizados.sort(key=lambda x: x.inicio)
        for item in finalizados[:len(self._items) - self._max_items]:
            del self._items[item.id]

    def _barra(self, progreso, ancho=10):
        lleno = int(progreso / 100 * ancho)
        return "█" * lleno + "░" * (ancho - lleno)

    def _icono(self, estado):
        return {
            Estado.COLA: "⏳",
            Estado.DESCARGANDO: "⬇️",
            Estado.CONVIRTIENDO: "🎞",
            Estado.COMPLETADO: "✅",
            Estado.ERROR: "❌",
            Estado.OMITIDO: "⏭",
            Estado.CANCELADO: "🚫",
        }.get(estado, "•")

    def ids_activos(self):
        with self._lock:
            return [
                i.id for i in self._items.values()
                if i.estado in (
                    Estado.COLA,
                    Estado.DESCARGANDO,
                    Estado.CONVIRTIENDO
                )
            ]

    def formatear(self):
        with self._lock:
            items = sorted(
                self._items.values(),
                key=lambda x: x.id
            )

        if not items:
            return (
                "📭 No hay descargas registradas.\n\n"
                "Inicia una con /download o /download_series"
            ), False

        activos = [
            i for i in items
            if i.estado in (
                Estado.COLA,
                Estado.DESCARGANDO,
                Estado.CONVIRTIENDO
            )
        ]
        recientes = [
            i for i in items
            if i.estado in (
                Estado.COMPLETADO,
                Estado.ERROR,
                Estado.OMITIDO,
                Estado.CANCELADO
            )
        ][-15:]

        lineas = ["📥 Estado de descargas\n"]

        if activos:
            lineas.append("▶️ Activas:\n")
            lotes_vistos = set()

            for item in activos:
                if item.lote and item.lote not in lotes_vistos:
                    lotes_vistos.add(item.lote)
                    en_lote = [
                        x for x in activos if x.lote == item.lote
                    ]
                    hechos = sum(
                        1 for x in items
                        if x.lote == item.lote
                        and x.estado == Estado.COMPLETADO
                    )
                    lineas.append(
                        f"📺 {item.lote} "
                        f"({hechos}/{len(en_lote) + hechos})\n"
                    )

                barra = self._barra(item.progreso)
                lineas.append(
                    f"{self._icono(item.estado)} "
                    f"#{item.id} {item.nombre}\n"
                    f"   {barra} {item.progreso}% "
                    f"— {item.estado.value}\n"
                )
        else:
            lineas.append("Sin descargas activas.\n")

        if recientes:
            lineas.append("\n📋 Recientes:\n")
            for item in reversed(recientes):
                extra = ""
                if item.estado == Estado.ERROR and item.error:
                    extra = f" ({item.error[:40]})"
                lineas.append(
                    f"{self._icono(item.estado)} {item.nombre}"
                    f"{extra}\n"
                )

        lineas.append(
            "\n/cancel_download — cancelar todas\n"
            "/cancel_download ID — cancelar una"
        )

        return "".join(lineas)[:4000], bool(activos)


tracker = DownloadTracker()
