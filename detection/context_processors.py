from .models import DirectMessage, Appointment

def vet_sidebar_counts(request):
    if not request.user.is_authenticated:
        return {}
    try:
        is_vet = hasattr(request.user, 'profile') and request.user.profile.role == 'vet'
    except Exception:
        return {}
    if not is_vet:
        return {}
    try:
        unread = DirectMessage.objects.filter(recipient=request.user, is_read=False).count()
    except Exception:
        unread = 0
    try:
        pending = Appointment.objects.filter(vet=request.user, status='pending').count()
    except Exception:
        pending = 0
    return {'vet_unread_count': unread, 'vet_pending_appts': pending}