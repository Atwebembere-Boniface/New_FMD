"""
notifications.py
Centralised notification service for the FMD Detection System.

This file sends:
- SMS using EgoSMS
- Emails using Django SMTP settings
- In-app notifications

Important:
FMD alert SMS and email are sent when confidence_score >= 70.
"""

import logging
import requests

from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth.models import User
from django.db.models import Q

logger = logging.getLogger(__name__)


# --------------------------------------------------
# SMS HELPERS
# --------------------------------------------------
def _normalise_phone(number: str) -> str:
    """
    Converts Uganda phone numbers to 256XXXXXXXXX format.
    Example:
    0764286203 -> 256764286203
    +256764286203 -> 256764286203
    """
    if not number:
        return ""

    n = str(number).strip()
    n = n.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    if n.startswith("+"):
        n = n[1:]

    if n.startswith("0") and len(n) >= 10:
        n = "256" + n[1:]

    if len(n) == 9:
        n = "256" + n

    return n


def send_sms(phone_number: str, message: str) -> bool:
    """
    Send SMS using EgoSMS.
    """
    sms_enabled = getattr(settings, "SMS_ENABLED", True)

    if not sms_enabled:
        logger.warning("[SMS] SMS sending is disabled in settings.")
        return False

    username = getattr(settings, "EGOSMS_USERNAME", "")
    password = getattr(settings, "EGOSMS_PASSWORD", "")
    sender = getattr(settings, "EGOSMS_SENDER", "FMDSystem")
    api_url = getattr(
        settings,
        "EGOSMS_API_URL",
        "https://www.egosms.co/api/v1/plain/"
    )

    if not username or not password:
        logger.warning("[SMS] EgoSMS username or password is missing.")
        return False

    number = _normalise_phone(phone_number)

    if not number:
        logger.warning("[SMS] Invalid phone number. SMS not sent.")
        return False

    params = {
        "username": username,
        "password": password,
        "number": number,
        "message": message,
        "sender": sender,
    }

    try:
        response = requests.get(api_url, params=params, timeout=20)
        response_text = response.text.strip()

        logger.info("[SMS] EgoSMS response for %s: %s", number, response_text)

        if response.status_code == 200 and (
            response_text.upper().startswith("OK")
            or "SUCCESS" in response_text.upper()
            or "SENT" in response_text.upper()
        ):
            return True

        logger.error(
            "[SMS] EgoSMS failed. Status: %s, Response: %s",
            response.status_code,
            response_text
        )
        return False

    except requests.RequestException as exc:
        logger.error("[SMS] EgoSMS request error for %s: %s", number, exc)
        return False


def send_sms_bulk(phone_numbers: list, message: str):
    results = []

    for number in phone_numbers:
        results.append(send_sms(number, message))

    return results


# --------------------------------------------------
# EMAIL HELPER
# --------------------------------------------------
def send_email_notification(subject: str, message: str, recipient_email: str) -> bool:
    """
    Send email using Django SMTP settings.
    """
    email_enabled = getattr(settings, "EMAIL_ENABLED", True)

    if not email_enabled:
        logger.warning("[EMAIL] Email sending is disabled in settings.")
        return False

    if not recipient_email:
        logger.warning("[EMAIL] Recipient email is missing.")
        return False

    if not getattr(settings, "EMAIL_HOST_USER", ""):
        logger.warning("[EMAIL] EMAIL_HOST_USER is missing.")
        return False

    if not getattr(settings, "EMAIL_HOST_PASSWORD", ""):
        logger.warning("[EMAIL] EMAIL_HOST_PASSWORD is missing.")
        return False

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )

        logger.info("[EMAIL] Email sent successfully to %s", recipient_email)
        return True

    except Exception as exc:
        logger.error("[EMAIL] Failed to send email to %s: %s", recipient_email, exc)
        return False


# --------------------------------------------------
# ADMIN USERS
# --------------------------------------------------
def _get_admins():
    """
    Get system admins.
    """
    return User.objects.filter(
        Q(is_superuser=True) | Q(profile__role="admin")
    ).distinct().select_related("profile")


def _get_user_phone(user):
    """
    Safely get user's phone number from profile.
    """
    try:
        return user.profile.phone_number or ""
    except Exception:
        return ""


def _get_user_role(user):
    """
    Safely get user's role from profile.
    """
    try:
        return user.profile.role or ""
    except Exception:
        return ""


