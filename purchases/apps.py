from django.apps import AppConfig

class ComprasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'purchases'
    verbose_name = 'Purchases'

    def ready(self):
        from . import signals  # noqa: F401
