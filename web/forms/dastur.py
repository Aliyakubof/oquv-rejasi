"""O'qituvchining o'quv dastur topshirishi va AOH rad etishi uchun formalar."""

from django import forms
from django.core.files.uploadedfile import UploadedFile

from plans.uploads import zip_faylini_tekshir

MAX_DASTUR_HAJMI = 20 * 1024 * 1024  # 20 MB


class DasturTopshirishForm(forms.Form):
    fayl = forms.FileField(
        label="O'quv dastur (.docx)",
        widget=forms.ClearableFileInput(attrs={"accept": ".docx"}),
    )

    def clean_fayl(self) -> UploadedFile:
        fayl: UploadedFile = self.cleaned_data["fayl"]
        toza_nom = zip_faylini_tekshir(
            fayl,
            kutilgan_kengaytma=".docx",
            max_hajm=MAX_DASTUR_HAJMI,
            zarur_fayl="word/document.xml",
        )
        fayl.name = toza_nom
        return fayl


class DasturRadEtishForm(forms.Form):
    izoh = forms.CharField(
        label="Rad etish sababi",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
