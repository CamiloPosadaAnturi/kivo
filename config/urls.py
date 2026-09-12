from core.views import robots_txt, sitemap_xml
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap_xml, name='sitemap_xml'),

    path('admin/', admin.site.urls),
    path('', include('users.urls')),
    path('categories/', include('core.urls')),
    path('incomes/', include('incomes.urls')),
    path('expenses/', include('expenses.urls')),
    path('bank-accounts/', include('bank_accounts.urls')),
    path('inventario/', include('inventory.urls')),
    path('compras/', include('purchases.urls')),
    path('nomina/', include('payroll.urls')),
    path('reportes/', include('reports.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
