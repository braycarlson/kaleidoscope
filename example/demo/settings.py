from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'kaleidoscope-example',
    }
}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'database.sqlite3',
    }
}

DEBUG = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'kaleidoscope',
    'bookstore'
]

INTERNAL_IPS = ['127.0.0.1']

LANGUAGE_CODE = 'en-us'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'kaleidoscope.middleware.KaleidoscopeMiddleware'
]

ROOT_URLCONF = 'demo.urls'

SECRET_KEY = 'kaleidoscope-example-insecure-secret-key'

STATIC_URL = 'static/'

STATICFILES_DIRS = [BASE_DIR / 'static']

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages'
            ]
        }
    }
]

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

WSGI_APPLICATION = 'demo.wsgi.application'

X_FRAME_OPTIONS = 'SAMEORIGIN'
