"""Session safety middleware enforcing account active status on every request."""

from collections.abc import Callable

from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse


class ActiveUserMiddleware:
    """Immediately log out deactivated users if an old session remains active."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated and not request.user.is_active:
            logout(request)
            messages.error(request, "Hisobingiz faolsizlantirilgan.")
        return self.get_response(request)
