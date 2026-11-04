"""Teacher's own workload table for the selected academic year."""

from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import TemplateView

from plans import services
from plans.dastur.service import dastur_egasimi, dastur_render
from plans.dastur.topshirish import dastur_topshirish
from plans.models import DasturTopshirish, FanVariant, SoatTuri, Yuklama
from web.forms.dastur import DasturTopshirishForm
from web.mixins import OqituvchiTalabMixin, YilTanlovMixin


class MenYuklamalarimView(OqituvchiTalabMixin, YilTanlovMixin, TemplateView):
    template_name = "web/men/yuklamalar.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        profil = getattr(self.request.user, "oqituvchi_profil", None)
        context["profil"] = profil
        if profil is None:
            return context
        yuklamalar = list(
            Yuklama.objects.filter(oqituvchi=profil)
            .akademik_yilda(self.yil)
            .select_related("fan_semestr__variant__fan__reja", "guruh")
            .prefetch_related(
                Prefetch(
                    "fan_semestr__variant__dastur_topshirishlari",
                    queryset=DasturTopshirish.objects.select_related("korib_chiqqan"),
                )
            )
            .order_by("fan_semestr__variant__nomi", "fan_semestr__semestr", "tur")
        )
        korilgan_variantlar: set[int] = set()
        for yuklama in yuklamalar:
            vid = yuklama.fan_semestr.variant_id
            yuklama.dastur_korsatilsin = (
                yuklama.tur == SoatTuri.MARUZA and vid not in korilgan_variantlar
            )
            if yuklama.dastur_korsatilsin:
                korilgan_variantlar.add(vid)
        context.update(
            {
                "yuklamalar": yuklamalar,
                "tur_jami": _tur_jami(yuklamalar),
                "jami_soat": services.oqituvchi_yillik_yuklamasi(profil, self.yil),
            }
        )
        return context


class MenOquvDasturView(OqituvchiTalabMixin, View):
    def get(self, request: HttpRequest, variant_id: int) -> HttpResponse:
        variant = get_object_or_404(FanVariant, pk=variant_id)
        profil = getattr(request.user, "oqituvchi_profil", None)
        if profil is None or not dastur_egasimi(variant, profil):
            return HttpResponseForbidden(
                "Bu fan dasturini faqat ma'ruza egasi yaratishi mumkin."
            )
        prefiks = (variant.kodi or variant.nomi).replace("/", "_").replace("\\", "_")
        return FileResponse(
            dastur_render(variant),
            as_attachment=True,
            filename=f"{prefiks}_oquv_dastur.docx",
        )


class MenDasturTopshirishView(OqituvchiTalabMixin, View):
    def post(self, request: HttpRequest, variant_id: int) -> HttpResponse:
        variant = get_object_or_404(FanVariant, pk=variant_id)
        profil = getattr(request.user, "oqituvchi_profil", None)
        if profil is None or not dastur_egasimi(variant, profil):
            return HttpResponseForbidden(
                "Bu fan dasturini faqat ma'ruza egasi topshirishi mumkin."
            )
        form = DasturTopshirishForm(request.POST, request.FILES)
        xato = None
        if form.is_valid():
            try:
                dastur_topshirish(variant, profil, form.cleaned_data["fayl"])
            except ValidationError as e:
                xato = " ".join(e.messages)
        else:
            xato = " ".join(x for xs in form.errors.values() for x in xs)
        return _dastur_javobi(request, variant, xato=xato)


class MenDasturTarixiView(OqituvchiTalabMixin, View):
    def get(self, request: HttpRequest, variant_id: int) -> HttpResponse:
        variant = get_object_or_404(FanVariant, pk=variant_id)
        profil = getattr(request.user, "oqituvchi_profil", None)
        if profil is None or not dastur_egasimi(variant, profil):
            return HttpResponseForbidden(
                "Bu fan dasturini faqat ma'ruza egasi ko'rishi mumkin."
            )
        return render(request, "web/men/_dastur_panel.html", _panel_kontekst(variant))


class MenDasturFaylView(OqituvchiTalabMixin, View):
    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        topshirish = get_object_or_404(
            DasturTopshirish.objects.select_related("variant"), pk=pk
        )
        profil = getattr(request.user, "oqituvchi_profil", None)
        if profil is None or not dastur_egasimi(topshirish.variant, profil):
            return HttpResponseForbidden(
                "Bu faylni faqat ma'ruza egasi ko'rishi mumkin."
            )
        try:
            return FileResponse(topshirish.fayl.open("rb"), as_attachment=True)
        except FileNotFoundError as exc:
            raise Http404("Fayl topilmadi.") from exc


def _panel_kontekst(
    variant: FanVariant, *, xato: str | None = None
) -> dict[str, object]:
    urinishlar = list(variant.dastur_topshirishlari.select_related("korib_chiqqan"))
    return {
        "variant": variant,
        "urinishlar": urinishlar,
        "joriy": urinishlar[0] if urinishlar else None,
        "xato": xato,
    }


def _dastur_javobi(
    request: HttpRequest, variant: FanVariant, *, xato: str | None = None
) -> HttpResponse:
    return render(
        request,
        "web/men/_dastur_qator_va_panel.html",
        _panel_kontekst(variant, xato=xato),
    )


def _tur_jami(yuklamalar: list[Yuklama]) -> list[tuple[str, int]]:
    jami: dict[str, int] = defaultdict(int)
    for yuklama in yuklamalar:
        jami[yuklama.tur] += yuklama.soat
    return [(SoatTuri(tur).label, soat) for tur, soat in jami.items()]
