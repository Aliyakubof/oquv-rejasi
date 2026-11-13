"""O'quv reja screens: list, Excel import, detail (semestrovka), edit and delete."""

import re

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, FormView, ListView, UpdateView

from accounts.models import Department
from plans import dashboard, services
from plans.audit import audit_yoz
from plans.importer import ImportNatija, ImportXato
from plans.models import AuditAmali, FanTuri, OquvReja, Yuklama
from plans.services import SemestrTahrir, semestrovka_yangilash
from plans.uploads import fayldan_import_qilish
from web.forms.reja import RejaImportForm, RejaTahrirForm
from web.mixins import OfficeAdminTalabMixin, office_admin_talab, xato_matni

RUXSAT_ETILGAN_TABLAR = frozenset({"jadval", "semestr", "semestrovka"})


class RejaListView(OfficeAdminTalabMixin, ListView):
    template_name = "web/office/rejalar/list.html"
    context_object_name = "rejalar"
    queryset = OquvReja.objects.order_by("-boshlanish_yili", "yonalish_nomi")


class RejaImportView(OfficeAdminTalabMixin, FormView):
    template_name = "web/office/rejalar/yangi.html"
    form_class = RejaImportForm

    def form_valid(self, form: RejaImportForm) -> HttpResponse:
        try:
            natija = fayldan_import_qilish(
                form.cleaned_data["fayl"], form.parametrlar()
            )
        except ImportXato as xato:
            form.add_error(None, str(xato))
            return self.form_invalid(form)
        amal = AuditAmali.YARATILDI if natija.yaratildi else AuditAmali.TAHRIRLANDI
        audit_yoz(
            amal,
            f"O'quv reja import qilindi: {natija.reja} ({natija.fan_soni} fan).",
            obyekt=natija.reja,
            request=self.request,
        )
        self._xabarlar(natija)
        return redirect("office:reja_detail", pk=natija.reja.pk)

    def _xabarlar(self, natija: ImportNatija) -> None:
        holat = "yaratildi" if natija.yaratildi else "yangilandi"
        messages.success(
            self.request,
            f"{natija.reja} {holat}: {natija.fan_soni} fan, "
            f"{natija.variant_soni} variant.",
        )
        for ogohlantirish in natija.ogohlantirishlar:
            messages.warning(self.request, ogohlantirish)


class RejaDetailView(OfficeAdminTalabMixin, DetailView):
    template_name = "web/office/rejalar/detail.html"
    context_object_name = "reja"
    queryset = OquvReja.objects.prefetch_related("guruhlar")

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        reja = self.object
        satrlar = dashboard.reja_semestrovkasi(reja)
        taqsimot = services.taqsimot_hisoboti(reja)
        semestr_kesimi = dashboard.reja_semestr_kesimi(
            reja, satrlar=satrlar, taqsimot=taqsimot
        )
        birinchi_semestr = min(semestr_kesimi, default=None)
        sorov_tab = self.request.GET.get("tab")
        tab = sorov_tab if sorov_tab in RUXSAT_ETILGAN_TABLAR else "jadval"
        sorov_sem = self.request.GET.get("sem")
        tanlangan_semestr = (
            int(sorov_sem)
            if sorov_sem
            and sorov_sem.isascii()
            and sorov_sem.isdigit()
            and int(sorov_sem) in semestr_kesimi
            else birinchi_semestr
        )
        context.update(
            {
                "tab": tab,
                "satrlar": satrlar,
                "majburiy_satrlar": [
                    s for s in satrlar if s.fan.turi == FanTuri.MAJBURIY
                ],
                "tanlov_satrlar": [s for s in satrlar if s.fan.turi == FanTuri.TANLOV],
                "semestr_raqamlari": range(1, reja.semestrlar_soni + 1),
                "stat": dashboard.statlarni_hisoblash(taqsimot),
                "kafedralar": Department.objects.order_by("nomi"),
                "semestr_kesimi": semestr_kesimi,
                "birinchi_semestr": birinchi_semestr,
                "tanlangan_semestr": tanlangan_semestr,
            }
        )
        return context


