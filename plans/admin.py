from django import forms
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from plans.models import (
    DasturTopshirish,
    Fan,
    FanSemestr,
    FanVariant,
    Guruh,
    OquvReja,
    TalimYonalishi,
    Yuklama,
)
from plans.services import fan_semestr_talabi, guruhlarni_sinxronlash


class GuruhInline(admin.TabularInline):
    model = Guruh
    fields = ("raqam", "nomi")
    readonly_fields = ("raqam", "nomi")
    extra = 0
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: object = None) -> bool:
        # Groups are synced from guruhlar_soni, not entered by hand.
        return False


@admin.register(OquvReja)
class OquvRejaAdmin(admin.ModelAdmin):
    list_display = (
        "yonalish_kodi",
        "yonalish_nomi",
        "bilim_sohasi_kodi",
        "talim_sohasi_kodi",
        "boshlanish_yili",
        "talim_shakli",
        "talabalar_soni",
        "guruhlar_soni",
    )
    list_filter = (
        "boshlanish_yili",
        "talim_shakli",
        "bilim_sohasi_kodi",
        "talim_sohasi_kodi",
    )
    search_fields = ("yonalish_kodi", "yonalish_nomi")
    readonly_fields = ("manba_fayl", "import_vaqti")
    inlines = [GuruhInline]

    def save_model(
        self, request: HttpRequest, obj: OquvReja, form: forms.ModelForm, change: bool
    ) -> None:
        super().save_model(request, obj, form, change)
        guruhlarni_sinxronlash(obj)


@admin.register(TalimYonalishi)
class TalimYonalishiAdmin(admin.ModelAdmin):
    list_display = ("kodi", "nomi", "bilim_sohasi_kodi", "talim_sohasi_kodi")
    search_fields = ("kodi", "nomi")


class FanForm(forms.ModelForm):
    class Meta:
        model = Fan
        fields = "__all__"

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        variantlar = (
            self.instance.variantlar.all()
            if self.instance.pk
            else FanVariant.objects.none()
        )
        self.fields["tanlangan_variant"].queryset = variantlar


class FanVariantInline(admin.TabularInline):
    model = FanVariant
    fields = (
        "kodi",
        "nomi",
        "kafedra",
        "auditoriya_soat",
        "maruza_soat",
        "amaliyot_soat",
        "laboratoriya_soat",
        "seminar_soat",
        "kurs_ishi_soat",
    )
    extra = 0


class TanlovHolatiFilter(admin.SimpleListFilter):
    title = "tanlov holati"
    parameter_name = "tanlov_holati"

    def lookups(self, request: HttpRequest, model_admin: admin.ModelAdmin) -> list:
        return [("kutilmoqda", "Kutilmoqda"), ("tanlangan", "Tanlangan")]

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        if self.value() == "kutilmoqda":
            return queryset.tanlov_kutilmoqda()
        if self.value() == "tanlangan":
            return queryset.tanlov_tanlangan()
        return queryset


@admin.register(Fan)
class FanAdmin(admin.ModelAdmin):
    form = FanForm
    list_display = (
        "raqam",
        "turi",
        "effektiv_nomi",
        "jami_soat",
        "effektiv_kafedra",
        "tanlov_holati",
    )
    list_filter = ("reja", "turi", TanlovHolatiFilter)
    search_fields = ("raqam", "variantlar__nomi", "variantlar__kodi")
    inlines = [FanVariantInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return (
            super()
            .get_queryset(request)
            .select_related("tanlangan_variant__kafedra", "reja")
        )

    @admin.display(description="Nomi")
    def effektiv_nomi(self, obj: Fan) -> str:
        return obj.tanlangan_variant.nomi if obj.tanlangan_variant else "—"

    @admin.display(description="Kafedra")
    def effektiv_kafedra(self, obj: Fan) -> str:
        variant = obj.tanlangan_variant
        return str(variant.kafedra) if variant and variant.kafedra else "—"

    @admin.display(description="Tanlov", boolean=True)
    def tanlov_holati(self, obj: Fan) -> bool:
        return obj.tanlangan_variant is not None


class FanSemestrInline(admin.TabularInline):
    model = FanSemestr
    fields = (
        "semestr",
        "kredit",
        "haftalik_soat",
        "maruza_soat",
        "amaliyot_soat",
        "laboratoriya_soat",
        "seminar_soat",
        "kurs_ishi_bor",
    )
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: object = None) -> bool:
        # Materialized by import_reja; edits belong in the source sheet.
        return False


