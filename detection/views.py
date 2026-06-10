from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from datetime import timedelta
from django.core.mail import send_mail, EmailMessage
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import logging

from .forms import UserRegistrationForm, UserLoginForm, DetectionUploadForm, VetRegistrationForm, ProfileUpdateForm
from .models import Detection, SystemStatistics, UserProfile, Report, Notification
from .models import DirectMessage, Appointment, VaccinationRecord
from .models import MarketListing, MarketComment
from .services import analyze_cattle_image
from .recommendations import generate_recommendation
from . import notifications as notif_service   # centralised notification module

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# PERMISSION HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def is_admin(user):
    return user.is_superuser or (hasattr(user, 'profile') and user.profile.role == 'admin')


def is_vet(user):
    return hasattr(user, 'profile') and user.profile.role == 'vet'


def is_admin_or_vet(user):
    return is_admin(user) or is_vet(user)


# ═══════════════════════════════════════════════════════════════════════════
# AUTHENTICATION VIEWS
# ═══════════════════════════════════════════════════════════════════════════

def register_view(request):
    if request.user.is_authenticated:
        return _redirect_by_role(request.user)

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            role = form.cleaned_data.get('role')

            if role == 'vet':
                # Fire all vet-registration notifications (in-app + email + SMS)
                try:
                    notif_service.notify_vet_registration(request, user)
                except Exception as e:
                    logger.error("notify_vet_registration failed: %s", e)

                messages.success(
                    request,
                    '✅ Your veterinary doctor account has been created! '
                    'Your account is currently <strong>pending admin approval</strong>. '
                    'You will be able to log in once an administrator reviews and approves '
                    'your account. You will receive an email and SMS notification.',
                )
            else:
                messages.success(
                    request,
                    'Account created successfully! Please login with your email and password.',
                )
            return redirect('login')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserRegistrationForm()

    return render(request, 'auth/register.html', {
        'form': form,
        'title': 'Register - FMD Detection System',
    })


def login_view(request):
    if request.user.is_authenticated:
        return _redirect_by_role(request.user)

    if request.method == 'POST':
        email = request.POST.get('username', '').strip().lower()

        # Detect pending vet before Django's auth even runs
        try:
            pending_user = User.objects.get(username=email)
            if (
                not pending_user.is_active
                and hasattr(pending_user, 'profile')
                and pending_user.profile.role == 'vet'
                and not pending_user.profile.is_approved
            ):
                return render(request, 'auth/login.html', {
                    'form': UserLoginForm(),
                    'title': 'Login - FMD Detection System',
                    'pending_vet': True,
                    'pending_email': pending_user.email,
                })
        except User.DoesNotExist:
            pass

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

    return render(request, 'auth/login.html', {
        'form': form,
        'title': 'Login - FMD Detection System',
    })


def _redirect_by_role(user):
    if is_admin(user):
        return redirect('admin_dashboard')
    elif is_vet(user):
        return redirect('vet_dashboard')
    return redirect('dashboard')




@login_required
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ProfileUpdateForm(instance=profile, user=request.user)

    if is_admin(request.user):
        dashboard_url = 'admin_dashboard'
        role_title = 'Administrator'
    elif is_vet(request.user):
        dashboard_url = 'vet_dashboard'
        role_title = 'Veterinary Doctor'
    else:
        dashboard_url = 'dashboard'
        role_title = 'Farmer'

    return render(request, 'dashboard/profile.html', {
        'title': 'My Profile - FMD Detection System',
        'form': form,
        'profile': profile,
        'dashboard_url': dashboard_url,
        'role_title': role_title,
    })

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')


