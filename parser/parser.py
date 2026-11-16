import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from pathlib import Path
from zipfile import BadZipFile

import openpyxl
from lxml.etree import XMLSyntaxError
from openpyxl.cell.cell import Cell
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from parser.models import (
    MajburiyFan,
    TahlilNatijasi,
    TahlilXatosi,
    TanlovFani,
    TanlovVarianti,
    UstunJoyi,
)

FAN_RAQAMI_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")
BOLIM_BELGISI_RE = re.compile(r"^(\d+)(?:\.0+)?\.?$")
KOD_RE = re.compile(r"\d{6,9}")
AJRATUVCHI_RE = re.compile(r"^[\s:\-–—]+")
MUDDAT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*yil")
BOSHLANISH_YILI_RE = re.compile(r"(\d{4})\s*[-/–]\s*\d{4}")
TUTUQ_RE = re.compile(r"['\u2018\u2019\u02bb`]")
# Vazirlik xodimlari ba'zan sarlavhani ruscha klaviaturada yozib yuboradi —
# bir xil ko'ringan kirill harflarni qidiruvdan oldin lotinchaga o'giramiz.
KIRILL_OXSHASHLAR = str.maketrans(
    {
        "\u0410": "A",
        "\u0412": "B",
        "\u0415": "E",
        "\u041a": "K",
        "\u041c": "M",
        "\u041d": "H",
        "\u041e": "O",
        "\u0420": "P",
        "\u0421": "C",
        "\u0422": "T",
        "\u0423": "Y",
        "\u0425": "X",
        "\u0430": "a",
        "\u0435": "e",
        "\u043e": "o",
        "\u0440": "p",
        "\u0441": "c",
        "\u0443": "y",
        "\u0445": "x",
    }
)

TALIM_SHAKLI_XARITASI = {
    "kunduzgi": "Kunduzgi",
    "kechki": "Kechki",
    "kechgi": "Kechki",
    "sirtqi": "Sirtqi",
    "sirtki": "Sirtqi",
}

HAFTALIK_SARLAVHA_BELGILARI = ("haftalar soni", "kurslardagi haftalar")
KREDIT_SARLAVHA_BELGILARI = ("kredit",)
OTKAZILADIGAN_QATORLAR = (
    "malakaviy amaliyot",
    "malaka amaliyot",
    "yakuniy davlat attestatsiyasi",
    "hammasi",
)
SOAT_MAYDONLARI = (
    "auditoriya",
    "maruza",
    "amaliyot",
    "laboratoriya",
    "seminar",
    "kurs_ishi",
)

_OQILMAYDI = object()


def fan_raqamimi(qiymat: object) -> bool:
    if qiymat is None:
        return False
    return bool(FAN_RAQAMI_RE.match(str(qiymat).strip()))


def bolim_boshi(fan_raqami: object) -> str:
    return str(fan_raqami).strip().split(".")[0]


def _matnni_normallashtir(qiymat: str) -> str:
    """Harflarni kichraytiradi, barcha tutuq variantlarini bir xil qiladi va
    adashib kirib qolgan kirill harflarni lotinchaga almashtiradi."""
    qiymat = TUTUQ_RE.sub("'", qiymat).translate(KIRILL_OXSHASHLAR)
    return qiymat.casefold()


def _talim_shaklini_tekisla(xom: str) -> str | None:
    """Ta'lim shakli matnini Kunduzgi/Kechki/Sirtqi ko'rinishiga keltiradi."""
    norm = _matnni_normallashtir(xom).strip()
    for kalit, standart in TALIM_SHAKLI_XARITASI.items():
        if kalit in norm:
            return standart
    return None


def _bolim_belgisini_ol(qiymat: object) -> str | None:
    """'1.00', '1,0', '1.00.' kabi bo'lim raqamini oddiy '1' ko'rinishiga keltiradi."""
    if qiymat is None:
        return None
    matn = str(qiymat).strip().replace(",", ".")
    mos = BOLIM_BELGISI_RE.match(matn)
    return mos.group(1) if mos else None


def katakni_matn_bilan_top(varaq: Worksheet, qism: str) -> Cell | None:
    qidiruv = _matnni_normallashtir(qism)
    for qator in varaq.iter_rows(max_row=15):
        for katak in qator:
            if isinstance(katak.value, str) and qidiruv in _matnni_normallashtir(
                katak.value
            ):
                return katak
    return None


def chiziqdan_keyin(xom: str) -> str:
    qismlar = re.split(r"\s*[-–—:]\s*", xom, maxsplit=1)
    return qismlar[1].strip() if len(qismlar) > 1 else xom.strip()


def _kod_va_nomni_ajrat(xom: str) -> tuple[str, str] | None:
    """Matn ichidan 6-9 xonali yo'nalish kodini va undan keyingi nomni oladi."""
    mos = KOD_RE.search(xom)
    if mos is None:
        return None
    kod = mos.group()
    nom = AJRATUVCHI_RE.sub("", xom[mos.end() :]).strip()
    return kod, nom


def yonalishni_top(
    varaq: Worksheet, ogohlantirishlar: list[str]
) -> tuple[str, str] | None:
    """Yo'nalish kodi va nomini yorliq katakdan, o'ngidan yoki pastidan topadi."""
    katak = katakni_matn_bilan_top(varaq, "nalishi")
    if katak is None:
        return None
    nomzodlar = [
        katak.value,
        varaq.cell(row=katak.row, column=katak.column + 1).value,
        varaq.cell(row=katak.row + 1, column=katak.column).value,
    ]
    for xom in nomzodlar:
        if not isinstance(xom, str):
            continue
        ajratilgan = _kod_va_nomni_ajrat(xom)
        if ajratilgan is not None:
            return ajratilgan
    ogohlantirishlar.append(f"yo'nalishi kodi topilmadi: {katak.value!r}")
    return "", chiziqdan_keyin(str(katak.value or ""))


