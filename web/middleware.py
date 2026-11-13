"""Session safety middleware enforcing account active status and password reset."""

from collections.abc import Callable

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


class ActiveUserMiddleware:
    """Immediately log out deactivated users if an old session remains active."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated and not request.user.is_active:
            logout(request)
            messages.error(request, "Hisobingiz faolsizlantirilgan.")
        return self.get_response(request)


class ParolAlmashtirishMajburiyMiddleware:
    """Redirect users holding a one-time password straight to password change."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def _ruxsat_etilgan_yolmi(self, yol: str) -> bool:
        static_url = getattr(settings, "STATIC_URL", "/static/")
        if not static_url.startswith("/"):
            static_url = f"/{static_url}"
        if yol.startswith(static_url):
            return True
        ruxsat_nomlari = (
            "parol_ozgartirish",
            "chiqish",
            "korinish_saqlash",
            "profil_telegram_saqlash",
            "healthcheck",
            "kirish",
        )
        return yol in {reverse(nom) for nom in ruxsat_nomlari}

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and getattr(user, "parol_ozgartirish_kerak", False)
            and not self._ruxsat_etilgan_yolmi(request.path_info)
        ):
            parol_url = reverse("parol_ozgartirish")
            if request.headers.get("HX-Request"):
                javob = HttpResponse(status=401)
                javob["HX-Redirect"] = parol_url
                return javob
            return redirect(parol_url)
        return self.get_response(request)