@admin.register(FanVariant)
class FanVariantAdmin(admin.ModelAdmin):
    list_display = ("kodi", "nomi", "fan", "kafedra")
    list_filter = ("kafedra", "fan__reja")
    list_select_related = ("fan__reja", "kafedra")
    search_fields = ("kodi", "nomi")
    inlines = [FanSemestrInline]


@admin.register(FanSemestr)
class FanSemestrAdmin(admin.ModelAdmin):
    list_display = ("variant", "semestr", "talab", "taqsimlangan", "qoldiq")
    list_filter = ("semestr", "variant__kafedra", "variant__fan__reja")
    search_fields = ("variant__nomi", "variant__kodi")

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return (
            super()
            .get_queryset(request)
            .select_related("variant__fan__reja")
            .prefetch_related("yuklamalar")
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False

    @staticmethod
    def _jamlar(obj: FanSemestr) -> dict[str, int]:
        jamlar: dict[str, int] = {}
        for yuklama in obj.yuklamalar.all():
            jamlar[yuklama.tur] = jamlar.get(yuklama.tur, 0) + yuklama.soat
        return jamlar

    @admin.display(description="Talab")
    def talab(self, obj: FanSemestr) -> str:
        talab = fan_semestr_talabi(obj, obj.variant.fan.reja)
        return self._soat_matni({t: s for t, s in talab.items()})

    @admin.display(description="Taqsimlangan")
    def taqsimlangan(self, obj: FanSemestr) -> str:
        jamlar = self._jamlar(obj)
        return self._soat_matni(jamlar)

    @admin.display(description="Qoldiq")
    def qoldiq(self, obj: FanSemestr) -> str:
        talab = fan_semestr_talabi(obj, obj.variant.fan.reja)
        jamlar = self._jamlar(obj)
        qoldiq = {
            tur: None if soat is None else soat - jamlar.get(tur, 0)
            for tur, soat in talab.items()
        }
        return self._soat_matni(qoldiq)

    @staticmethod
    def _soat_matni(soatlar: dict[str, int | None]) -> str:
        if not soatlar:
            return "—"
        return ", ".join(
            f"{tur.capitalize()}: {'?' if soat is None else soat}"
            for tur, soat in soatlar.items()
        )


@admin.register(Guruh)
class GuruhAdmin(admin.ModelAdmin):
    list_display = ("nomi", "reja")
    list_filter = ("reja",)
    # Required for Yuklama.guruh autocomplete.
    search_fields = ("nomi",)


@admin.register(Yuklama)
class YuklamaAdmin(admin.ModelAdmin):
    list_display = (
        "fan_semestr",
        "tur",
        "oqituvchi",
        "guruh",
        "talabalar_soni",
        "soat",
    )
    list_filter = ("tur", "oqituvchi__kafedra", "fan_semestr__variant__fan__reja")
    autocomplete_fields = ("fan_semestr", "oqituvchi", "guruh")

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return (
            super()
            .get_queryset(request)
            .select_related(
                "fan_semestr__variant__fan__reja",
                "oqituvchi__foydalanuvchi",
                "guruh",
            )
        )


@admin.register(DasturTopshirish)
class DasturTopshirishAdmin(admin.ModelAdmin):
    list_display = (
        "variant",
        "urinish_raqami",
        "oqituvchi",
        "holat",
        "yuborilgan_vaqt",
        "korib_chiqilgan_vaqt",
        "korib_chiqqan",
    )
    list_filter = ("holat",)
    search_fields = (
        "variant__nomi",
        "variant__kodi",
        "oqituvchi__foydalanuvchi__first_name",
    )
    autocomplete_fields = ("variant", "oqituvchi", "korib_chiqqan")

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return (
            super()
            .get_queryset(request)
            .select_related(
                "variant__fan__reja", "oqituvchi__foydalanuvchi", "korib_chiqqan"
            )
        )
