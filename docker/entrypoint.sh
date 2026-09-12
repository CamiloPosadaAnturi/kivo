#!/bin/sh
# Lo que pasa cada vez que arranca el contenedor, antes de servir nada:
# esperar la base, aplicar migraciones y juntar los estáticos.
#
# Todo es idempotente: si ya está hecho, no hace nada. Así un redespliegue
# no necesita que entres a correr comandos a mano.

set -e

esperar_base() {
    # Con DATABASE_URL se saca el host y el puerto de ahí; si no, del .env.
    if [ -n "$DATABASE_URL" ]; then
        host=$(python -c "import os,urllib.parse as u; print(u.urlparse(os.environ['DATABASE_URL']).hostname or '')")
        puerto=$(python -c "import os,urllib.parse as u; print(u.urlparse(os.environ['DATABASE_URL']).port or 5432)")
    else
        host="$DB_HOST"
        puerto="${DB_PORT:-5432}"
    fi

    [ -z "$host" ] && return 0

    echo "Esperando la base de datos en $host:$puerto..."
    intentos=0
    while ! nc -z "$host" "$puerto" 2>/dev/null; do
        intentos=$((intentos + 1))
        if [ "$intentos" -ge 60 ]; then
            echo "La base no respondió en 60 intentos. Reviso que esté arriba y las variables del .env."
            exit 1
        fi
        sleep 1
    done
    echo "Base lista."
}

esperar_base

if [ "${KIVO_SKIP_MIGRATE:-0}" != "1" ]; then
    echo "Aplicando migraciones..."
    python manage.py migrate --noinput
fi

if [ "${KIVO_SKIP_COLLECTSTATIC:-0}" != "1" ]; then
    echo "Recogiendo archivos estáticos..."
    python manage.py collectstatic --noinput --clear
fi

echo "Arrancando: $*"
exec "$@"
