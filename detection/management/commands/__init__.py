"""
Management command to populate initial test data
Create directory structure first:
mkdir -p detection/management/commands
touch detection/management/__init__.py
touch detection/management/commands/__init__.py
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from detection.models import UserProfile, SystemStatistics

class Command(BaseCommand):
    help = 'Populate database with initial test data'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Starting data population...'))
        
        # Create test user if doesn't exist
        if not User.objects.filter(username='testuser').exists():
            user = User.objects.create_user(
                username='testuser',
                email='test@simbafarns.com',
                password='testpass123',
                first_name='Test',
                last_name='User'
            )
            
            # Create profile
            UserProfile.objects.create(
                user=user,
                phone_number='+256700000000',
                farm_name='Simba Farms',
                location='Ibanda District',
                is_verified=True
            )
            
            self.stdout.write(self.style.SUCCESS(f'Created test user: {user.username}'))
        
        # Create initial statistics entry
        SystemStatistics.objects.get_or_create(
            date=timezone.now().date(),
            defaults={
                'total_scans': 0,
                'fmd_detected': 0,
                'healthy_cattle': 0,
                'not_cow_detected': 0
            }
        )
        
        self.stdout.write(self.style.SUCCESS('Data population completed!'))
        self.stdout.write(self.style.WARNING('Test user credentials:'))
        self.stdout.write(self.style.WARNING('Username: testuser'))
        self.stdout.write(self.style.WARNING('Password: testpass123'))