"""
Root URL configuration for avofinance.

/api/v1/  → finance endpoints
/api/auth/ → auth endpoints
/admin/   → Django admin
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

api_v1_patterns = [
    path('accounts/', include('apps.accounts.urls')),
    path('finances/', include('apps.finances.urls')),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(api_v1_patterns)),
    path('api/auth/', include('rest_framework.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
