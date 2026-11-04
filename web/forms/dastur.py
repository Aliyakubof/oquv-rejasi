"""Forms for teacher submission and AOH decline of an O'quv Dastur."""

from django import forms

MAX_DASTUR_HAJMI = 20 * 1024 * 1024  # 20 MB


class DasturTopshirishForm(forms.Form):
    fayl = forms.FileField(
        label="O'quv dastur (.docx)",
        widget=forms.ClearableFileInput(attrs={"accept": ".docx"}),
    )

    def clean_fayl(self) -> object:
        fayl = self.cleaned_data["fayl"]
        if not fayl.name.lower().endswith(".docx"):
            raise forms.ValidationError("Fayl .docx formatida bo'lishi kerak.")
        if fayl.size and fayl.size > MAX_DASTUR_HAJMI:
            raise forms.ValidationError("Fayl hajmi 20 MB dan oshmasligi kerak.")
        return fayl


class DasturRadEtishForm(forms.Form):
    izoh = forms.CharField(
        label="Rad etish sababi",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