# --------------------------------------------------
# 1. VET REGISTRATION NOTIFICATION
# --------------------------------------------------
def notify_vet_registration(request, vet_user):
    from .models import Notification

    vet_name = vet_user.get_full_name() or vet_user.email
    profile = vet_user.profile

    license_no = getattr(profile, "license_number", "") or "Not provided"
    specialization = getattr(profile, "specialization", "") or "Not provided"
    phone_num = getattr(profile, "phone_number", "") or "Not provided"

    pending_url = request.build_absolute_uri("/admin-panel/vets/pending/")

    admins = _get_admins()

    for admin in admins:
        Notification.objects.create(
            recipient=admin,
            notification_type="vet_registration",
            title=f"New Vet Registration — {vet_name}",
            message=(
                f"Dr. {vet_name} has registered and is awaiting approval.\n"
                f"Email: {vet_user.email}\n"
                f"License: {license_no}\n"
                f"Specialization: {specialization}\n"
                f"Phone: {phone_num}"
            ),
        )

        email_subject = "FMD System — New Vet Registration Pending Approval"
        email_message = (
            f"Hello {admin.get_full_name() or admin.email},\n\n"
            f"A new veterinary doctor has registered and is awaiting approval.\n\n"
            f"Name: Dr. {vet_name}\n"
            f"Email: {vet_user.email}\n"
            f"License: {license_no}\n"
            f"Specialization: {specialization}\n"
            f"Phone: {phone_num}\n\n"
            f"Review here: {pending_url}\n\n"
            f"FMD Detection System"
        )

        send_email_notification(email_subject, email_message, admin.email)

        admin_phone = _get_user_phone(admin)
        if admin_phone:
            sms_body = (
                f"FMD SYSTEM: New vet Dr. {vet_name} has registered "
                f"and is pending approval. Please review."
            )
            send_sms(admin_phone, sms_body)


# --------------------------------------------------
# 2. VET APPROVAL NOTIFICATION
# --------------------------------------------------
def notify_vet_approved(request, vet_user):
    vet_name = vet_user.get_full_name() or vet_user.email
    login_url = request.build_absolute_uri("/")
    vet_phone = _get_user_phone(vet_user)

    subject = "FMD Detection System — Account Approved"
    message = (
        f"Dear Dr. {vet_name},\n\n"
        f"Your veterinary doctor account has been approved.\n\n"
        f"You can now log in using:\n"
        f"Email: {vet_user.email}\n"
        f"URL: {login_url}\n\n"
        f"FMD Detection System"
    )

    send_email_notification(subject, message, vet_user.email)

    if vet_phone:
        sms = (
            f"FMD SYSTEM: Congratulations Dr. {vet_name}. "
            f"Your vet account has been approved. Login: {login_url}"
        )
        send_sms(vet_phone, sms)


# --------------------------------------------------
# 3. VET REJECTION NOTIFICATION
# --------------------------------------------------
def notify_vet_rejected(vet_user, rejection_reason: str = ""):
    vet_name = vet_user.get_full_name() or vet_user.email
    vet_phone = _get_user_phone(vet_user)

    reason_text = f"\n\nReason: {rejection_reason}" if rejection_reason else ""

    subject = "FMD Detection System — Account Application Update"
    message = (
        f"Dear Dr. {vet_name},\n\n"
        f"Your veterinary doctor account application was not approved at this time."
        f"{reason_text}\n\n"
        f"Please contact the system administrator for more information.\n\n"
        f"FMD Detection System"
    )

    send_email_notification(subject, message, vet_user.email)

    if vet_phone:
        sms = f"FMD SYSTEM: Dear Dr. {vet_name}, your vet account was not approved."
        if rejection_reason:
            sms += f" Reason: {rejection_reason[:80]}"
        send_sms(vet_phone, sms)


# --------------------------------------------------
# 4. APPOINTMENT BOOKED NOTIFICATION
# --------------------------------------------------
def notify_appointment_booked(request, appointment):
    vet = appointment.vet
    farmer = appointment.farmer

    vet_name = vet.get_full_name() or vet.email
    farmer_name = farmer.get_full_name() or farmer.email

    appt_date = appointment.preferred_date.strftime("%b %d, %Y at %H:%M")
    reason = appointment.reason[:120]
    location = appointment.location or "Not specified"
    appt_url = request.build_absolute_uri("/vet/appointments/")
    vet_phone = _get_user_phone(vet)

    subject = f"FMD System — New Appointment Request from {farmer_name}"
    message = (
        f"Dear Dr. {vet_name},\n\n"
        f"A farmer has requested an appointment with you.\n\n"
        f"Farmer: {farmer_name} ({farmer.email})\n"
        f"Date/Time: {appt_date}\n"
        f"Reason: {reason}\n"
        f"Location: {location}\n\n"
        f"Review here: {appt_url}\n\n"
        f"FMD Detection System"
    )

    send_email_notification(subject, message, vet.email)

    if vet_phone:
        sms = (
            f"FMD SYSTEM: New appointment from {farmer_name} "
            f"on {appt_date}. Login to review."
        )
        send_sms(vet_phone, sms)


