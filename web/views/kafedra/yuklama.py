"""HTMX endpoints creating and removing Yuklama rows for one kafedra.

Every endpoint resolves objects THROUGH self.kafedra (from the mixin), so a
mudir can only ever touch fan-semestrs delegated to, and teachers employed
by, their own department.
"""

from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from accounts.models import OqituvchiProfil
from plans import dashboard, delegation, services
from plans.audit import audit_yoz
from plans.models import PER_GURUH_TURLAR, AuditAmali, FanSemestr, Yuklama
from web.forms.yuklama import (
    GuruhYuklamaForm,
    KursIshiYuklamaForm,
    MaruzaYuklamaForm,
    YuklamaAsosForm,
)
from web.mixins import KafedraMudiriTalabMixin

FORMALAR: dict[str, type[YuklamaAsosForm]] = {
    "maruza": MaruzaYuklamaForm,
    "guruh": GuruhYuklamaForm,
    "kurs_ishi": KursIshiYuklamaForm,
}


class PanelAsosView(KafedraMudiriTalabMixin, View):
    """Shared helpers: kafedra-scoped lookups and the panel response."""

    def fan_semestr(self, pk: int) -> FanSemestr:
        return get_object_or_404(
            FanSemestr.objects.select_related("variant__fan__reja"),
            pk=pk,
            variant__kafedra=self.kafedra,
        )

    def panel_javobi(
        self,
        request: HttpRequest,
        fs: FanSemestr,
        *,
        xato: str | None = None,
        oob: bool = False,
    ) -> HttpResponse:
        shablon = (
            "web/kafedra/_panel_va_qator.html" if oob else "web/kafedra/_panel.html"
        )
        soatlar = {
            h.oqituvchi.pk: h
            for h in services.yuklama_kamomadi(fs.akademik_yil, kafedra=self.kafedra)
        }
        oqituvchilar = list(
            OqituvchiProfil.objects.kafedrada(self.kafedra)
            .filter(foydalanuvchi__is_active=True)
            .toliq()
            .order_by("foydalanuvchi__last_name", "foydalanuvchi__first_name")
        )
        for p in oqituvchilar:
            holat = soatlar.get(p.pk)
            p.jami_soat = holat.jami_soat if holat else 0
            p.kamomad = holat.kamomad if holat else p.turi.min_soat
            p.tolganmi = p.jami_soat >= p.turi.min_soat
            p.foiz = (
                round((p.jami_soat / p.turi.min_soat) * 100) if p.turi.min_soat else 0
            )
        return render(
            request,
            shablon,
            {
                "fs": fs,
                "holatlar": delegation.fan_semestr_holati(fs),
                "satr": delegation.fs_satri(fs),
                "oqituvchilar": oqituvchilar,
                "qulflangan": services.kafedra_yuklama_qulflanganmi(
                    self.kafedra, fs.akademik_yil
                ),
                "stat": dashboard.statlarni_hisoblash(
                    services.kafedra_taqsimoti(self.kafedra, fs.akademik_yil)
                ),
                "xato": xato,
            },
        )


class TaqsimotPanelView(PanelAsosView):
    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        return self.panel_javobi(request, self.fan_semestr(pk))


class YuklamaYaratishView(PanelAsosView):
    """POST /fan-semestr/<pk>/<shakl>/ — one endpoint per Yuklama shape."""

    shakl = ""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        fs = self.fan_semestr(pk)
        if services.kafedra_yuklama_qulflanganmi(self.kafedra, fs.akademik_yil):
            return self.panel_javobi(
                request,
                fs,
                xato="Yuklama tasdiqqa yuborilgan yoki tasdiqlangan — qulflangan.",
                oob=True,
            )
        form = FORMALAR[self.shakl](fs, self.kafedra, request.POST)
        if form.is_valid():
            yuklama = form.save()
            matn = (
                f"{self.kafedra.nomi}: {fs.variant.nomi} "
                f"({fs.semestr}-semestr, {yuklama.get_tur_display()}) "
                f"yuklamasi {yuklama.oqituvchi} ga taqsimlandi ({yuklama.soat} soat)."
            )
            audit_yoz(
                AuditAmali.YARATILDI,
                matn,
                model_nomi="Yuklama",
                obyekt_id=yuklama.pk,
                request=request,
            )
            return self.panel_javobi(request, fs, oob=True)
        return self.panel_javobi(request, fs, xato=_xato_matni(form), oob=True)


def _xato_matni(form: YuklamaAsosForm) -> str:
    qismlar = []
    for maydon, xatolar in form.errors.items():
        nomi = "" if maydon == "__all__" else f"{maydon}: "
        qismlar.append(f"{nomi}{' '.join(xatolar)}")
    return " ".join(qismlar)