# ═══════════════════════════════════════════════════════════════════════════
# FARMER DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def dashboard_view(request):
    if is_admin(request.user):
        return redirect('admin_dashboard')
    if is_vet(request.user):
        return redirect('vet_dashboard')

    user_detections = Detection.objects.filter(user=request.user)
    total_scans     = user_detections.count()
    fmd_detected    = user_detections.filter(result='fmd').count()
    healthy_cattle  = user_detections.filter(result='healthy').count()
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


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def admin_dashboard_view(request):
    if not is_admin(request.user):
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('dashboard')

    all_detections = Detection.objects.select_related('user', 'user__profile').all()
    total_scans    = all_detections.count()
    fmd_detected   = all_detections.filter(result='fmd').count()
    healthy_cattle = all_detections.filter(result='healthy').count()
    total_users    = User.objects.filter(profile__role='farmer').count()
    total_vets     = User.objects.filter(profile__role='vet', profile__is_approved=True).count()
    pending_vets   = User.objects.filter(profile__role='vet', profile__is_approved=False).count()
    recent_detections = all_detections[:10]
    unread_notifications = Notification.objects.filter(recipient=request.user, is_read=False).count()
    week_ago    = timezone.now() - timedelta(days=7)
    weekly_scans = all_detections.filter(uploaded_at__gte=week_ago).count()
    weekly_fmd   = all_detections.filter(uploaded_at__gte=week_ago, result='fmd').count()

    context = {
        'title': 'Admin Dashboard - FMD Detection System',
        'total_scans': total_scans,
        'fmd_detected': fmd_detected,
        'healthy_cattle': healthy_cattle,
        'total_users': total_users,
        'total_vets': total_vets,
        'pending_vets': pending_vets,
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

    detections   = Detection.objects.select_related('user', 'user__profile').all()
    result_filter = request.GET.get('result', '')
    status_filter = request.GET.get('status', '')
    user_filter   = request.GET.get('user', '')

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
            # Send credentials email + approval SMS to vet
            try:
                send_mail(
                    subject='FMD Detection System - Your Veterinary Doctor Account',
                    message=(
                        f"Dear Dr. {vet_user.get_full_name()},\n\n"
                        f"Your veterinary doctor account has been created and approved by the administrator.\n\n"
                        f"Email   : {vet_user.email}\n"
                        f"Password: {form.cleaned_data['password']}\n\n"
                        f"Login at: {request.build_absolute_uri('/')}\n\n"
                        f"FMD Detection System — Simba Farms"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[vet_user.email],
                    fail_silently=True,
                )
            except Exception as e:
                logger.error("Failed to send vet credentials email: %s", e)

            # SMS to newly registered vet
            vet_phone = form.cleaned_data.get('phone_number', '')
            if vet_phone:
                from .notifications import send_sms
                send_sms(
                    vet_phone,
                    f"FMD SYSTEM: Dr. {vet_user.get_full_name()}, your vet account has been created. "
                    f"Login at {request.build_absolute_uri('/')} with {vet_user.email}."
                )

            messages.success(request, f'Dr. {vet_user.get_full_name()} registered successfully!')
            return redirect('admin_vets')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = VetRegistrationForm()

    return render(request, 'admin_panel/register_vet.html', {
        'form': form,
        'title': 'Register Veterinary Doctor',
    })


@login_required
def admin_vets_view(request):
    if not is_admin(request.user):
        return redirect('dashboard')

    vets         = User.objects.filter(profile__role='vet', profile__is_approved=True).select_related('profile')
    pending_vets = User.objects.filter(profile__role='vet', profile__is_approved=False).select_related('profile')

    return render(request, 'admin_panel/vets.html', {
        'title': 'Veterinary Doctors - Admin',
        'vets': vets,
        'pending_vets': pending_vets,
    })


@login_required
def admin_pending_vets_view(request):
    if not is_admin(request.user):
        return redirect('dashboard')

    pending_vets = User.objects.filter(
        profile__role='vet', profile__is_approved=False
    ).select_related('profile').order_by('-profile__created_at')

    return render(request, 'admin_panel/pending_vets.html', {
        'title': 'Pending Vet Approvals - Admin',
        'pending_vets': pending_vets,
    })


@login_required
def admin_approve_vet_view(request, vet_id):
    if not is_admin(request.user):
        return redirect('dashboard')
    if request.method != 'POST':
        return redirect('admin_pending_vets')

    vet_user = get_object_or_404(User, id=vet_id, profile__role='vet')
    profile  = vet_user.profile

    if profile.is_approved:
        messages.info(request, f'Dr. {vet_user.get_full_name() or vet_user.email} is already approved.')
        return redirect('admin_vets')

    # Activate account
    profile.is_approved = True
    profile.is_verified = True
    profile.save()
    vet_user.is_active = True
    vet_user.save()

    # Mark related in-app notifications as read
    Notification.objects.filter(
        notification_type='vet_registration',
        message__icontains=vet_user.email,
    ).update(is_read=True)

    # Email + SMS to vet
    try:
        notif_service.notify_vet_approved(request, vet_user)
    except Exception as e:
        logger.error("notify_vet_approved failed: %s", e)

    messages.success(
        request,
        f'✅ Dr. {vet_user.get_full_name() or vet_user.email} has been approved. '
        f'They have been notified by email and SMS.'
    )
    return redirect('admin_pending_vets')


@login_required
def admin_reject_vet_view(request, vet_id):
    if not is_admin(request.user):
        return redirect('dashboard')
    if request.method != 'POST':
        return redirect('admin_pending_vets')

    vet_user         = get_object_or_404(User, id=vet_id, profile__role='vet')
    rejection_reason = request.POST.get('rejection_reason', '').strip()
    vet_name         = vet_user.get_full_name() or vet_user.email

    # Email + SMS before deletion
    try:
        notif_service.notify_vet_rejected(vet_user, rejection_reason)
    except Exception as e:
        logger.error("notify_vet_rejected failed: %s", e)

    vet_user.delete()

    messages.warning(
        request,
        f'❌ The account for Dr. {vet_name} has been rejected and removed. '
        f'They have been notified by email and SMS.'
    )
    return redirect('admin_pending_vets')


@login_required
def admin_notifications_view(request):
    if not is_admin(request.user):
        return redirect('dashboard')

    notifications = Notification.objects.filter(
        recipient=request.user
    ).select_related('detection', 'detection__user')
    notifications.filter(is_read=False).update(is_read=True)

    return render(request, 'admin_panel/notifications.html', {
        'title': 'Notifications - Admin',
        'notifications': notifications,
    })


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
        response['Content-Disposition'] = (
            f'attachment; filename="FMD_Admin_{report_type}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
        )
        return response
    except Exception as e:
        messages.error(request, f'Error generating report: {str(e)}')
        return redirect('admin_dashboard')


# ═══════════════════════════════════════════════════════════════════════════
# VET DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def vet_dashboard_view(request):
    if not is_vet(request.user):
        if is_admin(request.user):
            return redirect('admin_dashboard')
        messages.error(request, 'Access denied. Veterinary doctor privileges required.')
        return redirect('dashboard')

    all_detections  = Detection.objects.select_related('user', 'user__profile').all()
    vet_detections  = Detection.objects.filter(user=request.user)

    context = {
        'title': 'Veterinary Dashboard - FMD Detection System',
        'total_scans':   all_detections.count(),
        'fmd_detected':  all_detections.filter(result='fmd').count(),
        'healthy_cattle': all_detections.filter(result='healthy').count(),
        'recent_detections': all_detections[:8],
        'vet_total': vet_detections.count(),
        'vet_fmd':   vet_detections.filter(result='fmd').count(),
    }
    return render(request, 'vet/dashboard.html', context)


@login_required
def vet_all_uploads_view(request):
    if not is_vet(request.user):
        return redirect('dashboard')

    detections    = Detection.objects.select_related('user', 'user__profile').all()
    result_filter = request.GET.get('result', '')
    if result_filter:
        detections = detections.filter(result=result_filter)

    return render(request, 'vet/all_uploads.html', {
        'title': 'All Farm Detections - Vet',
        'detections': detections,
        'result_filter': result_filter,
    })


@login_required
def vet_generate_report_view(request, report_type):
    if not is_vet(request.user):
        return redirect('dashboard')
    if report_type not in ['daily', 'weekly', 'monthly', 'all']:
        messages.error(request, 'Invalid report type.')
        return redirect('vet_dashboard')
    try:
        from .reports import VetReportGenerator
        generator   = VetReportGenerator(request.user, report_type)
        pdf         = generator.generate()
        rtype       = report_type if report_type != 'all' else 'monthly'
        start_date, end_date, _ = generator.get_date_range()
        data        = generator.get_report_data(start_date, end_date)
        Report.objects.create(
            user=request.user, report_type=rtype,
            start_date=start_date, end_date=end_date,
            total_scans=data['total_scans'],
            fmd_detected=data['fmd_detected'],
            healthy_cattle=data['healthy_cattle'],
        )
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="FMD_Vet_{report_type}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
        )
        return response
    except Exception as e:
        messages.error(request, f'Error generating report: {str(e)}')
        return redirect('vet_dashboard')


@login_required
def vet_detection_detail_view(request, detection_id):
    if not is_vet(request.user):
        return redirect('dashboard')
    detection = get_object_or_404(Detection, id=detection_id)
    return render(request, 'vet/detection_detail.html', {
        'title': 'Detection Details',
        'detection': detection,
    })


# ═══════════════════════════════════════════════════════════════════════════
# SHARED UPLOAD & DETECTION VIEWS
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def upload_image_view(request):
    if request.method == 'POST':
        captured_image_data = request.POST.get('captured_image', '')
        if captured_image_data:
            import base64
            from django.core.files.base import ContentFile
            format_, imgstr = captured_image_data.split(';base64,')
            ext        = format_.split('/')[-1]
            image_data = ContentFile(
                base64.b64decode(imgstr),
                name=f'captured_{timezone.now().strftime("%Y%m%d_%H%M%S")}.{ext}',
            )
            detection = Detection(user=request.user, image=image_data, status='analyzing')
            detection.save()
        else:
            form = DetectionUploadForm(request.POST, request.FILES)
            if not form.is_valid():
                messages.error(request, 'Please correct the errors below.')
                return render(request, _upload_template(request.user), {
                    'form': form, 'title': 'Upload Image',
                })
            detection = form.save(commit=False)
            detection.user   = request.user
            detection.status = 'analyzing'
            detection.save()

        try:
            analysis_result = analyze_cattle_image(detection.image.path)
            detection.status          = 'completed'
            detection.result          = analysis_result['result']
            detection.result_label    = analysis_result.get('result_label', '')
            detection.confidence_score = analysis_result['confidence_score']
            detection.bounding_boxes  = analysis_result.get('bounding_boxes', [])
            detection.analyzed_at     = timezone.now()
            detection.save()

            if detection.result == 'fmd' and detection.bounding_boxes:
                try:
                    _save_annotated_image(detection)
                except Exception as ann_err:
                    logger.warning("Could not save annotated image: %s", ann_err)

            update_statistics(detection)

            try:
                generate_recommendation(detection)
            except Exception as rec_err:
                logger.warning("Could not generate recommendation: %s", rec_err)

            # ── Notifications ────────────────────────────────────────────────
            # Always send general upload notification (in-app + email)
            try:
                notif_service.notify_upload(request, detection)
            except Exception as ne:
                logger.error("notify_upload failed: %s", ne)

            # FMD with ≥70% confidence → additional SMS + priority notifications
            conf = detection.confidence_score or 0
            if detection.result == 'fmd' and conf >= 70:
                try:
                    notif_service.notify_fmd_detected(request, detection)
                except Exception as ne:
                    logger.error("notify_fmd_detected failed: %s", ne)

            if detection.result == 'fmd':
                messages.warning(
                    request,
                    f'⚠️ Foot and mouth disease detected with {detection.confidence_score:.1f}% '
                    f'confidence! Please isolate the animal immediately.'
                )
            else:
                messages.success(
                    request,
                    f'✅ No FMD detected ({detection.confidence_score:.1f}% confidence).',
                )

        except Exception as e:
            logger.error("Analysis error: %s", e)
            detection.status           = 'completed'
            detection.result           = 'healthy'
            detection.result_label     = 'Foot and mouth disease not detected'
            detection.confidence_score = 0.0
            detection.bounding_boxes   = []
            detection.analyzed_at      = timezone.now()
            detection.save()
            update_statistics(detection)
            messages.warning(request, 'Analysis completed. Please try uploading a clearer image.')

        if is_vet(request.user):
            return redirect('vet_detection_detail', detection_id=detection.id)
        return redirect('detection_detail', detection_id=detection.id)

    else:
        form = DetectionUploadForm()

    return render(request, _upload_template(request.user), {
        'form': form, 'title': 'Upload Image - FMD Detection System',
    })


def _upload_template(user):
    return 'vet/upload.html' if is_vet(user) else 'dashboard/upload.html'


def _save_annotated_image(detection):
    from PIL import Image, ImageDraw
    import io, os
    from django.core.files.base import ContentFile

    img  = Image.open(detection.image.path).convert('RGB')
    draw = ImageDraw.Draw(img)
    img_w, img_h = img.size

    for box in detection.bounding_boxes:
        cx, cy   = box.get('x', 0), box.get('y', 0)
        bw, bh   = box.get('width', 0), box.get('height', 0)
        conf     = box.get('confidence', 0)
        label    = f"FMD {conf:.1f}%"
        x1, y1   = max(0, int(cx - bw / 2)), max(0, int(cy - bh / 2))
        x2, y2   = min(img_w, int(cx + bw / 2)), min(img_h, int(cy + bh / 2))
        for t in range(3):
            draw.rectangle([x1 - t, y1 - t, x2 + t, y2 + t], outline='#DC2626')
        label_w = len(label) * 7 + 8
        draw.rectangle([x1, y1 - 18, x1 + label_w, y1], fill='#DC2626')
        draw.text((x1 + 4, y1 - 16), label, fill='white')

    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=90)
    buf.seek(0)
    annotated_name = f"annotated_{os.path.basename(detection.image.name)}"
    detection.annotated_image.save(annotated_name, ContentFile(buf.read()), save=True)


