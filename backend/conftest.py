"""Pytest bootstrap for the Study Trail Builder backend test suite.

This lightweight conftest lives at the backend root so that running ``pytest``
from ``backend/`` puts this directory on ``sys.path`` (making ``import trail``
and ``import config`` work) and configures Django before any test module that
touches the HTTP view is collected.

We deliberately avoid adding ``pytest-django`` as a dependency: the view tests
only need Django's settings loaded and ``django.setup()`` called once, which a
few lines here accomplish without a new package (design: proportionate scope).
"""

from __future__ import annotations

import os

import django

# Point Django at the project settings and initialize the app registry once,
# at collection time, so ``trail.views`` (which imports django.http) and the
# RequestFactory/Client used by the view tests work without a running server.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

# The Django test ``Client`` sends requests with the host ``testserver``. Allow
# it here (test process only) so CommonMiddleware does not reject requests with
# a 400 before they reach the view. This mutates only the in-memory settings of
# the test run; it does not change the project's deployed ALLOWED_HOSTS.
from django.conf import settings  # noqa: E402  (import must follow django.setup)

if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]
