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
        form = DetectionUploadForm(request.POST, request.FILES)
        if form.is_valid():
            # Save the detection record
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
            messages.error(request, 'Please correct the errors below.')
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