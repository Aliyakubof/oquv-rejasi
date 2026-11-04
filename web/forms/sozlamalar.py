"""Forms for managing institution name, position norms and major classifier."""

from django import forms

from accounts.models import OqituvchiTuri, Universitet
from plans.models import TalimYonalishi


class UniversitetForm(forms.ModelForm):
    class Meta:
        model = Universitet
        fields = ["rasmiy_nomi"]
        labels = {"rasmiy_nomi": "Universitet rasmiy nomi"}


class OqituvchiTuriForm(forms.ModelForm):
    class Meta:
        model = OqituvchiTuri
        fields = ["nomi", "min_soat"]
        labels = {
            "nomi": "Lavozim nomi",
            "min_soat": "Minimal yillik yuklama (soat)",
        }


class TalimYonalishiForm(forms.ModelForm):
    class Meta:
        model = TalimYonalishi
        fields = [
            "kodi",
            "nomi",
            "bilim_sohasi_kodi",
            "bilim_sohasi_nomi",
            "talim_sohasi_kodi",
            "talim_sohasi_nomi",
        ]
        labels = {
            "kodi": "Yo'nalish kodi",
            "nomi": "Yo'nalish nomi",
            "bilim_sohasi_kodi": "Bilim sohasi kodi",
            "bilim_sohasi_nomi": "Bilim sohasi nomi",
            "talim_sohasi_kodi": "Ta'lim sohasi kodi",
            "talim_sohasi_nomi": "Ta'lim sohasi nomi",
        }
