"""
Configuración para correr las pruebas: SQLite en memoria y sin nada de lo que
solo tiene sentido detrás de un dominio real.
"""
from .settings import *  # noqa

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# El cliente de pruebas habla http contra "testserver": si Django redirige a
# https o exige cookies seguras, cada prueba se va en un 301 y no prueba nada.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

# Hashear contraseñas con el algoritmo lento multiplica el tiempo de la suite.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