# --------------------------------------------------
# 5. FMD DETECTED NOTIFICATION
# --------------------------------------------------
def notify_fmd_detected(request, detection):
    """
    Sends SMS and email when confidence_score is 70 or above.
    """
    from .models import Notification

    confidence = detection.confidence_score or 0

    if confidence < 70:
        logger.info(
            "[FMD ALERT] Confidence %.1f is below 70. SMS/email not sent.",
            confidence
        )
        return False

    uploader = detection.user
    uploader_name = uploader.get_full_name() or uploader.email

    result = str(getattr(detection, "result", "")).lower()
    result_label = str(getattr(detection, "result_label", "")).lower()

    is_fmd = (
        result == "fmd"
        or "fmd" in result
        or "foot" in result_label
        or "mouth" in result_label
    )

    if not is_fmd:
        logger.info(
            "[FMD ALERT] Confidence is above 70 but result is not FMD. Result: %s",
            result
        )
        return False

    animal_id = getattr(detection, "animal_id", "") or "Unknown"
    location = getattr(detection, "location", "") or "Not recorded"
    conf_str = f"{confidence:.1f}%"

    try:
        uploaded_time = detection.uploaded_at.strftime("%Y-%m-%d %H:%M")
    except Exception:
        uploaded_time = "Not recorded"

    detail_url = request.build_absolute_uri("/admin-panel/uploads/")

    subject = f"FMD ALERT — {conf_str} Confidence"

    email_body = (
        f"FOOT AND MOUTH DISEASE ALERT\n"
        f"====================================\n\n"
        f"FMD has been detected with a confidence score of {conf_str}.\n\n"
        f"Uploaded By: {uploader_name}\n"
        f"Uploader Email: {uploader.email}\n"
        f"Animal ID: {animal_id}\n"
        f"Location: {location}\n"
        f"Confidence: {conf_str}\n"
        f"Time: {uploaded_time}\n\n"
        f"Immediate action required:\n"
        f"1. Isolate the affected animal immediately.\n"
        f"2. Avoid movement of animals from the farm.\n"
        f"3. Inform the veterinary doctor or district veterinary officer.\n"
        f"4. Apply biosecurity measures around the farm.\n\n"
        f"View details: {detail_url}\n\n"
        f"FMD Detection System"
    )

    sms_body = (
        f"FMD ALERT: Disease detected with {conf_str} confidence. "
        f"Animal: {animal_id}. Location: {location}. "
        f"Isolate the animal immediately."
    )

    admins = _get_admins()

    sent_any = False

    for admin in admins:
        Notification.objects.create(
            recipient=admin,
            notification_type="fmd_alert",
            title=f"FMD Alert — {conf_str}",
            message=(
                f"FMD detected with {conf_str} confidence.\n"
                f"Uploaded by: {uploader_name}\n"
                f"Animal: {animal_id}\n"
                f"Location: {location}"
            ),
            detection=detection,
        )

        if admin.email:
            email_sent = send_email_notification(subject, email_body, admin.email)
            sent_any = sent_any or email_sent

        admin_phone = _get_user_phone(admin)
        if admin_phone:
            sms_sent = send_sms(admin_phone, sms_body)
            sent_any = sent_any or sms_sent

    uploader_role = _get_user_role(uploader)
    uploader_phone = _get_user_phone(uploader)

    if uploader.email:
        email_sent = send_email_notification(subject, email_body, uploader.email)
        sent_any = sent_any or email_sent

    if uploader_phone:
        sms_sent = send_sms(uploader_phone, sms_body)
        sent_any = sent_any or sms_sent

    logger.info(
        "[FMD ALERT] Notification process completed. Sent any: %s",
        sent_any
    )

    return sent_any


# --------------------------------------------------
# 6. GENERAL UPLOAD NOTIFICATION
# --------------------------------------------------
def notify_upload(request, detection):
    """
    Standard upload notification.

    If result is FMD and confidence_score >= 70,
    this function automatically calls notify_fmd_detected().
    """
    from .models import Notification

    uploader = detection.user
    uploader_name = uploader.get_full_name() or uploader.email

    confidence_value = detection.confidence_score or 0
    confidence = f"{confidence_value:.1f}%" if confidence_value else "N/A"

    try:
        result_display = detection.result_label or detection.get_result_display()
    except Exception:
        result_display = getattr(detection, "result", "Unknown")

    result = str(getattr(detection, "result", "")).lower()
    result_label = str(getattr(detection, "result_label", "")).lower()

    is_fmd = (
        result == "fmd"
        or "fmd" in result
        or "foot" in result_label
        or "mouth" in result_label
    )

    if is_fmd and confidence_value >= 70:
        notify_fmd_detected(request, detection)
        return

    admins = _get_admins()

    notif_type = "analysis_done"
    notif_title = f"New Detection by {uploader_name}"

    subject = "FMD Detection System — New Upload"
    message = (
        f"A new image has been uploaded and analysed.\n\n"
        f"Uploaded By: {uploader_name}\n"
        f"Result: {result_display}\n"
        f"Confidence: {confidence}\n"
        f"Time: {detection.uploaded_at.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"FMD Detection System"
    )

    for admin in admins:
        Notification.objects.create(
            recipient=admin,
            notification_type=notif_type,
            title=notif_title,
            message=(
                f"Result: {result_display} | "
                f"Confidence: {confidence} | "
                f"By: {uploader_name}"
            ),
            detection=detection,
        )

        if admin.email:
            send_email_notification(subject, message, admin.email)