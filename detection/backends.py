"""
Custom authentication backend to allow login with email or username
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q
import logging

logger = logging.getLogger(__name__)


class EmailOrUsernameBackend(ModelBackend):
    """
    Custom authentication backend that allows users to log in with either
    their email address or username
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate user by email or username
        """
        if username is None or password is None:
            return None
        
        try:
            # Try to find user by username or email (case-insensitive)
            user = User.objects.filter(
                Q(username__iexact=username) | Q(email__iexact=username)
            ).first()
            
            if user is None:
                logger.info(f"No user found with username/email: {username}")
                return None
            
            # Check if password is correct
            if user.check_password(password):
                logger.info(f"User {user.username} authenticated successfully")
                return user
            else:
                logger.info(f"Invalid password for user: {user.username}")
                return None
            
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return None
    
    def get_user(self, user_id):
        """
        Get user by ID
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None