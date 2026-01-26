"""
Custom authentication backend to allow login with email or username
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q


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
            # Try to find user by username or email
            user = User.objects.get(Q(username=username) | Q(email=username))
            
            # Check if password is correct
            if user.check_password(password):
                return user
            
        except User.DoesNotExist:
            # Run the default password hasher once to reduce timing
            # difference between existing and non-existing users
            User().set_password(password)
            return None
        
        except User.MultipleObjectsReturned:
            # This shouldn't happen if emails are unique, but handle it
            user = User.objects.filter(Q(username=username) | Q(email=username)).first()
            if user and user.check_password(password):
                return user
        
        return None
    
    def get_user(self, user_id):
        """
        Get user by ID
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None