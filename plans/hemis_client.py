"""HEMIS integration helpers: inbound payload normalization and outbound pull."""

import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest

from accounts.models import Foydalanuvchi
from plans.audit import audit_yoz
from plans.models import (
    AuditAmali,
    FanSemestr,
    KafedraTasdiqHolati,
    KafedraYuklamaTasdiq,
    OquvReja,
)
from plans.services import eng_kop_kurs_ishi_talabasi, guruhlarni_sinxronlash


def butun_son_oqish(
    item: dict[str, object], maydon: str, *, min_qiymat: int = 1
) -> int | None:
    if maydon not in item or item[maydon] is None:
        return None
    xom = item[maydon]
    if isinstance(xom, bool):
        raise ValueError(f"{maydon} butun son bo'lishi kerak")
    if isinstance(xom, int):
        qiymat = xom
    elif isinstance(xom, str) and xom.strip().isascii() and xom.strip().isdigit():
        qiymat = int(xom.strip())
    else:
        raise ValueError(f"{maydon} butun son bo'lishi kerak")
    if qiymat < min_qiymat:
        raise ValueError(f"{maydon} kamida {min_qiymat} bo'lishi kerak")
    return qiymat


def sync_rejani_top(item: dict[str, object]) -> OquvReja | None:
    reja_id = butun_son_oqish(item, "id") or butun_son_oqish(item, "reja_id")
    if reja_id is not None:
        return OquvReja.objects.select_for_update().filter(id=reja_id).first()
    if "yonalish_kodi" in item and "boshlanish_yili" in item:
        kod = item["yonalish_kodi"]
        if not isinstance(kod, str) or not kod.strip():
            raise ValueError("yonalish_kodi matn bo'lishi kerak")
        yil = butun_son_oqish(item, "boshlanish_yili", min_qiymat=1900)
        filtr: dict[str, object] = {
            "yonalish_kodi": kod.strip(),
            "boshlanish_yili": yil,
        }
        if item.get("talim_shakli"):
            if not isinstance(item["talim_shakli"], str):
                raise ValueError("talim_shakli matn bo'lishi kerak")
            filtr["talim_shakli"] = item["talim_shakli"].strip()
        return OquvReja.objects.select_for_update().filter(**filtr).first()
    return None


