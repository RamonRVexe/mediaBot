import asyncio
import json
import logging
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

from config import TMDB_API_KEY, TMDB_READ_TOKEN, tmdb_configurado

from downloader.utils import (
    extraer_anio,
    limpiar_nombre,
    nombre_pelicula_destino,
    sanitizar_carpeta
)

log = logging.getLogger(__name__)

TAGS_RE = re.compile(
    r"\[.*?\]|\{.*?\}|"
    r"\b\d{3,4}p\b|"
    r"\b(?:x264|x265|h264|h265|hevc|avc|aac|dts|hdr|"
    r"webrip|bluray|brrip|remux|proper|repack|extended|"
    r"dual|latino|castellano|english|subs?)\b",
    re.I
)


def _limpiar_query(nombre):
    base = limpiar_nombre(nombre)
    base = re.sub(
        r"\.(mkv|mp4|avi|mov|wmv|m4v|ts|webm)$",
        "",
        base,
        flags=re.I
    )
    anio = extraer_anio(base)
    base = re.sub(r"\(\d{4}\)", "", base)
    base = re.sub(r"\b\d{4}\b", "", base)
    base = TAGS_RE.sub(" ", base)
    base = re.sub(r"[._\-]+", " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base, anio


def _headers():
    headers = {
        "Accept": "application/json",
        "User-Agent": "MediaBot/1.0",
    }
    if TMDB_READ_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_READ_TOKEN}"
    return headers


def _nombre_serie_fallback(nombre):
    return sanitizar_carpeta(nombre.strip()) or "serie"


def _buscar_tmdb(endpoint, query, anio=None, campo_anio="year"):
    params = {
        "query": query,
        "include_adult": "false",
    }

    if TMDB_API_KEY and not TMDB_READ_TOKEN:
        params["api_key"] = TMDB_API_KEY

    if anio:
        params[campo_anio] = str(anio)

    for idioma in ("es-ES", "en-US"):
        params["language"] = idioma
        url = (
            f"https://api.themoviedb.org/3/search/{endpoint}?"
            + urllib.parse.urlencode(params)
        )

        req = urllib.request.Request(url, headers=_headers())

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
            if isinstance(e, urllib.error.HTTPError):
                cuerpo = e.read().decode(errors="ignore")[:200]
                log.warning(
                    "TMDB HTTP %s en %s para '%s': %s",
                    e.code,
                    endpoint,
                    query,
                    cuerpo
                )
            else:
                log.warning(
                    "TMDB error de conexión en %s para '%s': %s",
                    endpoint,
                    query,
                    str(e)
                )
            raise

        results = data.get("results", [])
        if results:
            if anio:
                campo_fecha = (
                    "first_air_date"
                    if endpoint == "tv"
                    else "release_date"
                )
                for item in results:
                    fecha = item.get(campo_fecha, "")
                    if fecha.startswith(str(anio)):
                        return item
            return results[0]

    return None


def _fetch_tmdb(query, anio=None):
    return _buscar_tmdb("movie", query, anio, "year")


def _fetch_tmdb_tv(query, anio=None):
    return _buscar_tmdb(
        "tv",
        query,
        anio,
        "first_air_date_year"
    )


async def resolver_titulo_pelicula(nombre_archivo, anio_hint=None):
    async def fetch(query, anio_archivo):
        anio = anio_hint or anio_archivo
        return await asyncio.to_thread(_fetch_tmdb, query, anio)

    fallback = nombre_pelicula_destino(nombre_archivo)

    if not tmdb_configurado():
        return fallback, False

    query, anio_archivo = _limpiar_query(nombre_archivo)
    anio = anio_hint or anio_archivo

    if not query or len(query) < 2:
        return fallback, False

    try:
        resultado = await fetch(query, anio_archivo)
    except Exception:
        return fallback, False

    if not resultado:
        return fallback, False

    titulo = (
        resultado.get("title")
        or resultado.get("original_title")
    )
    if not titulo:
        return fallback, False

    fecha = resultado.get("release_date", "")
    anio_final = fecha[:4] if len(fecha) >= 4 else anio

    if anio_final:
        nombre = sanitizar_carpeta(f"{titulo} ({anio_final})")
    else:
        nombre = sanitizar_carpeta(titulo)

    nombre = nombre or fallback
    return nombre, nombre != fallback


async def _resolver_tmdb(
    nombre,
    fallback_fn,
    fetch_fn,
    campos_titulo,
    campo_fecha,
    tipo="película"
):
    fallback = fallback_fn(nombre)

    if not tmdb_configurado():
        return fallback, False

    query, anio = _limpiar_query(nombre)

    if not query or len(query) < 2:
        log.warning("TMDB: query muy corta para %s '%s'", tipo, nombre)
        return fallback, False

    try:
        resultado = await asyncio.to_thread(fetch_fn, query, anio)
    except Exception as e:
        log.warning(
            "TMDB error buscando %s '%s' (query: '%s'): %s",
            tipo,
            nombre,
            query,
            e
        )
        return fallback, False

    if not resultado:
        log.warning(
            "TMDB sin resultados para %s '%s' (query: '%s')",
            tipo,
            nombre,
            query
        )
        return fallback, False

    titulo = None
    for campo in campos_titulo:
        titulo = resultado.get(campo)
        if titulo:
            break

    if not titulo:
        return fallback, False

    fecha = resultado.get(campo_fecha, "")
    anio_final = fecha[:4] if len(fecha) >= 4 else anio

    if anio_final:
        nombre_final = sanitizar_carpeta(f"{titulo} ({anio_final})")
    else:
        nombre_final = sanitizar_carpeta(titulo)

    nombre_final = nombre_final or fallback

    if nombre_final != fallback:
        log.info("TMDB %s: '%s' -> '%s'", tipo, nombre, nombre_final)

    return nombre_final, nombre_final != fallback


async def resolver_titulo_serie(nombre, alternativo=None):
    titulo, ok = await _resolver_tmdb(
        nombre,
        _nombre_serie_fallback,
        _fetch_tmdb_tv,
        ("name", "original_name"),
        "first_air_date",
        "serie"
    )

    if ok or not alternativo:
        return titulo, ok

    if sanitizar_carpeta(alternativo) == titulo:
        return titulo, ok

    return await _resolver_tmdb(
        alternativo,
        _nombre_serie_fallback,
        _fetch_tmdb_tv,
        ("name", "original_name"),
        "first_air_date",
        "serie"
    )
