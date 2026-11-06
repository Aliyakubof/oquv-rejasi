"""Shared base views and helpers for teacher CRUD across office and kafedra."""

from collections import defaultdict

from django.contrib import messages
from django.forms import Form
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import FormView, TemplateView

from accounts.models import OqituvchiProfil
from plans import dashboard
from plans.audit import audit_yoz
from plans.dashboard import yilni_tanlash
from plans.models import AuditAmali, SoatTuri, Yuklama
from web.mixins import YilTanlovMixin


def _shakl1_guruh_matni(qator: dict[str, object]) -> str:
    guruh_nomi = qator.get("_guruh_nomi")
    if guruh_nomi:
        return str(guruh_nomi)
    talabalar = int(qator.get("_talabalar_soni", 0))
    maruza_bor = int(qator.get("maruza", 0)) > 0
    if maruza_bor and talabalar > 0:
        return f"Oqim ({talabalar} talaba)"
    if talabalar > 0:
        return f"{talabalar} talaba"
    return "Oqim"


def oqituvchi_yuklama_konteksti(
    profil: OqituvchiProfil, sorov_yil: str | None, *, orqaga_url: str
) -> dict[str, object]:
    """Shared workload sheet context for a single teacher."""
    yillar, yil = yilni_tanlash(sorov_yil)
    yil = yil or dashboard.joriy_akademik_yil()
    yuklamalar = list(
        Yuklama.objects.filter(oqituvchi=profil)
        .akademik_yilda(yil)
        .select_related("fan_semestr__variant__fan__reja", "guruh")
        .order_by("fan_semestr__semestr", "fan_semestr__variant__nomi", "tur")
    )
    tur_jami: dict[str, int] = defaultdict(int)
    shakl1_qatorlar: dict[tuple[int, int | None], dict[str, object]] = {}
    for y in yuklamalar:
        tur_jami[y.tur] += y.soat
        fs = y.fan_semestr
        kalit = (fs.pk, y.guruh_id)
        if kalit not in shakl1_qatorlar:
            reja = fs.variant.fan.reja
            kurs = (fs.semestr + 1) // 2
            shakl1_qatorlar[kalit] = {
                "fan": fs.variant.nomi,
                "kodi": fs.variant.kodi,
                "yonalish": f"{reja.yonalish_kodi} {reja.yonalish_nomi}",
                "kurs": kurs,
                "semestr": fs.semestr,
                "guruh": "Oqim",
                "_guruh_nomi": y.guruh.nomi if y.guruh else "",
                "_talabalar_soni": 0,
                "maruza": 0,
                "amaliyot": 0,
                "laboratoriya": 0,
                "seminar": 0,
                "kurs_ishi": 0,
                "jami": 0,
            }
        if y.talabalar_soni:
            shakl1_qatorlar[kalit]["_talabalar_soni"] = (
                int(shakl1_qatorlar[kalit]["_talabalar_soni"]) + y.talabalar_soni
            )
        tur_kalit = y.tur.lower()
        if tur_kalit in shakl1_qatorlar[kalit]:
            shakl1_qatorlar[kalit][tur_kalit] = (
                int(shakl1_qatorlar[kalit][tur_kalit]) + y.soat
            )
        shakl1_qatorlar[kalit]["jami"] = int(shakl1_qatorlar[kalit]["jami"]) + y.soat
        shakl1_qatorlar[kalit]["guruh"] = _shakl1_guruh_matni(shakl1_qatorlar[kalit])

    jami_soat = sum(y.soat for y in yuklamalar)
    return {
        "profil": profil,
        "yillar": yillar,
        "yil": yil,
        "yuklamalar": yuklamalar,
        "shakl1_satrlar": list(shakl1_qatorlar.values()),
        "jami_soat": jami_soat,
        "kamomad": max(0, profil.turi.min_soat - jami_soat),
        "tur_jami": [(SoatTuri(t).label, s) for t, s in tur_jami.items()],
        "orqaga_url": orqaga_url,
    }


class OqituvchiYuklamaAsosView(YilTanlovMixin, TemplateView):
    template_name = "web/parts/oqituvchi_yuklama.html"
    orqaga_url: str = ""

    def profil_olish(self) -> OqituvchiProfil:
        raise NotImplementedError

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        profil = self.profil_olish()
        context.update(
            oqituvchi_yuklama_konteksti(
                profil,
                self.request.GET.get("yil"),
                orqaga_url=self.orqaga_url,
            )
        )
        return context


class OqituvchiYangiAsosView(FormView):
    success_url_name: str = ""

    def form_valid(self, form: Form) -> HttpResponse:
        profil = form.saqlash()  # type: ignore[attr-defined]
        audit_yoz(
            AuditAmali.YARATILDI,
            f"O'qituvchi yaratildi: {profil} ({profil.kafedra.nomi}).",
            obyekt=profil,
            request=self.request,
        )
        messages.success(self.request, f"{profil} yaratildi.")
        return redirect(self.success_url_name)


class OqituvchiTahrirAsosView(FormView):
    success_url_name: str = ""

    def profil_olish(self) -> OqituvchiProfil:
        return get_object_or_404(
            OqituvchiProfil.objects.bilan_foydalanuvchi(),
            pk=self.kwargs["pk"],
        )

    def get_form_kwargs(self) -> dict[str, object]:
        kwargs = super().get_form_kwargs()
        kwargs["profil"] = self.profil_olish()
        return kwargs

    def form_valid(self, form: Form) -> HttpResponse:
        form.saqlash()  # type: ignore[attr-defined]
        profil = form.profil  # type: ignore[attr-defined]
        audit_yoz(
            AuditAmali.TAHRIRLANDI,
            f"O'qituvchi ma'lumotlari tahrirlandi: {profil} ({profil.kafedra.nomi}).",
            obyekt=profil,
            request=self.request,
        )
        messages.success(self.request, f"{profil} saqlandi.")
        return redirect(self.success_url_name)
