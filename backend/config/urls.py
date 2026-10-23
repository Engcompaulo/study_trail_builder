"""URL routing for the Study Trail Builder backend.

A single endpoint is exposed: ``POST /api/trail``. The view itself is added in
a later task (``trail.views.trail_view``); this module only defines the route
table and is kept intentionally minimal (design: single-endpoint backend).
"""

from django.urls import path

from trail.views import trail_view

# A single endpoint is exposed. The path has no trailing slash so it matches the
# CORS_URLS_REGEX (``^/api/trail$``) configured in settings.
urlpatterns = [
    path("api/trail", trail_view, name="trail"),
]
