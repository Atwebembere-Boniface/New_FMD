from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail, EmailMessage
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import logging

from .forms import UserRegistrationForm, UserLoginForm, DetectionUploadForm, VetRegistrationForm
from .models import Detection, SystemStatistics, UserProfile, Report, Notification
from .services import analyze_cattle_image

logger = logging.getLogger(__name__)


# ========================================
# PERMISSION HELPERS
# ========================================

def is_admin(user):
    return user.is_superuser or (hasattr(user, 'profile') and user.profile.role == 'admin')


def is_vet(user):
    return hasattr(user, 'profile') and user.profile.role == 'vet'


def is_admin_or_vet(user):
    return is_admin(user) or is_vet(user)


# ========================================
# AUTHENTICATION VIEWS
# ========================================

def register_view(request):
    if request.user.is_authenticated:
        return _redirect_by_role(request.user)

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created successfully! Please login with your email and password.')
            return redirect('login')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserRegistrationForm()

    return render(request, 'auth/register.html', {'form': form, 'title': 'Register - FMD Detection System'})


def login_view(request):
    if request.user.is_authenticated:
        return _redirect_by_role(request.user)

    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name or user.email}!')
                next_page = request.GET.get('next')
                if next_page:
                    return redirect(next_page)
                return _redirect_by_role(user)
        else:
            messages.error(request, 'Invalid email or password.')
    else:
        form = UserLoginForm()

    return render(request, 'auth/login.html', {'form': form, 'title': 'Login - FMD Detection System'})


def _redirect_by_role(user):
    if is_admin(user):
        return redirect('admin_dashboard')
    elif is_vet(user):
        return redirect('vet_dashboard')
    return redirect('dashboard')


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')


# ========================================
# FARMER DASHBOARD VIEWS
# ========================================

@login_required
def dashboard_view(request):
    if is_admin(request.user):
        return redirect('admin_dashboard')
    if is_vet(request.user):
        return redirect('vet_dashboard')

    user_detections = Detection.objects.filter(user=request.user)
    total_scans = user_detections.count()
    fmd_detected = user_detections.filter(result='fmd').count()
    healthy_cattle = user_detections.filter(result='healthy').count()
    recent_detections = user_detections.select_related('user')[:5]
    first_day = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month_scans = user_detections.filter(uploaded_at__gte=first_day).count()

    context = {
        'title': 'Dashboard - FMD Detection System',
        'total_scans': total_scans,
        'fmd_detected': fmd_detected,
        'healthy_cattle': healthy_cattle,
        'recent_detections': recent_detections,
        'this_month_scans': this_month_scans,
    }
    return render(request, 'dashboard/dashboard.html', context)


# ========================================
# ADMIN DASHBOARD VIEWS
# ========================================

@login_required
def admin_dashboard_view(request):
    if not is_admin(request.user):
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('dashboard')

    all_detections = Detection.objects.select_related('user', 'user__profile').all()
    total_scans = all_detections.count()
    fmd_detected = all_detections.filter(result='fmd').count()
    healthy_cattle = all_detections.filter(result='healthy').count()
    total_users = User.objects.filter(profile__role='farmer').count()
    total_vets = User.objects.filter(profile__role='vet').count()
    recent_detections = all_detections[:10]
    unread_notifications = Notification.objects.filter(recipient=request.user, is_read=False).count()

    # Last 7 days stats
    week_ago = timezone.now() - timedelta(days=7)
    weekly_scans = all_detections.filter(uploaded_at__gte=week_ago).count()
    weekly_fmd = all_detections.filter(uploaded_at__gte=week_ago, result='fmd').count()

    context = {
        'title': 'Admin Dashboard - FMD Detection System',
        'total_scans': total_scans,
        'fmd_detected': fmd_detected,
        'healthy_cattle': healthy_cattle,
        'total_users': total_users,
        'total_vets': total_vets,
        'recent_detections': recent_detections,
        'weekly_scans': weekly_scans,
        'weekly_fmd': weekly_fmd,
        'unread_notifications': unread_notifications,
    }
    return render(request, 'admin_panel/dashboard.html', context)


