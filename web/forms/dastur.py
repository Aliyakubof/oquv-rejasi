"""Forms for teacher submission and AOH decline of an O'quv Dastur."""

from pathlib import Path

from django import forms
from django.core.files.uploadedfile import UploadedFile

MAX_DASTUR_HAJMI = 20 * 1024 * 1024  # 20 MB


class DasturTopshirishForm(forms.Form):
    fayl = forms.FileField(
        label="O'quv dastur (.docx)",
        widget=forms.ClearableFileInput(attrs={"accept": ".docx"}),
    )

    def clean_fayl(self) -> UploadedFile:
        fayl: UploadedFile = self.cleaned_data["fayl"]
        toza_nom = Path(fayl.name or "").name
        if not toza_nom.lower().endswith(".docx") or "\x00" in toza_nom:
            raise forms.ValidationError("Fayl .docx formatida bo'lishi kerak.")
        if not fayl.size:
            raise forms.ValidationError("Bo'sh fayl yuklab bo'lmaydi.")
        if fayl.size > MAX_DASTUR_HAJMI:
            raise forms.ValidationError("Fayl hajmi 20 MB dan oshmasligi kerak.")
        fayl.name = toza_nom
        return fayl


class DasturRadEtishForm(forms.Form):
    izoh = forms.CharField(
        label="Rad etish sababi",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
