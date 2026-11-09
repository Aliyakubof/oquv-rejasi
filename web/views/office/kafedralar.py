"""Department administration: CRUD, coverage overview and mudir assignment."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, TemplateView, UpdateView

from accounts.models import Department, OqituvchiProfil
from accounts.services import mudir_tayinlash
from plans import dashboard, services
from plans.audit import audit_yoz
from plans.dashboard import yilni_tanlash
from plans.models import AuditAmali
from web.forms.kafedra import KafedraForm
from web.mixins import (
    OfficeAdminTalabMixin,
    YilTanlovMixin,
    office_admin_talab,
    xato_matni,
)


class KafedraListView(OfficeAdminTalabMixin, YilTanlovMixin, TemplateView):
    template_name = "web/office/kafedralar/list.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        context["qamrovlar"] = dashboard.kafedra_qamrovi(self.yil)
        return context


class KafedraYangiView(OfficeAdminTalabMixin, CreateView):
    template_name = "web/office/kafedralar/form.html"
    form_class = KafedraForm
    success_url = reverse_lazy("office:kafedra_list")

    def form_valid(self, form: KafedraForm) -> HttpResponse:
        javob = super().form_valid(form)
        audit_yoz(
            AuditAmali.YARATILDI,
            f"Kafedra yaratildi: {self.object.nomi}.",
            obyekt=self.object,
            request=self.request,
        )
        messages.success(self.request, "Kafedra yaratildi.")
        return javob


class KafedraTahrirView(OfficeAdminTalabMixin, UpdateView):
    template_name = "web/office/kafedralar/form.html"
    form_class = KafedraForm
    queryset = Department.objects.all()
    success_url = reverse_lazy("office:kafedra_list")

    def form_valid(self, form: KafedraForm) -> HttpResponse:
        javob = super().form_valid(form)
        audit_yoz(
            AuditAmali.TAHRIRLANDI,
            f"Kafedra tahrirlandi: {self.object.nomi}.",
            obyekt=self.object,
            request=self.request,
        )
        messages.success(self.request, "Kafedra saqlandi.")
        return javob


@require_POST
@office_admin_talab
def kafedra_ochirish(request: HttpRequest, pk: int) -> HttpResponse:
    kafedra = get_object_or_404(Department, pk=pk)
    try:
        nomi = kafedra.nomi
        kafedra_id = kafedra.pk
        kafedra.delete()
        audit_yoz(
            AuditAmali.OCHIRILDI,
            f"Kafedra o'chirildi: {nomi}.",
            model_nomi="Department",
            obyekt_id=kafedra_id,
            request=request,
        )
        messages.success(request, f"{nomi} o'chirildi.")
    except ProtectedError:
        messages.error(
            request,
            f"{kafedra.nomi} kafedrasida o'qituvchilar yoki fanlar bor — "
            "avval ularni boshqa kafedraga ko'chiring.",
        )
    return redirect("office:kafedra_list")


@require_POST
@office_admin_talab
def kafedra_mudir(request: HttpRequest, pk: int) -> HttpResponse:
    kafedra = get_object_or_404(Department, pk=pk)
    profil_id = request.POST.get("profil") or None
    profil = get_object_or_404(OqituvchiProfil, pk=profil_id) if profil_id else None
    try:
        mudir_tayinlash(kafedra, profil)
        if profil is None:
            audit_yoz(
                AuditAmali.TAHRIRLANDI,
                f"{kafedra.nomi}: kafedra mudiri bekor qilindi.",
                obyekt=kafedra,
                request=request,
            )
            messages.success(request, f"{kafedra.nomi}: mudir bekor qilindi.")
        else:
            audit_yoz(
                AuditAmali.TAHRIRLANDI,
                f"{kafedra.nomi}: {profil} kafedra mudiri etib tayinlandi.",
                obyekt=kafedra,
                request=request,
            )
            messages.success(
                request, f"{kafedra.nomi}: {profil} mudir etib tayinlandi."
            )
    except ValidationError as xato:
        messages.error(request, xato_matni(xato))
    _, yil = yilni_tanlash(request.POST.get("yil"))
    if yil:
        return redirect(f"{reverse_lazy('office:kafedra_list')}?yil={yil}")
    return redirect("office:kafedra_list")


@require_POST
@office_admin_talab
def kafedra_yuklama_tasdiqlash(request: HttpRequest, pk: int) -> HttpResponse:
    kafedra = get_object_or_404(Department, pk=pk)
    _, yil = yilni_tanlash(request.POST.get("yil"))
    yil = yil or dashboard.joriy_akademik_yil()
    izoh = request.POST.get("izoh", "").strip()
    tasdiq = services.yuklamani_tasdiqlash(kafedra, yil, request.user, izoh)
    audit_yoz(
        AuditAmali.TASDIQLANDI,
        f"{kafedra.nomi}: {yil}/{yil + 1} yuklamasi tasdiqlandi va qulflandi.",
        model_nomi="KafedraYuklamaTasdiq",
        obyekt_id=tasdiq.pk,
        request=request,
    )
    messages.success(request, f"{kafedra.nomi} yuklamasi tasdiqlandi.")
    return redirect(f"{reverse_lazy('office:kafedra_list')}?yil={yil}")


@require_POST
@office_admin_talab
def kafedra_yuklama_qaytarish(request: HttpRequest, pk: int) -> HttpResponse:
    kafedra = get_object_or_404(Department, pk=pk)
    _, yil = yilni_tanlash(request.POST.get("yil"))
    yil = yil or dashboard.joriy_akademik_yil()
    izoh = request.POST.get("izoh", "").strip()
    tasdiq = services.yuklamani_qaytarish(kafedra, yil, request.user, izoh)
    sabab = izoh or "Izohsiz"
    audit_yoz(
        AuditAmali.QAYTARILDI,
        f"{kafedra.nomi}: {yil}/{yil + 1} yuklamasi qaytarildi. Sabab: {sabab}",
        model_nomi="KafedraYuklamaTasdiq",
        obyekt_id=tasdiq.pk,
        request=request,
    )
    messages.warning(request, f"{kafedra.nomi} yuklamasi qaytarildi.")
    return redirect(f"{reverse_lazy('office:kafedra_list')}?yil={yil}")
