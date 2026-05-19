from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('students.urls')),
    path('', include('academics.urls')),
    path('', include('attendance.urls')),
    path('', include('finance.urls')),
    path('reports/', include('reports.urls')),
    path('cbc/', include('cbc.urls')),
    path('communication/', include('communication.urls')),
    path('', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