class YuklamaOchirishView(PanelAsosView):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        yuklama = get_object_or_404(
            Yuklama.objects.select_related("fan_semestr__variant__fan__reja"),
            pk=pk,
            fan_semestr__variant__kafedra=self.kafedra,
        )
        fs = yuklama.fan_semestr
        if services.kafedra_yuklama_qulflanganmi(self.kafedra, fs.akademik_yil):
            return self.panel_javobi(
                request,
                fs,
                xato="Yuklama tasdiqqa yuborilgan yoki tasdiqlangan — qulflangan.",
                oob=True,
            )
        tavsif = (
            f"{self.kafedra.nomi}: {fs.variant.nomi} "
            f"({fs.semestr}-semestr, {yuklama.get_tur_display()}) "
            f"yuklamasi ({yuklama.oqituvchi}) o'chirildi."
        )
        yuklama.delete()
        audit_yoz(
            AuditAmali.OCHIRILDI,
            tavsif,
            model_nomi="Yuklama",
            obyekt_id=pk,
            request=request,
        )
        return self.panel_javobi(request, fs, oob=True)

    def delete(self, request: HttpRequest, pk: int) -> HttpResponse:
        return self.post(request, pk)


class GuruhlarOmmaviyYaratishView(PanelAsosView):
    """Assigns one teacher to all unassigned groups for an activity type."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        fs = self.fan_semestr(pk)
        if services.kafedra_yuklama_qulflanganmi(self.kafedra, fs.akademik_yil):
            return self.panel_javobi(
                request,
                fs,
                xato="Yuklama tasdiqqa yuborilgan yoki tasdiqlangan — qulflangan.",
                oob=True,
            )

        oqituvchi_id = request.POST.get("oqituvchi")
        tur = request.POST.get("tur")
        if not oqituvchi_id or not tur or tur not in PER_GURUH_TURLAR:
            return self.panel_javobi(
                request,
                fs,
                xato="O'qituvchi yoki mashg'ulot turi tanlanmadi.",
                oob=True,
            )

        oqituvchi = get_object_or_404(
            OqituvchiProfil.objects.kafedrada(self.kafedra).filter(
                foydalanuvchi__is_active=True
            ),
            pk=oqituvchi_id,
        )

        reja = fs.variant.fan.reja
        band_guruh_idlar = set(
            Yuklama.objects.filter(fan_semestr=fs, tur=tur).values_list(
                "guruh_id", flat=True
            )
        )
        bosh_guruhlar = [g for g in reja.guruhlar.all() if g.pk not in band_guruh_idlar]

        if not bosh_guruhlar:
            return self.panel_javobi(
                request,
                fs,
                xato="Barcha guruhlar allaqachon taqsimlangan.",
                oob=True,
            )

        with transaction.atomic():
            yangi_yuklamalar = []
            for guruh in bosh_guruhlar:
                yuklama = Yuklama(
                    fan_semestr=fs,
                    tur=tur,
                    oqituvchi=oqituvchi,
                    guruh=guruh,
                )
                yuklama.full_clean()
                yuklama.save()
                yangi_yuklamalar.append(yuklama)

            matn = (
                f"{self.kafedra.nomi}: {fs.variant.nomi} ({fs.semestr}-semestr, {tur}) "
                f"barcha bo'sh ({len(yangi_yuklamalar)} ta) guruhlar "
                f"{oqituvchi} ga taqsimlandi."
            )
            audit_yoz(
                AuditAmali.YARATILDI,
                matn,
                model_nomi="Yuklama",
                obyekt_id=yangi_yuklamalar[0].pk,
                request=request,
            )

        return self.panel_javobi(request, fs, oob=True)


class GuruhlarTozalashView(PanelAsosView):
    """Clears all group delegations for a given activity type in one step."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        fs = self.fan_semestr(pk)
        if services.kafedra_yuklama_qulflanganmi(self.kafedra, fs.akademik_yil):
            return self.panel_javobi(
                request,
                fs,
                xato="Yuklama tasdiqqa yuborilgan yoki tasdiqlangan — qulflangan.",
                oob=True,
            )

        tur = request.POST.get("tur")
        if not tur or tur not in PER_GURUH_TURLAR:
            return self.panel_javobi(
                request, fs, xato="Mashg'ulot turi noto'g'ri.", oob=True
            )

        ochirilganlar = Yuklama.objects.filter(fan_semestr=fs, tur=tur)
        soni = ochirilganlar.count()
        if soni == 0:
            return self.panel_javobi(request, fs, oob=True)

        with transaction.atomic():
            ochirilganlar.delete()
            matn = (
                f"{self.kafedra.nomi}: {fs.variant.nomi} ({fs.semestr}-semestr, {tur}) "
                f"barcha ({soni} ta) guruh taqsimoti tozalandi."
            )
            audit_yoz(
                AuditAmali.OCHIRILDI,
                matn,
                model_nomi="Yuklama",
                obyekt_id=pk,
                request=request,
            )

        return self.panel_javobi(request, fs, oob=True)
