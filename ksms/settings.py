"""
Django settings for Kenya School Management System (KSMS).
"""

from pathlib import Path
import sys

from decouple import config


# ─── Sentry (optional) ────────────────────────────────────────────────────────
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=config('SENTRY_ENVIRONMENT', default='production'),
        traces_sample_rate=config('SENTRY_TRACES_SAMPLE_RATE', default=0.1, cast=float),
        profiles_sample_rate=config('SENTRY_PROFILES_SAMPLE_RATE', default=0.1, cast=float),
    )


def csv_list(name, default=''):
    return [item.strip() for item in config(name, default=default).split(',') if item.strip()]

BASE_DIR = Path(__file__).resolve().parent.parent


# ─── Security ─────────────────────────────────────────────────────────────────
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
RUNNING_TESTS = 'test' in sys.argv
DEMO_MODE = config('DEMO_MODE', default=False, cast=bool)
DEMO_DEFAULT_PASSWORD = config('DEMO_DEFAULT_PASSWORD', default='ChangeMe12345')
DEMO_USERNAMES = csv_list('DEMO_USERNAMES', '')
FINAL_SUPERUSER_USERNAME = config('FINAL_SUPERUSER_USERNAME', default='')
FINAL_SUPERUSER_EMAIL = config('FINAL_SUPERUSER_EMAIL', default='')
FIELD_ENCRYPTION_KEY = config('FIELD_ENCRYPTION_KEY', default='')
# Always include platform hosting domains so env var overrides can't lock us out.
_PLATFORM_HOSTS = ['.vercel.app', '.onrender.com', '.up.railway.app']
_PLATFORM_ORIGINS = ['https://*.vercel.app', 'https://*.onrender.com', 'https://*.up.railway.app']

ALLOWED_HOSTS = list(set(
    csv_list('ALLOWED_HOSTS', '127.0.0.1,localhost') + _PLATFORM_HOSTS
))
CSRF_TRUSTED_ORIGINS = list(set(
    csv_list(
        'CSRF_TRUSTED_ORIGINS',
        'http://127.0.0.1:8000,http://localhost:8000' if DEBUG else '',
    ) + _PLATFORM_ORIGINS
))


# ─── Applications ─────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    # Django core
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    # Third-party
    'allauth',
    'allauth.account',
    'tailwind',
    'theme',
    'django_htmx',
    # Local apps
    'core.apps.CoreConfig',
    'students',
    'academics',
    'attendance',
    'finance',
    'reports',
    'communication',
    'cbc.apps.CbcConfig',
]


# ─── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware.RequestContextMiddleware',
    'core.middleware.SecurityHeadersMiddleware',
    'core.middleware.RateLimitHeadersMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

ROOT_URLCONF = 'ksms.urls'


# ─── Templates ─────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'ksms.wsgi.application'


# ─── Database (Supabase PostgreSQL, optional local SQLite fallback) ──────────
USE_SQLITE = config('USE_SQLITE', default=False, cast=bool)

if USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            # Allow concurrent reader/writer (e.g. STK push form + Daraja callback)
            # by enabling WAL journaling and a generous busy timeout. Without this,
            # SQLite raises "database is locked" the moment two requests overlap.
            'OPTIONS': {
                'timeout': 30,
                'init_command': 'PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;',
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='postgres'),
            'USER': config('DB_USER', default='postgres'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST'),
            'PORT': config('DB_PORT', default='5432'),
            'CONN_MAX_AGE': config('CONN_MAX_AGE', default=60, cast=int),
            'CONN_HEALTH_CHECKS': config('CONN_HEALTH_CHECKS', default=True, cast=bool),
            'OPTIONS': {
                'sslmode': 'require',
            },
        }
    }


# ─── Authentication ────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'core.User'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 12},
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

SITE_ID = 1
LOGIN_URL = 'account_login'


# ─── django-allauth (v65+) ─────────────────────────────────────────────────────
ACCOUNT_LOGIN_METHODS = {'username', 'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
# Keep strict verification for production-like environments while allowing
# local/dev and demo workflows to authenticate without mailbox round-trips.
ACCOUNT_EMAIL_VERIFICATION = 'none' if (DEMO_MODE or DEBUG) else 'mandatory'
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_PREVENT_ENUMERATION = True
ACCOUNT_SESSION_REMEMBER = False
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = True
ACCOUNT_AUTHENTICATED_LOGIN_REDIRECTS = True
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 2
ACCOUNT_EMAIL_SUBJECT_PREFIX = '[KSMS] '
ACCOUNT_ADAPTER = 'core.adapters.RateLimitedAccountAdapter'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'

EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.console.EmailBackend',
)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@ksms.local')


# ─── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True


