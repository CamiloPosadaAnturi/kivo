from django.core.exceptions import PermissionDenied

class TenantScopedMixin:
    """
    Filters querysets by user.business and automatically sets business on creation.
    """
    tenant_field = 'business'

    def get_tenant(self):
        user = getattr(self.request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            return getattr(user, 'business', None)
        return None

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = self.get_tenant()
        if tenant is not None:
            return qs.filter(**{self.tenant_field: tenant})
        return qs.none()

    def form_valid(self, form):
        tenant = self.get_tenant()
        setattr(form.instance, self.tenant_field, tenant)
        return super().form_valid(form)

class RoleRequiredMixin:
    """
    Restricts view access to specific roles (default 'admin').
    """
    required_roles = ('admin',)

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, 'role') or request.user.role not in self.required_roles:
            raise PermissionDenied('No permission.')
        return super().dispatch(request, *args, **kwargs)
