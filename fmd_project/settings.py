"""
Django settings for fmd_project
Development & Production Ready
"""

import os
import ssl
from pathlib import Path
import dj_database_url

# Fix SSL email issues on some hosts
ssl._create_default_https_context = ssl._create_unverified_context

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


# --------------------------------------------------
# SECURITY
# --------------------------------------------------
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-development-key-change-in-production"
)

DEBUG = os.environ.get("DEBUG", "True").lower() == "true"


# --------------------------------------------------
# ALLOWED HOSTS
# --------------------------------------------------
if DEBUG:
    ALLOWED_HOSTS = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
    ]
else:
    ALLOWED_HOSTS = [
        "new-fmd-1.onrender.com",
        ".onrender.com",
    ]

CSRF_TRUSTED_ORIGINS = [
    "https://new-fmd-1.onrender.com",
    "https://*.onrender.com",
]


# --------------------------------------------------
# APPLICATIONS
# --------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Local apps
    "detection",
]


# --------------------------------------------------
# MIDDLEWARE
# --------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# --------------------------------------------------
# URLS / WSGI
# --------------------------------------------------
ROOT_URLCONF = "fmd_project.urls"

WSGI_APPLICATION = "fmd_project.wsgi.application"


# --------------------------------------------------
# TEMPLATES
# --------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",

        "DIRS": [
            BASE_DIR / "templates"
        ],

        "APP_DIRS": True,

        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",

                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",

                "detection.context_processors.vet_sidebar_counts",
            ],
        },
    },
]


# --------------------------------------------------
# DATABASE
# --------------------------------------------------
if os.environ.get("DATABASE_URL"):

    DATABASES = {
        "default": dj_database_url.config(
            conn_max_age=600,
            conn_health_checks=True,
        )
    }

else:

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# --------------------------------------------------
# PASSWORD VALIDATION
# --------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"
    },
]


# --------------------------------------------------
# INTERNATIONALIZATION
# --------------------------------------------------
LANGUAGE_CODE = "en-us"

TIME_ZONE = "Africa/Kampala"

USE_I18N = True

USE_TZ = True


# --------------------------------------------------
# STATIC FILES
# --------------------------------------------------
STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    BASE_DIR / "static"
]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },

    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# --------------------------------------------------
# MEDIA FILES
# --------------------------------------------------
MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# --------------------------------------------------
# AUTH
# --------------------------------------------------
LOGIN_URL = "login"

LOGIN_REDIRECT_URL = "dashboard"

LOGOUT_REDIRECT_URL = "login"

AUTHENTICATION_BACKENDS = [
    "detection.backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"



EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'fmd001check@gmail.com'
EMAIL_HOST_PASSWORD = 'zwmgyaqfzxapfjde'
DEFAULT_FROM_EMAIL = 'FMD dection system <fmd001check@gmail.com>'



EGOSMS_USERNAME = 'atwebembereboniface'
EGOSMS_PASSWORD = '76def263b28138b7f7881667d6be313ce92552bf31d2c7d1'
EGOSMS_SENDER_ID = 'UG-SMS'
EGOSMS_API_URL = 'https://comms.egosms.co/api/v1/plain/'



# # --------------------------------------------------
# # EGOSMS SETTINGS
# # --------------------------------------------------
# EGOSMS_USERNAME = "atwebembereboniface"

# EGOSMS_PASSWORD = "76def263b28138b7f7881667d6be313ce92552bf31d2c7d1"

# EGOSMS_SENDER = "EgoSMS"

# EGOSMS_SENDER_ID = EGOSMS_SENDER

# EGOSMS_API_URL = "https://www.egosms.co/api/v1/plain"

# SMS_ENABLED = True

# --------------------------------------------------
# SECURITY - PRODUCTION ONLY
# --------------------------------------------------
if not DEBUG:

    SECURE_SSL_REDIRECT = True

    SESSION_COOKIE_SECURE = True

    CSRF_COOKIE_SECURE = True

    SECURE_BROWSER_XSS_FILTER = True

    SECURE_CONTENT_TYPE_NOSNIFF = True

    SECURE_HSTS_SECONDS = 31536000

    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

    SECURE_HSTS_PRELOAD = True

    X_FRAME_OPTIONS = "DENY"


# --------------------------------------------------
# LOGGING
# --------------------------------------------------
LOGGING = {
    "version": 1,

    "disable_existing_loggers": False,

    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },

    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },

    "loggers": {

        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },

        "django.core.mail": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },

        "detection.notifications": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}