def pascal_korinishiga(nom: str) -> str:
    return "".join(re.sub(r"[^a-zA-Z0-9]", "", s).capitalize() for s in nom.split())


def boshlanish_yilini_ol(xom: str) -> str:
    mos = BOSHLANISH_YILI_RE.search(xom)
    return mos.group(1) if mos else ""


def metamalumni_oqi(
    varaq: Worksheet, ogohlantirishlar: list[str]
) -> tuple[str, str, str]:
    """Varaq tepasidan akademik daraja, o'qish muddati va ta'lim shaklini o'qiydi."""
    daraja_katak = katakni_matn_bilan_top(varaq, "Akademik daraja")
    muddat_katak = katakni_matn_bilan_top(varaq, "muddati")
    shakl_katak = katakni_matn_bilan_top(varaq, "ta'lim shakli")
    daraja = chiziqdan_keyin(daraja_katak.value) if daraja_katak else ""
    muddat = chiziqdan_keyin(muddat_katak.value) if muddat_katak else ""
    if not daraja:
        ogohlantirishlar.append("akademik daraja topilmadi")
    if shakl_katak is None:
        ogohlantirishlar.append("ta'lim shakli topilmadi")
        return daraja, muddat, ""
    xom_shakl = chiziqdan_keyin(shakl_katak.value)
    talim_shakli = _talim_shaklini_tekisla(xom_shakl)
    if talim_shakli is None:
        ogohlantirishlar.append(f"ta'lim shakli tanilmadi: {xom_shakl!r}")
        return daraja, muddat, ""
    return daraja, muddat, talim_shakli


def sarlavha_ustunini_top(
    varaq: Worksheet, kalit_soz: str, oxirgi_qator: int, bosh_qator: int = 1
) -> int | None:
    """Kalit so'z uchragan birinchi sarlavha ustunining 0-based indeksini qaytaradi."""
    qidiruv = _matnni_normallashtir(kalit_soz)
    for qator in varaq.iter_rows(min_row=bosh_qator, max_row=oxirgi_qator):
        for katak in qator:
            if isinstance(katak.value, str) and qidiruv in _matnni_normallashtir(
                katak.value
            ):
                return katak.column - 1
    return None


def dastur_muddatini_ol(varaq: Worksheet) -> float:
    """O'qish muddatini yil hisobida (masalan 4 yoki 4.5) qaytaradi."""
    katak = katakni_matn_bilan_top(varaq, "muddati")
    if katak is None:
        raise TahlilXatosi("o'qish muddati topilmadi")
    matn = str(katak.value or "").replace(",", ".")
    mos = MUDDAT_RE.search(matn)
    if mos is None:
        raise TahlilXatosi(f"o'qish muddati aniqlanmadi: {katak.value!r}")
    yillar = float(mos.group(1))
    if not math.isfinite(yillar) or yillar <= 0:
        raise TahlilXatosi(f"o'qish muddati noto'g'ri: {katak.value!r}")
    return yillar


def _langar_katakni_top(
    varaq: Worksheet, ogohlantirishlar: list[str]
) -> tuple[int, int]:
    """'1.00' bo'lim katagini topadi; bir nechta bo'lsa 'majburiy' yozuvlisini oladi."""
    moslar = []
    for qator in varaq.iter_rows():
        for katak in qator:
            if _bolim_belgisini_ol(katak.value) == "1":
                moslar.append((katak.column - 1, katak.row))
    if not moslar:
        raise TahlilXatosi("'1.00' bo'lim belgisi topilmadi")

    for ustun, qator_raqami in moslar:
        qator_qiymatlari = next(
            varaq.iter_rows(
                min_row=qator_raqami, max_row=qator_raqami, values_only=True
            ),
            (),
        )
        if any(
            isinstance(q, str) and "majburiy" in _matnni_normallashtir(q)
            for q in qator_qiymatlari
        ):
            return ustun, qator_raqami
    ogohlantirishlar.append(
        "'1.00' bo'lim belgisi 'majburiy' yorlig'isiz topildi;"
        " birinchi mos katakka tayanildi"
    )
    return moslar[0]


def _floatga(qiymat: object) -> float | None:
    """Katak qiymatini float ga o'giradi; bo'sh yoki yaroqsiz bo'lsa None beradi."""
    if qiymat is None or isinstance(qiymat, bool):
        return None
    if isinstance(qiymat, str):
        qiymat = qiymat.replace("\xa0", "").replace(" ", "").replace(",", ".")
        if qiymat == "":
            return None
    elif not isinstance(qiymat, (int, float)):
        return None
    try:
        son = float(qiymat)
    except (ValueError, TypeError):
        return None
    return son if math.isfinite(son) else None


def _intga(qiymat: object) -> int | None:
    son = _floatga(qiymat)
    if son is None or son < 0 or not son.is_integer():
        return None
    return int(son)


def _int_yoki_belgi(xom: object) -> int | object | None:
    """Katak bo'shmi, sonmi yoki o'qib bo'lmaydigan matnmi — uchalasini ajratadi."""
    if xom is None:
        return None
    son = _intga(xom)
    return son if son is not None else _OQILMAYDI


def _katak_int(
    qator: Sequence[object], ustun: int, standart: int | None = None
) -> int | None:
    """Qatordan ustun bo'yicha butun son oladi, bo'lmasa standart qiymat qaytadi."""
    son = _intga(qator[ustun]) if len(qator) > ustun else None
    return son if son is not None else standart


