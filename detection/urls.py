"""
URL Configuration for detection app
"""
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [

    # ── Authentication ────────────────────────────────────────────────────────
    path('', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    path('password-reset/',
         auth_views.PasswordResetView.as_view(
             template_name='auth/password_reset.html',
             email_template_name='auth/password_reset_email.html',
             subject_template_name='auth/password_reset_subject.txt',
             success_url='/password-reset/done/'
         ), name='password_reset'),
    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(template_name='auth/password_reset_done.html'),
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='auth/password_reset_confirm.html',
             success_url='/password-reset-complete/'
         ), name='password_reset_confirm'),
    path('password-reset-complete/',
         auth_views.PasswordResetCompleteView.as_view(template_name='auth/password_reset_complete.html'),
         name='password_reset_complete'),

    # ── Farmer Dashboard ──────────────────────────────────────────────────────
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('upload/', views.upload_image_view, name='upload_image'),
    path('history/', views.history_view, name='history'),
    path('detection/<uuid:detection_id>/', views.detection_detail_view, name='detection_detail'),
    path('reports/', views.reports_view, name='reports'),
    path('reports/generate/<str:report_type>/', views.generate_report_view, name='generate_report'),
    path('reports/email/<str:report_type>/', views.email_report_view, name='email_report'),
    path('help/', views.help_view, name='help'),
    path('test-email-config/', views.test_email_config, name='test_email_config'),

    # ── Farmer Messaging ──────────────────────────────────────────────────────
    path('messages/', views.farmer_inbox_view, name='farmer_inbox'),

    # ── Farmer Appointments ───────────────────────────────────────────────────
    path('appointments/', views.farmer_appointments_view, name='farmer_appointments'),
    path('appointments/<uuid:appt_id>/cancel/', views.farmer_cancel_appointment, name='farmer_cancel_appointment'),

    # ── Farmer Vaccination ────────────────────────────────────────────────────
    path('vaccinations/', views.vaccination_list_view, name='vaccination_list'),
    path('vaccinations/add/', views.vaccination_add_view, name='vaccination_add'),
    path('vaccinations/<uuid:record_id>/delete/', views.vaccination_delete_view, name='vaccination_delete'),

    # ── Admin Panel ───────────────────────────────────────────────────────────
    path('admin-panel/', views.admin_dashboard_view, name='admin_dashboard'),
    path('admin-panel/uploads/', views.admin_uploads_view, name='admin_uploads'),
    path('admin-panel/vets/', views.admin_vets_view, name='admin_vets'),
    path('admin-panel/vets/register/', views.admin_register_vet_view, name='admin_register_vet'),
    path('admin-panel/notifications/', views.admin_notifications_view, name='admin_notifications'),
    path('admin-panel/reports/generate/<str:report_type>/', views.admin_generate_report_view, name='admin_generate_report'),

    # ── Veterinary Doctor Dashboard ───────────────────────────────────────────
    path('vet/', views.vet_dashboard_view, name='vet_dashboard'),
    path('vet/uploads/', views.vet_all_uploads_view, name='vet_uploads'),
    path('vet/detection/<uuid:detection_id>/', views.vet_detection_detail_view, name='vet_detection_detail'),
    path('vet/upload/', views.upload_image_view, name='vet_upload_image'),
    path('vet/reports/generate/<str:report_type>/', views.vet_generate_report_view, name='vet_generate_report'),

    # ── Vet Messaging ─────────────────────────────────────────────────────────
    path('vet/messages/', views.vet_inbox_view, name='vet_inbox'),

    # ── Vet Appointments ──────────────────────────────────────────────────────
    path('vet/appointments/', views.vet_appointments_view, name='vet_appointments'),
    path('vet/appointments/<uuid:appt_id>/respond/', views.vet_respond_appointment, name='vet_respond_appointment'),

    # ── AJAX ──────────────────────────────────────────────────────────────────
    path('api/unread-count/', views.unread_count_view, name='unread_count'),
]