def update_statistics(detection):
    today = timezone.now().date()
    stats, _ = SystemStatistics.objects.get_or_create(date=today)
    stats.total_scans += 1
    if detection.result == 'fmd':
        stats.fmd_detected += 1
    else:
        stats.healthy_cattle += 1
    stats.save()


@login_required
def history_view(request):
    detections    = Detection.objects.filter(user=request.user).select_related('user')
    status_filter = request.GET.get('status')
    result_filter = request.GET.get('result')
    if status_filter:
        detections = detections.filter(status=status_filter)
    if result_filter:
        detections = detections.filter(result=result_filter)
    return render(request, 'dashboard/history.html', {
        'title': 'Detection History',
        'detections': detections,
        'status_filter': status_filter,
        'result_filter': result_filter,
    })


@login_required
def detection_detail_view(request, detection_id):
    detection = get_object_or_404(Detection, id=detection_id, user=request.user)
    return render(request, 'dashboard/detection_detail.html', {
        'title': 'Detection Details',
        'detection': detection,
    })


@login_required
def help_view(request):
    return render(request, 'dashboard/help.html', {'title': 'Help & Support'})


# ═══════════════════════════════════════════════════════════════════════════
# REPORTS — FARMER
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def reports_view(request):
    user_reports = Report.objects.filter(user=request.user)[:10]
    return render(request, 'dashboard/reports.html', {
        'title': 'Reports', 'reports': user_reports,
    })