def _ketma_ket_sonlarni_top(
    varaq: Worksheet,
    bosh_qator: int,
    oxir_qator: int,
    ustun_bosh: int,
    ustun_oxir: int,
    n: int,
) -> dict[int, int]:
    """[ustun_bosh, ustun_oxir) da 1..n sonlari ketma-ket turgan qatorni topadi."""
    oxirgi_mos: dict[int, int] = {}
    for qator in varaq.iter_rows(
        min_row=bosh_qator, max_row=oxir_qator, values_only=True
    ):
        nomzodlar = []
        for idx in range(ustun_bosh, min(ustun_oxir, len(qator))):
            son = _intga(qator[idx])
            if son is not None and 1 <= son <= n:
                nomzodlar.append((idx, son))
        if len(nomzodlar) != n:
            continue
        nomzodlar.sort(key=lambda x: x[1])
        qiymatlar = [q for _, q in nomzodlar]
        if len(set(qiymatlar)) != n:
            continue
        if all(nomzodlar[i + 1][1] == nomzodlar[i][1] + 1 for i in range(n - 1)):
            oxirgi_mos = dict(nomzodlar)
    return oxirgi_mos


def _guruh_sarlavha_ustuni(
    varaq: Worksheet, bosh_qator: int, yorliqlar: tuple[str, ...]
) -> int | None:
    qidiruv_bosh = max(1, bosh_qator - 10)
    for qator in varaq.iter_rows(min_row=qidiruv_bosh, max_row=bosh_qator):
        for katak in qator:
            if isinstance(katak.value, str):
                norm = _matnni_normallashtir(katak.value)
                if any(yorliq in norm for yorliq in yorliqlar):
                    return katak.column - 1
    return None


def _yorliq_semestr_xaritalari(
    varaq: Worksheet, bosh_qator: int, n: int
) -> tuple[dict[int, int], dict[int, int]]:
    """Asosiy usul: haftalik soat va kredit guruh sarlavhalari ostidan 1..N ni topadi.

    Ba'zi jadvallarda semestr ustunlari oraliqda bo'shliq yoki qo'shimcha
    "kurs" ustuni bilan keladi, shu bois qidiruv oralig'ini kengroq olamiz.
    """
    qidiruv_bosh = max(1, bosh_qator - 10)
    haftalik_ustun = _guruh_sarlavha_ustuni(
        varaq, bosh_qator, HAFTALIK_SARLAVHA_BELGILARI
    )
    kredit_ustun = _guruh_sarlavha_ustuni(varaq, bosh_qator, KREDIT_SARLAVHA_BELGILARI)
    keng_oraliq = n * 6 + 5

    haftalik_xarita: dict[int, int] = {}
    if haftalik_ustun is not None:
        chegara = (
            kredit_ustun if kredit_ustun is not None else haftalik_ustun + keng_oraliq
        )
        haftalik_xarita = _ketma_ket_sonlarni_top(
            varaq, qidiruv_bosh, bosh_qator, haftalik_ustun, chegara, n
        )

    kredit_xarita: dict[int, int] = {}
    if kredit_ustun is not None:
        kredit_xarita = _ketma_ket_sonlarni_top(
            varaq, qidiruv_bosh, bosh_qator, kredit_ustun, kredit_ustun + keng_oraliq, n
        )
    return haftalik_xarita, kredit_xarita


def _ustun_oraligini_top(
    varaq: Worksheet, bosh_qator: int, past: int, yuqori: int, siljish: int
) -> dict[int, int]:
    """Zaxira usul: sarlavhada mantiqiy ustun raqamlari (1..29) qatorini qidiradi."""
    qidiruv_bosh = max(1, bosh_qator - 10)
    oxirgi_mos = None
    for qator in varaq.iter_rows(
        min_row=qidiruv_bosh, max_row=bosh_qator, values_only=True
    ):
        nomzodlar = []
        for idx, katak_qiymat in enumerate(qator):
            son = _intga(katak_qiymat)
            if son is not None and past <= son <= yuqori:
                nomzodlar.append((idx, son))

        if len(nomzodlar) < 3:
            continue
        qiymatlar = [q for _, q in nomzodlar]
        if len(qiymatlar) != len(set(qiymatlar)):
            continue
        nomzodlar.sort(key=lambda x: x[1])
        ketma_ketmi = all(
            nomzodlar[i + 1][1] == nomzodlar[i][1] + 1
            for i in range(len(nomzodlar) - 1)
        )
        if not ketma_ketmi:
            continue

        oxirgi_mos = {idx: son - siljish for idx, son in nomzodlar}

    return oxirgi_mos or {}


def _zaxira_semestr_xaritalari(
    varaq: Worksheet, bosh_qator: int, n: int
) -> tuple[dict[int, int], dict[int, int]]:
    haftalik = _ustun_oraligini_top(varaq, bosh_qator, 12, 11 + n, 11)
    kredit = _ustun_oraligini_top(varaq, bosh_qator, 12 + n, 11 + 2 * n, 11 + n)
    return haftalik, kredit


def _semestr_xaritalarini_tekshir(
    haftalik: dict[int, int], kredit: dict[int, int], n: int
) -> None:
    if len(haftalik) != n or len(kredit) != n:
        raise TahlilXatosi(
            "semestr ustunlari to'liq emas: "
            f"haftalik={sorted(haftalik)}, kredit={sorted(kredit)}, kutilgan soni={n}"
        )
    kesishma = set(haftalik) & set(kredit)
    if kesishma:
        raise TahlilXatosi(
            f"haftalik va kredit ustunlari kesishadi: {sorted(kesishma)}"
        )
    if max(haftalik) >= min(kredit):
        raise TahlilXatosi(
            "kredit ustunlari haftalik ustunlaridan o'ngda bo'lishi kerak: "
            f"haftalik={sorted(haftalik)}, kredit={sorted(kredit)}"
        )


