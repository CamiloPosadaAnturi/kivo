"""
El portero: si la empresa no está al día, no pasa de la pantalla de suspensión.

Esconder los enlaces no sirve de nada si escribiendo la URL se entra igual, así
que el corte se hace aquí, antes de que cualquier vista se ejecute.
"""

from django.shortcuts import redirect
from django.urls import reverse

from .services import estado_de_acceso


class SubscriptionGateMiddleware:
    """
    Deja el estado de pago en `request.subscription` para que las plantillas
    puedan avisar, y corta el paso cuando hay una cuota vencida sin pagar.
    """

    #: rutas que siguen abiertas aunque la cuenta esté bloqueada
    RUTAS_LIBRES = ('/', '/login/', '/logout/', '/demo/', '/suspendido/',
                    '/robots.txt', '/sitemap.xml')
    PREFIJOS_LIBRES = ('/static/', '/media/', '/admin/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        estado = estado_de_acceso(getattr(request, 'user', None))
        request.subscription = estado

        if estado.blocked and not self.es_libre(request.path):
            return redirect(reverse('billing:suspended'))

        return self.get_response(request)

    def es_libre(self, path):
        return path in self.RUTAS_LIBRES or path.startswith(self.PREFIJOS_LIBRES)
