from bank_accounts.services import ensure_cash_account

from .services import provision_business


class BusinessProvisionMiddleware:
    """
    Deja el negocio listo para operar en el primer request: bodega, unidades y
    categorías de inventario, más la caja donde se registra el efectivo.
    Ambas funciones son idempotentes.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and getattr(request.user, 'business', None) is not None:
            provision_business(request.user.business)
            ensure_cash_account(request.user.business)
        return self.get_response(request)