def semestr_ustunlarini_aniqla(
    varaq: Worksheet, bosh_qator: int, n: int
) -> tuple[dict[int, int], dict[int, int]]:
    """Haftalik va kredit ustunlari uchun {ustun_indeksi: semestr} xaritasini beradi."""
    haftalik_xarita, kredit_xarita = _yorliq_semestr_xaritalari(varaq, bosh_qator, n)
    if not haftalik_xarita or not kredit_xarita:
        z_haftalik, z_kredit = _zaxira_semestr_xaritalari(varaq, bosh_qator, n)
        haftalik_xarita = haftalik_xarita or z_haftalik
        kredit_xarita = kredit_xarita or z_kredit
    if not haftalik_xarita or not kredit_xarita:
        raise TahlilXatosi("semestr ustunlari (haftalik soat / kredit) aniqlanmadi")
    _semestr_xaritalarini_tekshir(haftalik_xarita, kredit_xarita, n)
    return haftalik_xarita, kredit_xarita


def _kod_nom_ustunlarini_top(
    varaq: Worksheet, raqam_ustun: int, bosh_qator: int
) -> tuple[int, int]:
    """Birinchi fan qatoridan kod va nom ustunlarini topadi; bo'lmasa +1/+2 oladi."""
    kod_ustun, nom_ustun = None, None
    for qator in varaq.iter_rows(
        min_row=bosh_qator + 1, max_row=bosh_qator + 10, values_only=True
    ):
        if not qator or len(qator) <= raqam_ustun or qator[raqam_ustun] is None:
            continue
        if not re.match(r"^\d+\.\d+", str(qator[raqam_ustun]).strip().rstrip(".")):
            continue
        topildi = []
        for i in range(raqam_ustun + 1, len(qator)):
            katak = qator[i]
            if katak is not None and str(katak).strip() and len(topildi) < 2:
                topildi.append(i)
        if len(topildi) >= 2:
            kod_ustun, nom_ustun = topildi[0], topildi[1]
        elif len(topildi) == 1:
            kod_ustun = nom_ustun = topildi[0]
        break

    if kod_ustun is None:
        kod_ustun = raqam_ustun + 1
    if nom_ustun is None:
        nom_ustun = raqam_ustun + 2
    return kod_ustun, nom_ustun


def jami_soat_ustunini_top(
    varaq: Worksheet, auditoriya_qator: int, bosh_qator: int
) -> int:
    """Umumiy soat ustunini 'auditoriya' sarlavhasi atrofidagi qatordan izlaydi."""
    oraliq_bosh = max(1, auditoriya_qator - 2)
    ustun = sarlavha_ustunini_top(
        varaq, "umumiy yuklama", bosh_qator, bosh_qator=oraliq_bosh
    )
    if ustun is None:
        ustun = sarlavha_ustunini_top(varaq, "soat", bosh_qator, bosh_qator=oraliq_bosh)
    if ustun is None:
        raise TahlilXatosi("'Umumiy yuklama'/'soat' ustuni topilmadi")
    return ustun


def _auditoriya_ustunini_top(varaq: Worksheet, bosh_qator: int) -> tuple[int, int]:
    """'Auditoriya' ustuni indeksini va u joylashgan sarlavha qatorini qaytaradi."""
    for qator in varaq.iter_rows(max_row=bosh_qator):
        for katak in qator:
            if isinstance(katak.value, str) and "auditoriya" in _matnni_normallashtir(
                katak.value
            ):
                return katak.column - 1, katak.row
    raise TahlilXatosi("'Auditoriya' ustuni topilmadi")


_ICHKI_USTUN_KALITLARI: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("maruza", ("maruza",)),
    ("amaliyot", ("amaliy",)),
    ("laboratoriya", ("laborator", "labarator")),
    ("seminar", ("seminar",)),
    ("kurs_ishi", ("kurs",)),
)


def _ichki_ustun_kaliti(norm: str) -> str | None:
    return next(
        (
            kalit
            for kalit, belgilar in _ICHKI_USTUN_KALITLARI
            if any(b in norm for b in belgilar)
        ),
        None,
    )


def _soat_turi_ustunlarini_top(
    varaq: Worksheet,
    auditoriya_qator: int,
    auditoriya_ustun: int,
    ogohlantirishlar: list[str],
) -> tuple[int, int, int | None, int | None, int | None]:
    """'Auditoriya' ostidagi qatordan ma'ruza, amaliy, lab, seminar, kursni topadi."""
    yorliq_qator = next(
        varaq.iter_rows(
            min_row=auditoriya_qator + 1,
            max_row=auditoriya_qator + 1,
            values_only=True,
        ),
        None,
    )
    if yorliq_qator is None:
        raise TahlilXatosi("'Ma'ruza'/'Amaliy' ustunlari topilmadi")
    ustunlar: dict[str, int | None] = {k: None for k, _ in _ICHKI_USTUN_KALITLARI}
    for i, qiymat in enumerate(yorliq_qator):
        if i <= auditoriya_ustun or not isinstance(qiymat, str):
            continue
        toza = re.sub(r"[^a-z]", "", _matnni_normallashtir(qiymat))
        kalit = _ichki_ustun_kaliti(toza)
        if kalit is not None and ustunlar[kalit] is None:
            ustunlar[kalit] = i
    if ustunlar["maruza"] is None or ustunlar["amaliyot"] is None:
        raise TahlilXatosi("'Ma'ruza'/'Amaliy' ustunlari topilmadi")
    for kalit, yorliq in (
        ("laboratoriya", "Laboratoriya"),
        ("seminar", "Seminar"),
        ("kurs_ishi", "Kurs ishi"),
    ):
        if ustunlar[kalit] is None:
            ogohlantirishlar.append(
                f"'{yorliq}' ustuni topilmadi; 0 soat deb hisoblandi"
            )
    return (
        ustunlar["maruza"],
        ustunlar["amaliyot"],
        ustunlar["laboratoriya"],
        ustunlar["seminar"],
        ustunlar["kurs_ishi"],
    )


