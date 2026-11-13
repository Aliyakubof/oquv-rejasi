"""Office settings: institution name, teacher position norms and major classifier."""

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, TemplateView, UpdateView

from accounts.excel_import import (
    yonalishlar_excel_import,
    yonalishlar_namuna_excel,
)
from accounts.models import OqituvchiTuri, Universitet
from accounts.services import universitet_olish
from plans.audit import audit_yoz
from plans.models import AuditAmali, OquvReja, TalimYonalishi
from web.forms.sozlamalar import (
    OqituvchiTuriForm,
    TalimYonalishiForm,
    UniversitetForm,
)
from web.mixins import OfficeAdminTalabMixin, office_admin_talab


class SozlamalarView(OfficeAdminTalabMixin, TemplateView):
    template_name = "web/office/sozlamalar/list.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        universitet = universitet_olish()
        q = self.request.GET.get("q", "").strip()
        yonalishlar_qs = TalimYonalishi.objects.order_by("kodi")
        if q:
            yonalishlar_qs = yonalishlar_qs.filter(
                Q(kodi__icontains=q)
                | Q(nomi__icontains=q)
                | Q(bilim_sohasi_nomi__icontains=q)
                | Q(talim_sohasi_nomi__icontains=q)
            )
        page_obj = Paginator(yonalishlar_qs, 25).get_page(self.request.GET.get("page"))
        context.update(
            {
                "universitet_form": UniversitetForm(instance=universitet),
                "lavozimlar": OqituvchiTuri.objects.annotate(
                    oqituvchilar_soni=Count("oqituvchilar")
                ).order_by("nomi"),
                "yonalishlar": page_obj.object_list,
                "page_obj": page_obj,
                "yonalish_q": q,
                "yonalish_query": urlencode({"q": q}) if q else "",
            }
        )
        return context


@require_POST
@office_admin_talab
def universitet_saqlash(request: HttpRequest) -> HttpResponse:
    with transaction.atomic():
        universitet = Universitet.objects.select_for_update().first() or Universitet()
        form = UniversitetForm(request.POST, instance=universitet)
        if form.is_valid():
            saqlangan = form.save()
            audit_yoz(
                AuditAmali.TAHRIRLANDI,
                f"Universitet nomi yangilandi: {saqlangan.rasmiy_nomi}.",
                obyekt=saqlangan,
                request=request,
            )
            messages.success(request, "Universitet rasmiy nomi saqlandi.")
        else:
            messages.error(request, "Universitet nomini tekshiring.")
    return redirect("office:sozlamalar")


class LavozimYangiView(OfficeAdminTalabMixin, CreateView):
    template_name = "web/office/sozlamalar/form.html"
    form_class = OqituvchiTuriForm
    success_url = reverse_lazy("office:sozlamalar")
    extra_context = {"sarlavha": "Yangi lavozim"}

    def form_valid(self, form: OqituvchiTuriForm) -> HttpResponse:
        javob = super().form_valid(form)
        audit_yoz(
            AuditAmali.YARATILDI,
            f"Lavozim yaratildi: {self.object.nomi} ({self.object.min_soat} soat).",
            obyekt=self.object,
            request=self.request,
        )
        messages.success(self.request, "Lavozim yaratildi.")
        return javob


class LavozimTahrirView(OfficeAdminTalabMixin, UpdateView):
    template_name = "web/office/sozlamalar/form.html"
    form_class = OqituvchiTuriForm
    queryset = OqituvchiTuri.objects.all()
    success_url = reverse_lazy("office:sozlamalar")
    extra_context = {"sarlavha": "Lavozimni tahrirlash"}

    def form_valid(self, form: OqituvchiTuriForm) -> HttpResponse:
        javob = super().form_valid(form)
        audit_yoz(
            AuditAmali.TAHRIRLANDI,
            f"Lavozim tahrirlandi: {self.object.nomi} ({self.object.min_soat} soat).",
            obyekt=self.object,
            request=self.request,
        )
        messages.success(self.request, "Lavozim saqlandi.")
        return javob


