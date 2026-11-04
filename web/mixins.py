"""Role-based access control for the web UI."""

from collections.abc import Callable
from functools import wraps

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from accounts.models import Department, Rol
from plans import dashboard
from plans.dashboard import yilni_tanlash


class RolTalabMixin(LoginRequiredMixin):
    """Allow only the listed roles; others are sent back with a message."""

    ruxsat_etilgan_rollar: tuple[str, ...] = ()

    def dispatch(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if request.user.rol not in self.ruxsat_etilgan_rollar:
            messages.error(request, "Bu sahifaga kirish huquqingiz yo'q.")
            return redirect("bosh_sahifa")
        return super().dispatch(request, *args, **kwargs)


class OfficeAdminTalabMixin(RolTalabMixin):
    ruxsat_etilgan_rollar = (Rol.OFFICE_ADMIN, Rol.SUPERADMIN)


class OqituvchiTalabMixin(RolTalabMixin):
    """Own-workload pages: teachers, and department heads (who also teach)."""

    ruxsat_etilgan_rollar = (Rol.TEACHER, Rol.DEPARTMENT_ADMIN)


class KafedraMudiriTalabMixin(RolTalabMixin):
    """Resolves the head's own kafedra; it is the only tenancy source.

    Views under /kafedra/ must read scope from self.kafedra, never from
    URL parameters — that is what keeps one mudir out of another's data.
    """

    ruxsat_etilgan_rollar = (Rol.DEPARTMENT_ADMIN, Rol.SUPERADMIN)

    def dispatch(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        if request.user.is_authenticated:
            kafedra = _boshqarayotgan_kafedra(request)
            if request.user.rol in self.ruxsat_etilgan_rollar and kafedra is None:
                messages.error(request, "Sizga kafedra biriktirilmagan.")
                return redirect("bosh_sahifa")
            self.kafedra = kafedra
        return super().dispatch(request, *args, **kwargs)


def _boshqarayotgan_kafedra(request: HttpRequest) -> Department | None:
    profil = getattr(request.user, "oqituvchi_profil", None)
    if profil is None:
        return None
    return getattr(profil, "boshqarayotgan_kafedra", None)


def office_admin_talab(
    view: Callable[..., HttpResponse],
) -> Callable[..., HttpResponse]:
    """Function-view counterpart of OfficeAdminTalabMixin for HTMX endpoints."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if not request.user.is_authenticated:
            return redirect("kirish")
        if request.user.rol not in (Rol.OFFICE_ADMIN, Rol.SUPERADMIN):
            messages.error(request, "Bu sahifaga kirish huquqingiz yo'q.")
            return redirect("bosh_sahifa")
        return view(request, *args, **kwargs)

    return wrapper


def xato_matni(exc: Exception) -> str:
    """Format ValidationError messages into a single user-facing string."""
    return " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)


class YilTanlovMixin:
    """Provides self.yil and self.yillar and injects them into template context."""

    yil: int
    yillar: list[int]

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        yillar, yil = yilni_tanlash(self.request.GET.get("yil"))
        self.yil = yil or dashboard.joriy_akademik_yil()
        self.yillar = yillar
        context["yil"] = self.yil
        context["yillar"] = self.yillar
        return context
