"""Mudir's own-department teacher list, workload detail and CRUD (kafedra locked)."""

from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from accounts.models import OqituvchiProfil, Rol
from plans import services
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


class KafedraOqituvchiListView(KafedraMudiriTalabMixin, YilTanlovMixin, TemplateView):
    template_name = "web/kafedra/oqituvchilar/list.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        holatlar = services.yuklama_kamomadi(self.yil, kafedra=self.kafedra)
        context.update(
            {
                "kafedra": self.kafedra,
                "holatlar": holatlar,
                "jami_yuklama": sum(h.jami_soat for h in holatlar),
                "jami_min": sum(h.min_soat for h in holatlar),
                "kamomadli_soni": sum(1 for h in holatlar if h.kamomad > 0),
            }
        )
        return context


class KafedraOqituvchiYuklamaView(KafedraMudiriTalabMixin, OqituvchiYuklamaAsosView):
    orqaga_url = "kafedra:oqituvchi_list"

    def profil_olish(self) -> OqituvchiProfil:
        return get_object_or_404(
            OqituvchiProfil.objects.toliq(),
            pk=self.kwargs["pk"],
            kafedra=self.kafedra,
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
