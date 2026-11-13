"""Forms for creating (via Excel upload) and correcting an o'quv reja."""

from zipfile import is_zipfile

from django import forms

from plans.models import OquvReja
from plans.services import eng_kop_kurs_ishi_talabasi
from plans.uploads import YuklashParametrlari, xavfsiz_fayl_nomi

MAX_REJA_HAJMI = 10 * 1024 * 1024  # 10 MB


class RejaImportForm(forms.Form):
    fayl = forms.FileField(
        label="Excel fayl (.xlsx)",
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}),
    )
    talabalar_soni = forms.IntegerField(label="Talabalar soni", min_value=1)
    guruhlar_soni = forms.IntegerField(label="Guruhlar soni", min_value=1)
    guruh_prefiksi = forms.CharField(
        label="Guruh prefiksi",
        required=False,
        max_length=20,
        help_text="Masalan: DI. Bo'sh qoldirilsa yo'nalish kodi ishlatiladi",
    )
    replace = forms.BooleanField(label="Mavjud rejani almashtirish", required=False)

    def clean_fayl(self) -> object:
        fayl = self.cleaned_data["fayl"]
        toza_nom = xavfsiz_fayl_nomi(getattr(fayl, "name", ""))
        if not toza_nom.lower().endswith(".xlsx"):
            raise forms.ValidationError("Fayl .xlsx formatida bo'lishi kerak.")
        if not fayl.size:
            raise forms.ValidationError("Bo'sh fayl yuklab bo'lmaydi.")
        if fayl.size > MAX_REJA_HAJMI:
            raise forms.ValidationError("Fayl hajmi 10 MB dan oshmasligi kerak.")
        try:
            haqiqiy_zip = is_zipfile(fayl)
        finally:
            fayl.seek(0)
        if not haqiqiy_zip:
            raise forms.ValidationError("Fayl .xlsx formatida emas yoki buzilgan.")
        fayl.name = toza_nom
        return fayl

    def parametrlar(self) -> YuklashParametrlari:
        return YuklashParametrlari(
            talabalar_soni=self.cleaned_data["talabalar_soni"],
            guruhlar_soni=self.cleaned_data["guruhlar_soni"],
            guruh_prefiksi=self.cleaned_data["guruh_prefiksi"],
            boshlanish_yili=None,
            replace=self.cleaned_data["replace"],
        )


class RejaTahrirForm(forms.ModelForm):
    class Meta:
        model = OquvReja
        fields = [
            "bilim_sohasi_kodi",
            "bilim_sohasi_nomi",
            "talim_sohasi_kodi",
            "talim_sohasi_nomi",
            "yonalish_kodi",
            "yonalish_nomi",
            "talim_shakli",
            "daraja",
            "talabalar_soni",
            "guruhlar_soni",
            "guruh_prefiksi",
        ]
        labels = {
            "bilim_sohasi_kodi": "Bilim sohasi kodi",
            "bilim_sohasi_nomi": "Bilim sohasi nomi",
            "talim_sohasi_kodi": "Ta'lim sohasi kodi",
            "talim_sohasi_nomi": "Ta'lim sohasi nomi",
            "yonalish_kodi": "Yo'nalish kodi",
            "yonalish_nomi": "Yo'nalish nomi",
            "talim_shakli": "Ta'lim shakli",
            "daraja": "Akademik daraja",
            "talabalar_soni": "Talabalar soni",
            "guruhlar_soni": "Guruhlar soni",
            "guruh_prefiksi": "Guruh prefiksi",
        }

    def clean_talabalar_soni(self) -> int | None:
        soni = self.cleaned_data.get("talabalar_soni")
        if soni is not None and soni < 1:
            raise forms.ValidationError("Talabalar soni kamida 1 bo'lishi kerak.")
        if self.instance.pk:
            eng_kop = eng_kop_kurs_ishi_talabasi(self.instance)
            if eng_kop and (soni is None or soni < eng_kop):
                raise forms.ValidationError(
                    f"Kurs ishiga allaqachon {eng_kop} ta talaba taqsimlangan."
                )
        return soni

    def clean_guruhlar_soni(self) -> int | None:
        soni = self.cleaned_data.get("guruhlar_soni")
        if soni is not None and soni < 1:
            raise forms.ValidationError("Guruhlar soni kamida 1 bo'lishi kerak.")
        return soni
