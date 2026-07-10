"""Development settings — enable debug + verbose logging."""
from .base import *  # noqa: F403, F401

DEBUG = True

INSTALLED_APPS += ['django_extensions']  # noqa: F405

# SQL logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
    },
}
