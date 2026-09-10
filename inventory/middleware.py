from .services import provision_business

class BusinessProvisionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and getattr(request.user, 'business', None) is not None:
            provision_business(request.user.business)
        return self.get_response(request)