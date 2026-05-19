from django.urls import path

from .views import AuditLogListView, DashboardView, health_check, HomeView, SchoolBackupDownloadView, secure_media_serve, service_worker, web_manifest

app_name = 'core'

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('health/', health_check, name='health-check'),
    path('manifest.webmanifest', web_manifest, name='web-manifest'),
    path('service-worker.js', service_worker, name='service-worker'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('dashboard/backup/', SchoolBackupDownloadView.as_view(), name='school-backup-download'),
    path('security/audit-logs/', AuditLogListView.as_view(), name='audit-log-list'),
    path('media/<path:path>', secure_media_serve, name='secure-media-serve'),
]
