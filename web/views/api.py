import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
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
    FanSemestr,
    KafedraTasdiqHolati,
    KafedraYuklamaTasdiq,
    OquvReja,
    Yuklama,
)
from plans.services import eng_kop_kurs_ishi_talabasi, guruhlarni_sinxronlash

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
        and request.user.is_active
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


def _sorov_int_yoki_xato(
    request: HttpRequest, nomi: str
) -> tuple[int | None, JsonResponse | None]:
    xom = request.GET.get(nomi)
    if not xom:
        return None, None
    if not (xom.isascii() and xom.isdigit()):
        return None, JsonResponse(
            {"xato": f"'{nomi}' musbat butun son bo'lishi kerak."}, status=400
        )
    return int(xom), None


class RejalarApiView(BaseApiView):
    """GET /api/v1/rejalar/ - Return list of curricula."""

    def get(self, request: HttpRequest) -> JsonResponse:
        yil, xato = _sorov_int_yoki_xato(request, "yil")
        if xato is not None:
            return xato
        qs = OquvReja.objects.annotate(fanlar_soni=Count("fanlar")).order_by(
            "-boshlanish_yili", "yonalish_kodi"
        )
        if yil is not None:
            qs = qs.filter(boshlanish_yili=yil)

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
        kafedra_id, xato = _sorov_int_yoki_xato(request, "kafedra_id")
        if xato is not None:
            return xato
        qs = (
            OqituvchiProfil.objects.toliq()
            .filter(foydalanuvchi__is_active=True)
            .annotate(jami_yuklama_soat=Sum("yuklamalar__soat"))
            .order_by("foydalanuvchi__last_name", "foydalanuvchi__first_name")
        )
        if kafedra_id is not None:
            qs = qs.filter(kafedra_id=kafedra_id)

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
    """GET /api/v1/yuklamalar/ - Return delegated course workloads."""

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
        ).order_by("fan_semestr__variant__nomi", "tur")

        if paramlar["kafedra_id"] is not None:
            qs = qs.filter(fan_semestr__variant__kafedra_id=paramlar["kafedra_id"])
        if paramlar["oqituvchi_id"] is not None:
            qs = qs.filter(oqituvchi_id=paramlar["oqituvchi_id"])
        if paramlar["yil"] is not None:
            qs = qs.akademik_yilda(paramlar["yil"])

        results = [_yuklama_dict(y) for y in qs]
        return JsonResponse({"count": len(results), "results": results})


def _sync_elementlarni_oqish(
    request: HttpRequest,
) -> tuple[list[dict[str, object]] | None, JsonResponse | None]:
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"xato": "Noto'g'ri JSON formati."}, status=400)
    elementlar: object
    if isinstance(data, list):
        elementlar = data
    elif isinstance(data, dict):
        elementlar = data["rejalar"] if "rejalar" in data else [data]
    else:
        return None, JsonResponse(
            {"xato": "JSON ro'yxat yoki obyekt bo'lishi kerak."}, status=400
        )
    if not isinstance(elementlar, list) or not all(
        isinstance(x, dict) for x in elementlar
    ):
        return None, JsonResponse(
            {"xato": "Har bir element JSON obyekt bo'lishi kerak."}, status=400
        )
    return elementlar, None


def _butun_son_oqish(
    item: dict[str, object], maydon: str, *, min_qiymat: int = 1
) -> int | None:
    if maydon not in item or item[maydon] is None:
        return None
    xom = item[maydon]
    if isinstance(xom, bool):
        raise ValueError(f"{maydon} butun son bo'lishi kerak")
    if isinstance(xom, int):
        qiymat = xom
    elif isinstance(xom, str) and xom.strip().isascii() and xom.strip().isdigit():
        qiymat = int(xom.strip())
    else:
        raise ValueError(f"{maydon} butun son bo'lishi kerak")
    if qiymat < min_qiymat:
        raise ValueError(f"{maydon} kamida {min_qiymat} bo'lishi kerak")
    return qiymat


def _sync_rejani_top(item: dict[str, object]) -> OquvReja | None:
    reja_id = _butun_son_oqish(item, "id") or _butun_son_oqish(item, "reja_id")
    if reja_id is not None:
        return OquvReja.objects.select_for_update().filter(id=reja_id).first()
    if "yonalish_kodi" in item and "boshlanish_yili" in item:
        kod = item["yonalish_kodi"]
        if not isinstance(kod, str) or not kod.strip():
            raise ValueError("yonalish_kodi matn bo'lishi kerak")
        yil = _butun_son_oqish(item, "boshlanish_yili", min_qiymat=1900)
        filtr: dict[str, object] = {
            "yonalish_kodi": kod.strip(),
            "boshlanish_yili": yil,
        }
        if item.get("talim_shakli"):
            if not isinstance(item["talim_shakli"], str):
                raise ValueError("talim_shakli matn bo'lishi kerak")
            filtr["talim_shakli"] = item["talim_shakli"].strip()
        return OquvReja.objects.select_for_update().filter(**filtr).first()
    return None


def _reja_qulflanganmi(reja: OquvReja) -> bool:
    fslar = (
        FanSemestr.objects.reja_uchun(reja)
        .filter(variant__kafedra__isnull=False)
        .values_list("variant__kafedra_id", "semestr")
    )
    juftlar = {
        (kafedra_id, reja.boshlanish_yili + (semestr - 1) // 2)
        for kafedra_id, semestr in fslar
    }
    if not juftlar:
        return False
    shart = Q()
    for kafedra_id, yil in juftlar:
        shart |= Q(kafedra_id=kafedra_id, akademik_yil=yil)
    return KafedraYuklamaTasdiq.objects.filter(
        shart,
        holat__in=(
            KafedraTasdiqHolati.TASDIQDA,
            KafedraTasdiqHolati.TASDIQLANGAN,
        ),
    ).exists()


def _sync_rejani_yangila(
    reja: OquvReja, item: dict[str, object]
) -> dict[str, object] | None:
    talabalar = _butun_son_oqish(item, "talabalar_soni", min_qiymat=1)
    guruhlar = _butun_son_oqish(item, "guruhlar_soni", min_qiymat=1)
    ozgardi = False
    if talabalar is not None and reja.talabalar_soni != talabalar:
        reja.talabalar_soni = talabalar
        ozgardi = True
    if guruhlar is not None and reja.guruhlar_soni != guruhlar:
        reja.guruhlar_soni = guruhlar
        ozgardi = True
    if "guruh_prefiksi" in item and item["guruh_prefiksi"] is not None:
        if not isinstance(item["guruh_prefiksi"], str):
            raise ValueError("guruh_prefiksi matn bo'lishi kerak")
        prefiks = item["guruh_prefiksi"].strip()
        if reja.guruh_prefiksi != prefiks:
            reja.guruh_prefiksi = prefiks
            ozgardi = True
    if not ozgardi:
        return None
    if _reja_qulflanganmi(reja):
        raise ValueError("tasdiqlangan kafedra yuklamasi qulflangan")
    if talabalar is not None:
        eng_kop = eng_kop_kurs_ishi_talabasi(reja)
        if eng_kop and reja.talabalar_soni < eng_kop:
            raise ValueError(f"kurs ishiga allaqachon {eng_kop} ta talaba taqsimlangan")
    reja.full_clean()
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
                try:
                    with transaction.atomic():
                        reja = _sync_rejani_top(item)
                        if reja is None:
                            xatolar.append(f"O'quv reja topilmadi: {item}")
                            continue
                        natija = _sync_rejani_yangila(reja, item)
                except (ValueError, TypeError, ValidationError) as err:
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
