"""WSGI entry point for the Study Trail Builder backend.

Exposes the module-level ``application`` object served by gunicorn as
``config.wsgi:application`` inside the Docker stack (design: Backend runs via
gunicorn).
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