# ─── Static & Media ───────────────────────────────────────────────────────────
STATIC_URL = config('STATIC_URL', default='/static/')
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# WhiteNoise compression and manifest
WHITENOISE_COMPRESSION_ENABLED = config('WHITENOISE_COMPRESSION_ENABLED', default=not DEBUG, cast=bool)
WHITENOISE_MANIFEST_STRICT = config('WHITENOISE_MANIFEST_STRICT', default=False, cast=bool)

# CDN overrides (set CDN_STATIC_URL to a full CDN URL to serve statics from CDN)
CDN_STATIC_URL = config('CDN_STATIC_URL', default='')
CDN_MEDIA_URL = config('CDN_MEDIA_URL', default='')

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': (
            'django.contrib.staticfiles.storage.StaticFilesStorage'
            if DEBUG or RUNNING_TESTS
            else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
        ),
    },
}

MEDIA_URL = config('MEDIA_URL', default='/media/')
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SESSION_COOKIE_NAME = 'ksms_sessionid'
CSRF_COOKIE_NAME = 'ksms_csrftoken'
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=not DEBUG, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=not DEBUG, cast=bool)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = config('SESSION_COOKIE_AGE', default=86400, cast=int)

SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=not DEBUG, cast=bool)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
SECURE_HSTS_SECONDS = config(
    'SECURE_HSTS_SECONDS',
    default=31536000 if not DEBUG else 0,
    cast=int,
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    'SECURE_HSTS_INCLUDE_SUBDOMAINS',
    default=not DEBUG,
    cast=bool,
)
SECURE_HSTS_PRELOAD = config(
    'SECURE_HSTS_PRELOAD',
    default=not DEBUG,
    cast=bool,
)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

CSP_SCRIPT_SRC = config(
    'CSP_SCRIPT_SRC',
    default="'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
)
CSP_STYLE_SRC = config(
    'CSP_STYLE_SRC',
    default="'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
)
CSP_IMG_SRC = config(
    'CSP_IMG_SRC',
    default="'self' data: https:",
)
CSP_CONNECT_SRC = config(
    'CSP_CONNECT_SRC',
    default="'self'",
)
CSP_FONT_SRC = config(
    'CSP_FONT_SRC',
    default="'self' https://cdnjs.cloudflare.com",
)
CSP_FRAME_ANCESTORS = config('CSP_FRAME_ANCESTORS', default="'none'")
CSP_DEFAULT_SRC = config('CSP_DEFAULT_SRC', default="'self'")


# ─── Caching ───────────────────────────────────────────────────────────────────
# Local-memory cache is sufficient for dev/staging.
# In production, switch to Redis-backed cache for cross-process sharing.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'ksms-default',
    }
}
CACHE_DASHBOARD_SECONDS = config('CACHE_DASHBOARD_SECONDS', default=300, cast=int)


# ─── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '{levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'ksms.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'security_file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'security.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'] if DEBUG else ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'] if DEBUG else ['file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'core.security': {
            'handlers': ['console', 'security_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'] if DEBUG else ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'ksms': {
            'handlers': ['console'] if DEBUG else ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'] if DEBUG else ['console', 'file'],
        'level': 'INFO',
    },
}


# ─── Tailwind ──────────────────────────────────────────────────────────────────
TAILWIND_APP_NAME = 'theme'
INTERNAL_IPS = ['127.0.0.1']


# ─── Finance Integrations ────────────────────────────────────────────────────
ARREARS_ENABLED = config('ARREARS_ENABLED', default=True, cast=bool)
MPESA_STK_ENABLED = config('MPESA_STK_ENABLED', default=False, cast=bool)
AUTO_REMINDERS_ENABLED = config('AUTO_REMINDERS_ENABLED', default=False, cast=bool)
SEND_PAYMENT_NOTIFICATIONS = config('SEND_PAYMENT_NOTIFICATIONS', default=False, cast=bool)
REMINDER_EMAIL_ENABLED = config('REMINDER_EMAIL_ENABLED', default=False, cast=bool)

MPESA_ENV = config('MPESA_ENV', default='sandbox')
MPESA_CONSUMER_KEY = config('MPESA_CONSUMER_KEY', default='')
MPESA_CONSUMER_SECRET = config('MPESA_CONSUMER_SECRET', default='')
MPESA_SHORTCODE = config('MPESA_SHORTCODE', default='174379')
MPESA_PASSKEY = config('MPESA_PASSKEY', default='')
MPESA_CALLBACK_TOKEN = config('MPESA_CALLBACK_TOKEN', default='')
MPESA_TRANSACTION_TYPE = config('MPESA_TRANSACTION_TYPE', default='CustomerPayBillOnline')
MPESA_ACCOUNT_REFERENCE = config('MPESA_ACCOUNT_REFERENCE', default='KSMS-FEES')
MPESA_BUSINESS_NAME = config('MPESA_BUSINESS_NAME', default='Kenya School MS')
MPESA_TIMEOUT_SECONDS = config('MPESA_TIMEOUT_SECONDS', default=20, cast=int)
MPESA_BASE_URL = config(
    'MPESA_BASE_URL',
    default=(
        'https://sandbox.safaricom.co.ke'
        if MPESA_ENV == 'sandbox'
        else 'https://api.safaricom.co.ke'
    ),
)