def fan_ustunlarini_aniqla(
    varaq: Worksheet, raqam_ustun: int, bosh_qator: int, ogohlantirishlar: list[str]
) -> UstunJoyi:
    """Fanlar jadvalining barcha kerakli ustunlarini aniqlab UstunJoyi qaytaradi."""
    kod_ustun, nom_ustun = _kod_nom_ustunlarini_top(varaq, raqam_ustun, bosh_qator)
    auditoriya_ustun, auditoriya_qator = _auditoriya_ustunini_top(varaq, bosh_qator)
    soat_ustun = jami_soat_ustunini_top(varaq, auditoriya_qator, bosh_qator)
    maruza_ustun, amaliyot_ustun, lab_ustun, seminar_ustun, kurs_ishi_ustun = (
        _soat_turi_ustunlarini_top(
            varaq, auditoriya_qator, auditoriya_ustun, ogohlantirishlar
        )
    )

    return UstunJoyi(
        raqam=raqam_ustun,
        kod=kod_ustun,
        nom=nom_ustun,
        soat=soat_ustun,
        auditoriya=auditoriya_ustun,
        maruza=maruza_ustun,
        amaliyot=amaliyot_ustun,
        laboratoriya=lab_ustun,
        seminar=seminar_ustun,
        kurs_ishi=kurs_ishi_ustun,
    )


def _yarim_yaxlitla(qiymat: float) -> int:
    return math.floor(qiymat + 0.5)


def semestr_qiymatlarini_yig(
    qator: Sequence[object],
    semestr_ustun_xaritasi: dict[int, int],
    yorliq: str,
    ogohlantirishlar: list[str],
) -> dict[int, int]:
    """Nol bo'lmagan semestr kataklari uchun {semestr: qiymat} lug'atini yig'adi.

    Kasr qiymat (masalan 1.5 kredit) kelsa, jim tashlab yubormasdan
    ogohlantiradi va yuqoriga qarab yaxlitlaydi.
    """
    natija = {}
    for ustun_idx, sem_raqami in semestr_ustun_xaritasi.items():
        xom = qator[ustun_idx] if len(qator) > ustun_idx else None
        son = _floatga(xom)
        if not son:
            continue
        if son < 0:
            ogohlantirishlar.append(
                f"{yorliq}: {sem_raqami}-sem. manfiy qiymat ({xom!r})"
                " e'tiborsiz qoldirildi"
            )
            continue
        yaxlit = _yarim_yaxlitla(son)
        if yaxlit != son:
            ogohlantirishlar.append(
                f"{yorliq}: {sem_raqami}-sem. {xom!r} -> {yaxlit} ga yaxlitlandi"
            )
        natija[sem_raqami] = yaxlit
    return natija


def _nomni_tozala(qiymat: object) -> str:
    """Fan nomini tozalaydi: ichki yangi qator va '|' belgilarni olib tashlaydi."""
    if qiymat is None:
        return ""
    return re.sub(r"\s+", " ", str(qiymat).replace("|", " ")).strip()


def _tashlanadigan_qatormi(qator: Sequence[object]) -> bool:
    return any(
        isinstance(katak, str)
        and any(b in _matnni_normallashtir(katak) for b in OTKAZILADIGAN_QATORLAR)
        for katak in qator
    )


def _bolim_qatorlari(
    varaq: Worksheet, raqam_ustun: int, bolim: int, bosh_qator: int
) -> Iterator[tuple[str | None, tuple[object, ...]]]:
    """Berilgan bo'lim (1 yoki 2) qatorlarini 'Jami' yoki keyingi bo'limgacha beradi.

    Skanerlash 1-qatordan emas, aynan '1.00' langar qatoridan boshlanadi — tepada
    kalendar jadvalidagi oddiy '1' raqamlari bo'lim belgisi deb xato olinmasin.
    """
    bolim_ichida = False
    for qator in varaq.iter_rows(min_row=bosh_qator, values_only=True):
        raqam = qator[raqam_ustun] if len(qator) > raqam_ustun else None
        toza_raqam = str(raqam).strip().rstrip(".") if raqam is not None else ""
        raqam_matn = toza_raqam or None
        belgi = _bolim_belgisini_ol(raqam)

        if not bolim_ichida:
            if belgi == str(bolim):
                bolim_ichida = True
            continue

        if any(
            katak is not None and str(katak).strip().rstrip(":").casefold() == "jami"
            for katak in qator
        ):
            return
        if belgi is not None:
            return

        yield raqam_matn, qator


def soat_taqsimoti(
    qator: Sequence[object], ustunlar: tuple[int | None, ...], bosh_qiymat: int
) -> dict[str, int]:
    """Oltita soat maydonini o'qiydi; ustuni yo'q tur doim 0 bo'ladi."""
    natija: dict[str, int] = {}
    for maydon, ustun in zip(SOAT_MAYDONLARI, ustunlar):
        if ustun is None:
            natija[maydon] = 0
        else:
            son = _katak_int(qator, ustun, bosh_qiymat)
            natija[maydon] = bosh_qiymat if son is None else son
    return natija


