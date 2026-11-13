"""HTMX endpoints creating and removing Yuklama rows for one kafedra.

Every endpoint resolves objects THROUGH self.kafedra (from the mixin), so a
mudir can only ever touch fan-semestrs delegated to, and teachers employed
by, their own department.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from accounts.models import Department, OqituvchiProfil
from plans import dashboard, delegation, services
from plans.audit import audit_yoz
from plans.models import PER_GURUH_TURLAR, AuditAmali, FanSemestr, Yuklama
from web.forms.yuklama import (
    GuruhYuklamaForm,
    KursIshiYuklamaForm,
    MaruzaYuklamaForm,
    YuklamaAsosForm,
)
from web.mixins import KafedraMudiriTalabMixin, musbat_int_yoki_none, xato_matni

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

    def _qulflangan_fs(self, pk: int) -> FanSemestr:
        Department.objects.select_for_update().filter(pk=self.kafedra.pk).first()
        return get_object_or_404(
            FanSemestr.objects.select_for_update().select_related("variant__fan__reja"),
            pk=pk,
            variant__kafedra=self.kafedra,
        )

    def _oqituvchilar_royxati(self, fs: FanSemestr) -> list[OqituvchiProfil]:
        kamomadlar = services.yuklama_kamomadi(fs.akademik_yil, kafedra=self.kafedra)
        saralangan = sorted(
            kamomadlar,
            key=lambda x: (
                x.oqituvchi.foydalanuvchi.last_name,
                x.oqituvchi.foydalanuvchi.first_name,
            ),
        )
        oqituvchilar = []
        for h in saralangan:
            p = h.oqituvchi
            p.jami_soat = h.jami_soat
            p.kamomad = h.kamomad
            p.tolganmi = p.jami_soat >= p.turi.min_soat
            p.foiz = (
                round((p.jami_soat / p.turi.min_soat) * 100) if p.turi.min_soat else 0
            )
            oqituvchilar.append(p)
        return oqituvchilar

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
        kontekst: dict[str, object] = {
            "fs": fs,
            "holatlar": delegation.fan_semestr_holati(fs),
            "oqituvchilar": self._oqituvchilar_royxati(fs),
            "qulflangan": services.kafedra_yuklama_qulflanganmi(
                self.kafedra, fs.akademik_yil
            ),
            "xato": xato,
        }
        if oob:
            kontekst["satr"] = delegation.fs_satri(fs)
            kontekst["stat"] = dashboard.statlarni_hisoblash(
                services.kafedra_taqsimoti(self.kafedra, fs.akademik_yil)
            )
        return render(request, shablon, kontekst)


class TaqsimotPanelView(PanelAsosView):
    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        return self.panel_javobi(request, self.fan_semestr(pk))


class YuklamaYaratishView(PanelAsosView):
    """POST /fan-semestr/<pk>/<shakl>/ — one endpoint per Yuklama shape."""

    shakl = ""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        with transaction.atomic():
            fs = self._qulflangan_fs(pk)
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
                    f"yuklamasi {yuklama.oqituvchi} ga taqsimlandi "
                    f"({yuklama.soat} soat)."
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
        with transaction.atomic():
            Department.objects.select_for_update().filter(pk=self.kafedra.pk).first()
            yuklama = get_object_or_404(
                Yuklama.objects.select_for_update().select_related(
                    "fan_semestr__variant__fan__reja"
                ),
                pk=pk,
                fan_semestr__variant__kafedra=self.kafedra,
            )
            fs = self._qulflangan_fs(yuklama.fan_semestr_id)
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
        oqituvchi_pk = musbat_int_yoki_none(request.POST.get("oqituvchi"))
        tur = request.POST.get("tur") or ""
        with transaction.atomic():
            fs = self._qulflangan_fs(pk)
            xato = self._tekshir(fs, oqituvchi_pk, tur)
            if xato:
                return self.panel_javobi(request, fs, xato=xato, oob=True)
            oqituvchi = get_object_or_404(
                OqituvchiProfil.objects.kafedrada(self.kafedra).filter(
                    foydalanuvchi__is_active=True
                ),
                pk=oqituvchi_pk,
            )
            try:
                yangi = services.guruhlarga_ommaviy_taqsimlash(fs, oqituvchi, tur)
            except ValidationError as exc:
                return self.panel_javobi(request, fs, xato=xato_matni(exc), oob=True)
            matn = (
                f"{self.kafedra.nomi}: {fs.variant.nomi} ({fs.semestr}-semestr, {tur}) "
                f"barcha bo'sh ({len(yangi)} ta) guruhlar {oqituvchi} ga taqsimlandi."
            )
            audit_yoz(
                AuditAmali.YARATILDI,
                matn,
                model_nomi="Yuklama",
                obyekt_id=yangi[0].pk,
                request=request,
            )
        return self.panel_javobi(request, fs, oob=True)

    def _tekshir(self, fs: FanSemestr, oqituvchi_pk: int | None, tur: str) -> str:
        if services.kafedra_yuklama_qulflanganmi(self.kafedra, fs.akademik_yil):
            return "Yuklama tasdiqqa yuborilgan yoki tasdiqlangan — qulflangan."
        if oqituvchi_pk is None or tur not in PER_GURUH_TURLAR:
            return "O'qituvchi yoki mashg'ulot turi tanlanmadi."
        return ""


class GuruhlarTozalashView(PanelAsosView):
    """Clears all group delegations for a given activity type in one step."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        tur = request.POST.get("tur")
        with transaction.atomic():
            fs = self._qulflangan_fs(pk)
            if services.kafedra_yuklama_qulflanganmi(self.kafedra, fs.akademik_yil):
                return self.panel_javobi(
                    request,
                    fs,
                    xato="Yuklama tasdiqqa yuborilgan yoki tasdiqlangan — qulflangan.",
                    oob=True,
                )
            if not tur or tur not in PER_GURUH_TURLAR:
                return self.panel_javobi(
                    request, fs, xato="Mashg'ulot turi noto'g'ri.", oob=True
                )
            ochirilganlar = Yuklama.objects.filter(fan_semestr=fs, tur=tur)
            soni = ochirilganlar.count()
            if soni == 0:
                return self.panel_javobi(request, fs, oob=True)
            ochirilganlar.delete()
            services.keshni_tozala()
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
