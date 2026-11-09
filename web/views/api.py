import json

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from accounts.models import Department, OqituvchiProfil
from plans.audit import audit_yoz
from plans.models import (
    AuditAmali,
    KafedraTasdiqHolati,
    KafedraYuklamaTasdiq,
    OquvReja,
    Yuklama,
)
from plans.services import guruhlarni_sinxronlash

_XAVFSIZ_METODLAR = ("GET", "HEAD", "OPTIONS", "TRACE")


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


def check_api_auth(request: HttpRequest) -> bool:
    """Validate request authentication via API token or CSRF-safe session."""
    if _kalit_mosmi(request):
        return True
    if not (
        request.user.is_authenticated
        and (
            request.user.is_staff
            or getattr(request.user, "is_office_admin", False)
            or getattr(request.user, "is_superadmin", False)
        )
    ):
        return False
    if request.method in _XAVFSIZ_METODLAR or getattr(
        request, "_dont_enforce_csrf_checks", False
    ):
        return True
    rad_javobi = CsrfViewMiddleware(lambda _r: HttpResponse()).process_view(
        request, None, (), {}
    )
    return rad_javobi is None


@method_decorator(csrf_exempt, name="dispatch")
class BaseApiView(View):
    """Base API view enforcing authentication."""

    def dispatch(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        if not check_api_auth(request):
            return JsonResponse(
                {
                    "xato": "Avtorizatsiyadan o'tilmagan yoki API kalit noto'g'ri.",
                    "izoh": "Authorization: Bearer <API_KEY> talab qilinadi.",
                },
                status=401,
            )
        return super().dispatch(request, *args, **kwargs)


class RejalarApiView(BaseApiView):
    """GET /api/v1/rejalar/ - Return list of curricula."""

    def get(self, request: HttpRequest) -> JsonResponse:
        boshlanish_yili = request.GET.get("yil")
        qs = OquvReja.objects.annotate(fanlar_soni=Count("fanlar")).order_by(
            "-boshlanish_yili", "yonalish_kodi"
        )
        if boshlanish_yili and boshlanish_yili.isdigit():
            qs = qs.filter(boshlanish_yili=int(boshlanish_yili))

        results = []
        for r in qs:
            results.append(
                {
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
                }
            )
        return JsonResponse({"count": len(results), "results": results})


class KafedralarApiView(BaseApiView):
    """GET /api/v1/kafedralar/ - Return list of departments with workload summary."""

    def get(self, request: HttpRequest) -> JsonResponse:
        qs = (
            Department.objects.select_related("mudir__foydalanuvchi")
            .annotate(
                oqituvchilar_soni=Count("oqituvchilar", distinct=True),
                fanlar_soni=Count("fanlar", distinct=True),
            )
            .order_by("nomi")
        )
        results = []
        for k in qs:
            mudir_nomi = k.mudir.foydalanuvchi.get_full_name() if k.mudir else None
            results.append(
                {
                    "id": k.id,
                    "nomi": k.nomi,
                    "fakultet": k.fakultet,
                    "mudir": mudir_nomi,
                    "oqituvchilar_soni": k.oqituvchilar_soni,
                    "fanlar_soni": k.fanlar_soni,
                }
            )
        return JsonResponse({"count": len(results), "results": results})


class OqituvchilarApiView(BaseApiView):
    """GET /api/v1/oqituvchilar/ - Return teachers and workload stats."""

    def get(self, request: HttpRequest) -> JsonResponse:
        kafedra_id = request.GET.get("kafedra_id")
        qs = (
            OqituvchiProfil.objects.toliq()
            .annotate(jami_yuklama_soat=Sum("yuklamalar__soat"))
            .order_by("foydalanuvchi__last_name", "foydalanuvchi__first_name")
        )
        if kafedra_id and kafedra_id.isdigit():
            qs = qs.filter(kafedra_id=int(kafedra_id))

        results = []
        for p in qs:
            results.append(
                {
                    "id": p.id,
                    "ism_familiya": p.foydalanuvchi.get_full_name(),
                    "telefon": p.foydalanuvchi.telefon,
                    "kafedra_id": p.kafedra_id,
                    "kafedra_nomi": p.kafedra.nomi,
                    "lavozim": p.turi.nomi,
                    "min_soat": p.turi.min_soat,
                    "jami_yuklama_soat": p.jami_yuklama_soat or 0,
                }
            )
        return JsonResponse({"count": len(results), "results": results})


class YuklamalarApiView(BaseApiView):
    """GET /api/v1/yuklamalar/ - Return delegated course workloads."""

    def get(self, request: HttpRequest) -> JsonResponse:
        yil = request.GET.get("yil")
        kafedra_id = request.GET.get("kafedra_id")
        oqituvchi_id = request.GET.get("oqituvchi_id")

        qs = Yuklama.objects.select_related(
            "fan_semestr__variant__fan__reja",
            "fan_semestr__variant__kafedra",
            "oqituvchi__foydalanuvchi",
            "guruh",
        ).order_by("fan_semestr__variant__nomi", "tur")

        if kafedra_id and kafedra_id.isdigit():
            qs = qs.filter(fan_semestr__variant__kafedra_id=int(kafedra_id))
        if oqituvchi_id and oqituvchi_id.isdigit():
            qs = qs.filter(oqituvchi_id=int(oqituvchi_id))
        if yil and yil.isdigit():
            qs = qs.akademik_yilda(int(yil))

        results = []
        for y in qs:
            variant = y.fan_semestr.variant
            reja = variant.fan.reja
            results.append(
                {
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
            )
        return JsonResponse({"count": len(results), "results": results})


def _sync_elementlarni_oqish(
    request: HttpRequest,
) -> tuple[list[dict[str, object]] | None, JsonResponse | None]:
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"xato": "Noto'g'ri JSON formati."}, status=400)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)], None
    if isinstance(data, dict):
        xom = data.get("rejalar", [data])
        if isinstance(xom, list):
            return [x for x in xom if isinstance(x, dict)], None
    return None, JsonResponse(
        {"xato": "JSON ro'yxat yoki obyekt bo'lishi kerak."}, status=400
    )


