"""Delegation forms: each maps one Yuklama shape onto model validation.

ModelForm._post_clean runs Yuklama.full_clean(), so every model rule
(variant selected, hours exist, guruh belongs to the reja, kurs-ishi
capacity, DB shape constraints) surfaces as a form error.
"""

from django import forms

from accounts.models import Department, OqituvchiProfil
from plans.models import PER_GURUH_TURLAR, FanSemestr, SoatTuri, Yuklama


class YuklamaAsosForm(forms.ModelForm):
    class Meta:
        model = Yuklama
        fields = ["oqituvchi"]

    def __init__(
        self,
        fan_semestr: FanSemestr,
        kafedra: Department,
        *args: object,
        **kwargs: object,
    ):
        super().__init__(*args, **kwargs)
        self.instance.fan_semestr = fan_semestr
        self.fields["oqituvchi"].queryset = (
            OqituvchiProfil.objects.kafedrada(kafedra)
            .bilan_foydalanuvchi()
            .filter(foydalanuvchi__is_active=True)
        )

    def _get_validation_exclusions(self) -> set[str]:
        # fan_semestr/tur are set programmatically; keep them in full_clean so
        # the shape constraints (uniq_guruh_yuklama, chk_yuklama_shakl) raise
        # form errors instead of DB IntegrityError.
        return super()._get_validation_exclusions() - {
            "fan_semestr",
            "tur",
            "guruh",
            "talabalar_soni",
        }


class MaruzaYuklamaForm(YuklamaAsosForm):
    def __init__(self, *args: object, **kwargs: object):
        super().__init__(*args, **kwargs)
        self.instance.tur = SoatTuri.MARUZA


class GuruhYuklamaForm(YuklamaAsosForm):
    tur = forms.ChoiceField(
        choices=[(t, t) for t in PER_GURUH_TURLAR], label="Mashg'ulot turi"
    )

    class Meta(YuklamaAsosForm.Meta):
        fields = ["oqituvchi", "guruh"]

    def __init__(self, *args: object, **kwargs: object):
        super().__init__(*args, **kwargs)
        self.fields[
            "guruh"
        ].queryset = self.instance.fan_semestr.variant.fan.reja.guruhlar.all()
        self.fields["guruh"].required = True

    def clean(self) -> dict[str, object]:
        cleaned = super().clean()
        if cleaned.get("tur"):
            self.instance.tur = cleaned["tur"]
        return cleaned


class KursIshiYuklamaForm(YuklamaAsosForm):
    class Meta(YuklamaAsosForm.Meta):
        fields = ["oqituvchi", "talabalar_soni"]

    def __init__(self, *args: object, **kwargs: object):
        super().__init__(*args, **kwargs)
        self.instance.tur = SoatTuri.KURS_ISHI
        self.fields["talabalar_soni"].required = True