AFRICASTALKING_ENABLED = config('AFRICASTALKING_ENABLED', default=False, cast=bool)
AFRICASTALKING_USERNAME = config('AFRICASTALKING_USERNAME', default='sandbox')
AFRICASTALKING_API_KEY = config('AFRICASTALKING_API_KEY', default='')
AFRICASTALKING_SENDER_ID = config('AFRICASTALKING_SENDER_ID', default='')
AFRICASTALKING_TIMEOUT_SECONDS = config('AFRICASTALKING_TIMEOUT_SECONDS', default=20, cast=int)
AFRICASTALKING_BASE_URL = config(
    'AFRICASTALKING_BASE_URL',
    default='https://api.africastalking.com/version1/messaging',
)

REMINDER_DAILY_ENABLED = config('REMINDER_DAILY_ENABLED', default=True, cast=bool)
REMINDER_WEEKLY_ENABLED = config('REMINDER_WEEKLY_ENABLED', default=True, cast=bool)
REMINDER_OVERDUE_ESCALATION_DAYS = config('REMINDER_OVERDUE_ESCALATION_DAYS', default=10, cast=int)
REMINDER_MIN_HOURS_BETWEEN_SENDS = config('REMINDER_MIN_HOURS_BETWEEN_SENDS', default=24, cast=int)


# ─── Celery ──────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default=CELERY_BROKER_URL)
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=RUNNING_TESTS, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = config('CELERY_TASK_EAGER_PROPAGATES', default=True, cast=bool)

# Task result expiry to prevent Redis memory growth
CELERY_RESULT_EXPIRES = 3600  # 1 hour

# Task serialization and acks
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

# Task rejection on worker loss (prevents lost tasks)
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# Priority queues: high > normal > default > low
CELERY_TASK_QUEUE_MAX_PRIORITY = 10
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_QUEUES = {
    'high': {
        'exchange': 'high',
        'exchange_type': 'direct',
        'routing_key': 'high',
        'x-max-priority': 10,
    },
    'normal': {
        'exchange': 'normal',
        'exchange_type': 'direct',
        'routing_key': 'normal',
        'x-max-priority': 10,
    },
    'default': {
        'exchange': 'default',
        'exchange_type': 'direct',
        'routing_key': 'default',
    },
    'low': {
        'exchange': 'low',
        'exchange_type': 'direct',
        'routing_key': 'low',
    },
}
CELERY_TASK_ROUTES = {
    'finance.tasks.send_payment_receipt_task': {'queue': 'high', 'priority': 9},
    'finance.tasks.send_daily_fee_reminders_task': {'queue': 'normal', 'priority': 5},
    'finance.tasks.send_weekly_fee_reminders_task': {'queue': 'normal', 'priority': 5},
    'finance.tasks.sync_fee_arrears_task': {'queue': 'default'},
}

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'finance-sync-fee-arrears-daily': {
        'task': 'finance.tasks.sync_fee_arrears_task',
        'schedule': crontab(
            minute=config('CELERY_SYNC_ARREARS_CRON_MINUTE', default=0, cast=int),
            hour=config('CELERY_SYNC_ARREARS_CRON_HOUR', default=2, cast=int),
        ),
    },
    'finance-send-daily-reminders': {
        'task': 'finance.tasks.send_daily_fee_reminders_task',
        'schedule': crontab(
            minute=config('CELERY_DAILY_REMINDER_CRON_MINUTE', default=30, cast=int),
            hour=config('CELERY_DAILY_REMINDER_CRON_HOUR', default=8, cast=int),
        ),
    },
    'finance-send-weekly-reminders': {
        'task': 'finance.tasks.send_weekly_fee_reminders_task',
        'schedule': crontab(
            minute=config('CELERY_WEEKLY_REMINDER_CRON_MINUTE', default=0, cast=int),
            hour=config('CELERY_WEEKLY_REMINDER_CRON_HOUR', default=9, cast=int),
            day_of_week=config('CELERY_WEEKLY_REMINDER_DAY', default=1, cast=int),
        ),
    },
}


# ─── Export Limits ───────────────────────────────────────────────────────────
EXPORT_ROW_LIMIT = config('EXPORT_ROW_LIMIT', default=5000, cast=int)
