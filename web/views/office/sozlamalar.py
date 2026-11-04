"""Office settings: institution name, teacher position norms and major classifier."""

from django.contrib import messages
from django.db.models import Count, ProtectedError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, TemplateView, UpdateView

from accounts.models import OqituvchiTuri, Universitet
from accounts.services import universitet_olish
from plans.models import TalimYonalishi
from web.forms.sozlamalar import (
    OqituvchiTuriForm,
    TalimYonalishiForm,
    UniversitetForm,
)
from web.mixins import OfficeAdminTalabMixin, office_admin_talab


class SozlamalarView(OfficeAdminTalabMixin, TemplateView):
    template_name = "web/office/sozlamalar/list.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        universitet = universitet_olish()
        context.update(
            {
                "universitet_form": UniversitetForm(instance=universitet),
                "lavozimlar": OqituvchiTuri.objects.annotate(
                    oqituvchilar_soni=Count("oqituvchilar")
                ).order_by("nomi"),
                "yonalishlar": TalimYonalishi.objects.order_by("kodi"),
            }
        )
        return context


@require_POST
@office_admin_talab
def universitet_saqlash(request: HttpRequest) -> HttpResponse:
    universitet = universitet_olish() or Universitet()
    form = UniversitetForm(request.POST, instance=universitet)
    if form.is_valid():
        form.save()
        messages.success(request, "Universitet rasmiy nomi saqlandi.")
    else:
        messages.error(request, "Universitet nomini tekshiring.")
    return redirect("office:sozlamalar")


class LavozimYangiView(OfficeAdminTalabMixin, CreateView):
    template_name = "web/office/sozlamalar/form.html"
    form_class = OqituvchiTuriForm
    success_url = reverse_lazy("office:sozlamalar")
    extra_context = {"sarlavha": "Yangi lavozim"}

    def form_valid(self, form: OqituvchiTuriForm) -> HttpResponse:
        messages.success(self.request, "Lavozim yaratildi.")
        return super().form_valid(form)


class LavozimTahrirView(OfficeAdminTalabMixin, UpdateView):
    template_name = "web/office/sozlamalar/form.html"
    form_class = OqituvchiTuriForm
    queryset = OqituvchiTuri.objects.all()
    success_url = reverse_lazy("office:sozlamalar")
    extra_context = {"sarlavha": "Lavozimni tahrirlash"}

    def form_valid(self, form: OqituvchiTuriForm) -> HttpResponse:
        messages.success(self.request, "Lavozim saqlandi.")
        return super().form_valid(form)


@require_POST
@office_admin_talab
def lavozim_ochirish(request: HttpRequest, pk: int) -> HttpResponse:
    lavozim = get_object_or_404(OqituvchiTuri, pk=pk)
    try:
        lavozim.delete()
        messages.success(request, f"{lavozim.nomi} lavozimi o'chirildi.")
    except ProtectedError:
        messages.error(
            request,
            f"{lavozim.nomi} lavozimida o'qituvchilar bor — "
            "avval ularning lavozimini o'zgartiring.",
        )
    return redirect("office:sozlamalar")


class YonalishYangiView(OfficeAdminTalabMixin, CreateView):
    template_name = "web/office/sozlamalar/form.html"
    form_class = TalimYonalishiForm
    success_url = reverse_lazy("office:sozlamalar")
    extra_context = {"sarlavha": "Yangi ta'lim yo'nalishi"}

    def form_valid(self, form: TalimYonalishiForm) -> HttpResponse:
        messages.success(self.request, "Ta'lim yo'nalishi yaratildi.")
        return super().form_valid(form)


class YonalishTahrirView(OfficeAdminTalabMixin, UpdateView):
    template_name = "web/office/sozlamalar/form.html"
    form_class = TalimYonalishiForm
    queryset = TalimYonalishi.objects.all()
    success_url = reverse_lazy("office:sozlamalar")
    extra_context = {"sarlavha": "Ta'lim yo'nalishini tahrirlash"}

    def form_valid(self, form: TalimYonalishiForm) -> HttpResponse:
        messages.success(self.request, "Ta'lim yo'nalishi saqlandi.")
        return super().form_valid(form)


@require_POST
@office_admin_talab
def yonalish_ochirish(request: HttpRequest, pk: int) -> HttpResponse:
    yonalish = get_object_or_404(TalimYonalishi, pk=pk)
    yonalish.delete()
    messages.success(request, f"{yonalish} o'chirildi.")
    return redirect("office:sozlamalar")
