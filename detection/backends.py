"""
Custom authentication backend — login with email address
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)


class EmailOrUsernameBackend(ModelBackend):
    """
    Authenticate users by email address (primary) or username (fallback).
    Credentials set at registration are stored permanently on the User object.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        try:
            # Try email first, then fall back to username
            try:
                user = User.objects.get(email__iexact=username)
            except User.DoesNotExist:
                try:
                    user = User.objects.get(username__iexact=username)
                except User.DoesNotExist:
                    logger.info(f"No user found with email/username: {username}")
                    return None

            if user.check_password(password) and self.user_can_authenticate(user):
                logger.info(f"User {user.email} authenticated successfully")
                return user
            else:
                logger.info(f"Invalid password for user: {user.email}")
                return None

        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
