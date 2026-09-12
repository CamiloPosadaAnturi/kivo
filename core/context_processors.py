from django.conf import settings


def site(request):
    """Datos del sitio disponibles en todas las plantillas, para el SEO."""
    return {
        'SITE_URL': settings.SITE_URL.rstrip('/'),
        'SITE_NAME': settings.SITE_NAME,
        'SITE_DESCRIPTION': settings.SITE_DESCRIPTION,
        'CANONICAL_URL': request.build_absolute_uri(request.path),
    }
