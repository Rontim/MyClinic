"""URL configuration for the MyClinic API project."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    # Accounts and Auth
    path("api/auth/", include("djoser.urls")),
    path("api/auth/", include("djoser.urls.jwt")),

    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[]), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema", permission_classes=[]),
        name="docs",
    ),
]
