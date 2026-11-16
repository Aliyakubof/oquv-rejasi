"""Faqat DEBUG da ishlaydigan rol almashtirgich: qayta kirmasdan rolga o'tish.

Rollar alohida emas — mudir uchun Department ga bog'langan OqituvchiProfil,
o'qituvchi uchun esa yuklama bo'lishi kerak. Shuning uchun bu vosita joriy
hisobning rolini shunchaki o'zgartirmasdan, o'sha rolga ega foydalanuvchiga
o'tkazadi.
"""

from collections.abc import Callable
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Department, Foydalanuvchi, OqituvchiProfil, Rol
from plans.dashboard import joriy_akademik_yil
from plans.models import Yuklama

ASL_KEY = "dev_asl_foydalanuvchi"
BACKEND = "django.contrib.auth.backends.ModelBackend"


def debug_talab(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """DEBUG o'chirilganda bu endpoint umuman yo'qdek ko'rinishi kerak.

    Tekshiruv urls.py da emas, shu yerda turadi — chunki URLconf import
    vaqtida tuziladi va testlarda override_settings(DEBUG=True) unga yetmaydi.
    """

    @wraps(view)
    def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if not settings.DEBUG:
            raise Http404
        return view(request, *args, **kwargs)

    return wrapper


def _dev_ruxsatmi(request: HttpRequest) -> bool:
    if request.user.rol in (Rol.OFFICE_ADMIN, Rol.SUPERADMIN):
        return True
    asl_pk = request.session.get(ASL_KEY)
    if asl_pk is None:
        return False
    return Foydalanuvchi.objects.filter(
        pk=asl_pk,
        is_active=True,
        rol__in=(Rol.OFFICE_ADMIN, Rol.SUPERADMIN),
    ).exists()


@debug_talab
@login_required
def rol_paneli(request: HttpRequest) -> HttpResponse:
    if not _dev_ruxsatmi(request):
        raise PermissionDenied
    return render(
        request,
        "web/parts/_rol_royxati.html",
        {
            "ofis_adminlar": _ofis_adminlar(),
            "kafedralar": _mudirli_kafedralar(),
            "oqituvchilar": _oqituvchilar(),
        },
    )


@debug_talab
@require_POST
@login_required
def rol_almashtirish(request: HttpRequest) -> HttpResponse:
    if not _dev_ruxsatmi(request):
        raise PermissionDenied
    xom_pk = request.POST.get("foydalanuvchi", "")
    if not (xom_pk.isascii() and xom_pk.isdigit()):
        raise Http404
    nishon = get_object_or_404(Foydalanuvchi, pk=int(xom_pk), is_active=True)
    asl_pk = request.session.get(ASL_KEY, request.user.pk)

    login(request, nishon, backend=BACKEND)

    # Foydalanuvchi o'zgarganda login() sessiyani yangilab yuboradi, shu bois asl
    # pk ham, xabar ham undan keyin yozilishi shart.
    if nishon.pk != asl_pk:
        request.session[ASL_KEY] = asl_pk
    messages.success(request, f"{nishon.get_full_name()} sifatida kirildi.")
    return redirect("bosh_sahifa")


@debug_talab
@require_POST
@login_required
def asl_hisobga_qaytish(request: HttpRequest) -> HttpResponse:
    asl_pk = request.session.get(ASL_KEY)
    if asl_pk is None:
        return redirect("bosh_sahifa")

    asl = get_object_or_404(Foydalanuvchi, pk=asl_pk, is_active=True)
    login(request, asl, backend=BACKEND)
    request.session.pop(ASL_KEY, None)
    messages.success(request, "Asl hisobingizga qaytdingiz.")
    return redirect("bosh_sahifa")


def _ofis_adminlar() -> list[Foydalanuvchi]:
    return list(
        Foydalanuvchi.objects.filter(
            rol__in=(Rol.OFFICE_ADMIN, Rol.SUPERADMIN), is_active=True
        ).order_by("last_name", "first_name")
    )


def _mudirli_kafedralar() -> list[Department]:
    """Faqat faol mudiri bor kafedralar — tizimga kira oladigan mudirlar shular.

    rol=DEPARTMENT_ADMIN bo'yicha filtrlansa, kafedraga biriktirilmagan mudirlar
    ham chiqadi va KafedraMudiriTalabMixin ularni darhol qaytarib yuboradi.
    """
    return list(
        Department.objects.exclude(mudir=None)
        .filter(mudir__foydalanuvchi__is_active=True)
        .select_related("mudir__foydalanuvchi")
        .order_by("nomi")
    )


def _oqituvchilar() -> list[OqituvchiProfil]:
    joriy_yuklamalar = Yuklama.objects.akademik_yilda(joriy_akademik_yil())
    return list(
        OqituvchiProfil.objects.filter(
            foydalanuvchi__rol=Rol.TEACHER, foydalanuvchi__is_active=True
        )
        .select_related("foydalanuvchi", "kafedra", "turi")
        .annotate(
            jami_soat=Coalesce(
                Sum("yuklamalar__soat", filter=Q(yuklamalar__in=joriy_yuklamalar)), 0
            )
        )
        .order_by("kafedra__nomi", "foydalanuvchi__last_name")
    )
