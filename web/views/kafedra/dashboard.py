"""Kafedra head's dashboard: own-department demand and delegation rows."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from plans import dashboard, delegation, services
from plans.audit import audit_yoz
from plans.dashboard import yilni_tanlash
from plans.models import AuditAmali
from web.mixins import (
    KafedraMudiriTalabMixin,
    YilTanlovMixin,
    _boshqarayotgan_kafedra,
    xato_matni,
)


class KafedraDashboardView(KafedraMudiriTalabMixin, YilTanlovMixin, TemplateView):
    template_name = "web/kafedra/dashboard.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        tasdiq = services.kafedra_tasdiq_holati(self.kafedra, self.yil)
        context.update(
            {
                "kafedra": self.kafedra,
                "tasdiq": tasdiq,
                "qulflangan": services.kafedra_yuklama_qulflanganmi(
                    self.kafedra, self.yil
                ),
                "stat": dashboard.statlarni_hisoblash(
                    services.kafedra_taqsimoti(self.kafedra, self.yil)
                ),
                "fs_satrlar": delegation.kafedra_fs_satrlari(self.kafedra, self.yil),
            }
        )
        return context


@require_POST
def tasdiqqa_yuborish_view(request: HttpRequest) -> HttpResponse:
    kafedra = _boshqarayotgan_kafedra(request)
    if not kafedra:
        messages.error(request, "Kafedra topilmadi.")
        return redirect("kafedra:dashboard")
    _, yil = yilni_tanlash(request.POST.get("yil"))
    yil = yil or dashboard.joriy_akademik_yil()
    izoh = request.POST.get("izoh", "").strip()
    try:
        tasdiq = services.yuklamani_tasdiqqa_yuborish(kafedra, yil, izoh)
        audit_yoz(
            AuditAmali.TASDIQ_YUBORILDI,
            f"{kafedra.nomi}: {yil}/{yil + 1} o'quv yili yuklamasi tasdiqqa yuborildi.",
            model_nomi="KafedraYuklamaTasdiq",
            obyekt_id=tasdiq.pk,
            request=request,
        )
        messages.success(request, "Yuklama o'quv bo'limiga tasdiqlash uchun yuborildi.")
    except ValidationError as e:
        messages.error(request, xato_matni(e))
    return redirect(f"{reverse('kafedra:dashboard')}?yil={yil}")