def reja_qulflanganmi(reja: OquvReja) -> bool:
    fslar = (
        FanSemestr.objects.reja_uchun(reja)
        .filter(variant__kafedra__isnull=False)
        .values_list("variant__kafedra_id", "semestr")
    )
    juftlar = {
        (kafedra_id, reja.boshlanish_yili + (semestr - 1) // 2)
        for kafedra_id, semestr in fslar
    }
    if not juftlar:
        return False
    shart = Q()
    for kafedra_id, yil in juftlar:
        shart |= Q(kafedra_id=kafedra_id, akademik_yil=yil)
    return KafedraYuklamaTasdiq.objects.filter(
        shart,
        holat__in=(
            KafedraTasdiqHolati.TASDIQDA,
            KafedraTasdiqHolati.TASDIQLANGAN,
        ),
    ).exists()


def sync_rejani_yangila(
    reja: OquvReja, item: dict[str, object]
) -> dict[str, object] | None:
    talabalar = butun_son_oqish(item, "talabalar_soni", min_qiymat=1)
    guruhlar = butun_son_oqish(item, "guruhlar_soni", min_qiymat=1)
    ozgardi = False
    if talabalar is not None and reja.talabalar_soni != talabalar:
        reja.talabalar_soni = talabalar
        ozgardi = True
    if guruhlar is not None and reja.guruhlar_soni != guruhlar:
        reja.guruhlar_soni = guruhlar
        ozgardi = True
    if "guruh_prefiksi" in item and item["guruh_prefiksi"] is not None:
        if not isinstance(item["guruh_prefiksi"], str):
            raise ValueError("guruh_prefiksi matn bo'lishi kerak")
        prefiks = item["guruh_prefiksi"].strip()
        if reja.guruh_prefiksi != prefiks:
            reja.guruh_prefiksi = prefiks
            ozgardi = True
    if not ozgardi:
        return None
    if reja_qulflanganmi(reja):
        raise ValueError("tasdiqlangan kafedra yuklamasi qulflangan")
    if talabalar is not None:
        eng_kop = eng_kop_kurs_ishi_talabasi(reja)
        if eng_kop and reja.talabalar_soni < eng_kop:
            raise ValueError(f"kurs ishiga allaqachon {eng_kop} ta talaba taqsimlangan")
    reja.full_clean()
    reja.save()
    guruhlarni_sinxronlash(reja)
    return {
        "id": reja.id,
        "yonalish_kodi": reja.yonalish_kodi,
        "yonalish_nomi": reja.yonalish_nomi,
        "boshlanish_yili": reja.boshlanish_yili,
        "talabalar_soni": reja.talabalar_soni,
        "guruhlar_soni": reja.guruhlar_soni,
        "guruhlar": [g.nomi for g in reja.guruhlar.all()],
    }


def hemis_elementlarni_sinxronlash(
    elementlar: list[dict[str, object]],
    *,
    foydalanuvchi: Foydalanuvchi | None = None,
    request: HttpRequest | None = None,
) -> tuple[list[dict[str, object]], list[str]]:
    """Apply HEMIS curriculum student/group updates atomically per item."""
    yangilangan: list[dict[str, object]] = []
    xatolar: list[str] = []

    with transaction.atomic():
        for item in elementlar:
            try:
                with transaction.atomic():
                    reja = sync_rejani_top(item)
                    if reja is None:
                        xatolar.append(f"O'quv reja topilmadi: {item}")
                        continue
                    natija = sync_rejani_yangila(reja, item)
            except (ValueError, TypeError, ValidationError) as err:
                xatolar.append(f"Xatolik ({err}): {item}")
                continue
            if natija is not None:
                yangilangan.append(natija)

        if yangilangan:
            kodlar = ", ".join(str(r["yonalish_kodi"]) for r in yangilangan)
            audit_yoz(
                AuditAmali.TAHRIRLANDI,
                f"HEMIS Sync: {len(yangilangan)} ta reja sinxronlandi ({kodlar})",
                foydalanuvchi=foydalanuvchi,
                model_nomi="OquvReja",
                request=request,
            )

    return yangilangan, xatolar


def _json_royxatni_ajrat(data: object) -> list[dict[str, object]]:
    if isinstance(data, list):
        elementlar = data
    elif isinstance(data, dict):
        for kalit in ("rejalar", "results", "data", "items"):
            if kalit in data and isinstance(data[kalit], list):
                elementlar = data[kalit]
                break
        else:
            elementlar = [data]
    else:
        raise ValueError("HEMIS javobi JSON ro'yxat yoki obyekt bo'lishi kerak.")
    if not all(isinstance(x, dict) for x in elementlar):
        raise ValueError("HEMIS javobidagi har bir element JSON obyekt bo'lishi kerak.")
    return elementlar


def hemis_dan_yuklash(
    base_url: str | None = None,
    api_key: str | None = None,
    *,
    timeout: int | None = None,
) -> list[dict[str, object]]:
    """Fetch curriculum counts from external HEMIS endpoint using stdlib HTTP."""
    manzil = (base_url or getattr(settings, "HEMIS_BASE_URL", "")).strip()
    if not manzil:
        raise ValueError("HEMIS_BASE_URL sozlanmagan.")
    kalit = api_key if api_key is not None else getattr(settings, "HEMIS_API_KEY", "")
    sarlavhalar = {"Accept": "application/json"}
    if kalit:
        sarlavhalar["Authorization"] = f"Bearer {kalit}"
        sarlavhalar["X-API-KEY"] = kalit
    sorov = urllib.request.Request(manzil, headers=sarlavhalar, method="GET")
    kutish = timeout or int(getattr(settings, "HEMIS_TIMEOUT", 15))
    try:
        with urllib.request.urlopen(sorov, timeout=kutish) as javob:
            xom = javob.read().decode("utf-8")
    except urllib.error.URLError as err:
        raise ConnectionError(f"HEMIS serveriga ulanib bo'lmadi: {err}") from err
    try:
        malumot = json.loads(xom)
    except json.JSONDecodeError as err:
        raise ValueError("HEMIS javobi yaroqli JSON emas.") from err
    return _json_royxatni_ajrat(malumot)
