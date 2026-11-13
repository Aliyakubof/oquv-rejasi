"""Office-wide teacher administration, coverage list, detail and Excel export."""

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from accounts.excel_import import (
    oqituvchi_import_natija_excel,
    oqituvchilar_excel_import,
    oqituvchilar_namuna_excel,
)
from accounts.models import Department, OqituvchiProfil, Rol
from accounts.services import mudir_tayinlash, vaqtinchalik_parol_yarat
from plans import dashboard, eksport, services
from plans.audit import audit_yoz
from plans.dashboard import yilni_tanlash
from plans.models import AuditAmali
from plans.shakl1_doc import shakl1_docx_render
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
    "oqituvchi_vaqtinchalik_parol",
    "oqituvchi_yuklama_konteksti",
    "oqituvchilar_excel_view",
]


def _tanlangan_kafedra(sorov: HttpRequest) -> Department | None:
    kafedra_pk = musbat_int_yoki_none(sorov.GET.get("kafedra"))
    if kafedra_pk is None:
        return None
    return Department.objects.filter(pk=kafedra_pk).first()


def _oqituvchi_qidiruvga_mosmi(holat: services.YuklamaHolati, q: str) -> bool:
    kalit = q.lower()
    oqit = holat.oqituvchi
    foy = oqit.foydalanuvchi
    matn = (
        f"{oqit} {foy.last_name} {foy.first_name} {foy.telefon} "
        f"{oqit.kafedra.nomi} {oqit.turi.nomi}"
    ).lower()
    return kalit in matn


class OqituvchiListView(OfficeAdminTalabMixin, YilTanlovMixin, TemplateView):
    template_name = "web/office/oqituvchilar/list.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        kafedra = _tanlangan_kafedra(self.request)
        q = self.request.GET.get("q", "").strip()
        barcha = services.yuklama_kamomadi(self.yil, kafedra=kafedra)
        if q:
            barcha = [h for h in barcha if _oqituvchi_qidiruvga_mosmi(h, q)]
        page_obj = Paginator(barcha, 30).get_page(self.request.GET.get("page"))
        paramlar: dict[str, str] = {"yil": str(self.yil)}
        if kafedra:
            paramlar["kafedra"] = str(kafedra.pk)
        if q:
            paramlar["q"] = q
        context.update(
            {
                "kafedralar": Department.objects.all(),
                "kafedra": kafedra,
                "holatlar": page_obj.object_list,
                "page_obj": page_obj,
                "qidiruv_q": q,
                "query_prefix": urlencode(paramlar),
                "vaqtinchalik_parol": self.request.session.pop(
                    "vaqtinchalik_parol_natija", None
                ),
            }
        )
        return context


class OqituvchiYuklamaView(OfficeAdminTalabMixin, OqituvchiYuklamaAsosView):
    orqaga_url = "office:oqituvchi_list"
    docx_url_name = "office:oqituvchi_shakl1_docx"

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


@require_POST
@office_admin_talab
def oqituvchi_vaqtinchalik_parol(request: HttpRequest, pk: int) -> HttpResponse:
    profil = get_object_or_404(OqituvchiProfil.objects.bilan_foydalanuvchi(), pk=pk)
    target = profil.foydalanuvchi
    if target.pk == request.user.pk:
        messages.error(request, "O'z parolingizni Parol sahifasidan o'zgartiring.")
        return redirect("office:oqituvchi_list")
    if target.rol == Rol.SUPERADMIN and request.user.rol != Rol.SUPERADMIN:
        messages.error(request, "Superadmin parolini tiklashga ruxsat yo'q.")
        return redirect("office:oqituvchi_list")
    parol = vaqtinchalik_parol_yarat(target)
    audit_yoz(
        AuditAmali.TAHRIRLANDI,
        f"Vaqtinchalik parol yaratildi: {profil}.",
        obyekt=profil,
        request=request,
    )
    request.session["vaqtinchalik_parol_natija"] = {
        "ism": str(profil),
        "telefon": target.telefon,
        "parol": parol,
    }
    messages.success(request, f"{profil} uchun yangi vaqtinchalik parol yaratildi.")
    return redirect("office:oqituvchi_list")


class OqituvchiImportView(OfficeAdminTalabMixin, View):
    template_name = "web/office/oqituvchilar/import.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, self.template_name, {})

    def post(self, request: HttpRequest) -> HttpResponse:
        fayl = request.FILES.get("fayl")
        if fayl is None:
            return render(
                request,
                self.template_name,
                {"xatolar": ["Excel (.xlsx) faylini tanlang."]},
            )
        try:
            natija = oqituvchilar_excel_import(fayl)
        except ValidationError as exc:
            return render(request, self.template_name, {"xatolar": exc.messages})
        parollar_mavjud = bool(natija.yaratilganlar)
        if parollar_mavjud:
            request.session["oqituvchi_import_parollar"] = natija.yaratilganlar
            audit_yoz(
                AuditAmali.YARATILDI,
                f"Excel dan {len(natija.yaratilganlar)} ta o'qituvchi import qilindi.",
                model_nomi="OqituvchiProfil",
                request=request,
            )
        messages.success(
            request,
            (
                f"{len(natija.yaratilganlar)} ta o'qituvchi qo'shildi, "
                f"{len(natija.otkazildi_mavjud)} ta mavjud raqam o'tkazib yuborildi."
            ),
        )
        return render(
            request,
            self.template_name,
            {"natija": natija, "parollar_mavjud": parollar_mavjud},
        )


@office_admin_talab
def oqituvchi_namuna_excel_view(request: HttpRequest) -> HttpResponse:
    return FileResponse(
        oqituvchilar_namuna_excel(),
        as_attachment=True,
        filename="oqituvchilar_namuna.xlsx",
    )


@office_admin_talab
def oqituvchi_import_parollar_view(request: HttpRequest) -> HttpResponse:
    yaratilganlar = request.session.pop("oqituvchi_import_parollar", None)
    if not yaratilganlar:
        raise Http404("Yuklab olish uchun yangi import parollari topilmadi.")
    return FileResponse(
        oqituvchi_import_natija_excel(yaratilganlar),
        as_attachment=True,
        filename="yangi_oqituvchilar_parollari.xlsx",
    )


@office_admin_talab
def oqituvchi_shakl1_docx_view(request: HttpRequest, pk: int) -> HttpResponse:
    profil = get_object_or_404(OqituvchiProfil.objects.toliq(), pk=pk)
    _, yil = yilni_tanlash(request.GET.get("yil"))
    yil = yil or dashboard.joriy_akademik_yil()
    return FileResponse(
        shakl1_docx_render(profil, yil),
        as_attachment=True,
        filename=f"1shakl_{profil.pk}_{yil}_{yil + 1}.docx",
    )
