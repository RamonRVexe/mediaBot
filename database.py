import sqlite3
import threading

DB = "media.db"
_lock = threading.Lock()
_conn = None


def _get_conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(
            DB,
            timeout=30,
            check_same_thread=False
        )
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("PRAGMA busy_timeout=30000")
    return _conn


def init_db():
    with _lock:
        conn = _get_conn()
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS peliculas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_id INTEGER NOT NULL,
            grupo_nombre TEXT,
            mensaje_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            anio INTEGER,
            UNIQUE(grupo_id, mensaje_id)
        )
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_peliculas_nombre
        ON peliculas(nombre)
        """)

        conn.commit()


def insert_peliculas_batch(registros):
    if not registros:
        return 0

    with _lock:
        conn = _get_conn()
        cur = conn.cursor()
        nuevos = 0

        for registro in registros:
            cur.execute("""
            INSERT OR IGNORE INTO peliculas(
                grupo_id,
                grupo_nombre,
                mensaje_id,
                nombre,
                anio
            )
            VALUES(?,?,?,?,?)
            """, registro)
            nuevos += cur.rowcount

        conn.commit()
        return nuevos


def search_peliculas(texto, limite=50):
    palabras = [
        p.strip()
        for p in texto.split()
        if p.strip()
    ]

    if not palabras:
        return []

    condiciones = " AND ".join(
        ["nombre LIKE ?"] * len(palabras)
    )
    params = [f"%{p}%" for p in palabras]

    with _lock:
        conn = _get_conn()
        cur = conn.cursor()

        cur.execute(f"""
        SELECT
            id,
            nombre,
            grupo_nombre,
            anio,
            grupo_id,
            mensaje_id
        FROM peliculas
        WHERE {condiciones}
        ORDER BY nombre
        LIMIT ?
        """, (*params, limite))

        return cur.fetchall()


def count_peliculas():
    with _lock:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM peliculas")
        return cur.fetchone()[0]


def list_peliculas(pagina=1, por_pagina=30):
    offset = (pagina - 1) * por_pagina

    with _lock:
        conn = _get_conn()
        cur = conn.cursor()

        cur.execute("""
        SELECT
            id,
            nombre,
            grupo_nombre,
            anio,
            grupo_id,
            mensaje_id
        FROM peliculas
        ORDER BY nombre COLLATE NOCASE
        LIMIT ? OFFSET ?
        """, (por_pagina, offset))

        return cur.fetchall()


def get_pelicula(pelicula_id):
    with _lock:
        conn = _get_conn()
        cur = conn.cursor()

        cur.execute("""
        SELECT
            id,
            nombre,
            grupo_nombre,
            anio,
            grupo_id,
            mensaje_id
        FROM peliculas
        WHERE id = ?
        """, (pelicula_id,))

        return cur.fetchone()