def meros_soat_taqsimoti(
    qator: Sequence[object],
    ustunlar: tuple[int | None, ...],
    asosiy_soatlar: dict[str, int],
    yorliq: str,
    ogohlantirishlar: list[str],
) -> dict[str, int]:
    """Tanlov fanining davomiy qatorlari uchun soat taqsimotini o'qiydi.

    Birlashtirilgan (merged) katak bo'sh (None) kelsa asosiy qatordan meros oladi;
    lekin ichida son bo'lmagan xato matn bo'lsa 0 qo'yib ogohlantirish beradi.
    """
    natija: dict[str, int] = {}
    for maydon, ustun in zip(SOAT_MAYDONLARI, ustunlar):
        if ustun is None:
            natija[maydon] = 0
            continue
        xom = qator[ustun] if len(qator) > ustun else None
        qiymat = _int_yoki_belgi(xom)
        if qiymat is None:
            natija[maydon] = asosiy_soatlar[maydon]
        elif qiymat is _OQILMAYDI:
            ogohlantirishlar.append(
                f"{yorliq}: {maydon} katakchasi o'qilmadi ({xom!r}); 0 deb hisoblandi"
            )
            natija[maydon] = 0
        else:
            natija[maydon] = int(qiymat)
    return natija


def _variant_qosh(
    blok: TanlovFani, kod_matn: str, nom_matn: str, taqsimot: dict[str, int]
) -> None:
    """Bo'sh davomiy qatorlarni tashlab, tanlov blokiga bitta variant qo'shadi."""
    if kod_matn or nom_matn:
        blok.variantlar.append(TanlovVarianti(kod=kod_matn, nom=nom_matn, **taqsimot))


def _tanlov_sloti_yarat(
    qator: Sequence[object],
    raqam_matn: str,
    joylashuv: UstunJoyi,
    kredit_xaritasi: dict[int, int],
    haftalik_xaritasi: dict[int, int],
    ogohlantirishlar: list[str],
) -> tuple[TanlovFani, dict[str, int]]:
    soat_xom = qator[joylashuv.soat] if len(qator) > joylashuv.soat else None
    blok = TanlovFani(
        raqam=raqam_matn,
        soat=_intga(soat_xom),
        semestr_kreditlari=semestr_qiymatlarini_yig(
            qator, kredit_xaritasi, raqam_matn, ogohlantirishlar
        ),
        semestr_haftalik_soatlar=semestr_qiymatlarini_yig(
            qator, haftalik_xaritasi, raqam_matn, ogohlantirishlar
        ),
    )
    blok_taqsimot = soat_taqsimoti(qator, joylashuv.taqsimot, 0)
    return blok, blok_taqsimot


def tanlov_fanlarni_oqi(
    varaq: Worksheet,
    joylashuv: UstunJoyi,
    kredit_xaritasi: dict[int, int],
    haftalik_xaritasi: dict[int, int],
    bosh_qator: int,
    ogohlantirishlar: list[str],
) -> list[TanlovFani]:
    """2-bo'lim (tanlov fanlar) qatorlarini TanlovFani ro'yxatiga yig'adi."""
    bloklar: list[TanlovFani] = []
    joriy: TanlovFani | None = None
    blok_taqsimot: dict[str, int] = {}

    for raqam_matn, qator in _bolim_qatorlari(varaq, joylashuv.raqam, 2, bosh_qator):
        kod = qator[joylashuv.kod] if len(qator) > joylashuv.kod else None
        nom = qator[joylashuv.nom] if len(qator) > joylashuv.nom else None
        kod_matn = str(kod).strip() if kod is not None else ""
        nom_matn = _nomni_tozala(nom)

        if (
            raqam_matn is not None
            and fan_raqamimi(raqam_matn)
            and bolim_boshi(raqam_matn) == "2"
        ):
            joriy, blok_taqsimot = _tanlov_sloti_yarat(
                qator,
                raqam_matn,
                joylashuv,
                kredit_xaritasi,
                haftalik_xaritasi,
                ogohlantirishlar,
            )
            bloklar.append(joriy)
            _variant_qosh(joriy, kod_matn, nom_matn, blok_taqsimot)
        elif joriy is not None and raqam_matn is None:
            meros = meros_soat_taqsimoti(
                qator, joylashuv.taqsimot, blok_taqsimot, joriy.raqam, ogohlantirishlar
            )
            _variant_qosh(joriy, kod_matn, nom_matn, meros)
        elif not _tashlanadigan_qatormi(qator):
            ogohlantirishlar.append(
                f"tanilmagan qator o'tkazib yuborildi: {qator[:3]!r}"
            )

    if not bloklar:
        ogohlantirishlar.append("tanlov fanlar topilmadi")
    return bloklar