@login_required
def generate_report_view(request, report_type):
    if report_type not in ['daily', 'weekly', 'monthly']:
        messages.error(request, 'Invalid report type.')
        return redirect('reports')
    try:
        from .reports import ReportGenerator
        generator = ReportGenerator(request.user, report_type)
        pdf       = generator.generate()
        start_date, end_date, title = generator.get_date_range()
        data      = generator.get_report_data(start_date, end_date)
        Report.objects.create(
            user=request.user, report_type=report_type,
            start_date=start_date, end_date=end_date,
            total_scans=data['total_scans'],
            fmd_detected=data['fmd_detected'],
            healthy_cattle=data['healthy_cattle'],
        )
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="FMD_{report_type}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
        )
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
        pdf       = generator.generate()
        start_date, end_date, title = generator.get_date_range()
        data      = generator.get_report_data(start_date, end_date)
        Report.objects.create(
            user=request.user, report_type=report_type,
            start_date=start_date, end_date=end_date,
            total_scans=data['total_scans'],
            fmd_detected=data['fmd_detected'],
            healthy_cattle=data['healthy_cattle'],
        )
        email = EmailMessage(
            subject=f'FMD Detection System - {title}',
            body=f'Dear {request.user.get_full_name()},\n\nPlease find attached your {report_type} report.\n\nFMD Detection System',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[request.user.email],
        )
        email.attach(f'FMD_{report_type}_{timezone.now().strftime("%Y%m%d")}.pdf', pdf, 'application/pdf')
        email.send()
        messages.success(request, f'Report sent to {request.user.email}!')
        return redirect('reports')
    except Exception as e:
        messages.error(request, f'Error sending report: {str(e)}')
        return redirect('reports')


