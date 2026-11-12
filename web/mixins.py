"""Role-based access control for the web UI."""

from collections.abc import Callable
from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from accounts.models import Department, Rol
from plans import dashboard
from plans.dashboard import yilni_tanlash


def _htmx_sorovmi(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def _rad_javobi(
    request: HttpRequest, xabar: str | None, manzil: str, *, status: int = 403
) -> HttpResponse:
    if xabar:
        messages.error(request, xabar)
    if _htmx_sorovmi(request):
        return HttpResponse(status=status, headers={"HX-Redirect": reverse(manzil)})
    return redirect(manzil)


def _foydalanuvchini_tekshir(
    request: HttpRequest, ruxsat_etilgan_rollar: tuple[str, ...]
) -> HttpResponse | None:
    if not request.user.is_authenticated:
        return _rad_javobi(request, None, "kirish", status=401)
    if not request.user.is_active:
        logout(request)
        return _rad_javobi(
            request, "Hisobingiz faolsizlantirilgan.", "kirish", status=401
        )
    if request.user.rol not in ruxsat_etilgan_rollar:
        return _rad_javobi(
            request, "Bu sahifaga kirish huquqingiz yo'q.", "bosh_sahifa", status=403
        )
    return None


class RolTalabMixin(LoginRequiredMixin):
    """Allow only the listed roles; others are sent back with a message."""

    ruxsat_etilgan_rollar: tuple[str, ...] = ()

    def handle_no_permission(self) -> HttpResponse:
        if _htmx_sorovmi(self.request):
            return HttpResponse(status=401, headers={"HX-Redirect": reverse("kirish")})
        return super().handle_no_permission()

    def dispatch(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        rad = _foydalanuvchini_tekshir(request, self.ruxsat_etilgan_rollar)
        if rad is not None:
            return rad
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
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        rad = _foydalanuvchini_tekshir(request, self.ruxsat_etilgan_rollar)
        if rad is not None:
            return rad
        kafedra = _boshqarayotgan_kafedra(request)
        if kafedra is None:
            return _rad_javobi(
                request, "Sizga kafedra biriktirilmagan.", "bosh_sahifa", status=403
            )
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
        rad = _foydalanuvchini_tekshir(request, (Rol.OFFICE_ADMIN, Rol.SUPERADMIN))
        if rad is not None:
            return rad
        return view(request, *args, **kwargs)

    return wrapper


def kafedra_mudiri_talab(
    view: Callable[..., HttpResponse],
) -> Callable[..., HttpResponse]:
    """Function-view counterpart of KafedraMudiriTalabMixin."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        rad = _foydalanuvchini_tekshir(request, (Rol.DEPARTMENT_ADMIN, Rol.SUPERADMIN))
        if rad is not None:
            return rad
        if _boshqarayotgan_kafedra(request) is None:
            return _rad_javobi(
                request, "Sizga kafedra biriktirilmagan.", "bosh_sahifa", status=403
            )
        return view(request, *args, **kwargs)

    return wrapper


def xato_matni(exc: Exception) -> str:
    """Format ValidationError messages into a single user-facing string."""
    return " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)


def musbat_int_yoki_none(qiymat: str | None) -> int | None:
    """Parse an ASCII non-negative integer string, returning None otherwise."""
    if not qiymat:
        return None
    toza = qiymat.strip()
    return int(toza) if toza.isascii() and toza.isdigit() else None


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
