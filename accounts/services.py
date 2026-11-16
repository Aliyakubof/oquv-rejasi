"""Xodimlar boshqaruvi: o'qituvchi hisoblari va kafedra mudirlarini tayinlash."""

import secrets

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from accounts.models import (
    Department,
    Foydalanuvchi,
    OqituvchiProfil,
    OqituvchiTuri,
    Rol,
    Universitet,
)
from accounts.phone import telefonni_normallashtir

_VAQTINCHALIK_ALIFBO = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def vaqtinchalik_parol_tasodifiy(uzunlik: int = 10) -> str:
    """Oson o'qiladigan kriptografik tasodifiy vaqtinchalik parol yaratadi."""
    return "".join(secrets.choice(_VAQTINCHALIK_ALIFBO) for _ in range(uzunlik))


@transaction.atomic
def vaqtinchalik_parol_yarat(foydalanuvchi: Foydalanuvchi) -> str:
    """Kirishda almashtirish sharti bilan bir martalik vaqtinchalik parol qo'yadi."""
    parol = vaqtinchalik_parol_tasodifiy()
    foydalanuvchi.set_password(parol)
    foydalanuvchi.parol_ozgartirish_kerak = True
    foydalanuvchi.save(update_fields=["password", "parol_ozgartirish_kerak"])
    return parol


def universitet_olish() -> Universitet | None:
    """Universitetning yagona yozuvini qaytaradi (hali yaratilmagan bo'lsa None)."""
    return Universitet.objects.first()


def universitet_nomi(bosh: str = "") -> str:
    """Universitet rasmiy nomini qaytaradi; kiritilmagan bo'lsa `bosh` qiymatni."""
    universitet = universitet_olish()
    return universitet.rasmiy_nomi if universitet and universitet.rasmiy_nomi else bosh


@transaction.atomic
def oqituvchi_yaratish(
    *,
    telefon: str,
    first_name: str,
    last_name: str,
    parol: str,
    kafedra: Department,
    turi: OqituvchiTuri,
) -> OqituvchiProfil:
    foydalanuvchi = Foydalanuvchi.objects.create_user(
        telefon=telefon,
        password=parol,
        first_name=first_name,
        last_name=last_name,
        rol=Rol.TEACHER,
    )
    return OqituvchiProfil.objects.create(
        foydalanuvchi=foydalanuvchi, kafedra=kafedra, turi=turi
    )


@transaction.atomic
def oqituvchi_yangilash(
    profil: OqituvchiProfil,
    *,
    telefon: str,
    first_name: str,
    last_name: str,
    kafedra: Department,
    turi: OqituvchiTuri,
    yangi_parol: str | None = None,
) -> None:
    if profil.kafedra_id != kafedra.pk and profil.yuklamalar.exists():
        raise ValidationError(
            {
                "kafedra": (
                    "O'qituvchiga joriy kafedrada yuklama biriktirilgan. "
                    "Boshqa kafedraga o'tkazishdan oldin yuklamalarni bekor qiling."
                )
            }
        )
    boshqa_kafedra = getattr(profil, "boshqarayotgan_kafedra", None)
    if boshqa_kafedra is not None and boshqa_kafedra.pk != kafedra.pk:
        mudir_tayinlash(boshqa_kafedra, None)
        profil.foydalanuvchi.refresh_from_db(fields=["rol"])
    foydalanuvchi = profil.foydalanuvchi
    foydalanuvchi.telefon = telefonni_normallashtir(telefon)
    foydalanuvchi.first_name = first_name
    foydalanuvchi.last_name = last_name
    yangilanadigan = ["telefon", "first_name", "last_name"]
    if yangi_parol:
        foydalanuvchi.set_password(yangi_parol)
        foydalanuvchi.parol_ozgartirish_kerak = False
        yangilanadigan.extend(["password", "parol_ozgartirish_kerak"])
    foydalanuvchi.full_clean(exclude=["password"])
    foydalanuvchi.save(update_fields=yangilanadigan)
    profil.kafedra = kafedra
    profil.turi = turi
    profil.full_clean()
    profil.save(update_fields=["kafedra", "turi"])


@transaction.atomic
def mudir_tayinlash(kafedra: Department, profil: OqituvchiProfil | None) -> None:
    """Kafedra mudirini tayinlaydi (profil=None da bo'shatadi) va rollarni moslaydi."""
    shart = Q(pk=kafedra.pk)
    if profil is not None:
        shart |= Q(mudir_id=profil.pk)
    qulflangan = {
        k.pk: k
        for k in Department.objects.select_for_update()
        .select_related("mudir__foydalanuvchi")
        .filter(shart)
        .order_by("pk")
    }
    kafedra_qulf = qulflangan[kafedra.pk]
    if profil is not None:
        profil = (
            OqituvchiProfil.objects.select_for_update()
            .select_related("foydalanuvchi")
            .get(pk=profil.pk)
        )
        if not profil.foydalanuvchi.is_active:
            raise ValidationError("Faolsizlantirilgan o'qituvchi mudir bo'la olmaydi.")
        if profil.kafedra_id != kafedra_qulf.pk:
            raise ValidationError("O'qituvchi boshqa kafedraga tegishli.")
        boshqa = next(
            (
                k
                for k in qulflangan.values()
                if k.mudir_id == profil.pk and k.pk != kafedra_qulf.pk
            ),
            None,
        )
        if boshqa is not None:
            raise ValidationError(f"{profil} allaqachon {boshqa} mudiri.")
    _mudirlikdan_tushirish(kafedra_qulf, profil)
    kafedra_qulf.mudir = profil
    kafedra_qulf.save(update_fields=["mudir"])
    kafedra.mudir = profil
    if profil is not None:
        _rolni_ornatish(profil.foydalanuvchi, Rol.DEPARTMENT_ADMIN)


def _mudirlikdan_tushirish(kafedra: Department, yangi: OqituvchiProfil | None) -> None:
    eski = kafedra.mudir
    if eski is not None and eski != yangi:
        _rolni_ornatish(eski.foydalanuvchi, Rol.TEACHER)


def _rolni_ornatish(foydalanuvchi: Foydalanuvchi, rol: str) -> None:
    # Superadmin/ofis admin hisoblari mudirlik bilan rolini o'zgartirmaydi.
    if foydalanuvchi.rol in (Rol.SUPERADMIN, Rol.OFFICE_ADMIN):
        return
    foydalanuvchi.rol = rol
    foydalanuvchi.save(update_fields=["rol"])
