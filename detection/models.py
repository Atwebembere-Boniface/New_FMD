from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid

class UserProfile(models.Model):
    """Extended user profile for additional information"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=15, blank=True)
    farm_name = models.CharField(max_length=100, default='Simba Farms')
    location = models.CharField(max_length=100, default='Ibanda District')
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.farm_name}"

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'


class Detection(models.Model):
    """Model to store cattle image detection results"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending Analysis'),
        ('analyzing', 'Analyzing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    RESULT_CHOICES = [
        ('healthy', 'Healthy'),
        ('fmd', 'FMD Detected'),
        ('not_cow', 'Not a Cow'),
        ('inconclusive', 'Inconclusive'),
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
        """Check if FMD was detected"""
        return self.result == 'fmd'
    
    @property
    def is_completed(self):
        """Check if analysis is complete"""
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