# Imagen de Kivo. La misma sirve para trabajar en tu máquina y para producción:
# lo único que cambia es el comando con el que se arranca (ver docker-compose).
#
# Las dependencias se instalan con uv a partir de uv.lock, así que el
# contenedor usa exactamente las mismas versiones que tu máquina.

FROM python:3.12-slim

# uv viene de su propia imagen oficial: un binario, sin instalarlo con pip.
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /bin/

# Sin .pyc en la imagen y logs sin buffer (así se ven en vivo).
# UV_COMPILE_BYTECODE arranca más rápido; UV_LINK_MODE=copy evita el aviso de
# uv cuando la caché y el destino están en sistemas de archivos distintos.
# El entorno vive en /opt/venv, fuera de /app a propósito: en desarrollo el
# código se monta encima de /app y un .venv ahí dentro quedaría tapado por el
# de Windows. Al meterlo en el PATH, `python` y `gunicorn` ya son los del
# entorno y nadie tiene que activarlo.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# libpq para psycopg2 y netcat para esperar a que la base responda.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Las dependencias van antes del código: mientras uv.lock no cambie, Docker
# reutiliza esta capa y el build siguiente tarda segundos.
# --locked exige que el lock esté al día: si alguien tocó pyproject.toml sin
# volver a bloquear, el build falla en vez de instalar algo distinto.
# --no-dev deja fuera las dependencias de desarrollo.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY . .

RUN chmod +x /app/docker/entrypoint.sh

# La app no corre como root: si alguien se cuela, entra como un usuario pelado.
RUN useradd --create-home --shell /bin/bash kivo \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R kivo:kivo /app
USER kivo

EXPOSE 8000

# Se invoca con sh a propósito: cuando el código viene montado desde Windows,
# el permiso de ejecución del archivo se pierde y un ENTRYPOINT directo falla.
ENTRYPOINT ["/bin/sh", "/app/docker/entrypoint.sh"]

# En forma de shell a propósito, para que ${PORT} se expanda: Railway y otras
# plataformas inyectan el puerto en el que hay que escuchar. Sin plataforma,
# usa el 8000 de siempre.
CMD gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers ${WEB_CONCURRENCY:-3} \
    --timeout 60 \
    --access-logfile -
