# Kivo

Software de gestión para mipymes colombianas. Una sola aplicación para el dinero,
el inventario, las compras y la gente de un negocio pequeño.

Hecho con Django y PostgreSQL. El frontend son plantillas de Django con Tailwind,
sin frameworks de JavaScript.

---

## Qué hace

| Módulo | Qué resuelve |
|---|---|
| **Ingresos y egresos** | Cada movimiento de dinero, clasificado por categoría. |
| **Cuentas y caja** | Bancos y efectivo con el saldo real. No deja registrar una salida mayor a lo que hay, y si no cuadra con el banco, se concilia. |
| **Inventario** | Productos, bodegas, unidades de medida y el kárdex de cada entrada y salida. Los ajustes se hacen registrando el conteo físico: el sistema calcula la diferencia. |
| **Compras** | Proveedores, órdenes de compra y recepción de mercancía. Al recibir, el stock entra solo y la orden cambia de estado. |
| **Reportes** | Inventario, compras e ingresos/egresos, con filtros por periodo, proveedor, categoría y nivel de stock. |
| **Nómina** | Empleados, conceptos configurables y liquidación por periodo. Las prestaciones sociales se calculan solas cuando se activan en el periodo. Al pagar sale el egreso de la cuenta elegida. |
| **Cobros** | Lo que cada empresa cliente le paga a Kivo. Genera las cuotas, registra los pagos y bloquea la cuenta cuando se vence la gracia. Solo lo ve el superusuario. |
| **Empresas** | Alta de clientes nuevos: crea la empresa, su primer negocio y el usuario dueño, ya aprovisionado. Solo el superusuario. |

Cada negocio ve únicamente sus datos: todos los modelos cuelgan de un `Business`
y las vistas filtran por el negocio del usuario que entró.

**Roles.** `admin` es el administrador de un negocio (ve nómina y todo lo suyo);
`employee` tiene acceso restringido. El **superusuario** es el dueño de Kivo:
ve Empresas y Cobros, que son de la plataforma, no de ningún cliente.

---

## Arrancar en tu máquina

### Con Docker (recomendado)

