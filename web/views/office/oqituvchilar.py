"""Office-wide teacher administration, coverage list, detail and Excel export."""

from django.contrib import messages
from django.db import transaction
from django.db.models import ProtectedError
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from accounts.models import Department, OqituvchiProfil
from accounts.services import mudir_tayinlash
from plans import dashboard, eksport, services
from plans.audit import audit_yoz
from plans.dashboard import yilni_tanlash
from plans.models import AuditAmali
from web.forms.oqituvchi import OqituvchiTahrirForm, OqituvchiYaratishForm
from web.mixins import (
    OfficeAdminTalabMixin,
    YilTanlovMixin,
    musbat_int_yoki_none,
    office_admin_talab,
)
from web.views.oqituvchi_base import (
    OqituvchiTahrirAsosView,
    OqituvchiYangiAsosView,
    OqituvchiYuklamaAsosView,
    oqituvchi_yuklama_konteksti,
)

# Re-export for any external consumers
__all__ = [
    "OqituvchiListView",
    "OqituvchiTahrirView",
    "OqituvchiYangiView",
    "OqituvchiYuklamaView",
    "oqituvchi_ochirish",
    "oqituvchi_yuklama_konteksti",
    "oqituvchilar_excel_view",
]


def _tanlangan_kafedra(sorov: HttpRequest) -> Department | None:
    kafedra_pk = musbat_int_yoki_none(sorov.GET.get("kafedra"))
    if kafedra_pk is None:
        return None
    return Department.objects.filter(pk=kafedra_pk).first()


class OqituvchiListView(OfficeAdminTalabMixin, YilTanlovMixin, TemplateView):
    template_name = "web/office/oqituvchilar/list.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        kafedra = _tanlangan_kafedra(self.request)
        context.update(
            {
                "kafedralar": Department.objects.all(),
                "kafedra": kafedra,
                "holatlar": services.yuklama_kamomadi(self.yil, kafedra=kafedra),
            }
        )
        return context


class OqituvchiYuklamaView(OfficeAdminTalabMixin, OqituvchiYuklamaAsosView):
    orqaga_url = "office:oqituvchi_list"

    def profil_olish(self) -> OqituvchiProfil:
        return get_object_or_404(
            OqituvchiProfil.objects.toliq(),
            pk=self.kwargs["pk"],
        )


@office_admin_talab
def oqituvchilar_excel_view(request: HttpRequest) -> HttpResponse:
    _, yil = yilni_tanlash(request.GET.get("yil"))
    yil = yil or dashboard.joriy_akademik_yil()
    kafedra = _tanlangan_kafedra(request)
    fayl_nomi = f"oqituvchilar_yuklamasi_{yil}_{yil + 1}.xlsx"
    return FileResponse(
        eksport.oqituvchilar_excel(yil, kafedra=kafedra),
        as_attachment=True,
        filename=fayl_nomi,
    )


class OqituvchiYangiView(OfficeAdminTalabMixin, OqituvchiYangiAsosView):
    template_name = "web/office/oqituvchilar/form.html"
    form_class = OqituvchiYaratishForm
    success_url_name = "office:oqituvchi_list"


class OqituvchiTahrirView(OfficeAdminTalabMixin, OqituvchiTahrirAsosView):
    template_name = "web/office/oqituvchilar/form.html"
    form_class = OqituvchiTahrirForm
    success_url_name = "office:oqituvchi_list"


def _oqituvchini_faolsizlantir(
    request: HttpRequest, profil: OqituvchiProfil, nom: str
) -> None:
    boshqa_kafedra = getattr(profil, "boshqarayotgan_kafedra", None)
    if boshqa_kafedra is not None:
        mudir_tayinlash(boshqa_kafedra, None)
    foydalanuvchi = profil.foydalanuvchi
    foydalanuvchi.is_active = False
    foydalanuvchi.save(update_fields=["is_active"])
    audit_yoz(
        AuditAmali.TAHRIRLANDI,
        f"O'qituvchi faolsizlantirildi: {nom}.",
        obyekt=profil,
        request=request,
    )
    messages.warning(
        request,
        f"{nom} yuklama yoki fan dasturi topshirig'iga ega — "
        "hisob o'chirilmasdan faolsizlantirildi.",
    )


@require_POST
@office_admin_talab
def oqituvchi_ochirish(request: HttpRequest, pk: int) -> HttpResponse:
    with transaction.atomic():
        profil = get_object_or_404(
            OqituvchiProfil.objects.bilan_foydalanuvchi().select_for_update(), pk=pk
        )
        if profil.foydalanuvchi_id == request.user.pk:
            messages.error(request, "O'z hisobingizni o'chira olmaysiz.")
            return redirect("office:oqituvchi_list")
        nom = str(profil)
        profil_id = profil.pk
        bogliq_bormi = (
            profil.yuklamalar.exists() or profil.dastur_topshirishlari.exists()
        )
        if bogliq_bormi:
            _oqituvchini_faolsizlantir(request, profil, nom)
            return redirect("office:oqituvchi_list")
        try:
            with transaction.atomic():
                profil.foydalanuvchi.delete()
        except ProtectedError:
            _oqituvchini_faolsizlantir(request, profil, nom)
            return redirect("office:oqituvchi_list")
        audit_yoz(
            AuditAmali.OCHIRILDI,
            f"O'qituvchi o'chirildi: {nom}.",
            model_nomi="OqituvchiProfil",
            obyekt_id=profil_id,
            request=request,
        )
        messages.success(request, f"{nom} o'chirildi.")
    return redirect("office:oqituvchi_list")