@login_required
@csrf_exempt
def test_email_config(request):
    config = {
        'EMAIL_BACKEND':       settings.EMAIL_BACKEND,
        'EMAIL_HOST':          getattr(settings, 'EMAIL_HOST', 'Not set'),
        'EMAIL_PORT':          getattr(settings, 'EMAIL_PORT', 'Not set'),
        'EMAIL_USE_TLS':       getattr(settings, 'EMAIL_USE_TLS', 'Not set'),
        'EMAIL_HOST_USER':     settings.EMAIL_HOST_USER or 'NOT SET',
        'EMAIL_HOST_PASSWORD': '***' + settings.EMAIL_HOST_PASSWORD[-4:] if settings.EMAIL_HOST_PASSWORD else 'NOT SET',
        'DEBUG':               settings.DEBUG,
        'DEFAULT_FROM_EMAIL':  settings.DEFAULT_FROM_EMAIL,
        'EGOSMS_USERNAME':     'SET' if notif_service.EGOSMS_USERNAME else 'NOT SET',
        'EGOSMS_SENDER':       notif_service.EGOSMS_SENDER,
    }
    try:
        result = send_mail(
            'Test Email from FMD System', 'Test email.',
            settings.DEFAULT_FROM_EMAIL, [request.user.email],
            fail_silently=False,
        )
        config.update({'email_sent': True, 'result': f'{result} email(s) sent', 'sent_to': request.user.email})
    except Exception as e:
        config.update({'email_sent': False, 'error': str(e), 'error_type': type(e).__name__})
    return JsonResponse(config, json_dumps_params={'indent': 2})


