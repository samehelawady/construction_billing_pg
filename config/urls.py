from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static
from billing.views import switch_company # or wherever you put switch_company

urlpatterns = [
    path('', lambda request: redirect('admin:index')),  # Redirect root to admin
    path('admin/', admin.site.urls),
    path('admin/switch-company/<int:company_id>/', switch_company, name='switch_company'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)