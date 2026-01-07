"""
URL Configuration for detection app
"""
from django.urls import path
from . import views

urlpatterns = [
    # Authentication URLs
    path('', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    
    # Dashboard URLs
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
    # Detection URLs
    path('upload/', views.upload_image_view, name='upload_image'),
    path('history/', views.history_view, name='history'),
    path('detection/<uuid:detection_id>/', views.detection_detail_view, name='detection_detail'),
    
    # Help and Support
    path('help/', views.help_view, name='help'),
]