"""Login and password-change forms working with phone-number usernames."""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from accounts.phone import normalize_phone


class TelefonKirishForm(AuthenticationForm):
    username = forms.CharField(
        label="Telefon raqam",
        widget=forms.TextInput(
            attrs={"placeholder": "+998901234567", "autofocus": True}
        ),
    )
    password = forms.CharField(label="Parol", widget=forms.PasswordInput)

    error_messages = {
        "invalid_login": "Telefon raqam yoki parol noto'g'ri.",
        "inactive": "Bu foydalanuvchi faol emas.",
    }

    def clean_username(self) -> str:
        return normalize_phone(self.cleaned_data["username"])


class ParolOzgartirishForm(PasswordChangeForm):
    old_password = forms.CharField(
        label="Joriy parol",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password", "autofocus": True}
        ),
    )
    new_password1 = forms.CharField(
        label="Yangi parol",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    new_password2 = forms.CharField(
        label="Yangi parolni tasdiqlang",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