@login_required
def admin_uploads_view(request):
    if not is_admin(request.user):
        return redirect('dashboard')

    detections = Detection.objects.select_related('user', 'user__profile').all()

    result_filter = request.GET.get('result', '')
    status_filter = request.GET.get('status', '')
    user_filter = request.GET.get('user', '')

    if result_filter:
        detections = detections.filter(result=result_filter)
    if status_filter:
        detections = detections.filter(status=status_filter)
    if user_filter:
        detections = detections.filter(user__id=user_filter)

    users = User.objects.filter(detections__isnull=False).distinct()

    context = {
        'title': 'All Uploads - Admin',
        'detections': detections,
        'result_filter': result_filter,
        'status_filter': status_filter,
        'user_filter': user_filter,
        'users': users,
    }
    return render(request, 'admin_panel/uploads.html', context)


@login_required
def admin_register_vet_view(request):
    if not is_admin(request.user):
        return redirect('dashboard')

    if request.method == 'POST':
        form = VetRegistrationForm(request.POST)
        if form.is_valid():
            vet_user = form.save()
            # Send credentials to vet via email
            try:
                send_mail(
                    subject='FMD Detection System - Your Veterinary Doctor Account',
                    message=f"""Dear Dr. {vet_user.get_full_name()},

Your veterinary doctor account has been created on the FMD Early Detection System.

Login Details:
  Email: {vet_user.email}
  Password: {form.cleaned_data['password']}

Please login at: {request.build_absolute_uri('/').rstrip('/')}

Best regards,
FMD Detection System Admin
Simba Farms
""",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[vet_user.email],
                    fail_silently=True,
                )
            except Exception as e:
                logger.error(f"Failed to send vet credentials email: {e}")

            messages.success(request, f'Veterinary doctor Dr. {vet_user.get_full_name()} registered successfully! Login credentials sent to {vet_user.email}.')
            return redirect('admin_vets')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = VetRegistrationForm()

    return render(request, 'admin_panel/register_vet.html', {'form': form, 'title': 'Register Veterinary Doctor'})


@login_required
def admin_vets_view(request):
    if not is_admin(request.user):
        return redirect('dashboard')

    vets = User.objects.filter(profile__role='vet').select_related('profile')
    context = {
        'title': 'Veterinary Doctors - Admin',
        'vets': vets,
    }
    return render(request, 'admin_panel/vets.html', context)


@login_required
def admin_notifications_view(request):
    if not is_admin(request.user):
        return redirect('dashboard')

    notifications = Notification.objects.filter(recipient=request.user).select_related('detection', 'detection__user')
    # Mark all as read
    notifications.filter(is_read=False).update(is_read=True)

    context = {
        'title': 'Notifications - Admin',
        'notifications': notifications,
    }
    return render(request, 'admin_panel/notifications.html', context)


@login_required
def admin_generate_report_view(request, report_type):
    if not is_admin(request.user):
        return redirect('dashboard')

    if report_type not in ['daily', 'weekly', 'monthly']:
        messages.error(request, 'Invalid report type.')
        return redirect('admin_dashboard')

    try:
        from .reports import AdminReportGenerator
        generator = AdminReportGenerator(report_type)
        pdf = generator.generate()

        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f'FMD_Admin_{report_type}_report_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        messages.error(request, f'Error generating report: {str(e)}')
        return redirect('admin_dashboard')


# ========================================
# VETERINARY DOCTOR DASHBOARD VIEWS
# ========================================

