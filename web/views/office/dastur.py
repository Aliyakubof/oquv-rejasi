"""AOH review of submitted O'quv Dastur files: list, accept, decline, open."""

from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from accounts.models import Department
from plans.audit import audit_yoz
from plans.dastur.topshirish import (
    dastur_qabul_qilish,
    dastur_rad_etish,
    joriy_topshirishlar,
    topshirilmagan_dasturlar,
)
from plans.models import AuditAmali, DasturTopshirish, FanVariant
from web.forms.dastur import DasturRadEtishForm
from web.mixins import OfficeAdminTalabMixin, office_admin_talab, xato_matni


class DasturTopshirishlarView(OfficeAdminTalabMixin, ListView):
    template_name = "web/office/dasturlar/list.html"
    context_object_name = "topshirishlar"

    def _kafedra_id(self) -> int | None:
        qiymat = self.request.GET.get("kafedra", "")
        return int(qiymat) if qiymat.isdigit() else None

    def get_queryset(self) -> list[DasturTopshirish]:
        holat = self.request.GET.get("holat")
        if holat == "TOPSHIRILMAGAN":
            return []
        qs = DasturTopshirish.objects.select_related(
            "variant__fan__reja", "variant__kafedra", "oqituvchi__foydalanuvchi"
        )
        kafedra_id = self._kafedra_id()
        if kafedra_id is not None:
            qs = qs.filter(variant__kafedra_id=kafedra_id)
        topshirishlar = joriy_topshirishlar(qs)
        if holat:
            topshirishlar = [t for t in topshirishlar if t.holat == holat]
        return topshirishlar

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        holat = self.request.GET.get("holat", "")
        kafedra_id = self._kafedra_id()
        topshirilmaganlar = topshirilmagan_dasturlar(kafedra_id=kafedra_id)
        context.update(
            {
                "holat": holat,
                "kafedra_id": kafedra_id,
                "kafedralar": Department.objects.order_by("nomi"),
                "topshirilmagan_soni": len(topshirilmaganlar),
                "topshirilmaganlar": (
                    topshirilmaganlar if holat == "TOPSHIRILMAGAN" else []
                ),
            }
        )
        return context


def _panel_kontekst(
    variant: FanVariant, *, xato: str | None = None
) -> dict[str, object]:
    urinishlar = list(
        variant.dastur_topshirishlari.select_related(
            "korib_chiqqan", "oqituvchi__foydalanuvchi"
        )
    )
    return {
        "variant": variant,
        "urinishlar": urinishlar,
        "t": urinishlar[0] if urinishlar else None,
        "xato": xato,
    }


def _javob(
    request: HttpRequest, variant: FanVariant, *, xato: str | None = None
) -> HttpResponse:
    return render(
        request,
        "web/office/dasturlar/_qator_va_panel.html",
        _panel_kontekst(variant, xato=xato),
    )


@require_POST
@office_admin_talab
def dastur_qabul(request: HttpRequest, pk: int) -> HttpResponse:
    topshirish = get_object_or_404(DasturTopshirish, pk=pk)
    xato = None
    try:
        dastur_qabul_qilish(topshirish, request.user)
        audit_yoz(
            AuditAmali.TASDIQLANDI,
            f"Fan dasturi qabul qilindi: {topshirish.variant.nomi}.",
            obyekt=topshirish,
            request=request,
        )
    except ValidationError as e:
        xato = xato_matni(e)
    return _javob(request, topshirish.variant, xato=xato)


@require_POST
@office_admin_talab
def dastur_rad(request: HttpRequest, pk: int) -> HttpResponse:
    topshirish = get_object_or_404(DasturTopshirish, pk=pk)
    form = DasturRadEtishForm(request.POST)
    xato = None
    if form.is_valid():
        try:
            izoh = form.cleaned_data["izoh"]
            dastur_rad_etish(topshirish, request.user, izoh)
            audit_yoz(
                AuditAmali.QAYTARILDI,
                f"Fan dasturi rad etildi: {topshirish.variant.nomi}. Sabab: {izoh}",
                obyekt=topshirish,
                request=request,
            )
        except ValidationError as e:
            xato = xato_matni(e)
    else:
        xato = " ".join(x for xs in form.errors.values() for x in xs)
    return _javob(request, topshirish.variant, xato=xato)


@office_admin_talab
def dastur_fayl(request: HttpRequest, pk: int) -> HttpResponse:
    topshirish = get_object_or_404(DasturTopshirish, pk=pk)
    try:
        return FileResponse(topshirish.fayl.open("rb"), as_attachment=True)
    except FileNotFoundError as exc:
        raise Http404("Fayl topilmadi.") from exc


@office_admin_talab
def dastur_tarixi(request: HttpRequest, variant_id: int) -> HttpResponse:
    variant = get_object_or_404(FanVariant, pk=variant_id)
    return render(
        request, "web/office/dasturlar/_tarix_panel.html", _panel_kontekst(variant)
    )