def majburiy_fanlarni_oqi(
    varaq: Worksheet,
    joylashuv: UstunJoyi,
    kredit_xaritasi: dict[int, int],
    haftalik_xaritasi: dict[int, int],
    bosh_qator: int,
    ogohlantirishlar: list[str],
) -> list[MajburiyFan]:
    """1-bo'lim (majburiy fanlar) qatorlarini MajburiyFan ro'yxatiga o'qiydi."""
    fanlar: list[MajburiyFan] = []

    for raqam_matn, qator in _bolim_qatorlari(varaq, joylashuv.raqam, 1, bosh_qator):
        if not (fan_raqamimi(raqam_matn) and bolim_boshi(raqam_matn) == "1"):
            if not _tashlanadigan_qatormi(qator):
                ogohlantirishlar.append(
                    f"tanilmagan qator o'tkazib yuborildi: {qator[:3]!r}"
                )
            continue
        kod = qator[joylashuv.kod] if len(qator) > joylashuv.kod else None
        nom = qator[joylashuv.nom] if len(qator) > joylashuv.nom else None
        soat_xom = qator[joylashuv.soat] if len(qator) > joylashuv.soat else None
        fan = MajburiyFan(
            raqam=raqam_matn,
            kod=str(kod).strip() if kod else "",
            nom=_nomni_tozala(nom),
            soat=_intga(soat_xom),
            **soat_taqsimoti(qator, joylashuv.taqsimot, 0),
            semestr_kreditlari=semestr_qiymatlarini_yig(
                qator, kredit_xaritasi, raqam_matn, ogohlantirishlar
            ),
            semestr_haftalik_soatlar=semestr_qiymatlarini_yig(
                qator, haftalik_xaritasi, raqam_matn, ogohlantirishlar
            ),
        )
        fanlar.append(fan)

    return fanlar


def _bolim_belgisi_soati(
    varaq: Worksheet, raqam_ustun: int, soat_ustun: int, bolim: int, bosh_qator: int
) -> int | None:
    for qator in varaq.iter_rows(min_row=bosh_qator, values_only=True):
        raqam = qator[raqam_ustun] if len(qator) > raqam_ustun else None
        if _bolim_belgisini_ol(raqam) == str(bolim):
            return _intga(qator[soat_ustun]) if len(qator) > soat_ustun else None
    return None


def _bolim_jamini_tekshir(
    varaq: Worksheet,
    joylashuv: UstunJoyi,
    bosh_qator: int,
    majburiy: list[MajburiyFan],
    tanlov: list[TanlovFani],
    ogohlantirishlar: list[str],
) -> None:
    """Bo'lim sarlavhasidagi soatni o'qilgan fanlar yig'indisi bilan solishtiradi."""
    majburiy_jami = sum(f.soat for f in majburiy if f.soat is not None)
    belgi1 = _bolim_belgisi_soati(varaq, joylashuv.raqam, joylashuv.soat, 1, bosh_qator)
    if belgi1 is not None and belgi1 != majburiy_jami:
        ogohlantirishlar.append(
            f"1-bo'lim jami soat mos kelmadi: varaqda {belgi1},"
            f" hisoblangan {majburiy_jami}"
        )

    tanlov_jami = sum(t.soat for t in tanlov if t.soat is not None)
    belgi2 = _bolim_belgisi_soati(varaq, joylashuv.raqam, joylashuv.soat, 2, bosh_qator)
    if belgi2 is not None and belgi2 != tanlov_jami:
        ogohlantirishlar.append(
            f"2-bo'lim jami soat mos kelmadi: varaqda {belgi2},"
            f" hisoblangan {tanlov_jami}"
        )


def _auditoriya_yigindisini_tekshir(
    yorliq: str,
    auditoriya: int,
    maruza: int,
    amaliyot: int,
    laboratoriya: int,
    seminar: int,
    ogohlantirishlar: list[str],
) -> None:
    jami = maruza + amaliyot + laboratoriya + seminar
    if auditoriya != jami:
        ogohlantirishlar.append(
            f"{yorliq}: auditoriya {auditoriya} != ma'ruza+amaliy+lab+seminar ({jami})"
        )


def _auditoriya_taqsimotini_tekshir(
    majburiy: list[MajburiyFan],
    tanlov: list[TanlovFani],
    ogohlantirishlar: list[str],
) -> None:
    for fan in majburiy:
        _auditoriya_yigindisini_tekshir(
            f"{fan.raqam} {fan.nom}",
            fan.auditoriya,
            fan.maruza,
            fan.amaliyot,
            fan.laboratoriya,
            fan.seminar,
            ogohlantirishlar,
        )
    for blok in tanlov:
        for var in blok.variantlar:
            _auditoriya_yigindisini_tekshir(
                f"{blok.raqam} {var.nom}",
                var.auditoriya,
                var.maruza,
                var.amaliyot,
                var.laboratoriya,
                var.seminar,
                ogohlantirishlar,
            )


def _kredit_soatni_tekshir(
    yorliq: str,
    soat: int | None,
    semestr_kreditlari: dict[int, int],
    ogohlantirishlar: list[str],
) -> None:
    if soat is None:
        return
    if not semestr_kreditlari:
        if soat:
            ogohlantirishlar.append(
                f"{yorliq}: soat {soat} bor, lekin semestr kreditlari yo'q"
            )
        return
    qoldiq = soat % 30
    if qoldiq != 0:
        ogohlantirishlar.append(
            f"{yorliq}: soat {soat} 30 ga qoldiqsiz bo'linmaydi (qoldiq {qoldiq})"
        )
    kutilgan = soat // 30
    amalda = sum(semestr_kreditlari.values())
    if kutilgan != amalda:
        ogohlantirishlar.append(
            f"{yorliq}: kredit {kutilgan} (soat/30) semestrlar yig'indisi {amalda}"
            " bilan mos kelmadi"
        )


def _kredit_soatlarni_tekshir(
    majburiy: list[MajburiyFan],
    tanlov: list[TanlovFani],
    ogohlantirishlar: list[str],
) -> None:
    for fan in majburiy:
        _kredit_soatni_tekshir(
            f"{fan.raqam} {fan.nom}",
            fan.soat,
            fan.semestr_kreditlari,
            ogohlantirishlar,
        )
    for blok in tanlov:
        nom = blok.variantlar[0].nom if blok.variantlar else ""
        _kredit_soatni_tekshir(
            f"{blok.raqam} {nom}", blok.soat, blok.semestr_kreditlari, ogohlantirishlar
        )


