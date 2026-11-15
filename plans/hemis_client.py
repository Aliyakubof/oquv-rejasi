"""HEMIS integration helpers: inbound payload normalization and outbound pull."""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from http.client import HTTPMessage

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest

from accounts.models import Foydalanuvchi
from plans.audit import audit_yoz
from plans.models import (
    AuditAmali,
    FanSemestr,
    OquvReja,
)
from plans.services import (
    eng_katta_band_guruh,
    eng_kop_kurs_ishi_talabasi,
    guruhlarni_sinxronlash,
    reja_qulflanganmi,
)

_LOGGER = logging.getLogger(__name__)
MAX_HEMIS_TALABA = 10000
MAX_HEMIS_GURUH = 200
MAX_HEMIS_JAVOB_BAYT = 5 * 1024 * 1024


class _YoqRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            "HEMIS redirect xavfsizlik sababli taqiqlangan.",
            headers,
            None,
        )


def butun_son_oqish(
    item: dict[str, object],
    maydon: str,
    *,
    min_qiymat: int = 1,
    max_qiymat: int | None = None,
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
    if max_qiymat is not None and qiymat > max_qiymat:
        raise ValueError(f"{maydon} ko'pi bilan {max_qiymat} bo'lishi kerak")
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


def _reja_maydonlarini_yangila(
    reja: OquvReja, item: dict[str, object]
) -> tuple[bool, int | None, int | None]:
    talabalar = butun_son_oqish(
        item, "talabalar_soni", min_qiymat=1, max_qiymat=MAX_HEMIS_TALABA
    )
    guruhlar = butun_son_oqish(
        item, "guruhlar_soni", min_qiymat=1, max_qiymat=MAX_HEMIS_GURUH
    )
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
    return ozgardi, talabalar, guruhlar


def _sync_cheklovlarini_tekshir(
    reja: OquvReja, talabalar: int | None, guruhlar: int | None
) -> None:
    if reja_qulflanganmi(reja):
        raise ValueError("tasdiqlangan kafedra yuklamasi qulflangan")
    if talabalar is not None:
        eng_kop = eng_kop_kurs_ishi_talabasi(reja)
        if eng_kop and reja.talabalar_soni < eng_kop:
            raise ValueError(f"kurs ishiga allaqachon {eng_kop} ta talaba taqsimlangan")
    if guruhlar is not None:
        eng_katta = eng_katta_band_guruh(reja)
        if eng_katta and reja.guruhlar_soni < eng_katta:
            raise ValueError(f"{eng_katta}-guruhga allaqachon yuklama taqsimlangan")


@transaction.atomic
def sync_rejani_yangila(
    reja: OquvReja, item: dict[str, object]
) -> dict[str, object] | None:
    """Apply atomic, lock-safe updates to one reja from a HEMIS sync item."""
    reja = OquvReja.objects.select_for_update().get(pk=reja.pk)
    ozgardi, talabalar, guruhlar = _reja_maydonlarini_yangila(reja, item)
    if not ozgardi:
        return None
    list(reja.guruhlar.select_for_update().order_by("pk"))
    list(FanSemestr.objects.reja_uchun(reja).select_for_update().order_by("pk"))
    _sync_cheklovlarini_tekshir(reja, talabalar, guruhlar)
    reja.full_clean()
    reja.save()
    yangilangan_guruhlar = guruhlarni_sinxronlash(reja)
    return {
        "id": reja.id,
        "yonalish_kodi": reja.yonalish_kodi,
        "yonalish_nomi": reja.yonalish_nomi,
        "boshlanish_yili": reja.boshlanish_yili,
        "talabalar_soni": reja.talabalar_soni,
        "guruhlar_soni": reja.guruhlar_soni,
        "guruhlar": [g.nomi for g in yangilangan_guruhlar],
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


def json_royxatni_ajrat(data: object) -> list[dict[str, object]]:
    """Normalize supported HEMIS JSON payloads to a list of dicts."""
    if isinstance(data, list):
        elementlar = data
    elif isinstance(data, dict):
        for kalit in ("rejalar", "results", "data", "items"):
            if kalit in data:
                if not isinstance(data[kalit], list):
                    raise ValueError(f"'{kalit}' maydoni ro'yxat bo'lishi kerak.")
                elementlar = data[kalit]
                break
        else:
            elementlar = [data]
    else:
        raise ValueError("HEMIS javobi JSON ro'yxat yoki obyekt bo'lishi kerak.")
    if not all(isinstance(x, dict) for x in elementlar):
        raise ValueError("HEMIS javobidagi har bir element JSON obyekt bo'lishi kerak.")
    return elementlar


def _manzilni_tekshir(manzil: str) -> None:
    parsed = urllib.parse.urlparse(manzil)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("HEMIS_BASE_URL yaroqli http(s) manzil bo'lishi kerak.")
    if parsed.scheme == "http" and (parsed.hostname or "") not in (
        "127.0.0.1",
        "localhost",
    ):
        if not settings.DEBUG:
            raise ValueError(
                "Production muhitida HEMIS_BASE_URL faqat https:// bo'lishi shart."
            )
        _LOGGER.warning("HEMIS so'rovi shifrlanmagan HTTP orqali yuborilmoqda.")


def _http_ochish(sorov: urllib.request.Request, kutish: int) -> bytes:
    opener = urllib.request.build_opener(_YoqRedirectHandler())
    with opener.open(sorov, timeout=kutish) as javob:
        xom = javob.read(MAX_HEMIS_JAVOB_BAYT + 1)
    if len(xom) > MAX_HEMIS_JAVOB_BAYT:
        raise ValueError("HEMIS javob hajmi belgilangan chegaradan katta.")
    return xom


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
    _manzilni_tekshir(manzil)
    kalit = api_key if api_key is not None else getattr(settings, "HEMIS_API_KEY", "")
    sarlavhalar = {"Accept": "application/json"}
    if kalit:
        sarlavhalar["Authorization"] = f"Bearer {kalit}"
        sarlavhalar["X-API-KEY"] = kalit
    sorov = urllib.request.Request(manzil, headers=sarlavhalar, method="GET")
    kutish = timeout or int(getattr(settings, "HEMIS_TIMEOUT", 15))
    try:
        xom = _http_ochish(sorov, kutish).decode("utf-8")
    except urllib.error.URLError as err:
        raise ConnectionError(f"HEMIS serveriga ulanib bo'lmadi: {err}") from err
    try:
        malumot = json.loads(xom)
    except json.JSONDecodeError as err:
        raise ValueError("HEMIS javobi yaroqli JSON emas.") from err
    return json_royxatni_ajrat(malumot)
