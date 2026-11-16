"""Tizim ichidagi bildirishnomalar va ixtiyoriy Telegram bot xabarnomalari."""

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

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
_TELEGRAM_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="telegram")


def ofis_adminlar() -> list[Foydalanuvchi]:
    """Faol ofis admin va superadmin hisoblarini qaytaradi."""
    return list(
        Foydalanuvchi.objects.filter(
            is_active=True,
            rol__in=(Rol.OFFICE_ADMIN, Rol.SUPERADMIN),
        ).order_by("pk")
    )


class _YoqRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect zanjiri orqali Telegram bot tokeni sizib chiqishini taqiqlaydi."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


_TELEGRAM_OPENER = urllib.request.build_opener(_YoqRedirectHandler)
_TELEGRAM_MAX_BELGI = 4096


def _matnni_qisqartir(matn: str) -> str:
    if len(matn) <= _TELEGRAM_MAX_BELGI:
        return matn
    return matn[: _TELEGRAM_MAX_BELGI - 1] + "…"


def telegram_xabar_yubor(chat_id: str, matn: str) -> bool:
    """Bot tokeni sozlangan bo'lsa, Telegram Bot API orqali xabar yuboradi."""
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "").strip()
    manzil_id = (chat_id or "").strip()
    if not token or not manzil_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    yuk = json.dumps(
        {
            "chat_id": manzil_id,
            "text": _matnni_qisqartir(matn),
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
        with _TELEGRAM_OPENER.open(sorov, timeout=5) as javob:
            if not (200 <= javob.status < 300):
                return False
            tana = javob.read(65_536).decode("utf-8", errors="replace")
            malumot = json.loads(tana) if tana else {}
            if not isinstance(malumot, dict) or malumot.get("ok") is not True:
                _LOGGER.warning(
                    "Telegram API xato qaytardi (chat_id=%s, status=%s)",
                    manzil_id,
                    javob.status,
                )
                return False
            return True
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as err:
        xato_nomi = type(err).__name__
        _LOGGER.warning(
            "Telegram xabari yuborilmadi (chat_id=%s): %s",
            manzil_id,
            xato_nomi,
        )
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
            try:
                telegram_xabar_yubor(chat_id, xabar)
            except Exception:
                _LOGGER.exception(
                    "Telegram navbatida kutilmagan xato (chat_id=%s)", chat_id
                )

    def _navbatlash() -> None:
        if getattr(settings, "IS_TEST", False):
            _yuborish()
        else:
            _TELEGRAM_EXECUTOR.submit(_yuborish)

    transaction.on_commit(_navbatlash)


def bildirishnoma_yubor(
    qabul_qiluvchilar: Iterable[Foydalanuvchi],
    sarlavha: str,
    matn: str = "",
    *,
    havola: str = "",
    turi: str = BildirishnomaTuri.INFO,
) -> list[Bildirishnoma]:
    """Faol foydalanuvchilarga bildirishnoma yozib, Telegram xabarini navbatlaydi."""
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
