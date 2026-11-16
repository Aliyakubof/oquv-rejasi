"""Telefon raqam orqali tizimga kirish va parolni almashtirish formalari."""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from accounts.models import Foydalanuvchi
from accounts.phone import telefonni_normallashtir


class TelefonKirishForm(AuthenticationForm):
    username = forms.CharField(
        label="Telefon raqam",
        widget=forms.TextInput(
            attrs={
                "placeholder": "+998901234567",
                "autofocus": True,
                "autocomplete": "username",
                "inputmode": "tel",
            }
        ),
    )
    password = forms.CharField(label="Parol", widget=forms.PasswordInput)

    error_messages = {
        "invalid_login": "Telefon raqam yoki parol noto'g'ri.",
        "inactive": "Bu foydalanuvchi faol emas.",
    }

    def clean_username(self) -> str:
        return telefonni_normallashtir(self.cleaned_data["username"])


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


class KorinishSozlamalariForm(forms.ModelForm):
    """Ilk kirishda yoki sozlamalarda tanlangan ko'rinish afzalliklarini saqlaydi."""

    class Meta:
        model = Foydalanuvchi
        fields = ("shrift_olchami", "yuqori_kontrast", "keng_rejim")

    def save(self, commit: bool = True) -> Foydalanuvchi:
        user: Foydalanuvchi = super().save(commit=False)
        user.korinish_tanlangan = True
        if commit:
            user.save(
                update_fields=[
                    "shrift_olchami",
                    "yuqori_kontrast",
                    "keng_rejim",
                    "korinish_tanlangan",
                ]
            )
        return user


class TelegramBoglashForm(forms.ModelForm):
    """Bildirishnomalar uchun Telegram Chat ID ni ulash yoki uzish formasi."""

    class Meta:
        model = Foydalanuvchi
        fields = ("telegram_chat_id",)
        labels = {"telegram_chat_id": "Telegram Chat ID"}
        widgets = {
            "telegram_chat_id": forms.TextInput(
                attrs={"placeholder": "Masalan: 123456789 (ixtiyoriy)"}
            )
        }

    def clean_telegram_chat_id(self) -> str:
        qiymat = (self.cleaned_data.get("telegram_chat_id") or "").strip()
        if not qiymat:
            return ""
        toza = qiymat.lstrip("-")
        if not (toza.isascii() and toza.isdigit()):
            raise forms.ValidationError(
                "Telegram Chat ID faqat raqamlardan iborat bo'lishi kerak."
            )
        return qiymat
