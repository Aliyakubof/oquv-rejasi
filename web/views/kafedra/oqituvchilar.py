"""Mudir's own-department teacher list, workload detail and CRUD (kafedra locked)."""

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View
from django.views.generic import TemplateView

from accounts.models import OqituvchiProfil, Rol
from plans import dashboard, services
from plans.dashboard import yilni_tanlash
from plans.shakl1_doc import shakl1_docx_render
from web.forms.oqituvchi import (
    KafedraOqituvchiTahrirForm,
    KafedraOqituvchiYaratishForm,
)
from web.mixins import KafedraMudiriTalabMixin, YilTanlovMixin
from web.views.oqituvchi_base import (
    OqituvchiTahrirAsosView,
    OqituvchiYangiAsosView,
    OqituvchiYuklamaAsosView,
)


def _kafedra_oqit_mosmi(
    holat: services.YuklamaHolati, q: str, faqat_kamomad: bool
) -> bool:
    if faqat_kamomad and holat.kamomad <= 0:
        return False
    if not q:
        return True
    o = holat.oqituvchi
    foy = o.foydalanuvchi
    matn = f"{o} {foy.last_name} {foy.first_name} {foy.telefon} {o.turi.nomi}".lower()
    return q.lower() in matn


class KafedraOqituvchiListView(KafedraMudiriTalabMixin, YilTanlovMixin, TemplateView):
    template_name = "web/kafedra/oqituvchilar/list.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        barcha = services.yuklama_kamomadi(self.yil, kafedra=self.kafedra)
        q = self.request.GET.get("q", "").strip()
        faqat_kamomad = self.request.GET.get("kamomad") == "1"
        filtrlangan = [h for h in barcha if _kafedra_oqit_mosmi(h, q, faqat_kamomad)]
        page_obj = Paginator(filtrlangan, 30).get_page(self.request.GET.get("page"))
        paramlar: dict[str, str] = {"yil": str(self.yil)}
        if q:
            paramlar["q"] = q
        if faqat_kamomad:
            paramlar["kamomad"] = "1"
        context.update(
            {
                "kafedra": self.kafedra,
                "holatlar": page_obj.object_list,
                "page_obj": page_obj,
                "oqituvchilar_soni": len(barcha),
                "qidiruv_q": q,
                "faqat_kamomad": faqat_kamomad,
                "query_prefix": urlencode(paramlar),
                "jami_yuklama": sum(h.jami_soat for h in barcha),
                "jami_min": sum(h.min_soat for h in barcha),
                "kamomadli_soni": sum(1 for h in barcha if h.kamomad > 0),
            }
        )
        return context


class KafedraOqituvchiYuklamaView(KafedraMudiriTalabMixin, OqituvchiYuklamaAsosView):
    orqaga_url = "kafedra:oqituvchi_list"
    docx_url_name = "kafedra:oqituvchi_shakl1_docx"

    def profil_olish(self) -> OqituvchiProfil:
        return get_object_or_404(
            OqituvchiProfil.objects.toliq(),
            pk=self.kwargs["pk"],
            kafedra=self.kafedra,
        )


class KafedraOqituvchiShakl1DocxView(KafedraMudiriTalabMixin, View):
    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        profil = get_object_or_404(
            OqituvchiProfil.objects.toliq(),
            pk=pk,
            kafedra=self.kafedra,
        )
        _, yil = yilni_tanlash(request.GET.get("yil"))
        yil = yil or dashboard.joriy_akademik_yil()
        return FileResponse(
            shakl1_docx_render(profil, yil),
            as_attachment=True,
            filename=f"1shakl_{profil.pk}_{yil}_{yil + 1}.docx",
        )


class KafedraOqituvchiYangiView(KafedraMudiriTalabMixin, OqituvchiYangiAsosView):
    template_name = "web/kafedra/oqituvchilar/form.html"
    form_class = KafedraOqituvchiYaratishForm
    success_url_name = "kafedra:oqituvchi_list"

    def get_form_kwargs(self) -> dict[str, object]:
        kwargs = super().get_form_kwargs()
        kwargs["kafedra"] = self.kafedra
        return kwargs


class KafedraOqituvchiTahrirView(KafedraMudiriTalabMixin, OqituvchiTahrirAsosView):
    template_name = "web/kafedra/oqituvchilar/form.html"
    form_class = KafedraOqituvchiTahrirForm
    success_url_name = "kafedra:oqituvchi_list"

    def profil_olish(self) -> OqituvchiProfil:
        qs = OqituvchiProfil.objects.bilan_foydalanuvchi().filter(kafedra=self.kafedra)
        if self.request.user.rol != Rol.SUPERADMIN:
            qs = qs.exclude(foydalanuvchi__rol__in=(Rol.OFFICE_ADMIN, Rol.SUPERADMIN))
        return get_object_or_404(qs, pk=self.kwargs["pk"])