# ═══════════════════════════════════════════════════════════════════════════
# MESSAGING — FARMER SIDE
# ═══════════════════════════════════════════════════════════════════════════

def _get_vets():
    return User.objects.filter(
        profile__role='vet', profile__is_approved=True
    ).select_related('profile')


@login_required
def farmer_inbox_view(request):
    vets         = _get_vets()
    selected_vet = None
    vet_id       = request.GET.get('vet')
    if vet_id:
        selected_vet = get_object_or_404(User, id=vet_id, profile__role='vet')

    if request.method == 'POST':
        vet_id_post = request.POST.get('vet_id')
        body        = request.POST.get('body', '').strip()
        image       = request.FILES.get('image')
        reply_to_id = request.POST.get('reply_to')
        if vet_id_post and (body or image):
            vet      = get_object_or_404(User, id=vet_id_post, profile__role='vet')
            reply_to = None
            if reply_to_id:
                try:
                    reply_to = DirectMessage.objects.get(id=reply_to_id)
                except DirectMessage.DoesNotExist:
                    pass
            DirectMessage.objects.create(
                sender=request.user, recipient=vet,
                body=body, image=image, reply_to=reply_to,
            )
            return redirect(f"{request.path}?vet={vet_id_post}")

    thread = []
    if selected_vet:
        thread = DirectMessage.objects.filter(
            Q(sender=request.user, recipient=selected_vet) |
            Q(sender=selected_vet, recipient=request.user)
        ).order_by('sent_at')
        DirectMessage.objects.filter(
            sender=selected_vet, recipient=request.user, is_read=False
        ).update(is_read=True)

    sent_to_ids       = list(DirectMessage.objects.filter(sender=request.user).values_list('recipient_id', flat=True))
    received_from_ids = list(DirectMessage.objects.filter(recipient=request.user).values_list('sender_id', flat=True))
    messaged_vet_ids  = set(sent_to_ids + received_from_ids)
    messaged_vets     = User.objects.filter(id__in=messaged_vet_ids, profile__role='vet').select_related('profile')
    new_vets          = vets.exclude(id__in=messaged_vet_ids)

    return render(request, 'dashboard/inbox.html', {
        'title': 'Messages', 'vets': vets,
        'messaged_vets': messaged_vets, 'new_vets': new_vets,
        'selected_vet': selected_vet, 'thread': thread,
    })


# ═══════════════════════════════════════════════════════════════════════════
# MESSAGING — VET SIDE
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def vet_inbox_view(request):
    if request.method == 'POST':
        body        = request.POST.get('body', '').strip()
        image       = request.FILES.get('image')
        reply_to_id = request.POST.get('reply_to_id')
        farmer_id   = request.POST.get('farmer_id')
        if (body or image) and farmer_id:
            farmer   = get_object_or_404(User, id=farmer_id)
            reply_to = None
            if reply_to_id:
                try:
                    reply_to = DirectMessage.objects.get(id=reply_to_id)
                except DirectMessage.DoesNotExist:
                    pass
            DirectMessage.objects.create(
                sender=request.user, recipient=farmer,
                body=body, image=image, reply_to=reply_to,
            )
            messages.success(request, f'Reply sent to {farmer.get_full_name() or farmer.email}.')
        return redirect('vet_inbox')

    all_inbox = DirectMessage.objects.filter(
        recipient=request.user
    ).select_related('sender', 'sender__profile', 'reply_to').order_by('-sent_at')
    unread_count = all_inbox.filter(is_read=False).count()
    all_inbox.filter(is_read=False).update(is_read=True)

    return render(request, 'vet/inbox.html', {
        'title': 'Farmer Messages',
        'all_inbox': all_inbox,
        'unread_count': unread_count,
    })


