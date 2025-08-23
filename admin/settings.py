import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-CHANGE-ME-IN-PRODUCTION')
DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() in ('true','1','yes','on')
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if h.strip()
]
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.admin",
    "django.contrib.staticfiles",
    "core",
]
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'botdb'),
        'USER': os.environ.get('POSTGRES_USER', 'bot'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', os.environ.get('DB_PASSWORD', 'botpass')),
        'HOST': os.environ.get('POSTGRES_HOST', os.environ.get('DB_HOST', 'db')),
        'PORT': os.environ.get('POSTGRES_PORT', os.environ.get('DB_PORT', '5432')),
    }
}
ROOT_URLCONF = "urls"
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

# WhiteNoise storage for compressed static files
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Internationalization
LANGUAGE_CODE = 'ru-RU'
TIME_ZONE = os.environ.get('TIMEZONE', 'Europe/Moscow')
USE_I18N = True
USE_L10N = True
USE_TZ = True