@require_POST
@office_admin_talab
def lavozim_ochirish(request: HttpRequest, pk: int) -> HttpResponse:
    lavozim = get_object_or_404(OqituvchiTuri, pk=pk)
    try:
        with transaction.atomic():
            lavozim = get_object_or_404(
                OqituvchiTuri.objects.select_for_update(), pk=pk
            )
            nomi = lavozim.nomi
            lavozim_id = lavozim.pk
            lavozim.delete()
            audit_yoz(
                AuditAmali.OCHIRILDI,
                f"Lavozim o'chirildi: {nomi}.",
                model_nomi="OqituvchiTuri",
                obyekt_id=lavozim_id,
                request=request,
            )
        messages.success(request, f"{nomi} lavozimi o'chirildi.")
    except ProtectedError:
        messages.error(
            request,
            f"{lavozim.nomi} lavozimida o'qituvchilar bor — "
            "avval ularning lavozimini o'zgartiring.",
        )
    return redirect("office:sozlamalar")


class YonalishYangiView(OfficeAdminTalabMixin, CreateView):
    template_name = "web/office/sozlamalar/form.html"
    form_class = TalimYonalishiForm
    success_url = reverse_lazy("office:sozlamalar")
    extra_context = {"sarlavha": "Yangi ta'lim yo'nalishi"}

    def form_valid(self, form: TalimYonalishiForm) -> HttpResponse:
        javob = super().form_valid(form)
        audit_yoz(
            AuditAmali.YARATILDI,
            f"Ta'lim yo'nalishi yaratildi: {self.object}.",
            obyekt=self.object,
            request=self.request,
        )
        messages.success(self.request, "Ta'lim yo'nalishi yaratildi.")
        return javob


class YonalishTahrirView(OfficeAdminTalabMixin, UpdateView):
    template_name = "web/office/sozlamalar/form.html"
    form_class = TalimYonalishiForm
    queryset = TalimYonalishi.objects.all()
    success_url = reverse_lazy("office:sozlamalar")
    extra_context = {"sarlavha": "Ta'lim yo'nalishini tahrirlash"}

    def form_valid(self, form: TalimYonalishiForm) -> HttpResponse:
        javob = super().form_valid(form)
        audit_yoz(
            AuditAmali.TAHRIRLANDI,
            f"Ta'lim yo'nalishi tahrirlandi: {self.object}.",
            obyekt=self.object,
            request=self.request,
        )
        messages.success(self.request, "Ta'lim yo'nalishi saqlandi.")
        return javob


@require_POST
@office_admin_talab
def yonalish_ochirish(request: HttpRequest, pk: int) -> HttpResponse:
    yonalish = get_object_or_404(TalimYonalishi, pk=pk)
    try:
        with transaction.atomic():
            yonalish = get_object_or_404(
                TalimYonalishi.objects.select_for_update(), pk=pk
            )
            if OquvReja.objects.filter(yonalish_kodi=yonalish.kodi).exists():
                messages.error(
                    request,
                    f"{yonalish.kodi} yo'nalishi bo'yicha o'quv rejalar mavjud — "
                    "avval bog'liq o'quv rejalarni o'chiring.",
                )
                return redirect("office:sozlamalar")
            nomi = str(yonalish)
            yonalish_id = yonalish.pk
            yonalish.delete()
            audit_yoz(
                AuditAmali.OCHIRILDI,
                f"Ta'lim yo'nalishi o'chirildi: {nomi}.",
                model_nomi="TalimYonalishi",
                obyekt_id=yonalish_id,
                request=request,
            )
        messages.success(request, f"{nomi} o'chirildi.")
    except ProtectedError:
        messages.error(
            request,
            (
                f"{yonalish.kodi} yo'nalishi boshqa yozuvlarga bog'langan — "
                "o'chirib bo'lmaydi."
            ),
        )
    return redirect("office:sozlamalar")


@office_admin_talab
def yonalish_namuna_excel_view(request: HttpRequest) -> HttpResponse:
    return FileResponse(
        yonalishlar_namuna_excel(),
        as_attachment=True,
        filename="yonalishlar_namuna.xlsx",
    )


@require_POST
@office_admin_talab
def yonalish_import_view(request: HttpRequest) -> HttpResponse:
    fayl = request.FILES.get("fayl")
    if fayl is None:
        messages.error(request, "Klassifikator Excel (.xlsx) faylini tanlang.")
        return redirect("office:sozlamalar")
    try:
        yaratildi, yangilandi = yonalishlar_excel_import(fayl)
        audit_yoz(
            AuditAmali.YARATILDI,
            (
                f"Yo'nalishlar Excel import: {yaratildi} ta yaratildi, "
                f"{yangilandi} ta yangilandi."
            ),
            model_nomi="TalimYonalishi",
            request=request,
        )
        messages.success(
            request,
            (
                f"Klassifikator yangilandi: {yaratildi} ta qo'shildi, "
                f"{yangilandi} ta yangilandi."
            ),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("office:sozlamalar")