def _sync_rejani_top(item: dict[str, object]) -> OquvReja | None:
    reja_id = item.get("id") or item.get("reja_id")
    if reja_id:
        return OquvReja.objects.filter(id=reja_id).first()
    if "yonalish_kodi" in item and "boshlanish_yili" in item:
        filtr: dict[str, object] = {
            "yonalish_kodi": item["yonalish_kodi"],
            "boshlanish_yili": item["boshlanish_yili"],
        }
        if item.get("talim_shakli"):
            filtr["talim_shakli"] = item["talim_shakli"]
        return OquvReja.objects.filter(**filtr).first()
    return None


def _reja_qulflanganmi(reja: OquvReja) -> bool:
    return KafedraYuklamaTasdiq.objects.filter(
        kafedra__fanlar__fan__reja=reja,
        holat__in=(
            KafedraTasdiqHolati.TASDIQDA,
            KafedraTasdiqHolati.TASDIQLANGAN,
        ),
    ).exists()


def _musbat_son_oqish(item: dict[str, object], maydon: str) -> int | None:
    if maydon not in item or item[maydon] is None:
        return None
    qiymat = int(str(item[maydon]))
    if qiymat < 0:
        raise ValueError(f"{maydon} manfiy bo'lishi mumkin emas")
    return qiymat


def _sync_rejani_yangila(
    reja: OquvReja, item: dict[str, object]
) -> dict[str, object] | None:
    talabalar = _musbat_son_oqish(item, "talabalar_soni")
    guruhlar = _musbat_son_oqish(item, "guruhlar_soni")
    ozgardi = False
    if talabalar is not None and reja.talabalar_soni != talabalar:
        reja.talabalar_soni = talabalar
        ozgardi = True
    if guruhlar is not None and reja.guruhlar_soni != guruhlar:
        reja.guruhlar_soni = guruhlar
        ozgardi = True
    if "guruh_prefiksi" in item and item["guruh_prefiksi"] is not None:
        prefiks = str(item["guruh_prefiksi"]).strip()
        if reja.guruh_prefiksi != prefiks:
            reja.guruh_prefiksi = prefiks
            ozgardi = True
    if not ozgardi:
        return None
    if _reja_qulflanganmi(reja):
        raise ValueError("tasdiqlangan kafedra yuklamasi qulflangan")
    reja.save()
    guruhlarni_sinxronlash(reja)
    return {
        "id": reja.id,
        "yonalish_kodi": reja.yonalish_kodi,
        "yonalish_nomi": reja.yonalish_nomi,
        "boshlanish_yili": reja.boshlanish_yili,
        "talabalar_soni": reja.talabalar_soni,
        "guruhlar_soni": reja.guruhlar_soni,
        "guruhlar": [g.nomi for g in reja.guruhlar.all()],
    }


class HemisSyncApiView(BaseApiView):
    """POST /api/v1/sync/ - Synchronize students and groups from HEMIS."""

    def post(self, request: HttpRequest) -> JsonResponse:
        items, xato_javob = _sync_elementlarni_oqish(request)
        if xato_javob is not None or items is None:
            return xato_javob  # type: ignore[return-value]

        yangilangan: list[dict[str, object]] = []
        xatolar: list[str] = []

        with transaction.atomic():
            for item in items:
                reja = _sync_rejani_top(item)
                if reja is None:
                    xatolar.append(f"O'quv reja topilmadi: {item}")
                    continue
                try:
                    natija = _sync_rejani_yangila(reja, item)
                except (ValueError, TypeError) as err:
                    xatolar.append(f"Xatolik ({err}): {item}")
                    continue
                if natija is not None:
                    yangilangan.append(natija)

            if yangilangan:
                kodlar = ", ".join(str(r["yonalish_kodi"]) for r in yangilangan)
                audit_yoz(
                    AuditAmali.TAHRIRLANDI,
                    f"HEMIS Sync: {len(yangilangan)} ta reja sinxronlandi ({kodlar})",
                    model_nomi="OquvReja",
                    request=request,
                )

        return JsonResponse(
            {
                "holat": "muvaffaqiyatli",
                "yangilandi_soni": len(yangilangan),
                "yangilangan_rejalar": yangilangan,
                "xatolar": xatolar,
            }
        )
