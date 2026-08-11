"""Session-authenticated browser account views."""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.http import HttpRequest, HttpResponse
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from core.security import RateLimitedViewMixin

from .forms import (
    AccountAuthenticationForm,
    AccountPasswordChangeForm,
    AccountPasswordResetForm,
    AccountSetPasswordForm,
    RegistrationForm,
)

authentication_logger = logging.getLogger("authentication")


class RegistrationView(RateLimitedViewMixin, FormView):
    """Register a user using Django's password validation and hashing."""

    template_name = "auth/register.html"
    form_class = RegistrationForm
    success_url = reverse_lazy("accounts:login")
    rate_limit_scope = "registration"
    rate_limit_methods = frozenset({"POST"})

    def form_valid(self, form: RegistrationForm) -> HttpResponse:
        user = form.save()
        authentication_logger.info("registration_success user_id=%s", user.pk)
        messages.success(self.request, "Your account was created. You can now sign in.")
        return super().form_valid(form)


class AccountLoginView(RateLimitedViewMixin, LoginView):
    """Authenticate a browser session without exposing submitted credentials."""

    template_name = "auth/login.html"
    authentication_form = AccountAuthenticationForm
    redirect_authenticated_user = True
    rate_limit_scope = "login"
    rate_limit_methods = frozenset({"POST"})

    def form_valid(self, form: AccountAuthenticationForm) -> HttpResponse:
        response = super().form_valid(form)
        authentication_logger.info("login_success user_id=%s", form.get_user().pk)
        return response

    def form_invalid(self, form: AccountAuthenticationForm) -> HttpResponse:
        authentication_logger.warning("login_failure")
        return super().form_invalid(form)


class AccountLogoutView(LogoutView):
    """End an authenticated session through a CSRF-protected POST request."""

    http_method_names = ["post", "options"]
    next_page = reverse_lazy("accounts:login")

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        user_id = request.user.pk if request.user.is_authenticated else None
        response = super().post(request, *args, **kwargs)
        authentication_logger.info("logout user_id=%s", user_id)
        return response


class ProfileView(LoginRequiredMixin, TemplateView):
    """Display the authenticated user's non-sensitive account details."""

    template_name = "auth/profile.html"


class AccountPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """Change a password using Django validators while retaining the session."""

    template_name = "auth/password_change.html"
    form_class = AccountPasswordChangeForm
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form: AccountPasswordChangeForm) -> HttpResponse:
        response = super().form_valid(form)
        authentication_logger.info("password_change user_id=%s", self.request.user.pk)
        messages.success(self.request, "Your password was changed successfully.")
        return response


class AccountPasswordResetView(RateLimitedViewMixin, PasswordResetView):
    """Email a signed reset link while keeping account existence private."""

    template_name = "auth/password_reset_request.html"
    form_class = AccountPasswordResetForm
    email_template_name = "auth/password_reset_email.txt"
    html_email_template_name = "auth/password_reset_email.html"
    subject_template_name = "auth/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")
    rate_limit_scope = "password_reset"
    rate_limit_methods = frozenset({"POST"})

    def form_valid(self, form: AccountPasswordResetForm) -> HttpResponse:
        response = super().form_valid(form)
        authentication_logger.info("password_reset_requested")
        return response


class AccountPasswordResetDoneView(PasswordResetDoneView):
    template_name = "auth/password_reset_done.html"


class AccountPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "auth/password_reset_confirm.html"
    form_class = AccountSetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")

    def form_valid(self, form: AccountSetPasswordForm) -> HttpResponse:
        user_id = self.user.pk
        response = super().form_valid(form)
        authentication_logger.info("password_reset_completed user_id=%s", user_id)
        return response


class AccountPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "auth/password_reset_complete.html"
