"""Kafedra head's dashboard: own-department demand and delegation rows."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from plans import dashboard, delegation, nusxalash, services
from plans.audit import audit_yoz
from plans.bildirishnoma import kafedra_yubordi_xabari
from plans.dashboard import yilni_tanlash
from plans.models import AuditAmali
from web.mixins import (
    KafedraMudiriTalabMixin,
    YilTanlovMixin,
    _boshqarayotgan_kafedra,
    kafedra_mudiri_talab,
    musbat_int_yoki_none,
    xato_matni,
)


class KafedraDashboardView(KafedraMudiriTalabMixin, YilTanlovMixin, TemplateView):
    template_name = "web/kafedra/dashboard.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        tasdiq = services.kafedra_tasdiq_oqish(self.kafedra, self.yil)
        taqsimot = services.kafedra_taqsimoti(self.kafedra, self.yil)
        context.update(
            {
                "kafedra": self.kafedra,
                "manba_yillar": nusxalash.manba_yillar_royxati(
                    self.yil, kafedra=self.kafedra
                ),
                "tasdiq": tasdiq,
                "qulflangan": services.tasdiq_qulflanganmi(tasdiq),
                "stat": dashboard.statlarni_hisoblash(taqsimot),
                "fs_satrlar": delegation.kafedra_fs_satrlari(
                    self.kafedra, self.yil, taqsimot=taqsimot
                ),
            }
        )
        return context


@require_POST
@kafedra_mudiri_talab
def tasdiqqa_yuborish_view(request: HttpRequest) -> HttpResponse:
    kafedra = _boshqarayotgan_kafedra(request)
    assert kafedra is not None
    _, yil = yilni_tanlash(request.POST.get("yil"))
    yil = yil or dashboard.joriy_akademik_yil()
    izoh = request.POST.get("izoh", "").strip()
    try:
        with transaction.atomic():
            tasdiq = services.yuklamani_tasdiqqa_yuborish(kafedra, yil, izoh)
            audit_yoz(
                AuditAmali.TASDIQ_YUBORILDI,
                (
                    f"{kafedra.nomi}: {yil}/{yil + 1} o'quv yili "
                    "yuklamasi tasdiqqa yuborildi."
                ),
                model_nomi="KafedraYuklamaTasdiq",
                obyekt_id=tasdiq.pk,
                request=request,
            )
            kafedra_yubordi_xabari(kafedra, yil)
        messages.success(request, "Yuklama o'quv bo'limiga tasdiqlash uchun yuborildi.")
    except ValidationError as e:
        messages.error(request, xato_matni(e))
    return redirect(f"{reverse('kafedra:dashboard')}?yil={yil}")


@require_POST
@kafedra_mudiri_talab
def taqsimot_nusxalash_view(request: HttpRequest) -> HttpResponse:
    kafedra = _boshqarayotgan_kafedra(request)
    assert kafedra is not None
    _, maqsad_yil = yilni_tanlash(request.POST.get("yil"))
    maqsad_yil = maqsad_yil or dashboard.joriy_akademik_yil()
    manba_yil = musbat_int_yoki_none(request.POST.get("manba_yil"))
    if manba_yil is None:
        messages.error(request, "Manba o'quv yilini tanlang.")
        return redirect(f"{reverse('kafedra:dashboard')}?yil={maqsad_yil}")
    try:
        natija = nusxalash.kafedra_taqsimotini_nusxalash(kafedra, manba_yil, maqsad_yil)
        audit_yoz(
            AuditAmali.TAHRIRLANDI,
            (
                f"{kafedra.nomi}: {manba_yil}/{manba_yil + 1} dan "
                f"{maqsad_yil}/{maqsad_yil + 1} ga {natija.yaratilgan_yuklamalar} ta "
                "yuklama nusxalandi."
            ),
            model_nomi="Yuklama",
            request=request,
        )
        messages.success(
            request,
            (
                f"{manba_yil}/{manba_yil + 1} yildan {natija.qamrab_olingan_fanlar} ta "
                f"fan bo'yicha {natija.yaratilgan_yuklamalar} ta yuklama ko'chirildi."
            ),
        )
    except ValidationError as e:
        messages.error(request, xato_matni(e))
    return redirect(f"{reverse('kafedra:dashboard')}?yil={maqsad_yil}")
