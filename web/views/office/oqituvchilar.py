"""Ofis miqyosida o'qituvchilar ro'yxati, batafsil yuklama va Excel eksport."""

import time
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
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
    OfisAdminTalabMixin,
    YilTanlovMixin,
    musbat_int_yoki_none,
    ofis_admin_talab,
    xavfsiz_qaytish,
)
from web.views.oqituvchi_base import (
    OqituvchiTahrirAsosView,
    OqituvchiYangiAsosView,
    OqituvchiYuklamaAsosView,
    oqituvchi_yuklama_konteksti,
)

# Tashqi modullar uchun qayta eksport qilamiz
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


_VAQTINCHALIK_PAROL_TTL = 300


def _sessionga_muddatli_qoyish(
    request: HttpRequest, kalit: str, qiymat: object
) -> None:
    request.session[kalit] = {
        "data": qiymat,
        "exp": int(time.time()) + _VAQTINCHALIK_PAROL_TTL,
    }


def _sessiondan_muddatli_olish(request: HttpRequest, kalit: str) -> object | None:
    yozuv = request.session.pop(kalit, None)
    if not isinstance(yozuv, dict):
        return yozuv
    if "data" in yozuv and "exp" in yozuv:
        if int(time.time()) > int(yozuv["exp"]):
            return None
        return yozuv["data"]
    return yozuv


def _tanlangan_kafedra(sorov: HttpRequest) -> Department | None:
    kafedra_pk = musbat_int_yoki_none(sorov.GET.get("kafedra"))
    if kafedra_pk is None:
        return None
    return Department.objects.filter(pk=kafedra_pk).first()


class OqituvchiListView(OfisAdminTalabMixin, YilTanlovMixin, TemplateView):
    template_name = "web/office/oqituvchilar/list.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        kafedra = _tanlangan_kafedra(self.request)
        q = self.request.GET.get("q", "").strip()
        barcha = services.yuklama_kamomadi(self.yil, kafedra=kafedra, q=q)
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
                "vaqtinchalik_parol": _sessiondan_muddatli_olish(
                    self.request, "vaqtinchalik_parol_natija"
                ),
            }
        )
        return context


class OqituvchiYuklamaView(OfisAdminTalabMixin, OqituvchiYuklamaAsosView):
    orqaga_url = "office:oqituvchi_list"
    docx_url_name = "office:oqituvchi_shakl1_docx"

    def profil_olish(self) -> OqituvchiProfil:
        return get_object_or_404(
            OqituvchiProfil.objects.toliq(),
            pk=self.kwargs["pk"],
        )


@ofis_admin_talab
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


class OqituvchiYangiView(OfisAdminTalabMixin, OqituvchiYangiAsosView):
    template_name = "web/office/oqituvchilar/form.html"
    form_class = OqituvchiYaratishForm
    success_url_name = "office:oqituvchi_list"


class OqituvchiTahrirView(OfisAdminTalabMixin, OqituvchiTahrirAsosView):
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
@ofis_admin_talab
def oqituvchi_ochirish(request: HttpRequest, pk: int) -> HttpResponse:
    with transaction.atomic():
        profil = get_object_or_404(
            OqituvchiProfil.objects.bilan_foydalanuvchi().select_for_update(), pk=pk
        )
        if profil.foydalanuvchi_id == request.user.pk:
            messages.error(request, "O'z hisobingizni o'chira olmaysiz.")
            return xavfsiz_qaytish(request, "office:oqituvchi_list")
        if (
            profil.foydalanuvchi.rol == Rol.SUPERADMIN
            and request.user.rol != Rol.SUPERADMIN
        ):
            messages.error(request, "Superadmin hisobini o'chirishga ruxsat yo'q.")
            return xavfsiz_qaytish(request, "office:oqituvchi_list")
        nom = str(profil)
        profil_id = profil.pk
        bogliq_bormi = (
            profil.yuklamalar.exists() or profil.dastur_topshirishlari.exists()
        )
        if bogliq_bormi:
            _oqituvchini_faolsizlantir(request, profil, nom)
            return xavfsiz_qaytish(request, "office:oqituvchi_list")
        try:
            with transaction.atomic():
                profil.foydalanuvchi.delete()
        except ProtectedError:
            _oqituvchini_faolsizlantir(request, profil, nom)
            return xavfsiz_qaytish(request, "office:oqituvchi_list")
        audit_yoz(
            AuditAmali.OCHIRILDI,
            f"O'qituvchi o'chirildi: {nom}.",
            model_nomi="OqituvchiProfil",
            obyekt_id=profil_id,
            request=request,
        )
        messages.success(request, f"{nom} o'chirildi.")
    return xavfsiz_qaytish(request, "office:oqituvchi_list")


@require_POST
@ofis_admin_talab
def oqituvchi_vaqtinchalik_parol(request: HttpRequest, pk: int) -> HttpResponse:
    profil = get_object_or_404(OqituvchiProfil.objects.bilan_foydalanuvchi(), pk=pk)
    target = profil.foydalanuvchi
    if target.pk == request.user.pk:
        messages.error(request, "O'z parolingizni Parol sahifasidan o'zgartiring.")
        return xavfsiz_qaytish(request, "office:oqituvchi_list")
    if target.rol == Rol.SUPERADMIN and request.user.rol != Rol.SUPERADMIN:
        messages.error(request, "Superadmin parolini tiklashga ruxsat yo'q.")
        return xavfsiz_qaytish(request, "office:oqituvchi_list")
    parol = vaqtinchalik_parol_yarat(target)
    audit_yoz(
        AuditAmali.TAHRIRLANDI,
        f"Vaqtinchalik parol yaratildi: {profil}.",
        obyekt=profil,
        request=request,
    )
    _sessionga_muddatli_qoyish(
        request,
        "vaqtinchalik_parol_natija",
        {
            "ism": str(profil),
            "telefon": target.telefon,
            "parol": parol,
        },
    )
    messages.success(request, f"{profil} uchun yangi vaqtinchalik parol yaratildi.")
    return xavfsiz_qaytish(request, "office:oqituvchi_list")


class OqituvchiImportView(OfisAdminTalabMixin, View):
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
            _sessionga_muddatli_qoyish(
                request, "oqituvchi_import_parollar", natija.yaratilganlar
            )
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


@ofis_admin_talab
def oqituvchi_namuna_excel_view(request: HttpRequest) -> HttpResponse:
    return FileResponse(
        oqituvchilar_namuna_excel(),
        as_attachment=True,
        filename="oqituvchilar_namuna.xlsx",
    )


@ofis_admin_talab
def oqituvchi_import_parollar_view(request: HttpRequest) -> HttpResponse:
    yaratilganlar = _sessiondan_muddatli_olish(request, "oqituvchi_import_parollar")
    if not yaratilganlar or not isinstance(yaratilganlar, list):
        raise Http404("Yuklab olish uchun yangi import parollari topilmadi.")
    return FileResponse(
        oqituvchi_import_natija_excel(yaratilganlar),
        as_attachment=True,
        filename="yangi_oqituvchilar_parollari.xlsx",
    )


@ofis_admin_talab
def oqituvchi_shakl1_docx_view(request: HttpRequest, pk: int) -> HttpResponse:
    profil = get_object_or_404(OqituvchiProfil.objects.toliq(), pk=pk)
    _, yil = yilni_tanlash(request.GET.get("yil"))
    yil = yil or dashboard.joriy_akademik_yil()
    return FileResponse(
        shakl1_docx_render(profil, yil),
        as_attachment=True,
        filename=f"1shakl_{profil.pk}_{yil}_{yil + 1}.docx",
    )
