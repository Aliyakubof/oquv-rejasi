"""Shared base views and helpers for teacher CRUD across office and kafedra."""

from django.contrib import messages
from django.forms import Form
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import FormView, TemplateView

from accounts.models import OqituvchiProfil
from plans import dashboard
from plans.audit import audit_yoz
from plans.dashboard import yilni_tanlash
from plans.models import AuditAmali, SoatTuri
from plans.shakl1 import (
    oqituvchi_yuklamalari,
)
from plans.shakl1 import (
    shakl1_satrlarini_yigish as _shakl1_satrlarini_yigish,
)


def oqituvchi_yuklama_konteksti(
    profil: OqituvchiProfil, sorov_yil: str | None, *, orqaga_url: str
) -> dict[str, object]:
    """Shared workload sheet context for a single teacher."""
    yillar, yil = yilni_tanlash(sorov_yil)
    yil = yil or dashboard.joriy_akademik_yil()
    yuklamalar = oqituvchi_yuklamalari(profil, yil)
    shakl1_satrlar, tur_jami = _shakl1_satrlarini_yigish(yuklamalar)
    jami_soat = sum(y.soat for y in yuklamalar)
    return {
        "profil": profil,
        "yillar": yillar,
        "yil": yil,
        "yuklamalar": yuklamalar,
        "shakl1_satrlar": shakl1_satrlar,
        "jami_soat": jami_soat,
        "kamomad": max(0, profil.turi.min_soat - jami_soat),
        "tur_jami": [(SoatTuri(t).label, s) for t, s in tur_jami.items()],
        "orqaga_url": orqaga_url,
    }


class OqituvchiYuklamaAsosView(TemplateView):
    template_name = "web/parts/oqituvchi_yuklama.html"
    orqaga_url: str = ""
    docx_url_name: str = ""

    def profil_olish(self) -> OqituvchiProfil:
        raise NotImplementedError

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        profil = self.profil_olish()
        malumot = oqituvchi_yuklama_konteksti(
            profil,
            self.request.GET.get("yil"),
            orqaga_url=self.orqaga_url,
        )
        context.update(malumot)
        if self.docx_url_name:
            base_url = reverse(self.docx_url_name, args=[profil.pk])
            context["docx_url"] = f"{base_url}?yil={malumot['yil']}"
        return context


class OqituvchiYangiAsosView(FormView):
    success_url_name: str = ""

    def form_valid(self, form: Form) -> HttpResponse:
        profil = form.saqlash()  # type: ignore[attr-defined]
        audit_yoz(
            AuditAmali.YARATILDI,
            f"O'qituvchi yaratildi: {profil} ({profil.kafedra.nomi}).",
            obyekt=profil,
            request=self.request,
        )
        messages.success(self.request, f"{profil} yaratildi.")
        return redirect(self.success_url_name)


class OqituvchiTahrirAsosView(FormView):
    success_url_name: str = ""

    def profil_olish(self) -> OqituvchiProfil:
        return get_object_or_404(
            OqituvchiProfil.objects.bilan_foydalanuvchi(),
            pk=self.kwargs["pk"],
        )

    def get_form_kwargs(self) -> dict[str, object]:
        kwargs = super().get_form_kwargs()
        kwargs["profil"] = self.profil_olish()
        return kwargs

    def form_valid(self, form: Form) -> HttpResponse:
        form.saqlash()  # type: ignore[attr-defined]
        profil = form.profil  # type: ignore[attr-defined]
        audit_yoz(
            AuditAmali.TAHRIRLANDI,
            f"O'qituvchi ma'lumotlari tahrirlandi: {profil} ({profil.kafedra.nomi}).",
            obyekt=profil,
            request=self.request,
        )
        messages.success(self.request, f"{profil} saqlandi.")
        return redirect(self.success_url_name)
