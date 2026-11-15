import json
from collections.abc import Callable
from typing import TypeVar

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Count, Model, QuerySet, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from accounts.models import Department, OqituvchiProfil
from plans.hemis_client import hemis_elementlarni_sinxronlash, json_royxatni_ajrat
from plans.models import FanVariant, OquvReja, Yuklama
from web.security import (
    api_sorov_limitdan_oshdimi,
    kirish_bloklanganmi,
    kirish_xatosini_qayd_et,
)

_XAVFSIZ_METODLAR = ("GET", "HEAD", "OPTIONS", "TRACE")
DEFAULT_API_SAHIFA_HAJMI = 100
MAX_API_SAHIFA_HAJMI = 500
MAX_SYNC_ELEMENT = 500
MAX_SYNC_BODY_BAYT = 2 * 1024 * 1024
_TModel = TypeVar("_TModel", bound=Model)


def _kalit_mosmi(request: HttpRequest) -> bool:
    expected_key = getattr(settings, "HEMIS_API_KEY", "")
    if not expected_key:
        return False
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith(("Bearer ", "Token ")):
        token = auth_header.split(" ", 1)[1].strip()
        if constant_time_compare(token, expected_key):
            return True
    x_api_key = request.headers.get("X-API-KEY", "").strip()
    return bool(x_api_key and constant_time_compare(x_api_key, expected_key))


def _api_kirish_tekshir(request: HttpRequest) -> tuple[bool, int, str]:
    """Validate API token or active office/superadmin session with CSRF."""
    bloklangan, _ = kirish_bloklanganmi(request)
    if bloklangan:
        return (
            False,
            429,
            "Juda ko'p noto'g'ri urinish. Birozdan so'ng qayta urinib ko'ring.",
        )
    if _kalit_mosmi(request):
        return True, 200, ""
    if request.headers.get("Authorization") or request.headers.get("X-API-KEY"):
        kirish_xatosini_qayd_et(request)
        return False, 401, "API kalit noto'g'ri yoki yaroqsiz."
    if not (request.user.is_authenticated and request.user.is_active):
        return False, 401, "Avtorizatsiyadan o'tilmagan yoki API kalit noto'g'ri."
    if not (
        getattr(request.user, "is_office_admin", False)
        or getattr(request.user, "is_superadmin", False)
    ):
        return False, 403, "Ushbu API bo'limiga kirish huquqi yo'q."
    if request.method in _XAVFSIZ_METODLAR or getattr(
        request, "_dont_enforce_csrf_checks", False
    ):
        return True, 200, ""
    rad_javobi = CsrfViewMiddleware(lambda _r: HttpResponse()).process_view(
        request, None, (), {}
    )
    if rad_javobi is not None:
        return False, 403, "CSRF tekshiruvi muvaffaqiyatsiz tugadi."
    return True, 200, ""


def check_api_auth(request: HttpRequest) -> bool:
    """Validate request authentication via API token or CSRF-safe session."""
    return _api_kirish_tekshir(request)[0]


