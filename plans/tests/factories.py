"""Test ma'lumotlarini yasovchi oddiy yordamchilar (ortiqcha kutubxonasiz)."""

from itertools import count

from accounts.models import Department, Foydalanuvchi, OqituvchiProfil, OqituvchiTuri
from plans.models import (
    Fan,
    FanSemestr,
    FanTuri,
    FanVariant,
    Guruh,
    OquvReja,
    TalimYonalishi,
)

_telefon_raqami = count(1)


def reja_yasa(**kwargs: object) -> OquvReja:
    maydonlar: dict[str, object] = {
        "bilim_sohasi_kodi": "6",
        "bilim_sohasi_nomi": "Test bilim sohasi",
        "talim_sohasi_kodi": "606",
        "talim_sohasi_nomi": "Test ta'lim sohasi",
        "yonalish_kodi": "60610100",
        "yonalish_nomi": "Dasturiy injiniring",
        "boshlanish_yili": 2024,
        "davomiylik_yil": 4,
        "talabalar_soni": 75,
        "guruhlar_soni": 3,
        "guruh_prefiksi": "DI",
    }
    maydonlar.update(kwargs)
    return OquvReja.objects.create(**maydonlar)


def yonalish_yasa(**kwargs: object) -> TalimYonalishi:
    maydonlar: dict[str, object] = {
        "kodi": "60610100",
        "nomi": "Dasturiy injiniring",
        "bilim_sohasi_kodi": "6",
        "bilim_sohasi_nomi": "Test bilim sohasi",
        "talim_sohasi_kodi": "606",
        "talim_sohasi_nomi": "Test ta'lim sohasi",
    }
    maydonlar.update(kwargs)
    return TalimYonalishi.objects.create(**maydonlar)


def fan_yasa(
    reja: OquvReja,
    raqam: str = "1.01",
    turi: str = FanTuri.MAJBURIY,
    jami_soat: int | None = 120,
    **variant_kwargs: object,
) -> Fan:
    """Bitta variantli Fan yasaydi; MAJBURIY bo'lsa uni avtomatik tanlaydi."""
    fan = Fan.objects.create(reja=reja, raqam=raqam, turi=turi, jami_soat=jami_soat)
    variant = variant_yasa(fan, **variant_kwargs)
    if turi == FanTuri.MAJBURIY:
        fan.tanlangan_variant = variant
        fan.save(update_fields=["tanlangan_variant"])
    return fan


def variant_yasa(fan: Fan, **kwargs: object) -> FanVariant:
    maydonlar: dict[str, object] = {
        "kodi": f"K{fan.raqam}-{fan.variantlar.count() + 1}",
        "nomi": "Dasturlashga kirish",
        "auditoriya_soat": 72,
        "maruza_soat": 24,
        "amaliyot_soat": 24,
        "laboratoriya_soat": 24,
    }
    maydonlar.update(kwargs)
    return FanVariant.objects.create(fan=fan, **maydonlar)


def fan_semestr_yasa(
    variant: FanVariant, semestr: int = 1, **kwargs: object
) -> FanSemestr:
    maydonlar: dict[str, object] = {
        "kredit": 4,
        "haftalik_soat": 4,
        "maruza_soat": 24,
        "amaliyot_soat": 24,
        "laboratoriya_soat": 24,
    }
    maydonlar.update(kwargs)
    return FanSemestr.objects.create(variant=variant, semestr=semestr, **maydonlar)


def guruh_yasa(reja: OquvReja, raqam: int = 1) -> Guruh:
    return Guruh.objects.create(
        reja=reja, raqam=raqam, nomi=f"DI-{reja.boshlanish_yili}-{raqam}"
    )


def oqituvchi_yasa(
    kafedra: Department | None = None, min_soat: int = 600
) -> OqituvchiProfil:
    n = next(_telefon_raqami)
    if kafedra is None:
        kafedra, _ = Department.objects.get_or_create(nomi="Raqamli texnologiyalar")
    turi, _ = OqituvchiTuri.objects.get_or_create(
        nomi=f"Dotsent-{min_soat}", defaults={"min_soat": min_soat}
    )
    foydalanuvchi = Foydalanuvchi.objects.create_user(
        telefon=f"+9989{n:08d}",
        password="test-parol-123",
        first_name="Test",
        last_name=f"Oqituvchi{n}",
    )
    return OqituvchiProfil.objects.create(
        foydalanuvchi=foydalanuvchi, kafedra=kafedra, turi=turi
    )
