# === PYTHON 3.14 COMPATIBILITY PATCH ===
import django.template.context as _ctx_mod

def _fixed_basecontext_copy(self):
    cls = self.__class__
    duplicate = cls.__new__(cls)
    duplicate.__dict__.update(self.__dict__)
    duplicate.dicts = self.dicts[:]
    return duplicate

def _fixed_context_copy(self):
    cls = self.__class__
    duplicate = cls.__new__(cls)
    duplicate.__dict__.update(self.__dict__)
    duplicate.dicts = [d.copy() for d in self.dicts]
    return duplicate

if hasattr(_ctx_mod.BaseContext, '__copy__'):
    _ctx_mod.BaseContext.__copy__ = _fixed_basecontext_copy
if hasattr(_ctx_mod.Context, '__copy__'):
    _ctx_mod.Context.__copy__ = _fixed_context_copy
# =======================================
"""
Django settings for Construction Billing & Project Management.
PostgreSQL backend. Ready for production with environment variables.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]

# ---------------------------------------------------------------------------
# APPS
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'billing',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
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

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ---------------------------------------------------------------------------
# DATABASE — PostgreSQL
# ---------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ---------------------------------------------------------------------------
# PASSWORD VALIDATION
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# INTERNATIONALIZATION
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dubai'  # Adjust to your region
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# STATIC & MEDIA
# ---------------------------------------------------------------------------
STATIC_URL = os.getenv('STATIC_URL', '/static/')
STATIC_ROOT = BASE_DIR / os.getenv('STATIC_ROOT', 'staticfiles')

MEDIA_URL = os.getenv('MEDIA_URL', '/media/')
MEDIA_ROOT = BASE_DIR / os.getenv('MEDIA_ROOT', 'media')

# ---------------------------------------------------------------------------
# DEFAULT PRIMARY KEY
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# SESSION & SECURITY
# ---------------------------------------------------------------------------
SESSION_COOKIE_AGE = 3600 * 8  # 8 hours
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# ---------------------------------------------------------------------------
# ADMIN SITE HEADER (pulled dynamically via CompanyProfile)
# ---------------------------------------------------------------------------
ADMIN_SITE_HEADER = "Billing & Project Management"
ADMIN_SITE_TITLE = "Billing & Project Management Portal"
ADMIN_INDEX_TITLE = "Dashboard"
