from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from .forms import UserRegistrationForm, UserLoginForm, DetectionUploadForm
from .models import Detection, SystemStatistics, UserProfile
from .services import analyze_cattle_image  # Import the service

# ========================================
# AUTHENTICATION VIEWS
# ========================================

def register_view(request):
    """Handle user registration"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome {user.first_name}! Your account has been created successfully.')
            return redirect('dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserRegistrationForm()
    
    context = {
        'form': form,
        'title': 'Register - FMD Detection System'
    }
    return render(request, 'auth/register.html', context)


def login_view(request):
    """Handle user login"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name}!')
                
                next_page = request.GET.get('next')
                if next_page:
                    return redirect(next_page)
                return redirect('dashboard')
        else:
            messages.error(request, 'Invalid email or password.')
    else:
        form = UserLoginForm()
    
    context = {
        'form': form,
        'title': 'Login - FMD Detection System'
    }
    return render(request, 'auth/login.html', context)


@login_required
def logout_view(request):
    """Handle user logout"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')


# ========================================
# DASHBOARD VIEWS
# ========================================

@login_required
def dashboard_view(request):
    """Display main dashboard with statistics"""
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


@login_required
def upload_image_view(request):
    """Handle cattle image upload and analysis"""
    if request.method == 'POST':
        # Check if image was captured from camera
        captured_image_data = request.POST.get('captured_image', '')
        
        if captured_image_data:
            # Handle captured image from camera
            import base64
            from django.core.files.base import ContentFile
            from django.utils import timezone
            
            # Remove data URL prefix
            format, imgstr = captured_image_data.split(';base64,')
            ext = format.split('/')[-1]
            
            # Create file from base64 data
            image_data = ContentFile(base64.b64decode(imgstr), name=f'captured_{timezone.now().strftime("%Y%m%d_%H%M%S")}.{ext}')
            
            # Create detection record
            detection = Detection(
                user=request.user,
                image=image_data,
                animal_id=request.POST.get('animal_id', ''),
                location=request.POST.get('location', ''),
                notes=request.POST.get('notes', ''),
                status='analyzing'
            )
            detection.save()
        else:
            # Handle uploaded file
            form = DetectionUploadForm(request.POST, request.FILES)
            if not form.is_valid():
                messages.error(request, 'Please correct the errors below.')
                context = {
                    'form': form,
                    'title': 'Upload Image - FMD Detection System'
                }
                return render(request, 'dashboard/upload.html', context)
            
            detection = form.save(commit=False)
            detection.user = request.user
            detection.status = 'analyzing'
            detection.save()
        
        try:
            # Get the absolute path to the uploaded image
            image_path = detection.image.path
            
            # Analyze the image using Roboflow
            analysis_result = analyze_cattle_image(image_path)
            
            if analysis_result['success']:
                # Update detection with results
                detection.status = analysis_result['status']
                detection.result = analysis_result['result']
                detection.confidence_score = analysis_result['confidence_score']
                detection.analyzed_at = timezone.now()
                detection.save()
                
                # Update system statistics
                update_statistics(detection)
                
                # Show success message with result
                if detection.result == 'fmd':
                    messages.warning(
                        request, 
                        f'⚠️ FMD Detected with {detection.confidence_score:.1f}% confidence! Please isolate the animal immediately.'
                    )
                elif detection.result == 'healthy':
                    messages.success(
                        request, 
                        f'✅ Animal appears healthy ({detection.confidence_score:.1f}% confidence).'
                    )
                else:
                    messages.info(
                        request, 
                        f'Analysis complete. Result: {detection.get_result_display()}'
                    )
            else:
                # Analysis failed
                detection.status = 'failed'
                detection.save()
                messages.error(
                    request, 
                    f'Analysis failed: {analysis_result.get("error", "Unknown error")}'
                )
            
        except Exception as e:
            detection.status = 'failed'
            detection.save()
            messages.error(request, f'Error during analysis: {str(e)}')
        
        return redirect('detection_detail', detection_id=detection.id)
    else:
        form = DetectionUploadForm()
    
    context = {
        'form': form,
        'title': 'Upload Image - FMD Detection System'
    }
    return render(request, 'dashboard/upload.html', context)


def update_statistics(detection):
    """Update system statistics after detection"""
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
    """Display detection history"""
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
    """Display details of a specific detection"""
    detection = get_object_or_404(Detection, id=detection_id, user=request.user)
    
    context = {
        'title': f'Detection Details - {detection.id}',
        'detection': detection,
    }
    return render(request, 'dashboard/detection_detail.html', context)


@login_required
def help_view(request):
    """Display help and support information"""
    context = {
        'title': 'Help & Support'
    }
    return render(request, 'dashboard/help.html', context)


# ========================================
# REPORT GENERATION VIEWS
# ========================================

@login_required
def reports_view(request):
    """Display reports dashboard"""
    # Get user's generated reports
    user_reports = Report.objects.filter(user=request.user)[:10]
    
    context = {
        'title': 'Reports',
        'reports': user_reports,
    }
    return render(request, 'dashboard/reports.html', context)


@login_required
def generate_report_view(request, report_type):
    """Generate and download a PDF report"""
    from django.http import HttpResponse
    from .reports import ReportGenerator
    from .models import Report
    
    # Validate report type
    if report_type not in ['daily', 'weekly', 'monthly']:
        messages.error(request, 'Invalid report type.')
        return redirect('reports')
    
    try:
        # Generate the report
        generator = ReportGenerator(request.user, report_type)
        pdf = generator.generate()
        
        # Get date range for report record
        start_date, end_date, title = generator.get_date_range()
        data = generator.get_report_data(start_date, end_date)
        
        # Save report record
        Report.objects.create(
            user=request.user,
            report_type=report_type,
            start_date=start_date,
            end_date=end_date,
            total_scans=data['total_scans'],
            fmd_detected=data['fmd_detected'],
            healthy_cattle=data['healthy_cattle']
        )
        
        # Create HTTP response with PDF
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f'FMD_{report_type}_report_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        messages.success(request, f'{report_type.capitalize()} report generated successfully!')
        return response
        
    except Exception as e:
        messages.error(request, f'Error generating report: {str(e)}')
        return redirect('reports')


@login_required
def email_report_view(request, report_type):
    """Generate and email a PDF report"""
    from django.core.mail import EmailMessage
    from .reports import ReportGenerator
    from .models import Report
    
    # Validate report type
    if report_type not in ['daily', 'weekly', 'monthly']:
        messages.error(request, 'Invalid report type.')
        return redirect('reports')
    
    try:
        # Generate the report
        generator = ReportGenerator(request.user, report_type)
        pdf = generator.generate()
        
        # Get date range
        start_date, end_date, title = generator.get_date_range()
        data = generator.get_report_data(start_date, end_date)
        
        # Save report record
        Report.objects.create(
            user=request.user,
            report_type=report_type,
            start_date=start_date,
            end_date=end_date,
            total_scans=data['total_scans'],
            fmd_detected=data['fmd_detected'],
            healthy_cattle=data['healthy_cattle']
        )
        
        # Send email
        subject = f'FMD Detection System - {title}'
        message = f"""
        Dear {request.user.get_full_name()},
        
        Please find attached your {report_type} FMD detection report.
        
        Summary:
        - Total Scans: {data['total_scans']}
        - FMD Detected: {data['fmd_detected']}
        - Healthy Cattle: {data['healthy_cattle']}
        
        Best regards,
        FMD Detection System
        Simba Farms
        """
        
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email='noreply@simbafarmsdetection.com',
            to=[request.user.email],
        )
        
        filename = f'FMD_{report_type}_report_{timezone.now().strftime("%Y%m%d")}.pdf'
        email.attach(filename, pdf, 'application/pdf')
        email.send()
        
        messages.success(request, f'Report has been sent to {request.user.email}!')
        return redirect('reports')
        
    except Exception as e:
        messages.error(request, f'Error sending report: {str(e)}')
        return redirect('reports')