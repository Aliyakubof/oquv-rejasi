import json

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Sum
from django.http import HttpRequest, JsonResponse
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from accounts.models import Department, OqituvchiProfil
from plans.audit import audit_yoz
from plans.models import AuditAmali, OquvReja, Yuklama
from plans.services import guruhlarni_sinxronlash


def check_api_auth(request: HttpRequest) -> bool:
    """Validate request authentication via session or API token."""
    if request.user.is_authenticated and (
        request.user.is_staff
        or getattr(request.user, "is_office_admin", False)
        or getattr(request.user, "is_superadmin", False)
    ):
        return True

    expected_key = getattr(settings, "HEMIS_API_KEY", "")
    if expected_key:
        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            if constant_time_compare(token, expected_key):
                return True
        elif auth_header.startswith("Token "):
            token = auth_header.split(" ", 1)[1].strip()
            if constant_time_compare(token, expected_key):
                return True

        x_api_key = request.headers.get("X-API-KEY", "").strip()
        if x_api_key and constant_time_compare(x_api_key, expected_key):
            return True

    return False


@method_decorator(csrf_exempt, name="dispatch")
class BaseApiView(View):
    """Base API view enforcing authentication."""

    def dispatch(self, request: HttpRequest, *args, **kwargs):
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
            qs = qs.filter(fan_semestr__akademik_yil=int(yil))

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


class HemisSyncApiView(BaseApiView):
    """POST /api/v1/sync/ - Synchronize students and groups from HEMIS."""

    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            data = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"xato": "Noto'g'ri JSON formati."}, status=400)

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("rejalar", [data])
        else:
            return JsonResponse(
                {"xato": "JSON ro'yxat yoki obyekt bo'lishi kerak."}, status=400
            )

        yangilangan = []
        xatolar = []

        with transaction.atomic():
            for item in items:
                if not isinstance(item, dict):
                    continue

                reja = None
                reja_id = item.get("id") or item.get("reja_id")
                if reja_id:
                    reja = OquvReja.objects.filter(id=reja_id).first()
                elif "yonalish_kodi" in item and "boshlanish_yili" in item:
                    reja = OquvReja.objects.filter(
                        yonalish_kodi=item["yonalish_kodi"],
                        boshlanish_yili=item["boshlanish_yili"],
                    ).first()

                if not reja:
                    xatolar.append(f"O'quv reja topilmadi: {item}")
                    continue

                ozgardi = False
                try:
                    if "talabalar_soni" in item and item["talabalar_soni"] is not None:
                        val = int(item["talabalar_soni"])
                        if val < 0:
                            raise ValueError(
                                "talabalar_soni manfiy bo'lishi mumkin emas"
                            )
                        reja.talabalar_soni = val
                        ozgardi = True
                    if "guruhlar_soni" in item and item["guruhlar_soni"] is not None:
                        val = int(item["guruhlar_soni"])
                        if val < 0:
                            raise ValueError(
                                "guruhlar_soni manfiy bo'lishi mumkin emas"
                            )
                        reja.guruhlar_soni = val
                        ozgardi = True
                except (ValueError, TypeError) as err:
                    xatolar.append(f"Noto'g'ri son formati ({err}): {item}")
                    continue

                if "guruh_prefiksi" in item and item["guruh_prefiksi"] is not None:
                    reja.guruh_prefiksi = str(item["guruh_prefiksi"]).strip()
                    ozgardi = True

                if ozgardi:
                    reja.save()
                    guruhlarni_sinxronlash(reja)
                    yangilangan.append(
                        {
                            "id": reja.id,
                            "yonalish_kodi": reja.yonalish_kodi,
                            "yonalish_nomi": reja.yonalish_nomi,
                            "boshlanish_yili": reja.boshlanish_yili,
                            "talabalar_soni": reja.talabalar_soni,
                            "guruhlar_soni": reja.guruhlar_soni,
                            "guruhlar": [g.nomi for g in reja.guruhlar.all()],
                        }
                    )

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