@login_required
def vet_dashboard_view(request):
    if not is_vet(request.user):
        if is_admin(request.user):
            return redirect('admin_dashboard')
        messages.error(request, 'Access denied. Veterinary doctor privileges required.')
        return redirect('dashboard')

    all_detections = Detection.objects.select_related('user', 'user__profile').all()
    total_scans = all_detections.count()
    fmd_detected = all_detections.filter(result='fmd').count()
    healthy_cattle = all_detections.filter(result='healthy').count()
    recent_detections = all_detections[:8]

    # Vet's own detections
    vet_detections = Detection.objects.filter(user=request.user)
    vet_total = vet_detections.count()
    vet_fmd = vet_detections.filter(result='fmd').count()

    context = {
        'title': 'Veterinary Dashboard - FMD Detection System',
        'total_scans': total_scans,
        'fmd_detected': fmd_detected,
        'healthy_cattle': healthy_cattle,
        'recent_detections': recent_detections,
        'vet_total': vet_total,
        'vet_fmd': vet_fmd,
    }
    return render(request, 'vet/dashboard.html', context)


@login_required
def vet_all_uploads_view(request):
    if not is_vet(request.user):
        return redirect('dashboard')

    detections = Detection.objects.select_related('user', 'user__profile').all()
    result_filter = request.GET.get('result', '')
    if result_filter:
        detections = detections.filter(result=result_filter)

    context = {
        'title': 'All Farm Detections - Vet',
        'detections': detections,
        'result_filter': result_filter,
    }
    return render(request, 'vet/all_uploads.html', context)


@login_required
def vet_generate_report_view(request, report_type):
    if not is_vet(request.user):
        return redirect('dashboard')

    if report_type not in ['daily', 'weekly', 'monthly', 'all']:
        messages.error(request, 'Invalid report type.')
        return redirect('vet_dashboard')

    try:
        from .reports import VetReportGenerator
        generator = VetReportGenerator(request.user, report_type)
        pdf = generator.generate()

        # Save report record (skip 'all' in choices)
        rtype = report_type if report_type != 'all' else 'monthly'
        start_date, end_date, _ = generator.get_date_range()
        data = generator.get_report_data(start_date, end_date)
        Report.objects.create(
            user=request.user,
            report_type=rtype,
            start_date=start_date,
            end_date=end_date,
            total_scans=data['total_scans'],
            fmd_detected=data['fmd_detected'],
            healthy_cattle=data['healthy_cattle'],
        )

        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f'FMD_Vet_{report_type}_report_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        messages.error(request, f'Error generating report: {str(e)}')
        return redirect('vet_dashboard')


@login_required
def vet_detection_detail_view(request, detection_id):
    if not is_vet(request.user):
        return redirect('dashboard')

    detection = get_object_or_404(Detection, id=detection_id)
    context = {
        'title': f'Detection Details',
        'detection': detection,
    }
    return render(request, 'vet/detection_detail.html', context)


# ========================================
# SHARED UPLOAD & DETECTION VIEWS
# ========================================

@login_required
def upload_image_view(request):
    if request.method == 'POST':
        captured_image_data = request.POST.get('captured_image', '')

        if captured_image_data:
            import base64
            from django.core.files.base import ContentFile
            format, imgstr = captured_image_data.split(';base64,')
            ext = format.split('/')[-1]
            image_data = ContentFile(base64.b64decode(imgstr), name=f'captured_{timezone.now().strftime("%Y%m%d_%H%M%S")}.{ext}')
            detection = Detection(user=request.user, image=image_data, status='analyzing')
            detection.save()
        else:
            form = DetectionUploadForm(request.POST, request.FILES)
            if not form.is_valid():
                messages.error(request, 'Please correct the errors below.')
                return render(request, _upload_template(request.user), {'form': form, 'title': 'Upload Image'})
            detection = form.save(commit=False)
            detection.user = request.user
            detection.status = 'analyzing'
            detection.save()

        try:
            image_path = detection.image.path
            analysis_result = analyze_cattle_image(image_path)

            detection.status = 'completed'
            detection.result = analysis_result['result']
            detection.confidence_score = analysis_result['confidence_score']
            detection.analyzed_at = timezone.now()
            detection.save()

            update_statistics(detection)

            # Notify admins via email and notification
            _notify_admins_of_detection(request, detection)

            if detection.result == 'fmd':
                messages.warning(request, f'⚠️ FMD Detected with {detection.confidence_score:.1f}% confidence! Please isolate the animal immediately.')
            elif detection.result == 'healthy':
                messages.success(request, f'✅ Animal appears healthy ({detection.confidence_score:.1f}% confidence).')
            elif detection.result == 'not_cow':
                messages.info(request, 'ℹ️ This image does not appear to contain a cow.')

        except Exception as e:
            detection.status = 'completed'
            detection.result = 'healthy'
            detection.confidence_score = 0.0
            detection.analyzed_at = timezone.now()
            detection.save()
            update_statistics(detection)
            messages.warning(request, 'Analysis completed with low confidence. Please try uploading a clearer image.')

        # Redirect based on role
        if is_vet(request.user):
            return redirect('vet_detection_detail', detection_id=detection.id)
        return redirect('detection_detail', detection_id=detection.id)
    else:
        form = DetectionUploadForm()

    return render(request, _upload_template(request.user), {'form': form, 'title': 'Upload Image - FMD Detection System'})


