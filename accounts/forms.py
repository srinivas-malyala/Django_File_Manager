"""Browser forms for account authentication workflows."""

from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)

from .models import User


class BootstrapFormMixin:
    """Apply Bootstrap's standard input class without coupling templates to field types."""

    fields: dict[str, forms.Field]

    def apply_bootstrap_styles(self) -> None:
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class RegistrationForm(BootstrapFormMixin, UserCreationForm):
    """Create a user while enforcing case-insensitive email uniqueness."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_styles()

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with that email already exists.")
        return email


class AccountAuthenticationForm(BootstrapFormMixin, AuthenticationForm):
    """Django's authentication form with presentation-only widget styling."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_styles()


class AccountPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    """Django's validated password-change form with Bootstrap styling."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_styles()


class AccountPasswordResetForm(BootstrapFormMixin, PasswordResetForm):
    """Request Django's signed reset link without disclosing account existence."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_styles()


class AccountSetPasswordForm(BootstrapFormMixin, SetPasswordForm):
    """Apply Django password validators to a valid reset-token workflow."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_styles()
