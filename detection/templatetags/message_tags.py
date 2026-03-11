from django import template
from django.db.models import Q
from detection.models import DirectMessage

register = template.Library()

@register.filter
def unread_message_count(user):
    if user.is_authenticated:
        # We count messages where:
        # 1. The message is part of a conversation the user is in
        # 2. The message was NOT sent by the current user (sender != user)
        # 3. The message is marked as unread (is_read=False)
        return DirectMessage.objects.filter(
            conversation__participants=user,
            is_read=False
        ).exclude(sender=user).count()
    return 0