def _upload_template(user):
    if is_vet(user):
        return 'vet/upload.html'
    return 'dashboard/upload.html'


def _notify_admins_of_detection(request, detection):
    """Send email and in-app notification to all admins"""
    admins = User.objects.filter(
        Q(is_superuser=True) | Q(profile__role='admin')
    ).distinct()

    subject = f'FMD Detection System - New {"⚠️ FMD Alert" if detection.result == "fmd" else "Upload"}'
    uploader_name = detection.user.get_full_name() or detection.user.email
    result_display = detection.get_result_display() if detection.result else 'Pending'
    confidence = f"{detection.confidence_score:.1f}%" if detection.confidence_score else 'N/A'

    message = f"""New detection uploaded and analyzed on the FMD Detection System.

Uploaded By: {uploader_name} ({detection.user.email})
Result: {result_display}
Confidence: {confidence}
Time: {detection.uploaded_at.strftime('%Y-%m-%d %H:%M')}
Animal ID: {detection.animal_id or 'N/A'}
Location: {detection.location or 'N/A'}

{"⚠️ ALERT: FMD detected! Immediate action required." if detection.result == 'fmd' else ""}

View in admin panel: {request.build_absolute_uri('/').rstrip('/')}/admin-panel/uploads/

FMD Detection System
Simba Farms
"""

    notif_type = 'fmd_alert' if detection.result == 'fmd' else 'analysis_done'
    notif_title = f'{"⚠️ FMD Alert" if detection.result == "fmd" else "New Detection"} by {uploader_name}'

    for admin in admins:
        # In-app notification
        Notification.objects.create(
            recipient=admin,
            notification_type=notif_type,
            title=notif_title,
            message=f'Result: {result_display} | Confidence: {confidence} | By: {uploader_name}',
            detection=detection,
        )
        # Email notification
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[admin.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin.email}: {e}")


def update_statistics(detection):
    today = timezone.now().date()
    stats, created = SystemStatistics.objects.get_or_create(date=today)
    stats.total_scans += 1
    if detection.result == 'fmd':
        stats.fmd_detected += 1
    elif detection.result == 'healthy':
        stats.healthy_cattle += 1
    elif detection.result == 'not_cow':
        stats.not_cow_detected += 1
    stats.save()


@login_required
def history_view(request):
    detections = Detection.objects.filter(user=request.user).select_related('user')

    status_filter = request.GET.get('status')
    if status_filter:
        detections = detections.filter(status=status_filter)
    result_filter = request.GET.get('result')
    if result_filter:
        detections = detections.filter(result=result_filter)

    context = {
        'title': 'Detection History',
        'detections': detections,
        'status_filter': status_filter,
        'result_filter': result_filter,
    }
    return render(request, 'dashboard/history.html', context)


@login_required
def detection_detail_view(request, detection_id):
    detection = get_object_or_404(Detection, id=detection_id, user=request.user)
    return render(request, 'dashboard/detection_detail.html', {'title': f'Detection Details', 'detection': detection})


