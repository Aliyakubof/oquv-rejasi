"""Office dashboard: year-scoped KPIs, course list and inline allocation."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from accounts.models import Department
from plans import dashboard, services
from plans.audit import audit_yoz
from plans.dashboard import yilni_tanlash
from plans.models import AuditAmali, Fan, FanVariant
from web.mixins import (
    OfficeAdminTalabMixin,
    musbat_int_yoki_none,
    office_admin_talab,
    xato_matni,
)

TURLAR_METRIKASI = [
    ("MARUZA", "Ma'ruza", "var(--tur-maruza, #10b981)"),
    ("AMALIYOT", "Amaliyot", "var(--tur-amaliyot, #2563eb)"),
    ("LABORATORIYA", "Laboratoriya", "var(--tur-lab, #0891b2)"),
    ("SEMINAR", "Seminar", "var(--tur-seminar, #7c3aed)"),
    ("KURS_ISHI", "Kurs ishi", "var(--tur-kurs, #f59e0b)"),
]


def _dashboard_konteksti(yil: int) -> dict[str, object]:
    taqsimot = services.ofis_taqsimoti(yil)
    return {
        "yil": yil,
        "stat": dashboard.statlarni_hisoblash(taqsimot),
        "jami_talabalar": dashboard.jami_talabalar(yil),
        "fan_satrlari": dashboard.ofis_fan_satrlari(yil),
        "kafedralar": Department.objects.all(),
        "qamrovlar": dashboard.kafedra_qamrovi(yil, taqsimot=taqsimot),
        "turlar_metrikasi": TURLAR_METRIKASI,
    }


class DashboardView(OfficeAdminTalabMixin, TemplateView):
    template_name = "web/office/dashboard.html"

    def get_template_names(self) -> list[str]:
        if self.request.headers.get("HX-Request") and not self.request.headers.get(
            "HX-Boosted"
        ):
            return ["web/office/_dashboard_kontent.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        yillar, yil = yilni_tanlash(self.request.GET.get("yil"))
        context["yillar"] = yillar
        if yil is not None:
            context.update(_dashboard_konteksti(yil))
        return context


@require_POST
@office_admin_talab
def variant_tanlash(request: HttpRequest, pk: int) -> HttpResponse:
    fan = get_object_or_404(Fan, pk=pk)
    variant_pk = musbat_int_yoki_none(request.POST.get("variant"))
    if variant_pk is None:
        raise Http404
    variant = get_object_or_404(FanVariant, pk=variant_pk, fan=fan)
    xato = None
    try:
        with transaction.atomic():
            services.variantni_tanlash(fan, variant)
            audit_yoz(
                AuditAmali.TAHRIRLANDI,
                f"Tanlov fani varianti tanlandi: {variant.nomi} ({fan.reja}).",
                obyekt=fan,
                request=request,
            )
    except ValidationError as e:
        xato = xato_matni(e)
    return _qator_javobi(request, fan, xato)


@require_POST
@office_admin_talab
def kafedra_biriktirish(request: HttpRequest, pk: int) -> HttpResponse:
    variant = get_object_or_404(FanVariant, pk=pk)
    xom_kafedra = request.POST.get("kafedra")
    if xom_kafedra:
        kafedra_pk = musbat_int_yoki_none(xom_kafedra)
        if kafedra_pk is None:
            raise Http404
        kafedra = get_object_or_404(Department, pk=kafedra_pk)
    else:
        kafedra = None
    xato = None
    try:
        with transaction.atomic():
            services.kafedraga_biriktirish(variant, kafedra)
            kaf_matni = kafedra.nomi if kafedra else "bekor qilindi"
            audit_yoz(
                AuditAmali.TAHRIRLANDI,
                f"Fan kafedraga biriktirildi: {variant.nomi} -> {kaf_matni}.",
                obyekt=variant,
                request=request,
            )
    except ValidationError as e:
        xato = xato_matni(e)
    return _qator_javobi(request, variant.fan, xato)


def _qator_javobi(request: HttpRequest, fan: Fan, xato: str | None) -> HttpResponse:
    """Re-render the mutated course row plus an out-of-band stats block.

    Non-HTMX callers (the reja detail page) pass `redirect` and get a normal
    redirect with the outcome delivered via messages.
    """
    redirect_url = request.POST.get("redirect")
    if redirect_url:
        if xato:
            messages.error(request, xato)
        if url_has_allowed_host_and_scheme(
            redirect_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(redirect_url)
        return redirect("office:dashboard")
    _, yil = yilni_tanlash(request.POST.get("yil"))
    if yil is None:
        kontekst: dict[str, object] = {}
        satr = None
    else:
        taqsimot = services.ofis_taqsimoti(yil)
        satrlar = dashboard.ofis_fan_satrlari(yil, fan_id=fan.pk)
        satr = satrlar[0] if satrlar else None
        kontekst = {
            "yil": yil,
            "stat": dashboard.statlarni_hisoblash(taqsimot),
            "jami_talabalar": dashboard.jami_talabalar(yil),
            "kafedralar": Department.objects.all(),
        }
    kontekst.update({"satr": satr, "xato": xato})
    return render(request, "web/office/_qator_va_statlar.html", kontekst)
