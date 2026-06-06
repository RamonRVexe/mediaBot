# MediaBot

Bot de Telegram para descargar series y películas desde grupos/canales usando tu cuenta de Telegram (Telethon) y organizarlas en carpetas listas para Plex, Jellyfin o Kodi.

## ¿Qué hace?

| Función | Descripción |
|---------|-------------|
| **Series** | Descarga episodios de un grupo dedicado (1 grupo = 1 serie), detecta temporadas automáticamente y guarda en `TV Shows/Nombre/Season 01/` |
| **Películas** | Indexa grupos con muchas películas en SQLite, permite buscar/listar y descargar por nombre |
| **Organización** | Renombra episodios (`Serie - S01E01.mkv`) y películas (`Película (Año)/Película (Año).mkv`) |
| **TMDB** | Renombra películas y series con título y año correctos usando The Movie Database (opcional) |
| **Conversión** | Remux a MKV con ffmpeg (sin re-codificar, copia directa de streams) |
| **Progreso** | Cola de descargas con barras de progreso y botones inline |
| **Reanudación** | Si se corta una descarga, retoma desde el archivo `.part` |
| **Cancelación** | Cancela descargas activas, individuales o series completas |
| **Cola limitada** | Evita saturar Telegram con demasiadas descargas simultáneas |
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
| `TMDB_API_KEY` | *(Opcional)* API key de [TMDB](https://www.themoviedb.org/settings/api) para renombrar películas y series |
| `MAX_DOWNLOAD_QUEUE` | Máximo de películas en cola (default: `50`) |
| `MAX_CONCURRENT_DOWNLOADS` | Descargas de películas en paralelo (default: `1`) |

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

## Instalación con Docker

Alternativa recomendada para dejar el bot corriendo siempre en un servidor Linux. Incluye Python, ffmpeg y dependencias en la imagen.

### Requisitos

- [Docker](https://docs.docker.com/get-docker/) y Docker Compose v2
- Archivos `.env` y `user_session.session` (genera la sesión con `python login.py` en tu PC o en el servidor)

### 1. Clonar y preparar

```bash
git clone https://github.com/RamonRVexe/mediaBot.git
cd mediaBot
cp .env.example .env
```

Edita `.env`. **Dentro del contenedor** las rutas de medios son fijas:

```env
TV_PATH=/media/TV Shows
MOVIES_PATH=/media/Movies
```

Copia `user_session.session` al directorio del proyecto si ya lo generaste en otro equipo.

### 2. Crear carpetas de medios en el servidor

```bash
sudo mkdir -p "/DATA/Media/TV Shows"
sudo mkdir -p "/DATA/Media/Movies"
sudo chown -R $USER:$USER "/DATA/Media"
```

Si tus rutas son distintas, edita la parte izquierda de los volúmenes en `docker-compose.yml`:

```yaml
volumes:
  - .:/app
  - /DATA/Media/TV Shows:/media/TV Shows   # ruta real en el host
  - /DATA/Media/Movies:/media/Movies       # ruta real en el host
```

La parte derecha (`/media/...`) debe coincidir con `TV_PATH` y `MOVIES_PATH` del `.env`.

### 3. Arrancar

```bash
docker compose up -d --build
```

La primera vez construye la imagen (1–3 min). Deberías ver en los logs:

```bash
docker compose logs -f
```

```
✅ ffmpeg disponible
🤖 Bot iniciado...
```

### Comandos útiles

| Acción | Comando |
|--------|---------|
| Ver logs | `docker compose logs -f` |
| Reiniciar | `docker compose restart` |
| Parar | `docker compose down` |
| Actualizar tras cambios | `docker compose up -d --build` |

Con `restart: unless-stopped` el contenedor vuelve a arrancar solo si reinicias el servidor.

### Actualizar el bot

```bash
cd mediaBot
git pull   # o copia los archivos nuevos
docker compose up -d --build
```

No borres `.env`, `user_session.session` ni `media.db` al actualizar.

### CasaOS

También puedes importar el `docker-compose.yml` desde **App Store → Install a customized app → Import**. Asegúrate de que el proyecto (con `.env` y `user_session.session`) esté en la carpeta montada como `.:/app` — por ejemplo `/DATA/AppData/mediabot`.

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
/list             → ver películas indexadas con botones ⬇
/list 2           → página 2
/search matrix    → buscar con botones de descarga
/download 0       → descargar por número (alternativo a botones)
```

En `/list` y `/search` cada película tiene un botón **⬇** para encolarla al instante.

### Descargas y utilidades

```
/downloads                  → cola activa + progreso + recientes
/cancel_download            → cancelar todas las descargas activas
/cancel_download 5          → cancelar la descarga #5
/cancel_download serie Nombre → cancelar descarga de una serie
/status                     → estado del bot
/groups                     → listar tus chats/grupos
/paths                      → rutas configuradas
/cancel                     → cancelar conversación activa
```

### Reanudar descargas interrumpidas

Si una descarga se corta (error, cancelación, reinicio), el archivo parcial queda como `.part`. Al volver a descargar la misma película o episodio, Telethon retoma desde donde se quedó.

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
│   ├── queue.py           # Cola limitada de películas
│   ├── tmdb.py            # Metadatos TMDB para renombrar
│   └── utils.py           # ffmpeg, progreso, reanudación
├── requirements.txt
├── Dockerfile             # Imagen Docker (Python + ffmpeg)
├── docker-compose.yml     # Despliegue en servidor o CasaOS
├── .dockerignore
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

### Docker: el contenedor no arranca

- Revisa los logs: `docker compose logs`
- Comprueba que `user_session.session` existe en la carpeta del proyecto (no subas solo la carpeta `.git` ni `venv`)
- Verifica que `TV_PATH` y `MOVIES_PATH` en `.env` usan las rutas del contenedor (`/media/...`), no las del host
- Asegúrate de que solo hay **una instancia** del bot (evita `database is locked`)

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