# ═══════════════════════════════════════════════════════════════════════════
# APPOINTMENTS — FARMER SIDE
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def farmer_appointments_view(request):
    appts = Appointment.objects.filter(farmer=request.user).select_related('vet', 'vet__profile')
    vets  = _get_vets()

    if request.method == 'POST':
        vet_id   = request.POST.get('vet_id')
        pref_dt  = request.POST.get('preferred_date')
        reason   = request.POST.get('reason', '').strip()
        location = request.POST.get('location', '').strip()

        if not (vet_id and pref_dt and reason):
            messages.error(request, 'Please fill in all required fields.')
        else:
            vet = get_object_or_404(User, id=vet_id, profile__role='vet')
            dt  = parse_datetime(pref_dt)
            if not dt:
                messages.error(request, 'Invalid date/time.')
            else:
                appointment = Appointment.objects.create(
                    farmer=request.user, vet=vet,
                    preferred_date=dt, reason=reason, location=location,
                )
                # Notify vet via email + SMS
                try:
                    notif_service.notify_appointment_booked(request, appointment)
                except Exception as e:
                    logger.error("notify_appointment_booked failed: %s", e)

                messages.success(
                    request,
                    f'Appointment request sent to Dr. {vet.get_full_name() or vet.email}. '
                    f'Awaiting approval. The doctor has been notified by email and SMS.'
                )
                return redirect('farmer_appointments')

    return render(request, 'dashboard/appointments.html', {
        'title': 'My Appointments',
        'appointments': appts,
        'vets': vets,
    })


@login_required
def farmer_cancel_appointment(request, appt_id):
    appt = get_object_or_404(Appointment, id=appt_id, farmer=request.user)
    if appt.status == 'pending':
        appt.status = 'cancelled'
        appt.save()
        messages.success(request, 'Appointment cancelled.')
    return redirect('farmer_appointments')


# ═══════════════════════════════════════════════════════════════════════════
# APPOINTMENTS — VET SIDE
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def vet_appointments_view(request):
    appts = Appointment.objects.filter(vet=request.user).select_related('farmer', 'farmer__profile')
    return render(request, 'vet/appointments.html', {
        'title': 'Appointment Requests',
        'appointments': appts,
    })


@login_required
def vet_respond_appointment(request, appt_id):
    if request.method != 'POST':
        return redirect('vet_appointments')

    appt   = get_object_or_404(Appointment, id=appt_id, vet=request.user)
    action = request.POST.get('action', '').strip()
    notes  = request.POST.get('vet_notes', '').strip()

    if action == 'approve':
        appt.status    = 'approved'
        appt.vet_notes = notes
        appt.save()
        messages.success(request, f'✅ Appointment with {appt.farmer.get_full_name() or appt.farmer.username} approved.')
    elif action == 'reject':
        appt.status    = 'rejected'
        appt.vet_notes = notes
        appt.save()
        messages.warning(request, '❌ Appointment rejected.')
    elif action == 'complete':
        appt.status = 'completed'
        appt.save()
        messages.success(request, '✅ Appointment marked as completed.')
    else:
        messages.error(request, f'Unknown action: "{action}"')

    return redirect('vet_appointments')


# ═══════════════════════════════════════════════════════════════════════════
# VACCINATION RECORDS
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def vaccination_list_view(request):
    records  = VaccinationRecord.objects.filter(farmer=request.user)
    overdue  = [r for r in records if r.is_overdue]
    due_soon = [r for r in records if r.due_soon and not r.is_overdue]
    return render(request, 'dashboard/vaccination.html', {
        'title': 'FMD Vaccination History',
        'records': records,
        'overdue': overdue,
        'due_soon': due_soon,
    })


