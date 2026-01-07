from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count, Q
from .models import UserProfile, Detection, SystemStatistics

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'farm_name', 'location', 'phone_number', 'is_verified', 'created_at']
    list_filter = ['is_verified', 'location', 'created_at']
    search_fields = ['user__username', 'user__email', 'farm_name', 'phone_number']
    list_editable = ['is_verified']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'phone_number')
        }),
        ('Farm Information', {
            'fields': ('farm_name', 'location')
        }),
        ('Verification', {
            'fields': ('is_verified',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Detection)
class DetectionAdmin(admin.ModelAdmin):
    list_display = [
        'id_short', 'user', 'status_badge', 'result_badge', 
        'confidence_display', 'uploaded_at', 'verified_badge'
    ]
    list_filter = ['status', 'result', 'verified_by_admin', 'uploaded_at']
    search_fields = ['user__username', 'animal_id', 'id']
    readonly_fields = ['id', 'uploaded_at', 'analyzed_at', 'image_preview']
    list_per_page = 50
    
    fieldsets = (
        ('Detection Information', {
            'fields': ('id', 'user', 'image', 'image_preview')
        }),
        ('Analysis Results', {
            'fields': ('status', 'result', 'confidence_score', 'analyzed_at')
        }),
        ('Metadata', {
            'fields': ('animal_id', 'location', 'notes')
        }),
        ('Admin Verification', {
            'fields': ('verified_by_admin', 'admin_notes'),
            'classes': ('collapse',)
        }),
    )
    
    def id_short(self, obj):
        """Display shortened ID"""
        return str(obj.id)[:8]
    id_short.short_description = 'ID'
    
    def status_badge(self, obj):
        """Display status with color coding"""
        colors = {
            'pending': 'gray',
            'analyzing': 'blue',
            'completed': 'green',
            'failed': 'red'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.status, 'gray'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def result_badge(self, obj):
        """Display result with color coding"""
        if not obj.result:
            return format_html('<span style="color: gray;">-</span>')
        
        colors = {
            'healthy': 'green',
            'fmd': 'red',
            'not_cow': 'orange',
            'inconclusive': 'gray'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.result, 'gray'),
            obj.get_result_display()
        )
    result_badge.short_description = 'Result'
    
    def confidence_display(self, obj):
        """Display confidence score as percentage"""
        if obj.confidence_score is None:
            return '-'
        return f"{obj.confidence_score:.1f}%"
    confidence_display.short_description = 'Confidence'
    
    def verified_badge(self, obj):
        """Display verification status"""
        if obj.verified_by_admin:
            return format_html('<span style="color: green;">✓ Verified</span>')
        return format_html('<span style="color: gray;">Not Verified</span>')
    verified_badge.short_description = 'Verified'
    
    def image_preview(self, obj):
        """Display image preview in admin"""
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 300px; max-height: 300px;" />',
                obj.image.url
            )
        return 'No image'
    image_preview.short_description = 'Image Preview'


@admin.register(SystemStatistics)
class SystemStatisticsAdmin(admin.ModelAdmin):
    list_display = ['date', 'total_scans', 'fmd_detected', 'healthy_cattle', 'not_cow_detected']
    list_filter = ['date']
    readonly_fields = ['date']
    
    def has_add_permission(self, request):
        """Prevent manual addition of statistics"""
        return False