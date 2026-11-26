from django.contrib import admin
from django.urls import path, include

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from rest_framework.permissions import AllowAny

from .health import live, ready

handler500 = "Backend.errors.server_error"


urlpatterns = [
    path("health/live/", live, name="health-live"),
    path("health/ready/", ready, name="health-ready"),

    # Django Admin
    path("admin/", admin.site.urls),

    # Authentication APIs
    path("api/auth/", include("accounts.urls")),

    # OpenAPI Schema
    path(
        "api/schema/",
        SpectacularAPIView.as_view(
            permission_classes=[AllowAny],
            authentication_classes=[],
        ),
        name="schema",
    ),

    # Swagger UI
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema",
            permission_classes=[AllowAny],
            authentication_classes=[],
        ),
        name="swagger-ui",
    ),

    # ReDoc
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(
            url_name="schema",
            permission_classes=[AllowAny],
            authentication_classes=[],
        ),
        name="redoc",
    ),
    path("api/", include("challenges.urls")),
    path("api/", include("notifications.urls")),
    path("api/", include("groups.urls")),
    path("api/reports/", include("reports.views")),
    path("api/coach/", include("coach.views")),
    path("api/premium/", include("premium.urls")),
    path("api/internal/n8n/", include("Backend.workflows")),

]