@login_required
def vaccination_add_view(request):
    if request.method == 'POST':
        date_admin = request.POST.get('date_administered', '').strip()
        if not date_admin:
            messages.error(request, 'Date administered is required.')
        else:
            VaccinationRecord.objects.create(
                farmer=request.user,
                vaccine_name=request.POST.get('vaccine_name', 'FMD Vaccine').strip() or 'FMD Vaccine',
                batch_number=request.POST.get('batch_number', '').strip(),
                date_administered=date_admin,
                next_due_date=request.POST.get('next_due_date', '').strip() or None,
                administered_by=request.POST.get('administered_by', '').strip(),
                notes=request.POST.get('notes', '').strip(),
            )
            messages.success(request, 'Vaccination record saved.')
            return redirect('vaccination_list')
    return render(request, 'dashboard/vaccination_add.html', {'title': 'Record Vaccination'})


@login_required
def vaccination_delete_view(request, record_id):
    record = get_object_or_404(VaccinationRecord, id=record_id, farmer=request.user)
    record.delete()
    messages.success(request, 'Record deleted.')
    return redirect('vaccination_list')


# ═══════════════════════════════════════════════════════════════════════════
# MARKETPLACE
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def marketplace_view(request):
    listings = MarketListing.objects.filter(
        is_active=True
    ).select_related('seller', 'seller__profile').prefetch_related('comments')
    search = request.GET.get('q', '').strip()
    if search:
        listings = listings.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search) |
            Q(location__icontains=search)
        )
    return render(request, 'marketplace/marketplace.html', {
        'title': 'Cattle Marketplace', 'listings': listings, 'search': search,
    })


@login_required
def marketplace_listing_detail(request, listing_id):
    listing  = get_object_or_404(MarketListing, id=listing_id)
    comments = listing.comments.select_related('author', 'author__profile', 'reply_to')
    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            reply_to    = None
            reply_to_id = request.POST.get('reply_to_id', '').strip()
            if reply_to_id:
                try:
                    reply_to = MarketComment.objects.get(id=reply_to_id)
                except MarketComment.DoesNotExist:
                    pass
            MarketComment.objects.create(listing=listing, author=request.user, body=body, reply_to=reply_to)
            messages.success(request, 'Comment posted.')
        return redirect('marketplace_detail', listing_id=listing_id)
    return render(request, 'marketplace/listing_detail.html', {
        'title': listing.title, 'listing': listing, 'comments': comments,
    })


@login_required
def marketplace_create(request):
    if request.method == 'POST':
        title    = request.POST.get('title', 'Cow for Sale').strip()
        desc     = request.POST.get('description', '').strip()
        price    = request.POST.get('price', '').strip()
        currency = request.POST.get('currency', 'UGX').strip()
        phone    = request.POST.get('phone', '').strip()
        location = request.POST.get('location', '').strip()
        image    = request.FILES.get('image')
        errors   = []
        if not image: errors.append('Please upload a cow image.')
        if not price: errors.append('Please enter a price.')
        if not phone: errors.append('Please enter a contact phone number.')
        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            try:
                price_val = float(price.replace(',', ''))
                MarketListing.objects.create(
                    seller=request.user, image=image, title=title,
                    description=desc, price=price_val, currency=currency,
                    phone=phone, location=location,
                )
                messages.success(request, 'Your listing has been posted to the marketplace!')
                return redirect('marketplace')
            except ValueError:
                messages.error(request, 'Invalid price format.')
    return render(request, 'marketplace/create_listing.html', {'title': 'Post a Listing'})


@login_required
def marketplace_delete(request, listing_id):
    listing = get_object_or_404(MarketListing, id=listing_id, seller=request.user)
    listing.delete()
    messages.success(request, 'Listing removed.')
    return redirect('marketplace')


@login_required
def marketplace_toggle(request, listing_id):
    listing = get_object_or_404(MarketListing, id=listing_id, seller=request.user)
    listing.is_active = not listing.is_active
    listing.save()
    status = 'active' if listing.is_active else 'marked as sold'
    messages.success(request, f'Listing {status}.')
    return redirect('marketplace_detail', listing_id=listing_id)


# ═══════════════════════════════════════════════════════════════════════════
# AJAX
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def unread_count_view(request):
    count = DirectMessage.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'unread': count})