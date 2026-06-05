# MediaBot

Bot de Telegram para descargar series y películas desde grupos/canales usando tu cuenta de Telegram (Telethon) y organizarlas en carpetas listas para Plex, Jellyfin o Kodi.

## ¿Qué hace?

| Función | Descripción |
|---------|-------------|
| **Series** | Descarga episodios de un grupo dedicado (1 grupo = 1 serie), detecta temporadas automáticamente y guarda en `TV Shows/Nombre/Season 01/` |
| **Películas** | Indexa grupos con muchas películas en SQLite, permite buscar/listar y descargar por nombre |
| **Organización** | Renombra episodios (`Serie - S01E01.mkv`) y películas (`Película/Película.mkv`) |
| **Conversión** | Remux a MKV con ffmpeg (sin re-codificar, copia directa de streams) |
| **Progreso** | Cola de descargas con barras de progreso consultables en cualquier momento |
| **Seguridad** | Solo responde al `ADMIN_ID` configurado |

## Requisitos

- **Python 3.10+**
- **ffmpeg** instalado y disponible en el `PATH`
- Cuenta de Telegram + API credentials en [my.telegram.org](https://my.telegram.org)
- Bot de Telegram creado con [@BotFather](https://t.me/BotFather)
- Acceso a los grupos/canales de donde quieres descargar (con la cuenta de Telethon)

### Instalar ffmpeg

**Windows (winget):**
```powershell
winget install Gyan.FFmpeg
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt update && sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/RamonRVexe/mediaBot.git
cd mediaBot
```

### 2. Crear entorno virtual (recomendado)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Copia la plantilla y edítala:

```bash
cp .env.example .env
```

| Variable | Descripción |
|----------|-------------|
| `BOT_TOKEN` | Token del bot desde BotFather |
| `API_ID` | API ID de my.telegram.org |
| `API_HASH` | API Hash de my.telegram.org |
| `ADMIN_ID` | Tu ID numérico de Telegram (usa [@userinfobot](https://t.me/userinfobot)) |
| `TV_PATH` | Ruta donde guardar series |
| `MOVIES_PATH` | Ruta donde guardar películas |

**Ejemplo Windows:**
```env
TV_PATH=F:\Media\TV Shows
MOVIES_PATH=F:\Media\Movies
```

**Ejemplo Linux:**
```env
TV_PATH=/DATA/Media/TV Shows
MOVIES_PATH=/DATA/Media/Movies
```

> ⚠️ **Nunca subas `.env` a GitHub.** Ya está incluido en `.gitignore`.

### 5. Autenticar la cuenta de Telethon (solo la primera vez)

El bot usa tu cuenta personal de Telegram para descargar archivos de grupos. Ejecuta:

```bash
python login.py
```

Te pedirá tu número de teléfono y el código de verificación. Esto crea el archivo `user_session.session` que el bot reutiliza.

### 6. Iniciar el bot

```bash
python bot.py
```

Deberías ver:
```
✅ ffmpeg disponible
🤖 Bot iniciado...
```

Abre Telegram, busca tu bot y envía `/start`.

## Comandos

### Series

Un grupo de Telegram = una serie. No hace falta indexar.

```
/download_series
```

1. Elige el número del grupo
2. Escribe el nombre de la carpeta (ej: `Breaking Bad`)
3. Elige temporadas:
   - `A` → todas
   - `1,3,5` → solo esas
   - `E:2,4` → todas excepto la 2 y la 4

### Películas

Para grupos con muchas películas mezcladas:

```
/index_movies     → indexar un grupo (solo películas, ignora episodios)
/list             → ver películas indexadas (página 1)
/list 2           → página 2
/search matrix    → buscar por palabras
/download 0       → descargar el resultado #0
```

### Descargas y utilidades

```
/downloads        → cola activa + progreso + recientes
/status           → estado del bot
/groups           → listar tus chats/grupos
/paths            → rutas configuradas
/cancel           → cancelar conversación activa
```

## Estructura de archivos descargados

```
TV Shows/
└── Breaking Bad/
    └── Season 01/
        ├── Breaking Bad - S01E01.mkv
        └── Breaking Bad - S01E02.mkv

Movies/
└── Inception (2010)/
    └── Inception (2010).mkv
```

## Patrones de episodios detectados

El bot reconoce estos formatos en los nombres de archivo:

- `S01E01`, `S01.E01`, `S01 EP01`
- `S 01 E 01`
- `T01E01`, `T01-E01`
- `1x01`, `1×01`
- `Temporada 1 Episodio 5`
- `Temp 1 Cap 5`
- `EP 5 T 1` (invertido)

## Arquitectura del proyecto

```
mediaBot/
├── bot.py                 # Bot de Telegram (comandos e interfaz)
├── config.py              # Carga variables desde .env
├── database.py            # SQLite para índice de películas
├── login.py               # Autenticación inicial de Telethon
├── downloader/
│   ├── series.py          # Descarga y detección de episodios
│   ├── movies.py          # Descarga de películas
│   ├── indexer.py         # Indexado de grupos de películas
│   ├── tracker.py         # Cola y progreso de descargas
│   └── utils.py           # ffmpeg, progreso, utilidades
├── requirements.txt
├── .env.example
└── .gitignore
```

### ¿Por qué dos librerías de Telegram?

- **python-telegram-bot** → interfaz del bot (comandos, mensajes)
- **Telethon** → descarga real de archivos con tu cuenta de usuario

Los bots normales de Telegram no pueden descargar archivos grandes de grupos privados; Telethon actúa como tu cuenta.

## Solución de problemas

### `database is locked`

- Cierra DB Browser u otro programa que tenga abierto `media.db`
- Asegúrate de que solo hay **una instancia** del bot corriendo
- Si persiste, borra `media.db-wal` y `media.db-shm` con el bot detenido

### El bot no responde

- Verifica que tu `ADMIN_ID` es correcto (solo ese usuario puede usarlo)
- Comprueba que `BOT_TOKEN` es válido

### `ffmpeg no está instalado`

Instala ffmpeg y reinicia la terminal. Verifica con:
```bash
ffmpeg -version
```

### Error de sesión Telethon

Borra `user_session.session` y vuelve a ejecutar `python login.py`.

### No encuentra episodios / temporadas

- El nombre del archivo debe contener un patrón reconocible (`S01E01`, `1x01`, etc.)
- Debes ser miembro del grupo con la cuenta usada en `login.py`

### Descarga lenta o flood de Telegram

Telegram limita la velocidad de descarga. El bot incluye pausas entre archivos para evitar bloqueos.

## Ejecutar en segundo plano (Linux)

Con **systemd**, crea `/etc/systemd/system/mediabot.service`:

```ini
[Unit]
Description=MediaBot Telegram
After=network.target

[Service]
Type=simple
User=tu_usuario
WorkingDirectory=/ruta/a/mediaBot
ExecStart=/ruta/a/mediaBot/venv/bin/python bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable mediabot
sudo systemctl start mediabot
sudo systemctl status mediabot
```

## Seguridad

- Regenera el `BOT_TOKEN` en BotFather si alguna vez se expuso
- No compartas `user_session.session` (equivale a tu cuenta de Telegram)
- El bot solo acepta comandos del `ADMIN_ID` configurado
- Usa el bot solo con contenido que tengas derecho a descargar

## Licencia

Uso personal. Ajusta la licencia según prefieras al publicar el repo.
