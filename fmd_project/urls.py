"""
Main URL Configuration for fmd_project
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', include('detection.urls')),
    path('account/login/', RedirectView.as_view(url='/', permanent=True)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Customize admin site
admin.site.site_header = "FMD Detection System Admin"
admin.site.site_title = "FMD Admin Portal"
admin.site.index_title = "Welcome to FMD Detection System Administration"
