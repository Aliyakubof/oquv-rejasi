"""Printable coverage report and Excel export for one kafedra's teachers."""

from django.http import FileResponse, HttpRequest, HttpResponse
from django.views import View
from django.views.generic import TemplateView

from plans import dashboard, eksport, services
from plans.dashboard import yilni_tanlash
from plans.shakl1_doc import shakl1_zip_yarat
from web.mixins import KafedraMudiriTalabMixin, YilTanlovMixin


class HisobotView(KafedraMudiriTalabMixin, YilTanlovMixin, TemplateView):
    template_name = "web/kafedra/hisobot.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        holatlar = services.yuklama_kamomadi(self.yil, kafedra=self.kafedra)
        context.update(
            {
                "kafedra": self.kafedra,
                "holatlar": holatlar,
                "jami_yuklama": sum(h.jami_soat for h in holatlar),
                "jami_min": sum(h.min_soat for h in holatlar),
            }
        )
        return context


class HisobotExcelView(KafedraMudiriTalabMixin, View):
    def get(self, request: HttpRequest) -> HttpResponse:
        _, yil = yilni_tanlash(request.GET.get("yil"))
        yil = yil or dashboard.joriy_akademik_yil()
        fayl_nomi = f"kafedra_hisobot_{yil}_{yil + 1}.xlsx"
        return FileResponse(
            eksport.oqituvchilar_excel(yil, kafedra=self.kafedra),
            as_attachment=True,
            filename=fayl_nomi,
        )


class HisobotZipView(KafedraMudiriTalabMixin, View):
    def get(self, request: HttpRequest) -> HttpResponse:
        _, yil = yilni_tanlash(request.GET.get("yil"))
        yil = yil or dashboard.joriy_akademik_yil()
        return FileResponse(
            shakl1_zip_yarat(yil, kafedra=self.kafedra),
            as_attachment=True,
            filename=f"kafedra_1shakl_{yil}_{yil + 1}.zip",
        )
