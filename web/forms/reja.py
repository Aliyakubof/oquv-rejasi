"""O'quv rejani Excel orqali yuklash va tahrirlash formalari."""

from django import forms
from django.core.files.uploadedfile import UploadedFile

from plans.models import OquvReja
from plans.services import (
    eng_katta_band_guruh,
    eng_kop_kurs_ishi_talabasi,
    reja_qulflanganmi,
)
from plans.uploads import YuklashParametrlari, zip_faylini_tekshir

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

    def clean_fayl(self) -> UploadedFile:
        fayl: UploadedFile = self.cleaned_data["fayl"]
        toza_nom = zip_faylini_tekshir(
            fayl,
            kutilgan_kengaytma=".xlsx",
            max_hajm=MAX_REJA_HAJMI,
            zarur_fayl="xl/workbook.xml",
        )
        fayl.name = toza_nom
        return fayl

    def parametrlar(self) -> YuklashParametrlari:
        return YuklashParametrlari(
            talabalar_soni=self.cleaned_data["talabalar_soni"],
            guruhlar_soni=self.cleaned_data["guruhlar_soni"],
            guruh_prefiksi=self.cleaned_data["guruh_prefiksi"],
            boshlanish_yili=None,
            almashtirish=self.cleaned_data["replace"],
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
        if self.instance.pk:
            eng_katta = eng_katta_band_guruh(self.instance)
            if eng_katta and (soni is None or soni < eng_katta):
                raise forms.ValidationError(
                    f"{eng_katta}-guruhga allaqachon o'qituvchi "
                    "yuklamasi biriktirilgan."
                )
        return soni

    def clean(self) -> dict[str, object]:
        cleaned = super().clean()
        if self.instance.pk and (
            cleaned.get("talabalar_soni") != self.instance.talabalar_soni
            or cleaned.get("guruhlar_soni") != self.instance.guruhlar_soni
        ):
            if reja_qulflanganmi(self.instance):
                raise forms.ValidationError(
                    "Ushbu o'quv reja bo'yicha kafedra yuklamasi qulflangan — "
                    "talabalar yoki guruhlar sonini o'zgartirishdan oldin "
                    "tasdiqni qaytaring."
                )
        return cleaned
