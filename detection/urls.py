"""
URL Configuration for detection app
"""
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Authentication URLs
    path('', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

        
    # Password Reset URLs
    path('password-reset/', 
         auth_views.PasswordResetView.as_view(
             template_name='auth/password_reset.html',
             email_template_name='auth/password_reset_email.html',
             subject_template_name='auth/password_reset_subject.txt',
             success_url='/password-reset/done/'
         ), 
         name='password_reset'),
    
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='auth/password_reset_done.html'
         ), 
         name='password_reset_done'),
    
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name='auth/password_reset_confirm.html',
             success_url='/password-reset-complete/'
         ), 
         name='password_reset_confirm'),
    
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='auth/password_reset_complete.html'
         ), 
         name='password_reset_complete'),
    
    # Dashboard URLs
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
    
    # Dashboard URLs
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
    # Detection URLs
    path('upload/', views.upload_image_view, name='upload_image'),
    path('history/', views.history_view, name='history'),
    path('detection/<uuid:detection_id>/', views.detection_detail_view, name='detection_detail'),
    
    # Report URLs
    path('reports/', views.reports_view, name='reports'),
    path('reports/generate/<str:report_type>/', views.generate_report_view, name='generate_report'),
    path('reports/email/<str:report_type>/', views.email_report_view, name='email_report'),
    
    # Help and Support
    path('help/', views.help_view, name='help'),
    #password-reset
    path('test-email-config/', views.test_email_config, name='test_email_config'),
    
]