@method_decorator(csrf_exempt, name="dispatch")
class BaseApiView(View):
    """Base API view enforcing authentication and rate limits."""

    def dispatch(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        ok, status, xato = _api_kirish_tekshir(request)
        if not ok:
            return JsonResponse(
                {
                    "xato": xato,
                    "izoh": "Authorization: Bearer <API_KEY> talab qilinadi.",
                },
                status=status,
            )
        if api_sorov_limitdan_oshdimi(request):
            return JsonResponse(
                {"xato": "So'rovlar limiti oshdi. Biroz kuting."},
                status=429,
            )
        return super().dispatch(request, *args, **kwargs)


def _sorov_int_yoki_xato(
    request: HttpRequest, nomi: str, *, min_qiymat: int = 0
) -> tuple[int | None, JsonResponse | None]:
    xom = request.GET.get(nomi)
    if not xom:
        return None, None
    if not (xom.isascii() and xom.isdigit()):
        return None, JsonResponse(
            {"xato": f"'{nomi}' musbat butun son bo'lishi kerak."}, status=400
        )
    qiymat = int(xom)
    if qiymat < min_qiymat:
        return None, JsonResponse(
            {"xato": f"'{nomi}' kamida {min_qiymat} bo'lishi kerak."}, status=400
        )
    return qiymat, None


def _sahifalangan_javob(
    request: HttpRequest,
    qs: QuerySet[_TModel],
    serializer: Callable[[_TModel], dict[str, object]],
) -> JsonResponse:
    sahifa, xato = _sorov_int_yoki_xato(request, "page", min_qiymat=1)
    if xato is not None:
        return xato
    hajm, xato = _sorov_int_yoki_xato(request, "page_size", min_qiymat=1)
    if xato is not None:
        return xato
    sahifa_hajmi = min(hajm or DEFAULT_API_SAHIFA_HAJMI, MAX_API_SAHIFA_HAJMI)
    page_obj = Paginator(qs, sahifa_hajmi).get_page(sahifa or 1)
    return JsonResponse(
        {
            "count": page_obj.paginator.count,
            "page": page_obj.number,
            "page_size": sahifa_hajmi,
            "num_pages": page_obj.paginator.num_pages,
            "results": [serializer(obyekt) for obyekt in page_obj.object_list],
        }
    )


class RejalarApiView(BaseApiView):
    """GET /api/v1/rejalar/ - Return paginated list of curricula."""

    def get(self, request: HttpRequest) -> JsonResponse:
        yil, xato = _sorov_int_yoki_xato(request, "yil")
        if xato is not None:
            return xato
        qs = OquvReja.objects.annotate(fanlar_soni=Count("fanlar")).order_by(
            "-boshlanish_yili", "yonalish_kodi"
        )
        if yil is not None:
            qs = qs.filter(boshlanish_yili=yil)
        return _sahifalangan_javob(
            request,
            qs,
            lambda r: {
                "id": r.id,
                "yonalish_kodi": r.yonalish_kodi,
                "yonalish_nomi": r.yonalish_nomi,
                "bilim_sohasi_nomi": r.bilim_sohasi_nomi,
                "boshlanish_yili": r.boshlanish_yili,
                "daraja": r.daraja,
                "talim_shakli": r.talim_shakli,
                "davomiylik_yil": r.davomiylik_yil,
                "talabalar_soni": r.talabalar_soni,
                "guruhlar_soni": r.guruhlar_soni,
                "guruh_prefiksi": r.guruh_prefiksi,
                "fanlar_soni": r.fanlar_soni,
            },
        )


def _kafedra_dict(
    k: Department, oqit_map: dict[int, int], fan_map: dict[int, int]
) -> dict[str, object]:
    return {
        "id": k.id,
        "nomi": k.nomi,
        "fakultet": k.fakultet,
        "mudir": k.mudir.foydalanuvchi.get_full_name() if k.mudir else None,
        "oqituvchilar_soni": oqit_map.get(k.pk, 0),
        "fanlar_soni": fan_map.get(k.pk, 0),
    }


class KafedralarApiView(BaseApiView):
    """GET /api/v1/kafedralar/ - Return paginated departments with summary."""

    def get(self, request: HttpRequest) -> JsonResponse:
        sahifa, xato = _sorov_int_yoki_xato(request, "page", min_qiymat=1)
        if xato is not None:
            return xato
        hajm, xato = _sorov_int_yoki_xato(request, "page_size", min_qiymat=1)
        if xato is not None:
            return xato
        sahifa_hajmi = min(hajm or DEFAULT_API_SAHIFA_HAJMI, MAX_API_SAHIFA_HAJMI)
        qs = Department.objects.select_related("mudir__foydalanuvchi").order_by("nomi")
        page_obj = Paginator(qs, sahifa_hajmi).get_page(sahifa or 1)
        kafedralar = list(page_obj.object_list)
        oqit_map = dict(
            OqituvchiProfil.objects.filter(
                kafedra__in=kafedralar, foydalanuvchi__is_active=True
            )
            .values_list("kafedra_id")
            .annotate(soni=Count("id"))
        )
        fan_map = dict(
            FanVariant.objects.effektiv()
            .filter(kafedra__in=kafedralar)
            .values_list("kafedra_id")
            .annotate(soni=Count("id"))
        )
        return JsonResponse(
            {
                "count": page_obj.paginator.count,
                "page": page_obj.number,
                "page_size": sahifa_hajmi,
                "num_pages": page_obj.paginator.num_pages,
                "results": [_kafedra_dict(k, oqit_map, fan_map) for k in kafedralar],
            }
        )


def _oqituvchi_dict(
    profil: OqituvchiProfil, soatlar: dict[int, int]
) -> dict[str, object]:
    return {
        "id": profil.id,
        "ism_familiya": profil.foydalanuvchi.get_full_name(),
        "telefon": profil.foydalanuvchi.telefon,
        "kafedra_id": profil.kafedra_id,
        "kafedra_nomi": profil.kafedra.nomi,
        "lavozim": profil.turi.nomi,
        "min_soat": profil.turi.min_soat,
        "jami_yuklama_soat": soatlar.get(profil.pk) or 0,
    }


class OqituvchilarApiView(BaseApiView):
    """GET /api/v1/oqituvchilar/ - Return paginated teachers and workload stats."""

    def get(self, request: HttpRequest) -> JsonResponse:
        kafedra_id, xato = _sorov_int_yoki_xato(request, "kafedra_id")
        if xato is not None:
            return xato
        yil, xato = _sorov_int_yoki_xato(request, "yil")
        if xato is not None:
            return xato
        sahifa, xato = _sorov_int_yoki_xato(request, "page", min_qiymat=1)
        if xato is not None:
            return xato
        hajm, xato = _sorov_int_yoki_xato(request, "page_size", min_qiymat=1)
        if xato is not None:
            return xato

        qs = OqituvchiProfil.objects.toliq().filter(foydalanuvchi__is_active=True)
        qs = qs.order_by("foydalanuvchi__last_name", "foydalanuvchi__first_name", "pk")
        if kafedra_id is not None:
            qs = qs.filter(kafedra_id=kafedra_id)

        sahifa_hajmi = min(hajm or DEFAULT_API_SAHIFA_HAJMI, MAX_API_SAHIFA_HAJMI)
        page_obj = Paginator(qs, sahifa_hajmi).get_page(sahifa or 1)
        profillar = list(page_obj.object_list)
        yuk_qs = Yuklama.objects.filter(oqituvchi__in=profillar)
        if yil is not None:
            yuk_qs = yuk_qs.akademik_yilda(yil)
        soatlar = dict(yuk_qs.values_list("oqituvchi_id").annotate(jami=Sum("soat")))

        return JsonResponse(
            {
                "count": page_obj.paginator.count,
                "page": page_obj.number,
                "page_size": sahifa_hajmi,
                "num_pages": page_obj.paginator.num_pages,
                "results": [_oqituvchi_dict(p, soatlar) for p in profillar],
            }
        )


def _yuklama_dict(y: Yuklama) -> dict[str, object]:
    variant = y.fan_semestr.variant
    reja = variant.fan.reja
    return {
        "id": y.id,
        "reja_id": reja.id,
        "reja_nomi": reja.yonalish_nomi,
        "reja_kodi": reja.yonalish_kodi,
        "fan_nomi": variant.nomi,
        "fan_kodi": variant.kodi,
        "semestr": y.fan_semestr.semestr,
        "akademik_yil": y.fan_semestr.akademik_yil,
        "tur": y.tur,
        "tur_nomi": y.get_tur_display(),
        "oqituvchi_id": y.oqituvchi_id,
        "oqituvchi": y.oqituvchi.foydalanuvchi.get_full_name(),
        "guruh": y.guruh.nomi if y.guruh else None,
        "talabalar_soni": y.talabalar_soni,
        "soat": y.soat,
    }


class YuklamalarApiView(BaseApiView):
    """GET /api/v1/yuklamalar/ - Return paginated delegated course workloads."""

    def get(self, request: HttpRequest) -> JsonResponse:
        paramlar: dict[str, int | None] = {}
        for nomi in ("yil", "kafedra_id", "oqituvchi_id"):
            qiymat, xato = _sorov_int_yoki_xato(request, nomi)
            if xato is not None:
                return xato
            paramlar[nomi] = qiymat

        qs = Yuklama.objects.select_related(
            "fan_semestr__variant__fan__reja",
            "fan_semestr__variant__kafedra",
            "oqituvchi__foydalanuvchi",
            "guruh",
        ).order_by("fan_semestr__variant__nomi", "tur", "pk")

        if paramlar["kafedra_id"] is not None:
            qs = qs.filter(fan_semestr__variant__kafedra_id=paramlar["kafedra_id"])
        if paramlar["oqituvchi_id"] is not None:
            qs = qs.filter(oqituvchi_id=paramlar["oqituvchi_id"])
        if paramlar["yil"] is not None:
            qs = qs.akademik_yilda(paramlar["yil"])

        return _sahifalangan_javob(request, qs, _yuklama_dict)


def _sync_elementlarni_oqish(
    request: HttpRequest,
) -> tuple[list[dict[str, object]] | None, JsonResponse | None]:
    if len(request.body) > MAX_SYNC_BODY_BAYT:
        return None, JsonResponse(
            {"xato": "So'rov hajmi ruxsat etilgan chegaradan katta."}, status=400
        )
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"xato": "Noto'g'ri JSON formati."}, status=400)
    try:
        elementlar = json_royxatni_ajrat(data)
    except ValueError as err:
        return None, JsonResponse({"xato": str(err)}, status=400)
    if len(elementlar) > MAX_SYNC_ELEMENT:
        return None, JsonResponse(
            {
                "xato": (
                    f"Bir so'rovda ko'pi bilan {MAX_SYNC_ELEMENT} ta "
                    "reja sinxronlanadi."
                )
            },
            status=400,
        )
    return elementlar, None


class HemisSyncApiView(BaseApiView):
    """POST /api/v1/sync/ - Synchronize students and groups from HEMIS."""

    def post(self, request: HttpRequest) -> JsonResponse:
        items, xato_javob = _sync_elementlarni_oqish(request)
        if xato_javob is not None or items is None:
            return xato_javob  # type: ignore[return-value]

        foydalanuvchi = request.user if request.user.is_authenticated else None
        yangilangan, xatolar = hemis_elementlarni_sinxronlash(
            items, foydalanuvchi=foydalanuvchi, request=request
        )
        return JsonResponse(
            {
                "holat": "muvaffaqiyatli",
                "yangilandi_soni": len(yangilangan),
                "yangilangan_rejalar": yangilangan,
                "xatolar": xatolar,
            }
        )
