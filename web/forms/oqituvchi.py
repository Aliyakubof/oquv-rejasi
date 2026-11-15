"""O'qituvchi qo'shish/tahrirlash formalari (saqlash mantiqi accounts.services da)."""

from django import forms
from django.contrib.auth import password_validation

from accounts.models import Department, Foydalanuvchi, OqituvchiProfil, OqituvchiTuri
from accounts.phone import telefonni_normallashtir, validate_uzbek_phone
from accounts.services import oqituvchi_yangilash, oqituvchi_yaratish


class OqituvchiAsosForm(forms.Form):
    telefon = forms.CharField(
        label="Telefon raqam",
        widget=forms.TextInput(attrs={"placeholder": "+998901234567"}),
    )
    first_name = forms.CharField(label="Ismi", max_length=150)
    last_name = forms.CharField(label="Familiyasi", max_length=150)
    kafedra = forms.ModelChoiceField(
        label="Kafedra", queryset=Department.objects.order_by("nomi")
    )
    turi = forms.ModelChoiceField(
        label="Lavozim", queryset=OqituvchiTuri.objects.order_by("nomi")
    )

    profil: OqituvchiProfil | None = None

    def clean_telefon(self) -> str:
        telefon = telefonni_normallashtir(self.cleaned_data["telefon"])
        validate_uzbek_phone(telefon)
        boshqalar = Foydalanuvchi.objects.filter(telefon=telefon)
        if self.profil is not None:
            boshqalar = boshqalar.exclude(pk=self.profil.foydalanuvchi_id)
        if boshqalar.exists():
            raise forms.ValidationError("Bu telefon raqam allaqachon ro'yxatda.")
        return telefon

    def clean_kafedra(self) -> Department:
        kafedra: Department = self.cleaned_data["kafedra"]
        if (
            self.profil is not None
            and self.profil.kafedra_id != kafedra.pk
            and self.profil.yuklamalar.exists()
        ):
            raise forms.ValidationError(
                "O'qituvchiga joriy kafedrada yuklama biriktirilgan. "
                "Boshqa kafedraga o'tkazishdan oldin yuklamalarni bekor qiling."
            )
        return kafedra


class OqituvchiYaratishForm(OqituvchiAsosForm):
    parol = forms.CharField(label="Parol", widget=forms.PasswordInput)

    def clean_parol(self) -> str:
        parol = self.cleaned_data["parol"]
        vaqtincha = Foydalanuvchi(
            telefon=self.cleaned_data.get("telefon", ""),
            first_name=self.cleaned_data.get("first_name", ""),
            last_name=self.cleaned_data.get("last_name", ""),
        )
        password_validation.validate_password(parol, user=vaqtincha)
        return parol

    def saqlash(self) -> OqituvchiProfil:
        return oqituvchi_yaratish(
            telefon=self.cleaned_data["telefon"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            parol=self.cleaned_data["parol"],
            kafedra=self.cleaned_data["kafedra"],
            turi=self.cleaned_data["turi"],
        )


class KafedraQulflanganMixin:
    """Kafedra mudiri formasi uchun mixin: kafedrani o'z kafedrasiga bog'lab qo'yadi."""

    kafedra_qiymati: Department

    def _kafedrani_qulflash(self) -> None:
        if "kafedra" in self.fields:
            del self.fields["kafedra"]

    def clean(self) -> dict[str, object]:
        cleaned = super().clean()
        cleaned["kafedra"] = self.kafedra_qiymati
        return cleaned


class KafedraOqituvchiYaratishForm(KafedraQulflanganMixin, OqituvchiYaratishForm):
    """Mudir uchun variant: kafedra tanlanmaydi, o'z kafedrasi avtomatik olinadi."""

    def __init__(self, kafedra: Department, *args: object, **kwargs: object):
        self.kafedra_qiymati = kafedra
        super().__init__(*args, **kwargs)
        self._kafedrani_qulflash()


class OqituvchiTahrirForm(OqituvchiAsosForm):
    yangi_parol = forms.CharField(
        label="Yangi parol",
        required=False,
        widget=forms.PasswordInput,
        help_text="Bo'sh qoldirilsa parol o'zgarmaydi",
    )

    def __init__(self, profil: OqituvchiProfil, *args: object, **kwargs: object):
        self.profil = profil
        kwargs.setdefault(
            "initial",
            {
                "telefon": profil.foydalanuvchi.telefon,
                "first_name": profil.foydalanuvchi.first_name,
                "last_name": profil.foydalanuvchi.last_name,
                "kafedra": profil.kafedra_id,
                "turi": profil.turi_id,
            },
        )
        super().__init__(*args, **kwargs)

    def clean_yangi_parol(self) -> str:
        parol = self.cleaned_data["yangi_parol"]
        if parol:
            password_validation.validate_password(parol, user=self.profil.foydalanuvchi)
        return parol

    def saqlash(self) -> None:
        oqituvchi_yangilash(
            self.profil,
            telefon=self.cleaned_data["telefon"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            kafedra=self.cleaned_data["kafedra"],
            turi=self.cleaned_data["turi"],
            yangi_parol=self.cleaned_data["yangi_parol"] or None,
        )


class KafedraOqituvchiTahrirForm(KafedraQulflanganMixin, OqituvchiTahrirForm):
    """Mudir uchun variant: o'qituvchi mudirning o'z kafedrasida qoladi."""

    def __init__(self, *args: object, **kwargs: object):
        super().__init__(*args, **kwargs)
        self.kafedra_qiymati = self.profil.kafedra
        self._kafedrani_qulflash()
