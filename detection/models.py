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
        ('healthy', 'Healthy'),
        ('fmd', 'FMD Detected'),
        ('not_cow', 'Not a Cow'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='detections')
    image = models.ImageField(upload_to='cattle_images/%Y/%m/%d/')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, null=True, blank=True)
    confidence_score = models.FloatField(null=True, blank=True)

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
