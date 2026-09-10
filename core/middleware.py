from django.shortcuts import redirect
from django.contrib import messages


class DemoReadOnlyMiddleware:
    """Bloquea operaciones de escritura para la cuenta demo (solo lectura)."""
    DEMO_BUSINESS_NAME = 'Café Mi Tierra'
    EXEMPT_PATHS = ('/login/', '/logout/', '/demo/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in self.EXEMPT_PATHS:
            return self.get_response(request)

        if (
            request.user.is_authenticated
            and hasattr(request.user, 'business')
            and request.user.business
            and request.user.business.name == self.DEMO_BUSINESS_NAME
            and request.method in ('POST', 'PUT', 'DELETE', 'PATCH')
        ):
            messages.warning(
                request,
                'Estás en modo demo. Esta acción no está permitida (solo lectura).'
            )
            referer = request.META.get('HTTP_REFERER')
            if referer:
                return redirect(referer)
            return redirect('dashboard')
        return self.get_response(request)