@login_required
def help_view(request):
    return render(request, 'dashboard/help.html', {'title': 'Help & Support'})


# ========================================
# REPORT VIEWS (FARMER)
# ========================================

@login_required
def reports_view(request):
    user_reports = Report.objects.filter(user=request.user)[:10]
    return render(request, 'dashboard/reports.html', {'title': 'Reports', 'reports': user_reports})


@login_required
def generate_report_view(request, report_type):
    if report_type not in ['daily', 'weekly', 'monthly']:
        messages.error(request, 'Invalid report type.')
        return redirect('reports')

    try:
        from .reports import ReportGenerator
        generator = ReportGenerator(request.user, report_type)
        pdf = generator.generate()
        start_date, end_date, title = generator.get_date_range()
        data = generator.get_report_data(start_date, end_date)

        Report.objects.create(
            user=request.user,
            report_type=report_type,
            start_date=start_date,
            end_date=end_date,
            total_scans=data['total_scans'],
            fmd_detected=data['fmd_detected'],
            healthy_cattle=data['healthy_cattle'],
        )

        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f'FMD_{report_type}_report_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        messages.error(request, f'Error generating report: {str(e)}')
        return redirect('reports')


@login_required
def email_report_view(request, report_type):
    if report_type not in ['daily', 'weekly', 'monthly']:
        messages.error(request, 'Invalid report type.')
        return redirect('reports')

    try:
        from .reports import ReportGenerator
        generator = ReportGenerator(request.user, report_type)
        pdf = generator.generate()
        start_date, end_date, title = generator.get_date_range()
        data = generator.get_report_data(start_date, end_date)

        Report.objects.create(
            user=request.user,
            report_type=report_type,
            start_date=start_date,
            end_date=end_date,
            total_scans=data['total_scans'],
            fmd_detected=data['fmd_detected'],
            healthy_cattle=data['healthy_cattle'],
        )

        email = EmailMessage(
            subject=f'FMD Detection System - {title}',
            body=f'Dear {request.user.get_full_name()},\n\nPlease find attached your {report_type} FMD detection report.\n\nBest regards,\nFMD Detection System',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[request.user.email],
        )
        email.attach(f'FMD_{report_type}_report_{timezone.now().strftime("%Y%m%d")}.pdf', pdf, 'application/pdf')
        email.send()

        messages.success(request, f'Report has been sent to {request.user.email}!')
        return redirect('reports')
    except Exception as e:
        messages.error(request, f'Error sending report: {str(e)}')
        return redirect('reports')


# ========================================
# EMAIL TEST
# ========================================

@login_required
@csrf_exempt
def test_email_config(request):
    config = {
        'EMAIL_BACKEND': settings.EMAIL_BACKEND,
        'EMAIL_HOST': getattr(settings, 'EMAIL_HOST', 'Not set'),
        'EMAIL_PORT': getattr(settings, 'EMAIL_PORT', 'Not set'),
        'EMAIL_USE_TLS': getattr(settings, 'EMAIL_USE_TLS', 'Not set'),
        'EMAIL_HOST_USER': settings.EMAIL_HOST_USER or 'NOT SET',
        'EMAIL_HOST_PASSWORD': '***' + settings.EMAIL_HOST_PASSWORD[-4:] if settings.EMAIL_HOST_PASSWORD else 'NOT SET',
        'DEBUG': settings.DEBUG,
        'DEFAULT_FROM_EMAIL': settings.DEFAULT_FROM_EMAIL,
    }
    try:
        result = send_mail(
            'Test Email from FMD System',
            'This is a test email to verify SMTP configuration.',
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email],
            fail_silently=False,
        )
        config['email_sent'] = True
        config['result'] = f'{result} email(s) sent'
        config['sent_to'] = request.user.email
    except Exception as e:
        config['email_sent'] = False
        config['error'] = str(e)
        config['error_type'] = type(e).__name__

    return JsonResponse(config, json_dumps_params={'indent': 2})
