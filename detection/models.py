from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid



class UserProfile(models.Model):
    """Extended user profile for additional information"""
    USER_ROLES = [
        ('farmer', 'Farmer'),
        ('vet', 'Veterinary Doctor'),
        ('admin', 'Administrator'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=USER_ROLES, default='farmer')
    phone_number = models.CharField(max_length=15, blank=True)
    farm_name = models.CharField(max_length=100, default='Simba Farms')
    location = models.CharField(max_length=100, default='Ibanda District')
    is_verified = models.BooleanField(default=False)

    # Vet-specific fields
    license_number = models.CharField(max_length=50, blank=True, null=True)
    specialization = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    def is_vet(self):
        return self.role == 'vet'

    def is_farmer(self):
        return self.role == 'farmer'

    def is_admin_user(self):
        return self.role == 'admin' or self.user.is_superuser

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'


# Signal to create user profile automatically
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        role = 'admin' if instance.is_superuser else 'farmer'
        UserProfile.objects.get_or_create(user=instance, defaults={'role': role})


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()


class Detection(models.Model):
    """Model to store cattle image detection results"""

    STATUS_CHOICES = [
        ('pending', 'Pending Analysis'),
        ('analyzing', 'Analyzing'),
        ('completed', 'Completed'),
    ]

    RESULT_CHOICES = [
        ('healthy', 'Foot and mouth disease not detected'),
        ('fmd', 'Foot and mouth disease detected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='detections')
    image = models.ImageField(upload_to='cattle_images/%Y/%m/%d/')
    # Annotated image with bounding boxes drawn on it (saved after analysis)
    annotated_image = models.ImageField(upload_to='annotated_images/%Y/%m/%d/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, null=True, blank=True)
    result_label = models.CharField(max_length=100, blank=True, default='')
    confidence_score = models.FloatField(null=True, blank=True)
    # JSON list of bounding box dicts: [{x, y, width, height, class, confidence}, ...]
    bounding_boxes = models.JSONField(default=list, blank=True)

    # Metadata
    animal_id = models.CharField(max_length=50, blank=True, null=True)
    notes = models.TextField(blank=True)
    location = models.CharField(max_length=100, blank=True)

    # Timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True)
    analyzed_at = models.DateTimeField(null=True, blank=True)

    # Admin actions
    verified_by_admin = models.BooleanField(default=False)
    admin_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Detection Record'
        verbose_name_plural = 'Detection Records'

    def __str__(self):
        return f"Detection {self.id} - {self.user.username} - {self.result or 'Pending'}"

    @property
    def is_positive(self):
        return self.result == 'fmd'

    @property
    def is_completed(self):
        return self.status == 'completed'


class SystemStatistics(models.Model):
    """Model to track system-wide statistics"""
    date = models.DateField(default=timezone.now, unique=True)
    total_scans = models.IntegerField(default=0)
    fmd_detected = models.IntegerField(default=0)
    healthy_cattle = models.IntegerField(default=0)
    not_cow_detected = models.IntegerField(default=0)

    class Meta:
        ordering = ['-date']
        verbose_name = 'System Statistics'
        verbose_name_plural = 'System Statistics'

    def __str__(self):
        return f"Stats for {self.date}"


class Report(models.Model):
    """Model to track generated reports"""
    REPORT_TYPE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports')
    report_type = models.CharField(max_length=10, choices=REPORT_TYPE_CHOICES)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    generated_at = models.DateTimeField(auto_now_add=True)

    # Statistics snapshot
    total_scans = models.IntegerField(default=0)
    fmd_detected = models.IntegerField(default=0)
    healthy_cattle = models.IntegerField(default=0)

    class Meta:
        ordering = ['-generated_at']
        verbose_name = 'Report'
        verbose_name_plural = 'Reports'

    def __str__(self):
        return f"{self.get_report_type_display()} Report - {self.generated_at.strftime('%Y-%m-%d')}"


class Notification(models.Model):
    """Model to store admin notifications"""
    NOTIFICATION_TYPES = [
        ('upload', 'New Upload'),
        ('fmd_alert', 'FMD Alert'),
        ('analysis_done', 'Analysis Complete'),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    detection = models.ForeignKey(Detection, on_delete=models.SET_NULL, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.notification_type} - {self.recipient.username}"


# new models

# ─────────────────────────────────────────────────────────────────────────────
#  RECOMMENDATION
# ─────────────────────────────────────────────────────────────────────────────

class Recommendation(models.Model):
    """Auto-generated clinical recommendation attached to a Detection."""

    URGENCY_CHOICES = [
        ('critical', 'Critical — Immediate Action'),
        ('high',     'High — Act Within 24 Hours'),
        ('moderate', 'Moderate — Monitor Closely'),
        ('low',      'Low — Routine Monitoring'),
    ]

    detection  = models.OneToOneField('Detection', on_delete=models.CASCADE, related_name='recommendation')
    urgency    = models.CharField(max_length=20, choices=URGENCY_CHOICES, default='low')
    summary    = models.TextField()    # short line shown in history table
    full_text  = models.TextField()    # full text shown on detail page
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Recommendation for {self.detection_id} [{self.urgency}]"

    class Meta:
        ordering = ['-created_at']


# ─────────────────────────────────────────────────────────────────────────────
#  MESSAGING  —  Single flat inbox per vet
#
#  Design:
#    • A farmer sends a DirectMessage directly to a vet (no thread/conversation).
#    • The vet's inbox shows ALL messages from ALL farmers in one chronological list.
#    • The vet can reply to any individual message; replies are linked via
#      reply_to so they form a lightweight chain when rendered.
#    • Farmers see only their own sent messages and replies from vets.
# ─────────────────────────────────────────────────────────────────────────────

class DirectMessage(models.Model):
    """A message from a farmer to a vet (or a vet reply back to a farmer)."""

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_direct_messages')
    recipient  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_direct_messages')
    body       = models.TextField(blank=True)
    image      = models.ImageField(upload_to='messages/%Y/%m/%d/', blank=True, null=True)
    reply_to   = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    is_read    = models.BooleanField(default=False)
    sent_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.sender.username} → {self.recipient.username} at {self.sent_at:%Y-%m-%d %H:%M}"

    @property
    def is_from_farmer(self):
        return hasattr(self.sender, 'profile') and self.sender.profile.role == 'farmer'

    @property
    def other_party(self):
        """Returns the farmer for a vet, and the vet for a farmer."""
        return self.recipient if self.is_from_farmer else self.sender


# ─────────────────────────────────────────────────────────────────────────────
#  APPOINTMENTS
# ─────────────────────────────────────────────────────────────────────────────

class Appointment(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending Approval'),
        ('approved',  'Approved'),
        ('rejected',  'Rejected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farmer         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='appointments_as_farmer')
    vet            = models.ForeignKey(User, on_delete=models.CASCADE, related_name='appointments_as_vet')
    preferred_date = models.DateTimeField()
    reason         = models.TextField()
    location       = models.CharField(max_length=200, blank=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    vet_notes      = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-preferred_date']

    def __str__(self):
        return f"{self.farmer.get_full_name()} → Dr. {self.vet.get_full_name()} on {self.preferred_date:%Y-%m-%d}"

    @property
    def status_color(self):
        return {'pending': '#F97316', 'approved': '#16A34A', 'rejected': '#DC2626',
                'completed': '#1D4ED8', 'cancelled': '#6B7280'}.get(self.status, '#6B7280')

    @property
    def status_bg(self):
        return {'pending': '#FEF3C7', 'approved': '#DCFCE7', 'rejected': '#FEE2E2',
                'completed': '#DBEAFE', 'cancelled': '#F3F4F6'}.get(self.status, '#F3F4F6')


# ─────────────────────────────────────────────────────────────────────────────
#  VACCINATION HISTORY
# ─────────────────────────────────────────────────────────────────────────────

class VaccinationRecord(models.Model):
    """FMD vaccination record for the farm (one entry per vaccination event)."""

    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farmer            = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vaccination_records')
    vaccine_name      = models.CharField(max_length=200, default='FMD Vaccine')
    batch_number      = models.CharField(max_length=100, blank=True)
    date_administered = models.DateField()
    next_due_date     = models.DateField(null=True, blank=True)
    administered_by   = models.CharField(max_length=200, blank=True, help_text='Vet name or clinic')
    notes             = models.TextField(blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_administered']
        verbose_name = 'Vaccination Record'
        verbose_name_plural = 'Vaccination Records'

    def __str__(self):
        return f"{self.vaccine_name} on {self.date_administered} — {self.farmer.username}"

    @property
    def is_overdue(self):
        return bool(self.next_due_date and self.next_due_date < timezone.now().date())

    @property
    def due_soon(self):
        if self.next_due_date:
            delta = self.next_due_date - timezone.now().date()
            return 0 <= delta.days <= 30
        return False