class RejaTahrirView(OfficeAdminTalabMixin, UpdateView):
    template_name = "web/office/rejalar/tahrir.html"
    form_class = RejaTahrirForm
    queryset = OquvReja.objects.all()
    context_object_name = "reja"

    def form_valid(self, form: RejaTahrirForm) -> HttpResponse:
        javob = super().form_valid(form)
        services.guruhlarni_sinxronlash(self.object)
        audit_yoz(
            AuditAmali.TAHRIRLANDI,
            f"O'quv reja tahrirlandi: {self.object}.",
            obyekt=self.object,
            request=self.request,
        )
        messages.success(self.request, "Reja saqlandi, guruhlar yangilandi.")
        return javob

    def get_success_url(self) -> str:
        return reverse("office:reja_detail", kwargs={"pk": self.object.pk})


@require_POST
@office_admin_talab
def reja_ochirish(request: HttpRequest, pk: int) -> HttpResponse:
    with transaction.atomic():
        reja = get_object_or_404(OquvReja.objects.select_for_update(), pk=pk)
        if Yuklama.objects.filter(fan_semestr__variant__fan__reja=reja).exists():
            messages.error(
                request,
                f"{reja} rejasida taqsimlangan yuklamalar bor — "
                "avval ularni bekor qiling.",
            )
            return redirect("office:reja_list")
        nom = str(reja)
        reja_id = reja.pk
        reja.delete()
        audit_yoz(
            AuditAmali.OCHIRILDI,
            f"O'quv reja o'chirildi: {nom}.",
            model_nomi="OquvReja",
            obyekt_id=reja_id,
            request=request,
        )
    messages.success(request, f"{nom} o'chirildi.")
    return redirect("office:reja_list")


_FS_MAYDON = re.compile(r"^fs-(\d+)-(?:maruza|amaliyot|lab|seminar|kursishi)$")


def _musbat_int(qiymat: str | None) -> int:
    if qiymat is None or qiymat.strip() == "":
        raise ValidationError("Soat qiymati bo'sh bo'lishi mumkin emas.")
    toza = qiymat.strip()
    if not (toza.isascii() and toza.isdigit()):
        raise ValidationError(
            f"Noto'g'ri soat qiymati: '{qiymat}'. Manfiy bo'lmagan butun son kiriting."
        )
    return int(toza)


def _tahrirlarni_oqish(post: object) -> list[SemestrTahrir]:
    """Collect one SemestrTahrir per fs-<pk>-* input group in the POST body."""
    pklar: dict[int, None] = {}
    for kalit in post:
        mos = _FS_MAYDON.match(kalit)
        if mos is not None:
            pklar.setdefault(int(mos.group(1)), None)
    return [
        SemestrTahrir(
            fan_semestr_id=pk,
            maruza_soat=_musbat_int(post.get(f"fs-{pk}-maruza")),
            amaliyot_soat=_musbat_int(post.get(f"fs-{pk}-amaliyot")),
            laboratoriya_soat=_musbat_int(post.get(f"fs-{pk}-lab")),
            seminar_soat=_musbat_int(post.get(f"fs-{pk}-seminar")),
            kurs_ishi_bor=post.get(f"fs-{pk}-kursishi") == "on",
        )
        for pk in pklar
    ]


@require_POST
@office_admin_talab
def semestrovka_saqlash(request: HttpRequest, pk: int) -> HttpResponse:
    reja = get_object_or_404(OquvReja, pk=pk)
    try:
        tahrirlar = _tahrirlarni_oqish(request.POST)
        with transaction.atomic():
            reja = get_object_or_404(OquvReja.objects.select_for_update(), pk=pk)
            semestrovka_yangilash(reja, tahrirlar)
            audit_yoz(
                AuditAmali.TAHRIRLANDI,
                f"Semestrovka soatlari tahrirlandi: {reja}.",
                obyekt=reja,
                request=request,
            )
    except ValidationError as xato:
        messages.error(request, xato_matni(xato))
    else:
        messages.success(request, "Semestrovka saqlandi.")
    manzil = reverse("office:reja_detail", kwargs={"pk": reja.pk})
    return redirect(f"{manzil}?tab=semestrovka")
