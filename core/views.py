from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from .models import Category
from .forms import CategoryForm


class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = 'core/category_list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return Category.objects.filter(
            business=self.request.user.business
        ).order_by('type', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        context['income_categories'] = qs.filter(type=Category.INCOME)
        context['expense_categories'] = qs.filter(type=Category.EXPENSE)
        context['active_tab'] = self.request.GET.get('tab', 'income')
        return context


class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'core/category_form.html'
    success_url = reverse_lazy('core:category_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.request.user.business
        return kwargs

    def form_valid(self, form):
        form.instance.business = self.request.user.business
        messages.success(self.request, 'Categoría creada exitosamente.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Nueva categoría'
        context['submit_text'] = 'Crear categoría'
        return context


class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'core/category_form.html'
    success_url = reverse_lazy('core:category_list')

    def get_queryset(self):
        return Category.objects.filter(business=self.request.user.business)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.request.user.business
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Categoría actualizada exitosamente.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Editar categoría'
        context['submit_text'] = 'Guardar cambios'
        return context


class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    template_name = 'core/category_confirm_delete.html'
    success_url = reverse_lazy('core:category_list')

    def get_queryset(self):
        return Category.objects.filter(business=self.request.user.business)

    def form_valid(self, form):
        category = self.get_object()
        has_transactions = category.incomes.exists() or category.expenses.exists()
        if has_transactions:
            category.is_active = False
            category.save()
            messages.warning(
                self.request,
                f'La categoría "{category.name}" tiene transacciones asociadas. '
                'Se ha desactivado en lugar de eliminarla.'
            )
        else:
            category.delete()
            messages.success(self.request, 'Categoría eliminada exitosamente.')
        return redirect(self.get_success_url())


# ---------------------------------------------------------------------------
# SEO: robots.txt y sitemap.xml
# ---------------------------------------------------------------------------

def robots_txt(request):
    """
    Solo el sitio público es indexable. Todo lo que va detrás del login se
    bloquea aquí y además con <meta robots> en base.html.
    """
    sitemap = request.build_absolute_uri(reverse('sitemap_xml'))
    lineas = [
        'User-agent: *',
        'Allow: /$',
        'Disallow: /dashboard/',
        'Disallow: /incomes/',
        'Disallow: /expenses/',
        'Disallow: /categories/',
        'Disallow: /bank-accounts/',
        'Disallow: /inventario/',
        'Disallow: /compras/',
        'Disallow: /reportes/',
        'Disallow: /admin/',
        'Disallow: /login/',
        'Disallow: /logout/',
        'Disallow: /demo/',
        '',
        f'Sitemap: {sitemap}',
    ]
    return HttpResponse('\n'.join(lineas), content_type='text/plain; charset=utf-8')


def sitemap_xml(request):
    """Sitemap de las páginas públicas. Hoy es la portada y sus secciones."""
    base = request.build_absolute_uri(reverse('index')).rstrip('/')
    hoy = timezone.localdate().isoformat()
    urls = [
        (f'{base}/', '1.0', 'weekly'),
        (f'{base}/#funcionalidades', '0.8', 'monthly'),
        (f'{base}/#modulos', '0.8', 'monthly'),
        (f'{base}/#proximamente', '0.5', 'monthly'),
    ]
    cuerpo = ''.join(
        f'<url><loc>{loc}</loc><lastmod>{hoy}</lastmod>'
        f'<changefreq>{freq}</changefreq><priority>{prio}</priority></url>'
        for loc, prio, freq in urls
    )
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           f'{cuerpo}</urlset>')
    return HttpResponse(xml, content_type='application/xml')