No necesitas Python ni PostgreSQL instalados; solo
[Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
git clone <url-del-repo> kivo
cd kivo
docker compose up
```

Listo: <http://localhost:8000>. La primera vez tarda unos minutos armando la
imagen; después arranca en segundos. Las migraciones se aplican solas.

Crea tu usuario y, si quieres, los datos de prueba:

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_demo_data    # cuenta demo con volumen
docker compose exec web python manage.py seed_payroll      # 2 empleados y una quincena
```

Comandos del día a día:

```bash
docker compose logs -f web    # ver qué está pasando
docker compose down           # apagar
docker compose down -v        # apagar y borrar la base (ojo)
docker compose build          # rearmar la imagen tras cambiar dependencias
```

El código está montado como volumen: lo que edites se recarga solo, no hay que
reconstruir nada para cambiar una vista o una plantilla.

### Sin Docker

Las dependencias las administra [uv](https://docs.astral.sh/uv/). Se instala una
sola vez y no necesita Python previo: él mismo baja el que pida el proyecto
(3.12, anotado en `.python-version`).

```powershell
# Instalar uv en Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

En macOS o Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

Después, dentro de la carpeta del proyecto y con un PostgreSQL corriendo:

```bash
uv sync                          # crea .venv e instala todo desde uv.lock
copy .env.example .env           # y llenas los valores

uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

`uv run` usa el entorno del proyecto sin que tengas que activarlo. Si prefieres
activarlo como antes, también sirve:

```powershell
.venv\Scripts\activate
python manage.py runserver
```

En el `.env` local necesitas `DEBUG=True`. Sin eso Django arranca en modo
producción: no sirve los estáticos y rechaza dominios que no estén en
`ALLOWED_HOSTS`.

#### Manejar dependencias

```bash
uv add <paquete>                 # agregar una dependencia
uv add --dev <paquete>           # agregar una de desarrollo (no va a producción)
uv remove <paquete>              # quitarla
uv sync                          # dejar el entorno igual al lock
uv lock --upgrade                # subir versiones, a propósito y de una vez
uv lock --upgrade-package django # subir solo una
```

`uv add` actualiza `pyproject.toml`, `uv.lock` y el entorno de una sola pasada.
Los tres archivos van a git: son los que hacen que tu máquina, Docker y el
servidor instalen exactamente lo mismo.

Ya no se usa `pip install`, ni `pip install -r requirements.txt`, ni
`python -m venv`: uv se encarga del entorno y del lock.

---

## Variables de entorno

Todas viven en el `.env`, que **nunca** se sube a git ni entra en la imagen.
`.env.example` tiene la lista completa con explicaciones; lo mínimo es:

| Variable | Para qué |
|---|---|
| `SECRET_KEY` | Con esto Django firma las sesiones. Genera una propia: `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DEBUG` | `True` solo en tu máquina. En el servidor **siempre** `False`. |
| `ALLOWED_HOSTS` | Dominios desde los que se sirve la app, separados por comas. |
| `SITE_URL` | Dominio público. Lo usan las URLs canónicas, el sitemap y la vista previa al compartir. |
| `DB_NAME` `DB_USER` `DB_PASSWORD` `DB_HOST` `DB_PORT` | La base, en local. |
| `DATABASE_URL` | La base, en las plataformas de despliegue. Si viene puesta, manda ella. |

---

## Pruebas

```bash
docker compose exec web python manage.py test tests_kivo_flow
```

Sin Docker: `uv run python manage.py test tests_kivo_flow`.

Son más de 330 pruebas y cubren los flujos completos, no solo que la página
cargue: que el stock entre al recibir mercancía, que una cuenta no quede en
negativo, que la nómina calcule el neto, que un moroso quede bloqueado y que un
negocio no vea los datos de otro.

---

## Despliegue

La misma imagen de Docker sirve en cualquier parte. Dos caminos, según qué
quieras mantener.

### Camino corto: una plataforma (recomendado para empezar)

La plataforma construye el `Dockerfile`, te da la base de datos, el dominio y el
HTTPS. No administras servidores ni certificados. Es lo que conviene para el
primer despliegue y para los primeros clientes.

**Railway** cuesta 5 USD al mes en el plan Hobby, y esos 5 dólares son crédito
de consumo: una app pequeña con su Postgres cabe ahí o se pasa por poco. Pasos:

1. Sube el proyecto a GitHub (el `.env` no, que está en `.gitignore`).
2. En [railway.com](https://railway.com) crea un proyecto → **Deploy from GitHub
   repo** y escoge el repositorio. Railway detecta el `Dockerfile` solo.
3. En el mismo proyecto, **+ New** → **Database** → **Add PostgreSQL**.
4. En el servicio de la app, pestaña **Variables**, agrega:

   ```
   SECRET_KEY      (una clave nueva, larga y aleatoria)
   DEBUG           False
   DATABASE_URL    ${{Postgres.DATABASE_URL}}
   ALLOWED_HOSTS   tu-app.up.railway.app
   SITE_URL        https://tu-app.up.railway.app
   ```

   `${{Postgres.DATABASE_URL}}` es una referencia: Railway la reemplaza por los
   datos reales de la base, así no copias claves a mano.
5. **Settings** → **Networking** → **Generate Domain**. Con ese dominio ajusta
   `ALLOWED_HOSTS` y `SITE_URL`, que al principio no los conocías.
6. Cuando termine el despliegue, crea tu usuario desde la consola del servicio:

   ```bash
   python manage.py createsuperuser
   ```

Las migraciones y los estáticos los hace el `entrypoint.sh` en cada arranque, así
que no hay que acordarse de correrlos. Railway inyecta la variable `PORT` y el
contenedor la respeta.

La imagen instala las dependencias con `uv sync --locked`, así que si alguien
toca `pyproject.toml` y se olvida de `uv lock`, el build falla en vez de
desplegar versiones distintas a las que probaste.

De ahí en adelante cada `git push` a la rama principal vuelve a desplegar.

**Render** es la alternativa conocida, pero ojo con su plan gratis para algo
real: el servicio se duerme a los 15 minutos sin visitas y **la base de datos
gratuita se borra 30 días después de creada**. Para probar sirve; para un
cliente que paga, no.

### Camino largo: tu propio servidor (VPS)

Más barato en el largo plazo y con control total, a cambio de que el
mantenimiento es tuyo: actualizaciones del sistema, respaldos, monitoreo. Un
Hetzner CX22 anda por unos 4–5 USD al mes.

```bash
# En el servidor, con Docker ya instalado
git clone <url-del-repo> kivo && cd kivo
cp .env.example .env
nano .env          # SECRET_KEY, DEBUG=False, ALLOWED_HOSTS, DB_*, DOMINIO

docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

`docker-compose.prod.yml` levanta tres contenedores: la app con gunicorn, el
Postgres, y **Caddy** al frente, que pide y renueva el certificado HTTPS solo.
Antes de subirlo apunta el dominio de `DOMINIO` a la IP del servidor.

Para actualizar:

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

**Respaldos.** Esto no lo hace nadie por ti en un VPS. Un volcado diario:

```bash
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U $DB_USER $DB_NAME > respaldo-$(date +%F).sql
```

Guárdalo **fuera** del servidor. Un respaldo que vive en la misma máquina que la
base no es un respaldo.

### Antes de abrirle la puerta a un cliente

```bash
uv run python manage.py check --deploy
```

Revisa la lista de Django y avisa lo que falte. Lo que no se negocia:

- `DEBUG=False`. Con `True`, cualquier error le muestra al visitante el código y
  las variables de entorno.
- `SECRET_KEY` nueva y distinta de la de desarrollo.
- `ALLOWED_HOSTS` con tu dominio, no con `*`.
- Respaldos andando y probados (restaura uno, no te fíes de que el archivo exista).
- `SECURE_HSTS_SECONDS` en `31536000` **solo** cuando ya estés seguro de que el
  dominio va siempre por https. Es difícil de revertir.

---

## Comandos propios

```bash
uv run python manage.py seed_demo_data                      # datos demo con volumen (100 de cada cosa)
uv run python manage.py seed_demo_data --reset              # los borra y los vuelve a sembrar
uv run python manage.py seed_payroll                        # 2 empleados y una quincena liquidada
uv run python manage.py seed_payroll --negocio 2 --pagar    # además la paga
uv run python manage.py seed_payroll --limpiar              # borra esos datos de ejemplo
```

Dentro de Docker, lo mismo pero con `docker compose exec web python manage.py ...`:
en la imagen el entorno ya está activo, así que ahí no hace falta el `uv run`.

Los de sembrado son para probar. En una base de un cliente real no se corren.

---

## Cómo está organizado

```
config/         settings, urls, wsgi
core/           categorías, mixins de multi-tenencia, formularios con estilo
users/          empresa, negocio, usuario, alta de clientes
bank_accounts/  cuentas, caja, saldos y conciliación
incomes/        ingresos
expenses/       egresos
inventory/      productos, bodegas, movimientos, kárdex
purchases/      proveedores, órdenes, recepciones, facturas
payroll/        empleados, conceptos, periodos, liquidaciones
billing/        planes, cuotas y bloqueo por falta de pago
reports/        reportes con filtros
templates/      plantillas, una carpeta por app
docker/         entrypoint y Caddyfile
pyproject.toml  dependencias del proyecto
uv.lock         las versiones exactas de todo, resueltas por uv
```

Cada app sigue la misma división: `models.py` para los datos, `services.py` para
las reglas de negocio, `forms.py` para la validación, `views.py` para el
pegamento. Las plantillas no hacen cálculos.

Tres piezas que conviene conocer antes de tocar código:

- **`TenantScopedMixin`** (en `core/mixins.py`) filtra los queryset por el
  negocio del usuario y marca el negocio al crear. Si una vista nueva no lo usa,
  está filtrando datos de todos.
- **`apply_stock_movement`** y **`apply_stock_count`** (en `inventory/services.py`)
  son la única puerta para mover inventario. Crear un `InventoryMovement` a mano
  deja el kárdex descuadrado.
- **`SubscriptionGateMiddleware`** (en `billing/middleware.py`) corre antes de
  cualquier vista y corta el paso a las empresas en mora. Esconder un enlace no
  protege nada; el corte va en el backend.

---

Juan Camilo Posada Anturi · Dagua, Valle del Cauca
