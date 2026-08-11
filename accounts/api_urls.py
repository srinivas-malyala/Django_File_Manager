"""JWT REST authentication URL configuration."""

from django.urls import path
from .api_views import (
    AuthenticationStatusView,
    ThrottledTokenBlacklistView,
    ThrottledTokenObtainPairView,
    ThrottledTokenRefreshView,
)

app_name = "account_api"

urlpatterns = [
    path("token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", ThrottledTokenRefreshView.as_view(), name="token_refresh"),
    path(
        "token/blacklist/",
        ThrottledTokenBlacklistView.as_view(),
        name="token_blacklist",
    ),
    path("status/", AuthenticationStatusView.as_view(), name="status"),
]
