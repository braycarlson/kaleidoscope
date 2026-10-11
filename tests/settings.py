from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ALLOWED_HOSTS = ['*']
API_TOKEN = 'canary-token-value'
DATABASE_PASSWD = 'canary-passwd-value'

CACHES = {
    'default': {'BACKEND': 'tests.testapp.cache.FaultCache', 'LOCATION': 'kaleidoscope-tests'},
}

DATABASES = {
    'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'},
    'other': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'},
}

DEBUG = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.staticfiles',
    'kaleidoscope',
    'tests.testapp',
]

INTERNAL_IPS = ['127.0.0.1']
KALEIDOSCOPE_IGNORE_PATHS = ['/ignored/']
KALEIDOSCOPE_SHOW_CALLBACK = 'tests.testapp.visibility.toolbar_visible'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'loggers': {'django.request': {'level': 'CRITICAL'}},
}

MIDDLEWARE = ['kaleidoscope.middleware.KaleidoscopeMiddleware']
ROOT_URLCONF = 'tests.testapp.urls'
SECRET_KEY = 'kaleidoscope-tests-secret-key'

SERVICE_CREDENTIALS = {
    'primary': {'HOST': 'service.internal', 'PASSWORD': 'canary-nested-password'},
    'replicas': [{'HOST': 'replica.internal', 'TOKEN': 'canary-nested-token'}],
    'webhook': {'SIGNATURE': 'canary-nested-signature', 'URL': 'https://hooks.internal/'},
}

STATIC_URL = '/static/'

TEMPLATES = [
    {
        'APP_DIRS': True,
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'OPTIONS': {},
    },
]

TIME_ZONE = 'UTC'
USE_TZ = True
