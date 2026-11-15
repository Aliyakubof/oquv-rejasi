"""Kursning umumiy soatlarini semestrlarga taqsimlab beruvchi sof funksiyalar.

Rejada kurs bo'yicha umumiy soatlar va har bir semestrdagi haftalik soatlar
beriladi. Bir semestr 15 hafta bo'lgani uchun haftalik soatlar tabiiy vazn
vazifasini bajaradi. Eng katta qoldiq usuli esa yaxlitlashda birorta ham
soat yo'qolib qolmasligini ta'minlaydi.
"""

HAFTA_SEMESTRDA = 15

TAQSIMOT_MAYDONLARI = (
    "maruza_soat",
    "amaliyot_soat",
    "laboratoriya_soat",
    "seminar_soat",
)


def eng_katta_qoldiq_bolish(jami: int, vaznlar: dict[int, int]) -> dict[int, int]:
    """Jami soatni vaznlarga proporsional bo'lib, yig'indisini aniq saqlaydi.

    Har bir ulushni pastga yaxlitlab, ortib qolgan soatlarni qoldig'i eng katta
    semestrlarga beradi. Qoldiq teng bo'lsa kichik semestr oldinroq oladi.
    """
    if not vaznlar:
        return {}
    jami_vazn = sum(vaznlar.values())
    if jami_vazn == 0:
        vaznlar = dict.fromkeys(vaznlar, 1)
        jami_vazn = len(vaznlar)
    natija = {s: (jami * w) // jami_vazn for s, w in vaznlar.items()}
    qoldiqlar = {s: (jami * w) % jami_vazn for s, w in vaznlar.items()}
    yetishmaydi = jami - sum(natija.values())
    for s in sorted(vaznlar, key=lambda s: (-qoldiqlar[s], s))[:yetishmaydi]:
        natija[s] += 1
    return natija


def semestr_vaznlari(
    haftalik: dict[int, int], kreditlar: dict[int, int]
) -> dict[int, int]:
    """Asosiy vazn sifatida haftalik soatni oladi; haftalik 0 bo'lsa yoki
    semestr faqat kreditda ko'ringan bo'lsa kreditiga tayanadi."""
    return {
        s: haftalik.get(s) or kreditlar.get(s, 0)
        for s in haftalik.keys() | kreditlar.keys()
    }


def soatni_semestrlarga_bol(
    maruza: int,
    amaliyot: int,
    laboratoriya: int,
    seminar: int,
    haftalik: dict[int, int],
    kreditlar: dict[int, int],
) -> tuple[dict[int, dict[str, int]], list[str]]:
    """Har bir semestr uchun {maydon: soat} taqsimotini va ogohlantirishlarni qaytaradi.

    Kurs ishi bu yerga kirmaydi: uning soati auditoriyadan emas, har bir talaba
    uchun 2 soat hisobidan chiqariladi.
    """
    vaznlar = semestr_vaznlari(haftalik, kreditlar)
    if not vaznlar:
        return {}, ["semestr taqsimoti yo'q: soatlar semestrlarga bo'linmadi"]

    satrlar: dict[int, dict[str, int]] = {s: {} for s in vaznlar}
    qiymatlar = (maruza, amaliyot, laboratoriya, seminar)
    for maydon, jami in zip(TAQSIMOT_MAYDONLARI, qiymatlar):
        for s, soat in eng_katta_qoldiq_bolish(jami, vaznlar).items():
            satrlar[s][maydon] = soat

    return satrlar, _mos_kelish_ogohlantirishlari(satrlar, haftalik, sum(qiymatlar))


def _mos_kelish_ogohlantirishlari(
    satrlar: dict[int, dict[str, int]], haftalik: dict[int, int], auditoriya: int
) -> list[str]:
    """Bo'lingan soatlarni 15 haftalik qoida (haftalik x 15) bilan solishtiradi."""
    if not haftalik:
        return []
    kutilgan = sum(haftalik.values()) * HAFTA_SEMESTRDA
    if kutilgan != auditoriya:
        return [
            f"haftalik soat x {HAFTA_SEMESTRDA} = {kutilgan}, "
            f"auditoriya bo'linmasi {auditoriya} ga teng emas"
        ]
    # Umumiy yig'indi to'g'ri chiqqan bo'lsagina semestrlar kesimida tekshiramiz —
    # aks holda yuqoridagi ogohlantirish hammasini tushuntirib bo'lgan.
    ogohlantirishlar = []
    for s, h_soat in haftalik.items():
        hisoblangan = sum(satrlar.get(s, {}).values())
        if h_soat * HAFTA_SEMESTRDA != hisoblangan:
            ogohlantirishlar.append(
                f"{s}-semestr: haftalik {h_soat} x {HAFTA_SEMESTRDA} = "
                f"{h_soat * HAFTA_SEMESTRDA}, bo'lingan soat {hisoblangan}"
            )
    return ogohlantirishlar
