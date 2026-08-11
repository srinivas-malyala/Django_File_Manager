"""Browser account URL configuration."""

from django.urls import path

from .views import (
    AccountLoginView,
    AccountLogoutView,
    AccountPasswordChangeView,
    AccountPasswordResetCompleteView,
    AccountPasswordResetConfirmView,
    AccountPasswordResetDoneView,
    AccountPasswordResetView,
    ProfileView,
    RegistrationView,
)

app_name = "accounts"

urlpatterns = [
    path("register/", RegistrationView.as_view(), name="register"),
    path("login/", AccountLoginView.as_view(), name="login"),
    path("logout/", AccountLogoutView.as_view(), name="logout"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path(
        "password/change/",
        AccountPasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "password/reset/request/",
        AccountPasswordResetView.as_view(),
        name="password_reset_request",
    ),
    path(
        "password/reset/requested/",
        AccountPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password/reset/confirm/<uidb64>/<token>/",
        AccountPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/complete/",
        AccountPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