def _soat_ustuni_toliq_boshmi(
    varaq: Worksheet, joylashuv: UstunJoyi, bosh_qator: int
) -> bool:
    for qator in varaq.iter_rows(min_row=bosh_qator, values_only=True):
        raqam = qator[joylashuv.raqam] if len(qator) > joylashuv.raqam else None
        if fan_raqamimi(str(raqam).strip().rstrip(".") if raqam is not None else None):
            if len(qator) > joylashuv.soat and qator[joylashuv.soat] is not None:
                return False
    return True


def _xlsx_kitobni_och(yol: Path, *, data_only: bool) -> Workbook:
    """Excel faylini ochadi; shikastlangan fayl bo'lsa TahlilXatosi ko'taradi."""
    try:
        return openpyxl.load_workbook(yol, data_only=data_only)
    except (
        BadZipFile,
        InvalidFileException,
        ET.ParseError,
        XMLSyntaxError,
        EOFError,
        OSError,
    ) as exc:
        raise TahlilXatosi(f"Excel faylini o'qib bo'lmadi ({yol.name}): {exc}") from exc


def _hisoblanmagan_formulalarni_tekshir(
    yol: Path, joylashuv: UstunJoyi, bosh_qator: int, ogohlantirishlar: list[str]
) -> None:
    """Excel'da saqlanmagan formulalar data_only=True da None ko'rinadi —
    shuning uchun formula bormi yoki ustun haqiqatda bo'shmi, qayta ochib tekshiramiz.
    """
    xom_kitob = _xlsx_kitobni_och(yol, data_only=False)
    try:
        xom_varaq = xom_kitob.worksheets[0]
        formula_bor = any(
            len(qator) > joylashuv.soat
            and isinstance(qator[joylashuv.soat], str)
            and qator[joylashuv.soat].startswith("=")
            for qator in xom_varaq.iter_rows(min_row=bosh_qator, values_only=True)
        )
    finally:
        xom_kitob.close()
    if formula_bor:
        raise TahlilXatosi(
            "soat ustunidagi formulalar hisoblanmagan;"
            " faylni Excelda ochib qayta saqlang"
        )
    ogohlantirishlar.append("soat ustuni bo'sh: birorta kurs uchun ham soat topilmadi")


def _varaqni_tahlil_qil(
    varaq: Worksheet, yol: Path, ogohlantirishlar: list[str]
) -> TahlilNatijasi:
    yonalish = yonalishni_top(varaq, ogohlantirishlar)
    yonalish_kodi, yonalish_nomi = yonalish if yonalish is not None else ("", "")

    yil_katak = katakni_matn_bilan_top(varaq, "quv yili")
    boshlanish_yili = boshlanish_yilini_ol(str(yil_katak.value)) if yil_katak else ""
    if not boshlanish_yili:
        ogohlantirishlar.append("o'quv yili topilmadi")

    daraja, _muddat_matni, talim_shakli = metamalumni_oqi(varaq, ogohlantirishlar)
    yillar = dastur_muddatini_ol(varaq)
    n = round(yillar * 2)

    raqam_ustun, bosh_qator = _langar_katakni_top(varaq, ogohlantirishlar)
    joylashuv = fan_ustunlarini_aniqla(varaq, raqam_ustun, bosh_qator, ogohlantirishlar)
    haftalik_xarita, kredit_xarita = semestr_ustunlarini_aniqla(varaq, bosh_qator, n)

    if _soat_ustuni_toliq_boshmi(varaq, joylashuv, bosh_qator):
        _hisoblanmagan_formulalarni_tekshir(
            yol, joylashuv, bosh_qator, ogohlantirishlar
        )

    majburiy = majburiy_fanlarni_oqi(
        varaq, joylashuv, kredit_xarita, haftalik_xarita, bosh_qator, ogohlantirishlar
    )
    tanlov = tanlov_fanlarni_oqi(
        varaq, joylashuv, kredit_xarita, haftalik_xarita, bosh_qator, ogohlantirishlar
    )
    _bolim_jamini_tekshir(
        varaq, joylashuv, bosh_qator, majburiy, tanlov, ogohlantirishlar
    )
    _auditoriya_taqsimotini_tekshir(majburiy, tanlov, ogohlantirishlar)
    _kredit_soatlarni_tekshir(majburiy, tanlov, ogohlantirishlar)

    return TahlilNatijasi(
        yonalish_kodi=yonalish_kodi,
        yonalish_nomi=yonalish_nomi,
        boshlanish_yili=boshlanish_yili,
        daraja=daraja,
        davomiylik_yil=yillar,
        talim_shakli=talim_shakli,
        majburiy_fanlar=majburiy,
        tanlov_fanlar=tanlov,
        ogohlantirishlar=ogohlantirishlar,
    )


def kitobni_tahlil_qil(yol: Path) -> TahlilNatijasi:
    """Bitta o'quv reja .xlsx faylini o'qib TahlilNatijasi qaytaradi."""
    ogohlantirishlar: list[str] = []
    kitob = _xlsx_kitobni_och(yol, data_only=True)
    try:
        if not kitob.worksheets:
            raise TahlilXatosi("Excel faylida varaqlar topilmadi")
        if len(kitob.sheetnames) > 1:
            ogohlantirishlar.append(
                "varaqda bir nechta varaq bor; birinchisi "
                f"{kitob.sheetnames[0]!r} o'qildi, qolganlari e'tiborsiz qoldirildi: "
                f"{kitob.sheetnames[1:]}"
            )
        return _varaqni_tahlil_qil(kitob.worksheets[0], yol, ogohlantirishlar)
    finally:
        kitob.close()
