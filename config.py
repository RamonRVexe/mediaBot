import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

TV_PATH = os.getenv("TV_PATH", "/DATA/Media/TV Shows")
MOVIES_PATH = os.getenv("MOVIES_PATH", "/DATA/Media/Movies")

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
TMDB_READ_TOKEN = os.getenv("TMDB_READ_TOKEN", "").strip()

MAX_DOWNLOAD_QUEUE = int(os.getenv("MAX_DOWNLOAD_QUEUE", "50"))
MAX_CONCURRENT_DOWNLOADS = int(
    os.getenv("MAX_CONCURRENT_DOWNLOADS", "1")
)


def tmdb_configurado():
    return bool(TMDB_API_KEY or TMDB_READ_TOKEN)


def validar_config():
    faltantes = []
    if not BOT_TOKEN:
        faltantes.append("BOT_TOKEN")
    if not API_ID:
        faltantes.append("API_ID")
    if not API_HASH:
        faltantes.append("API_HASH")
    if not ADMIN_ID:
        faltantes.append("ADMIN_ID")
    if faltantes:
        raise ValueError(
            f"Faltan variables en .env: {', '.join(faltantes)}"
        )
