"""Root URL configuration."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.api_urls")),
    path("api/auth/", include("accounts.api_urls")),
    path("api/files/", include("files.urls")),
    path("accounts/", include("accounts.urls")),
    path("console/", include("user_console.urls")),
    path("", include("core.urls")),
]

handler404 = "core.views.custom_404"
handler500 = "core.views.custom_500"
