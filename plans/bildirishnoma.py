"""In-app notification delivery and optional Telegram Bot dispatch."""

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Iterable

from django.conf import settings
from django.db import transaction
from django.urls import reverse

from accounts.models import Department, Foydalanuvchi, Rol
from plans.models import (
    Bildirishnoma,
    BildirishnomaTuri,
    DasturTopshirish,
    KafedraTasdiqHolati,
    KafedraYuklamaTasdiq,
)
from plans.services import keshni_tozala

_LOGGER = logging.getLogger(__name__)


def ofis_adminlar() -> list[Foydalanuvchi]:
    """Return active office and superadmin accounts."""
    return list(
        Foydalanuvchi.objects.filter(
            is_active=True,
            rol__in=(Rol.OFFICE_ADMIN, Rol.SUPERADMIN),
        ).order_by("pk")
    )


def telegram_xabar_yubor(chat_id: str, matn: str) -> bool:
    """Send a best-effort message to Telegram Bot API if token is configured."""
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "").strip()
    manzil_id = (chat_id or "").strip()
    if not token or not manzil_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    yuk = json.dumps(
        {
            "chat_id": manzil_id,
            "text": matn,
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    sorov = urllib.request.Request(
        url,
        data=yuk,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(sorov, timeout=5) as javob:
            return 200 <= javob.status < 300
    except (urllib.error.URLError, OSError) as err:
        _LOGGER.warning("Telegram xabari yuborilmadi (chat_id=%s): %s", manzil_id, err)
        return False


def _telegramga_navbatla(
    qabul_qiluvchilar: list[Foydalanuvchi], sarlavha: str, matn: str
) -> None:
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return
    chat_idlar = [
        u.telegram_chat_id.strip()
        for u in qabul_qiluvchilar
        if getattr(u, "telegram_chat_id", "").strip()
    ]
    if not chat_idlar:
        return
    xabar = f"{sarlavha}\n\n{matn}".strip()

    def _yuborish() -> None:
        for chat_id in chat_idlar:
            telegram_xabar_yubor(chat_id, xabar)

    transaction.on_commit(_yuborish)


def bildirishnoma_yubor(
    qabul_qiluvchilar: Iterable[Foydalanuvchi],
    sarlavha: str,
    matn: str = "",
    *,
    havola: str = "",
    turi: str = BildirishnomaTuri.INFO,
) -> list[Bildirishnoma]:
    """Create persistent notifications for active users and queue Telegram alerts."""
    noyoblar: dict[int, Foydalanuvchi] = {}
    for user in qabul_qiluvchilar:
        if user.pk and user.is_active:
            noyoblar[user.pk] = user
    if not noyoblar:
        return []
    foydalanuvchilar = list(noyoblar.values())
    qatorlar = [
        Bildirishnoma(
            qabul_qiluvchi=u,
            sarlavha=sarlavha[:200],
            matn=matn,
            havola=havola[:255],
            turi=turi,
        )
        for u in foydalanuvchilar
    ]
    yaratilgan = Bildirishnoma.objects.bulk_create(qatorlar)
    keshni_tozala()
    _telegramga_navbatla(foydalanuvchilar, sarlavha, matn)
    return yaratilgan


def dastur_topshirildi_xabari(topshirish: DasturTopshirish) -> None:
    variant = topshirish.variant
    oqituvchi = topshirish.oqituvchi
    bildirishnoma_yubor(
        ofis_adminlar(),
        f"Yangi o'quv dasturi: {variant.nomi}",
        f"{oqituvchi} tomonidan {topshirish.urinish_raqami}-urinish topshirildi.",
        havola=reverse("office:dastur_topshirishlar"),
        turi=BildirishnomaTuri.INFO,
    )


def dastur_korildi_xabari(topshirish: DasturTopshirish) -> None:
    variant = topshirish.variant
    if topshirish.holat == "QABUL_QILINDI":
        sarlavha = f"O'quv dasturi qabul qilindi: {variant.nomi}"
        matn = "O'quv bo'limi tomonidan tasdiqlandi."
        turi = BildirishnomaTuri.MUVAFFAQIYAT
    else:
        sarlavha = f"O'quv dasturi rad etildi: {variant.nomi}"
        matn = (
            f"Sabab: {topshirish.izoh}" if topshirish.izoh else "Qayta ko'rib chiqing."
        )
        turi = BildirishnomaTuri.XATO
    bildirishnoma_yubor(
        [topshirish.oqituvchi.foydalanuvchi],
        sarlavha,
        matn,
        havola=reverse("men:yuklamalar"),
        turi=turi,
    )


def kafedra_yubordi_xabari(kafedra: Department, yil: int) -> None:
    bildirishnoma_yubor(
        ofis_adminlar(),
        f"Yuklama tasdiqqa yuborildi: {kafedra.nomi}",
        f"{yil}/{yil + 1} o'quv yili kafedra yuklamasi ko'rib chiqishga yuborildi.",
        havola=f"{reverse('office:kafedra_list')}?yil={yil}",
        turi=BildirishnomaTuri.INFO,
    )


def kafedra_javobi_xabari(
    kafedra: Department, yil: int, tasdiq: KafedraYuklamaTasdiq
) -> None:
    mudir = getattr(kafedra, "mudir", None)
    if mudir is None:
        return
    if tasdiq.holat == KafedraTasdiqHolati.TASDIQLANGAN:
        sarlavha = f"Kafedra yuklamasi tasdiqlandi ({yil}/{yil + 1})"
        matn = (
            tasdiq.izoh
            or f"{kafedra.nomi} yuklamasi o'quv bo'limi tomonidan qabul qilindi."
        )
        turi = BildirishnomaTuri.MUVAFFAQIYAT
    else:
        sarlavha = f"Kafedra yuklamasi qaytarildi ({yil}/{yil + 1})"
        matn = f"Sabab: {tasdiq.izoh}" if tasdiq.izoh else "Tuzatish uchun qaytarildi."
        turi = BildirishnomaTuri.XATO
    bildirishnoma_yubor(
        [mudir.foydalanuvchi],
        sarlavha,
        matn,
        havola=f"{reverse('kafedra:dashboard')}?yil={yil}",
        turi=turi,
    )
